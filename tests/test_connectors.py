"""Els dos connectors han de donar el mateix resultat, i els 8 casos trampa han d'existir."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from connectors import Connector, CsvConnector, FhirConnector
from model import DadesPacient
from model.cataleg import CIAP2, LOINC

DADES = Path(__file__).resolve().parent.parent / "data" / "synthetic"
AVUI = date(2026, 11, 13)  # data de referència de les dades sintètiques


@pytest.fixture(scope="module")
def fhir() -> FhirConnector:
    return FhirConnector(DADES / "fhir")


@pytest.fixture(scope="module")
def csv() -> CsvConnector:
    return CsvConnector(DADES / "csv")


@pytest.fixture(scope="module", params=["fhir", "csv"])
def connector(request) -> Connector:
    return request.getfixturevalue(request.param)


# --- Equivalència entre connectors -----------------------------------------

def test_mateixos_pacients(fhir, csv):
    assert len(fhir.get_patients()) == 100
    assert fhir.get_patients() == csv.get_patients()


def test_mateixes_dades_per_pacient(fhir, csv):
    for p in fhir.get_patients():
        a, b = fhir.get_patient_data(p.id), csv.get_patient_data(p.id)
        assert a.pacient == b.pacient, p.id
        assert a.analitiques == b.analitiques, p.id
        assert a.diagnostics == b.diagnostics, p.id
        assert a.medicacions == b.medicacions, p.id
        assert a.analitiques, p.id


def test_pacient_inexistent(connector):
    with pytest.raises(KeyError):
        connector.get_patient_data("NO_EXISTEIX")


# --- Casos trampa ------------------------------------------------------------

def cas(connector: Connector, nom: str, edat: int, sexe: str) -> DadesPacient:
    trobats = [p for p in connector.get_patients() if p.nom == nom]
    assert len(trobats) == 1, f"{nom}: {len(trobats)} pacients"
    assert (trobats[0].edat, trobats[0].sexe) == (edat, sexe)
    return connector.get_patient_data(trobats[0].id)


def valors(d: DadesPacient, prova: str) -> list[float]:
    return [a.valor for a in d.serie(LOINC[prova])]


def dxs(d: DadesPacient) -> set[str]:
    return {clau for clau, codi in CIAP2.items() if d.te_diagnostic(codi)}


def grups(d: DadesPacient) -> set[str]:
    return {m.grup for m in d.medicacions}


def test_cas1_antonio_garcia(connector):
    d = cas(connector, "Antonio García", 64, "H")
    assert dxs(d) == {"dm2"}
    dm2 = next(x for x in d.diagnostics if x.codi_ciap2 == "T90")
    assert (dm2.codi_cie10, AVUI.year - dm2.data.year) == ("E11", 8)
    assert all(6.8 <= v <= 7.0 for v in valors(d, "hba1c"))
    assert all(v < 130 for v in valors(d, "pas")) and all(v < 80 for v in valors(d, "pad"))
    assert d.ultima(LOINC["uacr"]).data.year == 2023
    assert d.ultima(LOINC["creatinina"]).data.year == 2026  # la resta de l'analítica sí que es fa


def test_cas2_rosa_martinez(connector):
    d = cas(connector, "Rosa Martínez", 71, "D")
    assert dxs(d) == {"hta"}
    assert valors(d, "fge") == [85, 78, 71, 64]
    assert [a.data.year for a in d.serie(LOINC["fge"])] == [2023, 2024, 2025, 2026]
    assert all(v <= 1.1 for v in valors(d, "creatinina"))  # creatinina "normal" en dona


def test_cas3_jose_fernandez(connector):
    d = cas(connector, "José Fernández", 58, "H")
    assert dxs(d) == {"dm2", "hta"}
    uacr = {a.data.year: a.valor for a in d.serie(LOINC["uacr"])}
    assert (uacr[2025], uacr[2026]) == (45, 52)
    assert grups(d) == {"metformina"}


def test_cas4_pilar_lopez(connector):
    d = cas(connector, "Pilar López", 67, "D")
    assert dxs(d) == {"hta"}  # SENSE diagnòstic de MRC
    baixos = [a for a in d.serie(LOINC["fge"]) if a.valor < 60]
    assert [a.valor for a in baixos] == [55, 52]
    assert 150 <= (baixos[1].data - baixos[0].data).days <= 200  # ~6 mesos
    assert d.ultima(LOINC["uacr"]).valor == 40


def test_cas5_manuel_sanchez(connector):
    d = cas(connector, "Manuel Sánchez", 62, "H")
    assert d.pacient.fumador
    assert dxs(d) == {"hta", "dm2", "dislipemia", "tabac"}
    assert (d.ultima(LOINC["pas"]).valor, d.ultima(LOINC["pad"]).valor) == (138, 88)
    assert d.ultima(LOINC["hba1c"]).valor == 6.9
    assert d.ultima(LOINC["ldl"]).valor == 125
    assert not grups(d) & {"estatina", "IECA", "ARA-II", "iSGLT2"}


def test_cas6_dolores_ruiz(connector):
    d = cas(connector, "Dolores Ruiz", 74, "D")
    assert dxs(d) == {"hta", "dm2"}  # sense diagnòstic d'IC
    assert valors(d, "ntprobnp") == [450]


def test_cas7_francisco_jimenez(connector):
    d = cas(connector, "Francisco Jiménez", 63, "H")
    assert d.pacient.fumador
    assert dxs(d) == {"hta", "dm2", "dislipemia", "tabac"}
    assert {"estatina", "IECA", "iSGLT2"} <= grups(d)
    assert d.ultima(LOINC["hba1c"]).valor < 7
    assert d.ultima(LOINC["pas"]).valor < 130 and d.ultima(LOINC["pad"]).valor < 80
    for prova in ("uacr", "creatinina"):
        assert (AVUI - d.ultima(LOINC[prova]).data).days < 365


def test_cas8_laura_moreno(connector):
    d = cas(connector, "Laura Moreno", 45, "D")
    assert not d.pacient.fumador and not d.diagnostics and not d.medicacions
    assert all(v >= 90 for v in valors(d, "fge"))
    assert all(v < 100 for v in valors(d, "glucosa"))
    assert all(v < 130 for v in valors(d, "ldl"))
    assert all(v < 130 for v in valors(d, "pas")) and all(v < 85 for v in valors(d, "pad"))
