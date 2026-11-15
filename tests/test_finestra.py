"""Finestra de dades (minimització, art. 5.1.c RGPD): el motor només fa servir els anys necessaris de cada prova."""
from __future__ import annotations

import copy
import shutil
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from api.main import create_app
from connectors import CsvConnector, FhirConnector
from engine import RiskEngine
from model.cataleg import LOINC, PROVES

ARREL = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ARREL / "config" / "rules.yaml").read_text(encoding="utf-8"))
DEMO = ARREL / "simulador" / "datos" / "demo" / "fhir"
REALISTA = ARREL / "simulador" / "datos" / "realista" / "csv"
# Proves que llegeix el motor (risk_engine.py): totes han de tenir finestra > 0
USADES = {"creatinina", "uacr", "pas", "pad", "colesterol_total", "hdl", "ldl", "hba1c", "potasio", "ntprobnp"}


def _sense_finestra() -> dict:
    c = copy.deepcopy(CONFIG)
    c["motor"]["finestra_dades"]["enabled"] = False
    return c


def test_configuracio_coherent():
    f = CONFIG["motor"]["finestra_dades"]
    assert f["enabled"] and set(f["proves"]) <= set(PROVES)
    regles = set(CONFIG["rules"]) | set(CONFIG["motor"]) | set(CONFIG["motor"]["oportunitats"])
    for clau, p in f["proves"].items():
        assert set(p["regles"]) <= regles, clau
        assert (p["anys"] > 0) == bool(p["regles"]), clau  # 0 anys si i només si cap regla la fa servir
    assert {k for k, p in f["proves"].items() if p["anys"] > 0} == USADES
    # Les proves periòdiques: la finestra ha de cobrir el termini màxim sense prova (si no, l'alerta diria "mai")
    for regla, prova in (("uacr_falta", "uacr"), ("creatinina_falta", "creatinina")):
        assert f["proves"][prova]["anys"] * 12 >= CONFIG["rules"][regla]["max_mesos_sense_prova"]
    assert f["proves"]["creatinina"]["anys"] * 12 >= CONFIG["rules"]["ben_tractat"]["max_mesos_proves"]


@pytest.mark.parametrize("connector", [FhirConnector(DEMO), CsvConnector(REALISTA)], ids=["demo", "realista"])
def test_amb_la_finestra_els_resultats_son_identics(connector):
    """Les finestres són les mínimes (en anys sencers) que no canvien cap resultat de les dues cohorts."""
    amb = [r.to_dict() for r in RiskEngine(connector, CONFIG).avalua_cupo()]
    sense = [r.to_dict() for r in RiskEngine(connector, _sense_finestra()).avalua_cupo()]
    assert amb == sense


def test_minimitza_descarta_el_que_no_cal():
    motor = RiskEngine(FhirConnector(DEMO), CONFIG)
    proves = CONFIG["motor"]["finestra_dades"]["proves"]
    descartades = 0
    for p in FhirConnector(DEMO).get_patients():
        d = FhirConnector(DEMO).get_patient_data(p.id)
        m = motor.minimitza(d)
        assert (m.diagnostics, m.medicacions) == (d.diagnostics, d.medicacions)  # sense finestra
        for a in m.analitiques:
            clau = next(k for k, v in LOINC.items() if v == a.codi_loinc)
            assert proves[clau]["anys"] > 0, clau
            assert motor.avui - timedelta(days=round(proves[clau]["anys"] * 365.25)) <= a.data <= motor.avui
        descartades += len(d.analitiques) - len(m.analitiques)
    assert descartades > 0  # p. ex. el FGe informat pel laboratori, la glucosa i els triglicèrids


def test_la_fitxa_nomes_retorna_les_dades_de_la_finestra(tmp_path):
    rules = shutil.copy(ARREL / "config" / "rules.yaml", tmp_path / "rules.yaml")
    client = TestClient(create_app(font_per_defecte="local", rules_path=rules, dir_estats=tmp_path / "estats"))
    cos = client.get("/api/pacientes/P003").json()
    usats = {LOINC[k] for k in USADES}
    assert cos["analitiques"] and {a["codi_loinc"] for a in cos["analitiques"]} <= usats
    assert cos["meta"]["finestra_dades"]["creatinina"] == 5 and cos["meta"]["finestra_dades"]["glucosa"] == 0
    # La DIRAYA de P003 (2025) continua dins: és la que confirma la seva albuminúria
    assert any(a["origen"] == "DIRAYA - Andalucía" for a in cos["analitiques"])
