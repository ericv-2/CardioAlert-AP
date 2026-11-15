"""Estat de les alertes per pacient (Pendiente / Citado / Revisado / Pospuesto), llista «Hoy» i log d'auditoria.

L'API llegeix d'una estació simulada (la mateixa de test_fhir_ehr) i desa els estats en una carpeta temporal.
"""
from __future__ import annotations

import copy
import json
import shutil
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from api.estats import EstatsStore, carpeta_servidor, efectiu
from api.main import create_app
from tests.test_fhir_ehr import BASE, EstacioSimulada

ARREL = Path(__file__).resolve().parent.parent
CARMEN = {"id": "Practitioner/sim-0001", "nom": "Dra. Carmen Soler", "rol": "Medicina de familia"}


@pytest.fixture(scope="module")
def dades_estacio() -> EstacioSimulada:
    return EstacioSimulada()


@pytest.fixture()
def estacio(dades_estacio) -> EstacioSimulada:
    dades_estacio.bundles("demo")
    e = EstacioSimulada()
    e._bundles = {k: dict(v) for k, v in dades_estacio._bundles.items()}  # còpia: un test pot afegir-hi dades
    return e


@pytest.fixture()
def carpeta(tmp_path) -> Path:
    return tmp_path / "estats"


@pytest.fixture()
def client(estacio, carpeta, tmp_path) -> TestClient:
    rules = shutil.copy(ARREL / "config" / "rules.yaml", tmp_path / "rules.yaml")
    http = httpx.Client(transport=httpx.MockTransport(estacio))
    return TestClient(create_app(rules_path=rules, client_fhir=http, dir_estats=carpeta))


def _estat(client, pid, estat, fins=None, professional=CARMEN):
    return client.post(f"/api/pacientes/{pid}/estado", json={"estat": estat, "fins": fins, "professional": professional})


def test_hoy_son_els_primers_pendents_de_la_llista(client):
    cos = client.get("/api/cupo").json()
    assert cos["estats"] == {} and cos["recompte_estats"]["pendent"] == 100
    assert len(cos["llista_avui"]) == cos["meta"]["pacients_avui"] == 10
    ordre = [p["pacient_id"] for p in cos["pacients"]]
    assert cos["llista_avui"] == [pid for pid in ordre if pid in cos["llista_avui"]]  # en l'ordre de la llista


def test_citat_revisat_i_posposat_surten_de_hoy_pero_no_s_esborren(client, carpeta):
    abans = client.get("/api/cupo").json()["llista_avui"]
    a, b, c = abans[:3]
    assert _estat(client, a, "citat").status_code == 200
    assert _estat(client, b, "revisat").status_code == 200
    r = _estat(client, c, "posposat", "2026-12-15")
    assert r.status_code == 200 and r.json()["estat"] == {"estat": "posposat", "fins": "2026-12-15", "quan": r.json()["estat"]["quan"],
                                                          "qui": "Dra. Carmen Soler", "vencut": False}
    despres = client.get("/api/estados").json()
    assert not {a, b, c} & set(despres["llista_avui"]) and len(despres["llista_avui"]) == 10
    assert despres["llista_avui"][:7] == abans[3:]  # la resta puja
    assert {pid: e["estat"] for pid, e in despres["estats"].items()} == {a: "citat", b: "revisat", c: "posposat"}
    assert despres["recompte_estats"] == {"pendent": 97, "citat": 1, "revisat": 1, "posposat": 1}
    # El cupo segueix tenint els 100 pacients (no s'esborra ningú) i la fitxa en diu l'estat
    assert len(client.get("/api/cupo").json()["pacients"]) == 100
    assert client.get(f"/api/pacientes/{a}").json()["estat"]["estat"] == "citat"
    # Fitxers locals, separats per servidor FHIR
    dir_servidor = carpeta / carpeta_servidor(BASE)
    desat = json.loads((dir_servidor / "estats.json").read_text(encoding="utf-8"))
    assert desat["servidor"] == BASE and set(desat["pacients"]) == {a, b, c}
    assert desat["pacients"][a]["qui"] == CARMEN
    # Tornar a «Pendiente» el retorna a «Hoy»
    assert _estat(client, a, "pendent").status_code == 200
    assert a in client.get("/api/estados").json()["llista_avui"]


