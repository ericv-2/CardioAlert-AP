"""Vista «Pruebas pendientes»: uacr_falta i creatinina_falta no compten per a l'ordre ni per a «Hoy» i s'exporten
com a petició conjunta (CSV / Excel)."""
from __future__ import annotations

import io
import shutil
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from connectors import FhirConnector
from engine import RiskEngine

ARREL = Path(__file__).resolve().parent.parent
PROVES = {"uacr_falta", "creatinina_falta"}


@pytest.fixture(scope="module")
def cupo():
    return RiskEngine(FhirConnector(ARREL / "simulador" / "datos" / "demo" / "fhir")).avalua_cupo()


@pytest.fixture()
def client(tmp_path) -> TestClient:
    rules = shutil.copy(ARREL / "config" / "rules.yaml", tmp_path / "rules.yaml")
    return TestClient(create_app(font_per_defecte="local", rules_path=rules, dir_estats=tmp_path / "estats"))


def test_les_proves_pendents_no_sumen_punts(cupo):
    motor = RiskEngine(FhirConnector(ARREL / "simulador" / "datos" / "demo" / "fhir"))
    pesos = motor.motor["prioritat"]["kdigo"]
    assert set(motor.motor["prioritat"]["alertes_fora_avui"]) == PROVES
    amb_proves = [r for r in cupo if r.regles_actives() & PROVES]
    assert amb_proves
    for r in cupo:
        esperat = min(100, sum(a.pes for a in r.alertes_actives if a.regla not in PROVES) + pesos.get(r.risc_kdigo, 0))
        assert r.puntuacio_prioritat == esperat, r.pacient_id
        assert {p["regla"] for p in r.proves_pendents} == r.regles_actives() & PROVES, r.pacient_id
        if r.alertes_actives and r.regles_actives() - PROVES:
            assert r.alerta_principal not in PROVES, r.pacient_id  # el resum l'encapçala una alerta que compta


def test_cap_pacient_entra_a_hoy_nomes_per_una_prova_pendent(client):
    cos = client.get("/api/cupo").json()
    per_id = {p["pacient_id"]: p for p in cos["pacients"]}
    assert cos["llista_avui"]
    for pid in cos["llista_avui"]:
        assert {a["regla"] for a in per_id[pid]["alertes_actives"]} - PROVES, pid
    assert cos["kpis"]["proves_pendents"] == sum(bool(p["proves_pendents"]) for p in cos["pacients"]) > 0


def test_vista_i_exportacio(client):
    cos = client.get("/api/pruebas-pendientes").json()
    files = cos["files"]
    assert files and cos["pacients"] == len({f["pacient_id"] for f in files})
    assert {f["prova"] for f in files} <= {"UACR", "Creatinina"}
    # Primer les que no s'han fet mai; després, de més a menys mesos sense la prova
    claus = [(f["mesos_sense"] is not None, -(f["mesos_sense"] or 0)) for f in files]
    assert claus == sorted(claus)
    for f in files:
        assert f["ultima"] == "Nunca registrada" if f["ultima_data"] is None else f["mesos_sense"] > f["max_mesos"] - 1
    csv = client.get("/api/export/pruebas-pendientes", params={"formato": "csv"})
    assert csv.status_code == 200 and 'pruebas_pendientes.csv' in csv.headers["content-disposition"]
    linies = csv.content.decode("utf-8-sig").splitlines()
    assert linies[0].startswith("ID paciente;Nombre;") and len(linies) == len(files) + 1
    xlsx = client.get("/api/export/pruebas-pendientes")
    full = openpyxl.load_workbook(io.BytesIO(xlsx.content))["Petición conjunta"]
    valors = [[c.value for c in fila] for fila in full.iter_rows()]
    assert valors[0][0].startswith("Petición conjunta de laboratorio")
    inici = next(i for i, v in enumerate(valors) if v[0] == "ID paciente")
    assert len(valors) - inici - 1 == len(files)
    assert client.get("/api/export/pruebas-pendientes", params={"formato": "pdf"}).status_code == 422
