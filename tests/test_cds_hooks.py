"""Servei CDS Hooks: discovery i targeta del hook patient-view (format de l'especificació HL7 CDS Hooks)."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app

URL = "/cds-services/cardioalert-patient-view"
INDICADOR = {"ALT": "critical", "MITJA": "warning", "BAIX": "info"}


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


def test_targeta_del_pacient_amb_dada_creuada(client):
    r = client.post(URL, json=peticio("P003"))
    assert r.status_code == 200, r.text
    cards = r.json()["cards"]
    assert len(cards) == 1
    c = cards[0]
    assert c["indicator"] == "critical"  # José Fernández: nivell ALT
    assert "\n" not in c["summary"] and len(c["summary"]) < 140
    assert "ERC no diagnosticada" in c["summary"] and "+2 alertas" in c["summary"]
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


def test_indicator_segons_el_nivell_de_tot_el_cupo(client):
    """Cada pacient rep una targeta vàlida i l'indicator correspon al nivell de risc del motor."""
    vistos = set()
    for p in client.get("/api/cupo").json()["pacients"]:
        cards = client.post(URL, json=peticio(p["pacient_id"])).json()["cards"]
        assert len(cards) == 1
        c = cards[0]
        assert c["indicator"] == INDICADOR[p["nivell_risc"]]
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
    # Amb REGICOR el risc de José Fernández no arriba a alt: desapareix l'alerta de RCV calculada amb SCORE2-Diabetes
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
