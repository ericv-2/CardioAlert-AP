"""L'add-on llegeix les dades de l'estació clínica: connector `fhir_ehr`, CDS Hooks (`fhirServer` i prefetch),
`iss` del llançament SMART i exportació Bulk Data del cupo.

Dues estacions de prova:
  - `EstacioSimulada`: les mateixes rutes que simulador/servidor-fhir.js, amb httpx.MockTransport (sense xarxa).
  - el servidor FHIR real del simulador (`node simulador/servidor-fhir.js`), si hi ha Node instal·lat.
En tots dos casos el motor ha de donar exactament el mateix que llegint els fitxers.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from connectors import CsvConnector, FhirConnector, FhirEhrConnector
from connectors.fhir_ehr_connector import PREFETCH, TIPUS, ErrorFhirEhr, dades_de_prefetch
from engine import RiskEngine

ARREL = Path(__file__).resolve().parent.parent
DADES = ARREL / "simulador" / "datos"
BASE = "http://localhost:5174/fhir"  # l'estació per defecte de l'add-on
URL_CDS = "/cds-services/cardioalert-patient-view"
CUPOS = {"demo": ("Cupo demo", "Consultorio de demostración"), "realista": ("Cupo realista", "Centro de salud urbano")}


class EstacioSimulada:
    """Servidor FHIR de l'estació (només lectura) amb el cupo actiu que es vulgui i un comptador de peticions."""

    def __init__(self):
        self._bundles: dict[str, dict[str, dict]] = {}
        self.actiu = "demo"
        self.caiguda = False
        self.esperes_estat = 0  # quants cops l'estat de l'exportació respon 202 abans de donar el manifest
        self.peticions: list[str] = []

    def bundles(self, cupo: str) -> dict[str, dict]:
        if cupo not in self._bundles:
            self._bundles[cupo] = {f.stem: json.loads(f.read_text(encoding="utf-8"))
                                   for f in sorted((DADES / cupo / "fhir").glob("*.json"))}
        return self._bundles[cupo]

    def quantes(self, tros: str) -> int:
        return sum(tros in p for p in self.peticions)

    def exportacions(self) -> int:
        """Quants cops s'ha arrencat l'exportació Bulk Data del cupo."""
        return sum(p.endswith("/$export") for p in self.peticions)

    def __call__(self, peticio: httpx.Request) -> httpx.Response:
        if self.caiguda:
            raise httpx.ConnectError("estació aturada", request=peticio)
        base = f"{peticio.url.scheme}://{peticio.url.netloc.decode()}/fhir"
        ruta = peticio.url.path.removeprefix("/fhir")
        self.peticions.append(ruta)
        nom, centre = CUPOS[self.actiu]
        grup = {"resourceType": "Group", "id": f"cupo-{self.actiu}", "type": "person", "actual": True, "name": nom,
                "quantity": len(self.bundles(self.actiu)), "managingEntity": {"display": centre},
                "meta": {"versionId": f"v1-{self.actiu}", "lastUpdated": "2026-11-13T00:00:00+01:00"}}
        if ruta == "/metadata":
            return httpx.Response(200, json={"resourceType": "CapabilityStatement", "software": {"name": "Estación clínica simulada"}})
        if ruta == "/Group":
            return httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset", "entry": [{"resource": grup}]})
        if ruta == f"/Group/{grup['id']}/$export":
            assert peticio.headers["Prefer"] == "respond-async" and set(peticio.url.params["_type"].split(",")) == set(TIPUS)
            self.pendents = self.esperes_estat
            return httpx.Response(202, headers={"Content-Location": f"{base}/$export-status/{self.actiu}"})
        if ruta.startswith("/$export-status/"):
            if self.pendents > 0:
                self.pendents -= 1
                return httpx.Response(202, headers={"Retry-After": "0", "X-Progress": "en curso"})
            cupo = ruta.rsplit("/", 1)[-1]
            return httpx.Response(200, json={
                "transactionTime": "2026-11-13T00:00:00+01:00", "request": f"{base}/Group/cupo-{cupo}/$export",
                "requiresAccessToken": False, "error": [],
                "output": [{"type": t, "url": f"{base}/$export-file/{cupo}/{t}.ndjson"} for t in TIPUS]})
        if ruta.startswith("/$export-file/"):
            _, _, cupo, fitxer = ruta.split("/")
            tipus = fitxer.removesuffix(".ndjson")
            linies = [json.dumps(e["resource"], ensure_ascii=False) for b in self.bundles(cupo).values()
                      for e in b["entry"] if e["resource"]["resourceType"] == tipus]
            return httpx.Response(200, content=("\n".join(linies) + "\n").encode("utf-8"),
                                  headers={"Content-Type": "application/fhir+ndjson"})
        if ruta.startswith("/Patient/") and ruta.endswith("/$everything"):
            bundle = self.bundles(self.actiu).get(ruta.split("/")[2])
            if bundle is None:
                return httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": [{"diagnostics": "no encontrado"}]})
            return httpx.Response(200, json=bundle)
        return httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": [{"diagnostics": f"Ruta no soportada: {ruta}"}]})


