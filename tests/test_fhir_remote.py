"""Connector FHIR remot i script de pujada, sense xarxa (servidor FHIR simulat amb httpx.MockTransport)."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from connectors import FhirConnector, FhirRemoteConnector
from connectors.fhir_remote_connector import ETIQUETA, SISTEMA_ETIQUETA, ErrorFhirRemot
from engine import RiskEngine

ARREL = Path(__file__).resolve().parent.parent
DADES = ARREL / "simulador" / "datos" / "demo" / "fhir"
AVUI = date(2026, 11, 13)
sys.path.insert(0, str(ARREL / "scripts"))
import upload_to_fhir  # noqa: E402


class ServidorSimulat:
    """Desa el que rep per transacció i respon les cerques per tipus i etiqueta, amb paginació."""

    def __init__(self, pagina: int = 400):
        self.recursos: dict[str, dict] = {}
        self.pagina = pagina
        self.cerques = 0

    def __call__(self, peticio: httpx.Request) -> httpx.Response:
        if peticio.method == "POST":
            for e in json.loads(peticio.content)["entry"]:
                if e["request"]["method"] == "PUT":
                    self.recursos[e["request"]["url"]] = e["resource"]
                else:
                    self.recursos.pop(e["request"]["url"], None)
            return httpx.Response(200, json={"resourceType": "Bundle", "type": "transaction-response"})
        self.cerques += 1
        tipus = peticio.url.path.rsplit("/", 1)[-1]
        q = peticio.url.params
        assert q["_tag"] == f"{SISTEMA_ETIQUETA}|{ETIQUETA}"  # mai es demana res sense la nostra etiqueta
        tots = [r for url, r in sorted(self.recursos.items()) if url.startswith(tipus + "/")
                and any(t["code"] == ETIQUETA for t in r["meta"]["tag"])]
        inici = int(q.get("_offset", 0))
        bundle = {"resourceType": "Bundle", "type": "searchset",
                  "entry": [{"resource": r} for r in tots[inici:inici + self.pagina]]}
        if inici + self.pagina < len(tots):
            seguent = peticio.url.copy_merge_params({"_offset": str(inici + self.pagina)})
            bundle["link"] = [{"relation": "next", "url": str(seguent)}]
        return httpx.Response(200, json=bundle)


def _puja(servidor: ServidorSimulat, esborra: bool = False) -> None:
    with httpx.Client(transport=httpx.MockTransport(servidor)) as client:
        for fitxer in sorted(DADES.glob("*.json")):
            cos = upload_to_fhir.transaccio(json.loads(fitxer.read_text(encoding="utf-8")), esborra)
            client.post("https://fhir.example/baseR4", json=cos).raise_for_status()


@pytest.fixture(scope="module")
def servidor() -> ServidorSimulat:
    s = ServidorSimulat()
    _puja(s)
    return s


def _remot(servidor, **kwargs) -> FhirRemoteConnector:
    client = httpx.Client(transport=httpx.MockTransport(servidor))
    return FhirRemoteConnector("https://fhir.example/baseR4", data_referencia=AVUI, client=client, **kwargs)


def test_transaccio_de_pujada_etiqueta_tots_els_recursos():
    bundle = json.loads((DADES / "P003.json").read_text(encoding="utf-8"))
    tx = upload_to_fhir.transaccio(bundle)
    assert tx["type"] == "transaction" and len(tx["entry"]) == len(bundle["entry"])
    for e in tx["entry"]:
        r = e["resource"]
        assert e["request"] == {"method": "PUT", "url": f"{r['resourceType']}/{r['id']}"}
        assert r["id"].startswith("thegoats-P003")
        assert r["meta"]["tag"][0]["code"] == "the-goats-hackathon"
        if r["resourceType"] == "Patient":
            assert r["identifier"] == [{"system": "urn:cardioalert-ap:pacient", "value": "P003"}]
        else:
            assert r["subject"]["reference"] == "Patient/thegoats-P003"
    assert bundle["entry"][0]["resource"]["id"] == "P003"  # el bundle original no es modifica
    esborrat = upload_to_fhir.transaccio(bundle, esborra=True)
    assert all(e["request"]["method"] == "DELETE" for e in esborrat["entry"])
    assert esborrat["entry"][-1]["request"]["url"] == "Patient/thegoats-P003"


def test_remot_equival_al_local(servidor):
    remot = _remot(servidor)
    local = FhirConnector(DADES)
    assert [p.id for p in remot.get_patients()] == [p.id for p in local.get_patients()]
    assert remot.get_patient_data("P003") == local.get_patient_data("P003")
    assert servidor.cerques > 4  # hi ha hagut paginació (més d'una pàgina d'observacions)
    assert [r.to_dict() for r in RiskEngine(remot).avalua_cupo()] == [r.to_dict() for r in RiskEngine(local).avalua_cupo()]
    with pytest.raises(KeyError):
        remot.get_patient_data("P999")


def test_remot_ignora_recursos_sense_la_nostra_etiqueta(servidor):
    servidor.recursos["Patient/altre"] = {"resourceType": "Patient", "id": "altre", "meta": {"tag": [{"code": "x"}]},
                                          "name": [{"text": "Ajeno"}], "gender": "male", "birthDate": "1970-01-01"}
    try:
        assert len(_remot(servidor).get_patients()) == 100
    finally:
        del servidor.recursos["Patient/altre"]


def test_remot_falla_si_no_hi_ha_pacients_si_hi_ha_error_o_si_tarda():
    with pytest.raises(ErrorFhirRemot, match="upload_to_fhir"):
        _remot(ServidorSimulat())  # servidor buit: encara no s'ha pujat res
    with pytest.raises(ErrorFhirRemot):
        _remot(lambda peticio: httpx.Response(503))
    with pytest.raises(ErrorFhirRemot, match="tarda demasiado"):
        _remot(ServidorSimulat(), temps_maxim=-1)


def test_esborrat_deixa_el_servidor_net():
    s = ServidorSimulat()
    _puja(s)
    assert len([u for u in s.recursos if u.startswith("Patient/")]) == 100
    _puja(s, esborra=True)
    assert s.recursos == {}


def test_api_amb_font_remota(servidor, tmp_path):
    rules = shutil.copy(ARREL / "config" / "rules.yaml", tmp_path / "rules.yaml")
    crides = []

    def factory():
        crides.append(1)
        return _remot(servidor)

    client = TestClient(create_app(font_per_defecte="local", rules_path=rules, remote_factory=factory))
    remot = client.get("/api/cupo", params={"source": "remote"}).json()
    local = client.get("/api/cupo").json()
    assert remot["meta"]["font_usada"] == "remote" and remot["meta"]["avis"] is None
    assert remot["meta"]["font_etiqueta"] == "Servidor FHIR remoto"
    assert remot["pacients"] == local["pacients"] and remot["kpis"] == local["kpis"]
    assert client.get("/api/pacientes/P003", params={"source": "remote"}).json()["pacient"]["dades_creuades"] is True
    assert len(crides) == 1  # es descarrega un sol cop i es queda en memòria


def test_api_no_reintenta_el_remot_a_cada_peticio(tmp_path):
    rules = shutil.copy(ARREL / "config" / "rules.yaml", tmp_path / "rules.yaml")
    crides = []

    def factory():
        crides.append(1)
        raise ErrorFhirRemot("el servidor FHIR tarda demasiado")

    client = TestClient(create_app(font_per_defecte="local", rules_path=rules, remote_factory=factory))
    for _ in range(3):
        cos = client.get("/api/cupo", params={"source": "remote"}).json()
        assert cos["meta"]["font_usada"] == "local" and "tarda demasiado" in cos["meta"]["avis"]
        assert len(cos["pacients"]) == 100
    assert len(crides) == 1
