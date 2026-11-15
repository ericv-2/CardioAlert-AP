"""Coherència clínica i proporcions de les dades sintètiques, i càrrega de la config."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from connectors import CsvConnector
from model.cataleg import CIAP2, JUSTIFICACIO_GRUP, LOINC
from model.formules import ckd_epi_2021, edat_en

ARREL = Path(__file__).resolve().parent.parent
AVUI = date(2026, 11, 13)


@pytest.fixture(scope="module")
def pacients():
    c = CsvConnector(ARREL / "simulador" / "datos" / "demo" / "csv")
    return [c.get_patient_data(p.id) for p in c.get_patients()]


def _dxs(d) -> set[str]:
    return {clau for clau, codi in CIAP2.items() if d.te_diagnostic(codi)}


def test_demografia(pacients):
    assert len(pacients) == 100
    assert sum(d.pacient.sexe == "H" for d in pacients) == 50
    assert all(40 <= d.pacient.edat <= 85 for d in pacients)
    assert len({d.pacient.nom for d in pacients}) == 100


@pytest.mark.parametrize("clau, objectiu", [("hta", 40), ("dislipemia", 43), ("dm2", 30), ("mrc", 20), ("ic", 5)])
def test_prevalences(pacients, clau, objectiu):
    assert abs(sum(clau in _dxs(d) for d in pacients) - objectiu) <= 3


def test_fumadors_i_sans(pacients):
    assert abs(sum(d.pacient.fumador for d in pacients) - 24) <= 3
    assert all(d.pacient.fumador == ("tabac" in _dxs(d)) for d in pacients)
    assert abs(sum(not d.diagnostics for d in pacients) - 25) <= 3


def test_fge_calculat_amb_ckd_epi_2021(pacients):
    for d in pacients:
        creat = {a.data: a.valor for a in d.serie(LOINC["creatinina"])}
        fge = d.serie(LOINC["fge"])
        assert len(fge) == len(creat)
        for a in fge:
            edat = edat_en(d.pacient.data_naixement, a.data)
            assert a.valor == round(ckd_epi_2021(creat[a.data], edat, d.pacient.sexe)), d.pacient.id


def test_cap_farmac_sense_diagnostic(pacients):
    for d in pacients:
        for m in d.medicacions:
            assert JUSTIFICACIO_GRUP[m.grup] & _dxs(d), f"{d.pacient.id}: {m.nom} sense diagnòstic"


def test_diabetics_coherents(pacients):
    for d in pacients:
        hba1c = [a.valor for a in d.serie(LOINC["hba1c"])]
        if "dm2" in _dxs(d):
            tractat = any(m.grup in {"metformina", "iSGLT2", "aGLP-1", "insulina"} for m in d.medicacions)
            assert tractat or max(hba1c) >= 6.5, d.pacient.id
        else:
            assert all(v < 6.5 for v in hba1c), d.pacient.id


def test_historic_dins_del_periode(pacients):
    for d in pacients:
        assert all(date(2022, 11, 1) <= a.data <= AVUI for a in d.analitiques), d.pacient.id


def test_cronics_amb_proves_que_falten(pacients):
    """~25% dels crònics tenen UACR o creatinina fora de termini (>12 mesos)."""
    cronics = [d for d in pacients if _dxs(d) - {"tabac"}]

    def falta(d) -> bool:
        proves = ["creatinina"] + (["uacr"] if _dxs(d) & {"dm2", "hta", "mrc"} else [])
        return any(d.ultima(LOINC[p]) is None or (AVUI - d.ultima(LOINC[p]).data).days > 365 for p in proves)

    assert 0.15 <= sum(falta(d) for d in cronics) / len(cronics) <= 0.35


def test_config_regles():
    regles = yaml.safe_load((ARREL / "config" / "rules.yaml").read_text(encoding="utf-8"))["rules"]
    assert set(regles) == {"uacr_falta", "creatinina_falta", "fge_descens", "albuminuria_sense_accio",
                           "mrc_no_diagnosticada", "possible_ic", "risc_cardiovascular", "ben_tractat"}
    assert all(r["enabled"] is True for r in regles.values())
    rcv = regles["risc_cardiovascular"]
    # ESC + REGICOR de referència per defecte; calibració de la regió de risc baix (Espanya, figura 3 ESC 2021)
    assert (rcv["escala_per_defecte"], rcv["regio_score2"], rcv["edat_min"]) == ("totes_dues", "baix", 40)
    assert rcv["alertes"]["molt_alt"]["pes"] > rcv["alertes"]["alt"]["pes"]
    # Objectius de tractament de la figura 6 (ESC 2021)
    assert regles["ben_tractat"]["pressio_objectiu"] == {"sistolica": 140, "sistolica_optima": 130, "diastolica": 90}
    assert regles["ben_tractat"]["ldl_objectiu"] == {"base": 100, "alt": 70, "molt_alt": 55}
    # Talls ESC per edat (risc alt / molt alt, %): < 50, 50-69 i >= 70 anys
    assert [(t["edat_max"], t["alt"], t["molt_alt"]) for t in regles["risc_cardiovascular"]["talls_per_edat"]] == \
        [(49, 2.5, 7.5), (69, 5, 10), (200, 7.5, 15)]