@pytest.fixture(scope="module")
def dades_estacio() -> EstacioSimulada:
    """Els bundles llegits un sol cop per a tot el mòdul (el cupo realista en té 1.500)."""
    return EstacioSimulada()


@pytest.fixture()
def estacio(dades_estacio) -> EstacioSimulada:
    e = EstacioSimulada()
    e._bundles = dades_estacio._bundles
    return e


@pytest.fixture()
def http(estacio) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(estacio))


@pytest.fixture()
def client(http, tmp_path) -> TestClient:
    """L'API tal com corre a la demo: sense `source`, llegeix de l'estació."""
    rules = shutil.copy(ARREL / "config" / "rules.yaml", tmp_path / "rules.yaml")
    return TestClient(create_app(rules_path=rules, client_fhir=http))


def _iguals(a, b) -> bool:
    return (a.pacient, a.analitiques, a.diagnostics, a.medicacions) == (b.pacient, b.analitiques, b.diagnostics, b.medicacions)


def _resultats(connector, escala=None) -> list[dict]:
    return [r.to_dict() for r in RiskEngine(connector, escala=escala).avalua_cupo()]


def _peticio(pacient_id: str, **extra) -> dict:
    return {"hook": "patient-view", "hookInstance": "x", "context": {"userId": "Practitioner/sim", "patientId": pacient_id}, **extra}


def _sense_uuid(card: dict) -> dict:
    return {**{k: v for k, v in card.items() if k != "uuid"},
            "suggestions": [{k: v for k, v in s.items() if k != "uuid"} for s in card.get("suggestions", [])]}


# --- Connector fhir_ehr -----------------------------------------------------------------------

def test_cupo_i_sistema_de_l_estacio(estacio, http):
    con = FhirEhrConnector(BASE, client=http)
    cupo = con.cupo()
    assert (cupo.id, cupo.nom, cupo.pacients, cupo.centre) == ("cupo-demo", "Cupo demo", 100, "Consultorio de demostración")
    assert con.sistema() == "Estación clínica simulada"
    estacio.actiu = "realista"
    altre = con.cupo()
    assert (altre.id, altre.pacients) == ("cupo-realista", 1500) and altre.empremta != cupo.empremta


