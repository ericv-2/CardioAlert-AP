"""Servei CDS Hooks: discovery i targeta del hook patient-view (format de l'especificació HL7 CDS Hooks)."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app

URL = "/cds-services/cardioalert-patient-view"
INDICADOR = {1: "critical", 2: "warning", 3: "warning", 4: "info"}  # segons el grup de l'ordre de la llista


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def peticio(pacient_id: str, **extra) -> dict:
    return {"hook": "patient-view", "hookInstance": str(uuid.uuid4()),
            "context": {"userId": "Practitioner/demo", "patientId": pacient_id}, **extra}


def test_discovery(client):
    r = client.get("/cds-services")
    assert r.status_code == 200
    serveis = r.json()["services"]
    assert len(serveis) == 1
    s = serveis[0]
    assert s["id"] == "cardioalert-patient-view" and s["hook"] == "patient-view"
    assert s["title"] and s["description"]  # camps obligatoris de l'especificació


def test_discovery_anuncia_la_interficie_de_l_addon(monkeypatch):
    """L'estació clínica només coneix la URL de l'API: la de la interfície la llegeix del discovery."""
    app = lambda **kw: TestClient(create_app(**kw)).get("/cds-services").json()["services"][0]
    ext = app()["extension"]["cardioalert-app"]
    assert ext["launchUrl"] == "http://localhost:5173" and ext["title"] == "CardioAlert AP"
    assert app(url_interficie="http://addon.example:9000/")["extension"]["cardioalert-app"]["launchUrl"] == "http://addon.example:9000"
    monkeypatch.setenv("CARDIOALERT_UI_URL", "http://localhost:6001")
    assert app()["extension"]["cardioalert-app"]["launchUrl"] == "http://localhost:6001"
    assert "extension" not in app(url_interficie="")  # sense interfície, el servei CDS funciona igual


def test_targeta_amb_enllac_smart_a_la_interficie():
    card = lambda **kw: TestClient(create_app(**kw)).post(URL, json=peticio("P003")).json()["cards"][0]
    assert card(url_interficie="http://localhost:5173")["links"] == [
        {"label": "Abrir la ficha en CardioAlert AP", "url": "http://localhost:5173", "type": "smart"}]
    assert "links" not in card(url_interficie="")


def test_targeta_del_pacient_amb_dada_creuada(client):
    r = client.post(URL, json=peticio("P003"))
    assert r.status_code == 200, r.text
    cards = r.json()["cards"]
    assert len(cards) == 1
    c = cards[0]
    assert c["indicator"] == "warning"  # José Fernández: risc alt sense tractament adequat (grup 3)
    assert "\n" not in c["summary"] and len(c["summary"]) < 140
    assert c["summary"] == "ERC no diagnosticada (+2 alertas)"
    assert "Prioridad" not in c["summary"] + c["detail"]
    # El nivell de risc és el de la taula 5 de l'ESC 2021, amb el % i el rang, i l'avís de calibració
    assert c["detail"].startswith("**Riesgo cardiovascular: Alto** (SCORE2-Diabetes ")
    assert "referencia 50-69 años" in c["detail"] and "REGICOR (calibrada para población catalana)" in c["detail"]
    assert c["source"]["label"].startswith("CardioAlert AP")
    # detail: motiu + origen de la dada (l'analítica de DIRAYA és la que confirma l'albuminúria)
    assert "UACR" in c["detail"] and "Origen del dato: DIRAYA - Andalucía, eCAP - Catalunya" in c["detail"]
    assert "otra comunidad" in c["detail"]
    # suggestions: les accions del motor, en el mateix ordre
    fitxa = client.get("/api/pacientes/P003").json()["pacient"]
    assert [s["label"] for s in c["suggestions"]] == [a["text"] for a in fitxa["accions_recomanades"]]
    assert c["selectionBehavior"] == "any"
    assert all(uuid.UUID(s["uuid"]) for s in c["suggestions"]) and uuid.UUID(c["uuid"])
    assert [s["isRecommended"] for s in c["suggestions"]] == [True] + [False] * (len(c["suggestions"]) - 1)


def test_indicator_segons_el_grup_d_ordre_de_tot_el_cupo(client):
    """Cada pacient rep una targeta vàlida i l'indicator correspon al grup de l'ordre de la llista."""
    vistos = set()
    for p in client.get("/api/cupo").json()["pacients"]:
        cards = client.post(URL, json=peticio(p["pacient_id"])).json()["cards"]
        assert len(cards) == 1
        c = cards[0]
        assert c["indicator"] == INDICADOR[p["grup_ordre"]]
        assert f"**Riesgo cardiovascular: {p['text_risc_cv']}**" in c["detail"]
        assert 0 < len(c["summary"]) < 140 and c["detail"] and c["source"]["label"]
        assert ("suggestions" in c) == bool(p["accions_recomanades"])
        assert ("selectionBehavior" in c) == ("suggestions" in c)
        vistos.add(c["indicator"])
    assert vistos == {"critical", "warning", "info"}


def test_pacient_sense_alertes_rep_targeta_informativa(client):
    c = client.post(URL, json=peticio("P008")).json()["cards"][0]
    assert c["indicator"] == "info" and "suggestions" not in c
    assert c["summary"] == "Sin alertas ni acciones pendientes"


def test_accepta_referencia_fhir_i_selector_d_escala(client):
    c = client.post(URL, json=peticio("Patient/P003")).json()["cards"][0]
    assert "ERC no diagnosticada" in c["summary"]
    reg = client.post(URL, params={"scale": "regicor"}, json=peticio("P003")).json()["cards"][0]
    # REGICOR com a escala principal (comparació manual): la targeta ja no parla de SCORE2-Diabetes
    assert "SCORE2-Diabetes" in c["detail"] and "SCORE2-Diabetes" not in reg["detail"]
    assert client.post(URL, params={"scale": "framingham"}, json=peticio("P003")).status_code == 422


@pytest.mark.parametrize("cos, estat", [
    ({"hook": "order-select", "hookInstance": "x", "context": {"patientId": "P003"}}, 400),  # hook d'un altre servei
    ({"hook": "patient-view", "hookInstance": "x", "context": {"userId": "Practitioner/demo"}}, 400),
    ({"hook": "patient-view", "hookInstance": "x"}, 400),
    ({"hook": "patient-view", "hookInstance": "x", "context": {"patientId": "P999"}}, 404),
])
def test_peticions_invalides(client, cos, estat):
    assert client.post(URL, json=cos).status_code == estat


def test_servei_desconegut(client):
    assert client.post("/cds-services/altre-servei", json=peticio("P003")).status_code == 404


def test_el_servei_no_toca_el_motor():
    """El servei CDS només tradueix el resultat del motor: res de CDS Hooks dins d'engine/."""
    engine = Path(__file__).resolve().parent.parent / "engine"
    assert not any("cds_hooks" in f.read_text(encoding="utf-8") for f in engine.glob("*.py"))