def test_log_d_auditoria(client, carpeta):
    pid = client.get("/api/cupo").json()["llista_avui"][0]
    _estat(client, pid, "citat")
    _estat(client, pid, "posposat", "2027-01-10")
    log = client.get(f"/api/pacientes/{pid}/auditoria").json()["auditoria"]
    assert [(e["estat"], e["anterior"], e["origen"]) for e in log] == [("posposat", "citat", "manual"),
                                                                        ("citat", "pendent", "manual")]
    assert all(e["qui"] == CARMEN and e["pacient"] == pid and e["quan"] for e in log)
    assert log[0]["fins"] == "2027-01-10"
    linies = (carpeta / carpeta_servidor(BASE) / "auditoria.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(linies) == 2  # el fitxer només creix
    assert client.get("/api/auditoria").json()["auditoria"][0]["estat"] == "posposat"
    assert client.get(f"/api/pacientes/{pid}").json()["auditoria"][0]["estat"] == "posposat"


@pytest.mark.parametrize("cos, missatge", [
    ({"estat": "citat"}, "profesional"),
    ({"estat": "citat", "professional": {"nom": "  "}}, "profesional"),
    ({"estat": "esborrat", "professional": CARMEN}, "no válido"),
    ({"estat": "posposat", "professional": CARMEN}, "fecha válida"),
    ({"estat": "posposat", "fins": "2026-11-13", "professional": CARMEN}, "posterior"),
    ({"estat": "citat", "fins": "2026-12-01", "professional": CARMEN}, "Solo"),
])
def test_canvis_no_valids(client, carpeta, cos, missatge):
    r = client.post("/api/pacientes/P003/estado", json=cos)
    assert r.status_code == 422 and missatge in r.json()["detail"]
    assert not carpeta.exists()  # no s'ha desat res
    assert client.post("/api/pacientes/P999/estado", json={"estat": "citat", "professional": CARMEN}).status_code == 404


def test_una_alerta_nova_torna_el_pacient_a_pendent(client, estacio):
    cupo = client.get("/api/cupo").json()
    # Un pacient de >= 40 anys sense possible IC ni diagnòstic d'IC: li arribarà un NT-proBNP alt
    pid = next(p["pacient_id"] for p in cupo["pacients"] if p["edat"] >= 40 and p["alertes_actives"]
               and "possible_ic" not in {a["regla"] for a in p["alertes_actives"]}
               and not any(e["resource"].get("code", {}).get("coding", [{}])[0].get("code") == "K77"
                           for e in estacio.bundles("demo")[p["pacient_id"]]["entry"]))
    assert _estat(client, pid, "revisat").status_code == 200
    # Sense dades noves, tornar a llegir no canvia res
    assert client.get(f"/api/pacientes/{pid}").json()["estat"]["estat"] == "revisat"
    bundle = copy.deepcopy(estacio.bundles("demo")[pid])
    bundle["entry"].append({"resource": {
        "resourceType": "Observation", "id": f"{pid}-obs-nova", "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "33762-6", "display": "NT-proBNP"}], "text": "NT-proBNP"},
        "subject": {"reference": f"Patient/{pid}"}, "effectiveDateTime": "2026-11-12",
        "valueQuantity": {"value": 2400.0, "unit": "pg/mL", "system": "http://unitsofmeasure.org", "code": "pg/mL"},
        "performer": [{"display": "Lab. Hospital"}]}})
    estacio._bundles["demo"][pid] = bundle
    fitxa = client.get(f"/api/pacientes/{pid}").json()
    assert "possible_ic" in {a["regla"] for a in fitxa["pacient"]["alertes_actives"]}
    assert fitxa["estat"]["estat"] == "pendent"
    darrera = fitxa["auditoria"][0]
    assert (darrera["estat"], darrera["anterior"], darrera["origen"]) == ("pendent", "revisat", "recalculo")
    assert "possible_ic" in darrera["motiu"] and darrera["qui"]["nom"].startswith("CardioAlert AP")


def test_recalcular_un_pacient_quan_arriba_una_analitica_nova(client, estacio):
    cupo = client.get("/api/cupo").json()
    calculat = cupo["meta"]["calculat_a"]
    assert calculat and cupo["meta"]["en_memoria"] is False
    # Sense dades noves: el mateix resultat, sense tornar a exportar el cupo
    pid = "P050"
    exportacions = estacio.exportacions()
    r = client.post(f"/api/pacientes/{pid}/recalcular").json()
    assert r["alertes_noves"] == r["alertes_resoltes"] == [] and r["abans"] == {k: r["ara"][k] for k in r["abans"]}
    assert estacio.exportacions() == exportacions and r["recalculat_a"]
    # Arriba un NT-proBNP alt: possible IC (alerta urgent), el pacient puja al grup 1 i torna a «Pendiente»
    assert "possible_ic" not in {a["regla"] for a in next(p for p in cupo["pacients"] if p["pacient_id"] == pid)["alertes_actives"]}
    assert _estat(client, pid, "revisat").status_code == 200
    bundle = copy.deepcopy(estacio.bundles("demo")[pid])
    bundle["entry"].append({"resource": {
        "resourceType": "Observation", "id": f"{pid}-obs-nova", "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "33762-6", "display": "NT-proBNP"}], "text": "NT-proBNP"},
        "subject": {"reference": f"Patient/{pid}"}, "effectiveDateTime": "2026-11-12",
        "valueQuantity": {"value": 2400.0, "unit": "pg/mL", "system": "http://unitsofmeasure.org", "code": "pg/mL"},
        "performer": [{"display": "Lab. Hospital"}]}})
    estacio._bundles["demo"][pid] = bundle
    r = client.post(f"/api/pacientes/{pid}/recalcular").json()
    assert r["alertes_noves"] == ["possible_ic"] and r["ara"]["grup_ordre"] == 1 and r["estat"]["estat"] == "pendent"
    assert estacio.exportacions() == exportacions  # un sol pacient: no s'ha tornat a exportar el cupo
    # El cupo en memòria ja porta el resultat nou, reordenat, i l'hora del càlcul del cupo no canvia
    despres = client.get("/api/cupo").json()
    assert despres["meta"]["en_memoria"] is True and despres["meta"]["calculat_a"] == calculat
    ids = [p["pacient_id"] for p in despres["pacients"]]
    assert ids.index(pid) + 1 == r["ara"]["posicio"] and despres["pacients"][ids.index(pid)]["grup_ordre"] == 1
    ordre = [(p["grup_ordre"], -p["puntuacio_prioritat"], p["pacient_id"]) for p in despres["pacients"]]
    assert ordre == sorted(ordre) and len(ids) == 100
    assert despres["kpis"]["grups"]["1"] == cupo["kpis"]["grups"]["1"] + 1
    assert pid in despres["llista_avui"] or len(despres["llista_avui"]) == 10
    assert client.post("/api/pacientes/P999/recalcular").status_code == 404


def test_posposicio_vencuda_compta_com_a_pendent(tmp_path):
    store = EstatsStore(tmp_path)
    store.canvia("http://x/fhir", "P001", "posposat", CARMEN, {"fge_descens"}, date(2026, 11, 13), "2026-11-20")
    reg = store.registre("http://x/fhir", "P001")
    assert efectiu(reg, date(2026, 11, 19))["estat"] == "posposat"
    vencut = efectiu(reg, date(2026, 11, 20))
    assert vencut["estat"] == "pendent" and vencut["vencut"] and vencut["estat_desat"] == "posposat"
    # Cada servidor FHIR té els seus estats
    assert store.registre("http://altra/fhir", "P001") is None
    assert {p.name for p in tmp_path.iterdir()} == {carpeta_servidor("http://x/fhir")}