def test_exportacio_bulk_dona_el_mateix_que_els_fitxers(estacio, http):
    estacio.esperes_estat = 2  # l'exportació no és immediata: cal consultar-ne l'estat fins que acaba
    con = FhirEhrConnector(BASE, client=http)
    local = FhirConnector(DADES / "demo" / "fhir")
    assert con.get_patients() == local.get_patients() and len(con.get_patients()) == 100
    assert all(_iguals(con.get_patient_data(p.id), local.get_patient_data(p.id)) for p in local.get_patients())
    assert con.cupo_carregat.id == "cupo-demo" and con.segons_lectura is not None
    # Una sola exportació: arrencada, estat (dos "en curs" i el manifest) i un NDJSON per tipus de recurs
    assert estacio.quantes("/$export-status/") == 3 and estacio.quantes("/$export-file/") == len(TIPUS)
    assert estacio.quantes("$everything") == 0


def test_un_pacient_es_llegeix_amb_everything(estacio, http):
    con = FhirEhrConnector(BASE, client=http)
    d = con.get_patient_data("P003")  # sense cupo exportat: una sola petició
    assert _iguals(d, FhirConnector(DADES / "demo" / "fhir").get_patient_data("P003"))
    assert {a.origen for a in d.analitiques} >= {"eCAP - Catalunya", "DIRAYA - Andalucía"}
    assert estacio.peticions == ["/Patient/P003/$everything"]
    with pytest.raises(KeyError):
        con.llegeix_pacient("P999")


@pytest.mark.parametrize("escala", ["totes_dues", "score2", "regicor"])
def test_el_motor_dona_el_mateix_llegint_de_l_estacio_demo(http, escala):
    assert _resultats(FhirEhrConnector(BASE, client=http), escala) == _resultats(FhirConnector(DADES / "demo" / "fhir"), escala)


def test_el_motor_dona_el_mateix_llegint_de_l_estacio_realista(estacio, http):
    estacio.actiu = "realista"
    con = FhirEhrConnector(BASE, client=http)
    assert _resultats(con) == _resultats(CsvConnector(DADES / "realista" / "csv"))
    # Un pacient llegit sol ($everything) s'avalua igual que dins del cupo exportat
    motor, viu = RiskEngine(con), FhirEhrConnector(BASE, client=http)
    for p in con.get_patients()[::150]:
        assert motor.avalua_dades(viu.llegeix_pacient(p.id)).to_dict() == motor.avalua(p.id).to_dict()


def test_errors_de_l_estacio(estacio, http):
    con = FhirEhrConnector(BASE, client=http)
    with pytest.raises(ErrorFhirEhr, match="otro servidor"):  # mai se segueix una adreça d'un altre servidor
        con._get("http://un-altre-servidor.example/fhir/Patient")
    estacio.caiguda = True
    with pytest.raises(ErrorFhirEhr, match="no responde"):
        con.cupo()
    with pytest.raises(ErrorFhirEhr, match="no responde"):
        con.get_patients()


def test_dades_del_prefetch(dades_estacio):
    bundle = dades_estacio.bundles("demo")["P003"]
    recursos = [e["resource"] for e in bundle["entry"]]
    de = lambda tipus: {"resourceType": "Bundle", "type": "searchset",  # noqa: E731
                        "entry": [{"resource": r} for r in recursos if r["resourceType"] == tipus]}
    prefetch = {"patient": recursos[0], "observations": de("Observation"), "conditions": de("Condition"),
                "medications": de("MedicationStatement")}
    assert set(prefetch) == set(PREFETCH)
    local = FhirConnector(DADES / "demo" / "fhir").get_patient_data("P003")
    assert _iguals(dades_de_prefetch(prefetch, "P003", local.pacient.data_naixement.replace(year=2026, month=11, day=13)), local)
    assert dades_de_prefetch({**prefetch, "conditions": None}, "P003") is None  # incomplet: cal el servidor FHIR
    assert dades_de_prefetch(prefetch, "P001") is None  # no és el pacient del context
    assert dades_de_prefetch(None, "P003") is None


# --- API: el cupo es llegeix de l'estació (iss + Bulk Data) -------------------------------------

