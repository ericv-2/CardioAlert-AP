"""Exportació a Excel: 100 pacients, totes les columnes i textos sense truncar."""
from __future__ import annotations

import shutil
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from api.main import create_app
from connectors import FhirConnector
from engine import RiskEngine
from engine.__main__ import main
from engine.export_excel import COLUMNES, exporta_cupo

ARREL = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def cupo():
    return RiskEngine(FhirConnector(ARREL / "data" / "synthetic" / "fhir")).avalua_cupo()


def test_excel_complet_i_sense_truncar(cupo, tmp_path):
    cami = exporta_cupo(cupo, tmp_path / "sub" / "cupo.xlsx", {"Fuente de datos": "Local"})
    llibre = load_workbook(cami)
    assert llibre.sheetnames == ["Cupo", "Alertas", "Resumen"]
    full = llibre["Cupo"]
    files = list(full.iter_rows(values_only=True))
    capcalera, dades = files[0], files[1:]
    assert len(dades) == 100 and list(capcalera) == [c[0] for c in COLUMNES]
    col = {nom: i for i, nom in enumerate(capcalera)}
    assert [f[col["ID"]] for f in dades] == [r.pacient_id for r in cupo]  # mateix ordre de prioritat
    for fila, r in zip(dades, cupo):
        assert fila[col["Riesgo CV (tabla 5 ESC 2021)"]] == r.text_risc_cv
        assert fila[col["Grupo de la lista de trabajo"]] == f"{r.grup_ordre}. {r.grup_ordre_text}"
        assert fila[col["REGICOR de referencia (%)"]] == r.regicor_referencia
        assert fila[col["Escala CV usada"]] == r.escala_usada
        assert fila[col["Riesgo CV a 10 años (%)"]] == r.risc_cv_percentatge
        assert fila[col["Nota clínica (borrador)"]] == r.nota_clinica_auto  # text sencer, sense truncar
        assert fila[col["Resumen (por qué + acción)"]] == r.resum
        for a in r.alertes_actives:
            assert a.motiu in fila[col["Alertas (motivo y evidencia)"]]
    jose = next(f for f in dades if f[col["ID"]] == "P003")
    assert jose[col["Datos cruzados entre comunidades"]] == "Sí" and "DIRAYA - Andalucía" in jose[col["Sistemas de origen"]]
    assert llibre["Alertas"].max_row - 1 == sum(len(r.alertes_actives) for r in cupo)
    resum = dict(llibre["Resumen"].iter_rows(values_only=True))
    assert resum["Pacientes evaluados"] == 100 and resum["Fuente de datos"] == "Local"
    assert not any("ALT" in str(c) or "MITJA" in str(c) or "BAIX" in str(c) for c in capcalera)
    categories = [resum[f"Riesgo CV {t} (tabla 5 ESC 2021)"] for t in ("Bajo-moderado", "Alto", "Muy alto")]
    assert sum(categories) + resum["Sin categoría (< 40 años o faltan datos)"] == 100
    assert sum(v for k, v in resum.items() if str(k).startswith("Lista de trabajo, grupo")) == 100


def test_cli_excel(tmp_path, capsys):
    desti = tmp_path / "cupo_evaluado.xlsx"
    main(["--excel", str(desti), "--escala", "regicor"])
    assert "100 pacients" in capsys.readouterr().out
    full = load_workbook(desti)["Cupo"]
    assert full.max_row == 101
    capcalera = [c.value for c in full[1]]
    escales = {f[capcalera.index("Escala CV usada")].value for f in full.iter_rows(min_row=2)}
    assert escales == {"REGICOR", None}


def test_descarrega_des_de_l_api(tmp_path):
    rules = shutil.copy(ARREL / "config" / "rules.yaml", tmp_path / "rules.yaml")
    r = TestClient(create_app(rules_path=rules)).get("/api/export/excel", params={"scale": "score2"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert 'filename="cupo_evaluado.xlsx"' in r.headers["content-disposition"]
    llibre = load_workbook(BytesIO(r.content))
    assert llibre["Cupo"].max_row == 101