def test_api_llegeix_el_cupo_de_l_estacio(client, estacio):
    cos = client.get("/api/cupo").json()
    meta = cos["meta"]
    assert (meta["font_usada"], meta["fhir_server"], meta["cohort"]) == ("ehr", BASE, "cupo-demo")
    assert meta["dades_de"] == "Estación clínica simulada – Cupo demo (100)" and meta["avis"] is None
    assert meta["en_memoria"] is False and meta["segons_lectura"] is not None
    # Exactament el mateix que llegint els fitxers directament (font local, només per comparar)
    local = client.get("/api/cupo", params={"source": "local"}).json()
    assert cos["pacients"] == local["pacients"] and cos["kpis"] == local["kpis"]
    assert local["meta"]["dades_de"] == "Local (eCAP / DIRAYA Demo) – Demo (100)"
    # El `iss` del llançament SMART és el mateix servidor: no es torna a exportar
    amb_iss = client.get("/api/cupo", params={"iss": BASE + "/"}).json()
    assert amb_iss["meta"]["en_memoria"] is True and estacio.exportacions() == 1


def test_api_guarda_el_cupo_per_servidor_i_recalcula_en_canviar_de_cupo(client, estacio):
    assert client.get("/api/cupo").json()["meta"]["en_memoria"] is False
    for _ in range(3):
        assert client.get("/api/cupo").json()["meta"]["en_memoria"] is True
    assert estacio.exportacions() == 1 and estacio.quantes("/Group") >= 4  # només es mira el Group
    # L'estació canvia de cupo: l'add-on ho veu al Group i torna a exportar
    estacio.actiu = "realista"
    cos = client.get("/api/cupo").json()
    assert cos["meta"]["dades_de"] == "Estación clínica simulada – Cupo realista (1.500)"
    assert cos["meta"]["en_memoria"] is False and len(cos["pacients"]) == cos["kpis"]["total"] == 1500
    assert cos["pacients"][0]["pacient_id"].startswith("R") and estacio.exportacions() == 2
    assert client.get("/api/cupo").json()["meta"]["en_memoria"] is True
    # Botó de recàlcul: es torna a llegir encara que l'estació no hagi canviat
    cos = client.get("/api/cupo", params={"refresh": "true"}).json()
    assert cos["meta"]["en_memoria"] is False and estacio.exportacions() == 3
    # Un altre servidor FHIR té la seva pròpia memòria
    altre = client.get("/api/cupo", params={"iss": "http://localhost:6001/fhir"}).json()
    assert altre["meta"]["fhir_server"] == "http://localhost:6001/fhir" and altre["meta"]["en_memoria"] is False
    assert client.get("/api/cupo").json()["meta"]["en_memoria"] is True and estacio.exportacions() == 4


def test_api_un_canvi_de_regles_no_torna_a_llegir_l_estacio(client, estacio):
    abans = client.get("/api/cupo").json()
    assert client.post("/api/rules", json={"canvis": {"motor.prioritat.pacients_avui": 7}}).status_code == 200
    despres = client.get("/api/cupo").json()
    assert despres["meta"]["pacients_avui"] == 7 and despres["meta"]["en_memoria"] is False
    assert despres["pacients"] == abans["pacients"] and estacio.exportacions() == 1


def test_api_la_fitxa_llegeix_el_pacient_de_l_estacio(client, estacio):
    cos = client.get("/api/pacientes/P003", params={"iss": BASE}).json()
    assert cos["pacient"]["nom"] == "José Fernández" and cos["comunitat_habitual"] == "Catalunya"
    assert cos["meta"]["dades_de"] == "Estación clínica simulada – Cupo demo (100)"
    assert any(m["origen"] == "DIRAYA - Andalucía" for m in cos["series"]["uacr"])
    assert estacio.quantes("$everything") == 1 and estacio.exportacions() == 0  # no cal exportar el cupo
    local = client.get("/api/pacientes/P003", params={"source": "local"}).json()
    assert {k: cos[k] for k in cos if k != "meta"} == {k: local[k] for k in local if k != "meta"}
    assert client.get("/api/pacientes/P999").status_code == 404
    excel = client.get("/api/export/excel")
    assert excel.status_code == 200 and excel.content[:2] == b"PK"


def test_api_estacio_aturada_o_no_autoritzada(client, estacio):
    r = client.get("/api/cupo", params={"iss": "http://fhir.example.org/baseR4"})
    assert r.status_code == 403 and "no autorizado" in r.json()["detail"]
    assert estacio.peticions == []  # no s'arriba a demanar res a un servidor que no és de la llista
    estacio.caiguda = True
    r = client.get("/api/cupo")
    assert r.status_code == 502 and "estación clínica" in r.json()["detail"] and BASE in r.json()["detail"]
    assert client.get("/api/pacientes/P003").status_code == 502
    estacio.caiguda = False
    assert client.get("/api/cupo").status_code == 200  # quan torna, es llegeix sense reiniciar res


# --- CDS Hooks: fhirServer i prefetch -----------------------------------------------------------

def test_cds_llegeix_el_pacient_del_fhirserver(client, estacio):
    r = client.post(URL_CDS, json=_peticio("P003", fhirServer=BASE))
    assert r.status_code == 200, r.text
    card = r.json()["cards"][0]
    assert card["summary"] == "ERC no diagnosticada (+2 alertas)" and card["indicator"] == "warning"
    assert "Origen del dato: DIRAYA - Andalucía, eCAP - Catalunya" in card["detail"]
    assert estacio.peticions == ["/Patient/P003/$everything"]  # una sola lectura, sense exportar el cupo
    local = client.post(URL_CDS, params={"source": "local"}, json=_peticio("P003")).json()["cards"][0]
    assert _sense_uuid(card) == _sense_uuid(local)
    # Sense fhirServer, l'estació per defecte de l'add-on; un pacient que no hi és, 404
    assert _sense_uuid(client.post(URL_CDS, json=_peticio("P003")).json()["cards"][0]) == _sense_uuid(local)
    assert client.post(URL_CDS, json=_peticio("P999", fhirServer=BASE)).status_code == 404
    assert client.post(URL_CDS, json=_peticio("P003", fhirServer="http://fhir.example.org/r4")).status_code == 403


def test_cds_fa_servir_el_prefetch_si_hi_es_tot(client, estacio, dades_estacio):
    recursos = [e["resource"] for e in dades_estacio.bundles("demo")["P001"]["entry"]]
    de = lambda tipus: {"resourceType": "Bundle", "entry": [{"resource": r} for r in recursos if r["resourceType"] == tipus]}  # noqa: E731
    prefetch = {"patient": recursos[0], "observations": de("Observation"), "conditions": de("Condition"),
                "medications": de("MedicationStatement")}
    card = client.post(URL_CDS, json=_peticio("P001", fhirServer=BASE, prefetch=prefetch)).json()["cards"][0]
    assert estacio.peticions == []  # amb el prefetch complet no cal llegir res de l'estació
    local = client.post(URL_CDS, params={"source": "local"}, json=_peticio("P001")).json()["cards"][0]
    assert _sense_uuid(card) == _sense_uuid(local)
    # Prefetch incomplet: es llegeix del servidor FHIR
    parcial = client.post(URL_CDS, json=_peticio("P001", fhirServer=BASE, prefetch={"patient": recursos[0]})).json()["cards"][0]
    assert _sense_uuid(parcial) == _sense_uuid(local) and estacio.peticions == ["/Patient/P001/$everything"]


def test_cds_sense_dades_respon_412(client, estacio):
    estacio.caiguda = True
    r = client.post(URL_CDS, json=_peticio("P003", fhirServer=BASE))
    assert r.status_code == 412 and "estación clínica" in r.json()["detail"]


def test_discovery_anuncia_el_prefetch(client):
    servei = client.get("/cds-services").json()["services"][0]
    assert servei["prefetch"] == PREFETCH and "fhirServer" in servei["usageRequirements"]
    assert all("{{context.patientId}}" in plantilla for plantilla in servei["prefetch"].values())


# --- El servidor FHIR real del simulador (Node) -------------------------------------------------

@pytest.fixture(scope="module")
def servidor_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js no está instalado: no se puede arrancar el servidor FHIR del simulador")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proces = subprocess.Popen([node, str(ARREL / "simulador" / "servidor-fhir.js"), "--port", str(port), "--host", "127.0.0.1"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/fhir/metadata", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            pytest.fail(f"El servidor FHIR del simulador no arranca: {proces.stderr.read().decode(errors='replace')}")
        yield base
    finally:
        proces.terminate()
        proces.wait(timeout=10)


def test_servidor_fhir_del_simulador_i_cupo_actiu(servidor_node):
    fhir = f"{servidor_node}/fhir"
    cupos = httpx.get(f"{servidor_node}/estacion/cupos").json()
    assert cupos["activo"] == "demo" and {c["id"]: c["pacientes"] for c in cupos["cupos"]} == {"demo": 100, "realista": 1500}
    # Cerca de pacients i història d'un pacient
    cerca = httpx.get(f"{fhir}/Patient", params={"name": "fernandez", "_count": "5"}).json()
    assert cerca["type"] == "searchset" and "P003" in [e["resource"]["id"] for e in cerca["entry"]]
    assert httpx.get(f"{fhir}/Patient").json()["total"] == 100
    assert httpx.get(f"{fhir}/Patient/P003").json()["birthDate"] == "1968-06-15"
    assert httpx.get(f"{fhir}/Patient/P999/$everything").status_code == 404
    # Cupo demo: el motor dona el mateix que llegint els fitxers
    con = FhirEhrConnector(fhir)
    assert con.sistema() == "Estación clínica simulada" and con.cupo().id == "cupo-demo"
    assert _resultats(con) == _resultats(FhirConnector(DADES / "demo" / "fhir"))
    assert _iguals(FhirEhrConnector(fhir).llegeix_pacient("P003"), con.get_patient_data("P003"))
    # Bulk Data: arrencada asíncrona (202 + Content-Location), manifest i NDJSON
    inici = httpx.get(f"{fhir}/Group/cupo-demo/$export", headers={"Prefer": "respond-async"})
    assert inici.status_code == 202
    manifest = httpx.get(inici.headers["Content-Location"]).json()
    assert [o["type"] for o in manifest["output"]] == list(TIPUS) and manifest["output"][0]["count"] == 100
    ndjson = httpx.get(manifest["output"][0]["url"])
    assert ndjson.headers["content-type"].startswith("application/fhir+ndjson")
    assert [json.loads(linia)["id"] for linia in ndjson.text.splitlines()][:3] == ["P001", "P002", "P003"]
    # L'estació canvia de cupo: el mateix servidor FHIR serveix ara el cupo realista
    assert httpx.post(f"{servidor_node}/estacion/cupo", json={"id": "realista"}, timeout=60).json()["activo"] == "realista"
    try:
        assert con.cupo().empremta != con.cupo_carregat.empremta
        assert httpx.get(f"{fhir}/Group/cupo-demo/$export").status_code == 404  # ja no és el cupo actiu
        assert httpx.get(f"{fhir}/Patient/P003").status_code == 404
        realista = FhirEhrConnector(fhir)
        assert realista.cupo().pacients == 1500
        assert _resultats(realista) == _resultats(CsvConnector(DADES / "realista" / "csv"))
        assert httpx.post(f"{servidor_node}/estacion/cupo", json={"id": "inventat"}).status_code == 400
    finally:
        httpx.post(f"{servidor_node}/estacion/cupo", json={"id": "demo"})
