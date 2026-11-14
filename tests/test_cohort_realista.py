"""Cohort realista: les prevalences generades han de quedar a prop de les objectiu (REGICOR i ENRICA).

Els marges són amplis a propòsit: amb 1.500 pacients, un grup de 300 té un error de mostreig de ±2-3 punts.
Fonts i taula comparativa a docs/cohort_realista.md.
"""
from __future__ import annotations

import copy
from pathlib import Path
from statistics import mean

import pytest

from connectors import CsvConnector, FhirConnector
from engine import RiskEngine
from model.cataleg import CIAP2, JUSTIFICACIO_GRUP, LOINC
from model.formules import ckd_epi_2009, edat_en
from scripts import cohort_realista as cr

ARREL = Path(__file__).resolve().parent.parent
DADES = ARREL / "data" / "realista"
N = 1500


@pytest.fixture(scope="module")
def cfg() -> dict:
    return cr.carrega_config()


@pytest.fixture(scope="module")
def veritat() -> list[dict]:
    return cr.llegeix_veritat(DADES / "veritat.csv")


@pytest.fixture(scope="module")
def connector() -> CsvConnector:
    return CsvConnector(DADES / "csv")


@pytest.fixture(scope="module")
def dades(connector, veritat) -> dict:
    return {f["pacient_id"]: connector.get_patient_data(f["pacient_id"]) for f in veritat}


@pytest.fixture(scope="module")
def cupo(connector):
    return RiskEngine(connector).avalua_cupo()


def _grup(veritat, minim, maxim):
    return [f for f in veritat if minim <= f["edat"] <= maxim]


# --- Fitxers i reproductibilitat ------------------------------------------------------------

def test_fitxers_generats_i_reproduibles(cfg, veritat, connector):
    assert len(veritat) == N == cfg["n_pacients"] == len(connector.get_patients())
    assert len(list((DADES / "fhir").glob("*.json"))) == N
    assert all(f["pacient_id"].startswith("R") for f in veritat)  # no es confonen amb els P001-P100 de la demo
    assert len({p.nom for p in connector.get_patients()}) == N
    # Llavor fixa: tornar a generar dona exactament els mateixos pacients que hi ha desats
    pacients, perfils = cr.genera(cfg)
    assert [(p.id, p.edat, p.sexe, p.mrc, p.mrc_dx, p.imc) for p in perfils] == \
        [(f["pacient_id"], f["edat"], f["sexe"], bool(f["mrc"]), bool(f["mrc_dx"]), f["imc"]) for f in veritat]
    for nou in pacients[:60]:
        desat = connector.get_patient_data(nou.pacient.id)
        assert (nou.pacient, nou.analitiques, nou.diagnostics, nou.medicacions) == \
            (desat.pacient, desat.analitiques, desat.diagnostics, desat.medicacions)


def test_fhir_i_csv_donen_el_mateix(connector):
    fhir = FhirConnector(DADES / "fhir")
    assert [p.id for p in fhir.get_patients()] == [p.id for p in connector.get_patients()]
    for p in connector.get_patients()[::25]:
        a, b = fhir.get_patient_data(p.id), connector.get_patient_data(p.id)
        assert (a.pacient, a.analitiques, a.diagnostics, a.medicacions) == (b.pacient, b.analitiques, b.diagnostics, b.medicacions)


def test_nomes_local_no_es_puja_al_servidor_public():
    """L'script de pujada només llegeix data/synthetic (la cohort demo): la realista no surt de l'ordinador."""
    text = (ARREL / "scripts" / "upload_to_fhir.py").read_text(encoding="utf-8")
    assert 'CARPETA = ARREL / "data" / "synthetic" / "fhir"' in text and "realista" not in text


# --- Demografia -----------------------------------------------------------------------------

def test_distribucio_d_edat_d_adults_no_uniforme(cfg, veritat):
    total = sum(e["pes"] for e in cfg["edats"])
    for e in cfg["edats"]:
        obtingut = 100 * len(_grup(veritat, e["min"], e["max"])) / N
        assert obtingut == pytest.approx(100 * e["pes"] / total, abs=0.2)
    parts = [len(_grup(veritat, a, b)) / N for a, b in ((18, 39), (40, 64), (65, 120))]
    assert all(p > 0.2 for p in parts) and min(f["edat"] for f in veritat) >= 18
    assert 45 <= 100 * mean(f["sexe"] == "D" for f in veritat) <= 56
    # Més dones entre els més grans
    assert mean(f["sexe"] == "D" for f in _grup(veritat, 75, 120)) > mean(f["sexe"] == "D" for f in _grup(veritat, 18, 54))


# --- Factors de risc (REGICOR) --------------------------------------------------------------

@pytest.mark.parametrize("factor", ["dm2", "hta", "dislipemia", "fumador"])
def test_factors_de_risc_35_54_i_global(cfg, veritat, factor):
    o = cfg["objectius"]
    assert cr.pct(_grup(veritat, 35, 54), factor) == pytest.approx(o["regicor_35_54"][factor], abs=2.0)
    assert cr.pct(veritat, factor) == pytest.approx(o["regicor_global"][factor], abs=2.0)


@pytest.mark.parametrize("factor", ["dm2", "hta", "dislipemia"])
def test_la_prevalenca_augmenta_amb_l_edat(cfg, veritat, factor):
    per_banda = [cr.pct(_grup(veritat, a, b), factor) for a, b in cfg["factors"]["bandes"]]
    assert per_banda == sorted(per_banda) and per_banda[-1] > 3 * per_banda[1]


def test_tabac_baixa_en_els_grans(cfg, veritat):
    assert cr.pct(_grup(veritat, 75, 120), "fumador") < cr.pct(_grup(veritat, 35, 54), "fumador") / 2


def test_imc_mitja(cfg, veritat):
    assert mean(f["imc"] for f in veritat) == pytest.approx(cfg["objectius"]["regicor_global"]["imc"], abs=0.3)


@pytest.mark.parametrize("prova, marge", [("ldl", 6), ("hdl", 3), ("colesterol_total", 7), ("glucosa", 3),
                                          ("pas", 3), ("pad", 3), ("imc", 0.7)])
def test_valors_dels_sans_de_35_54_anys(cfg, veritat, dades, prova, marge):
    """Última analítica dels pacients de 35-54 anys sense patologia: centrada a la taula 1 (enquesta 2018)."""
    sans = [f for f in _grup(veritat, 35, 54) if not (f["hta"] or f["dm2"] or f["dislipemia"] or f["mrc"] or f["ic"])]
    valors = [a.valor for f in sans if (a := dades[f["pacient_id"]].ultima(LOINC[prova]))]
    assert len(valors) > 150
    assert mean(valors) == pytest.approx(cfg["objectius"]["sans_35_54"][prova], abs=marge)


# --- Malaltia renal crònica (ENRICA) --------------------------------------------------------

def test_mrc_per_edat(cfg, veritat):
    for b in cfg["objectius"]["enrica"]["per_edat"]:
        assert cr.pct(_grup(veritat, b["min"], b["max"]), "mrc") == pytest.approx(b["pct"], abs=2.0)


def test_mrc_global_i_per_sexe(cfg, veritat):
    e = cfg["objectius"]["enrica"]
    # El total surt d'aplicar les taxes per edat a l'estructura d'edat de la cohort (més envellida que la
    # mostra d'ENRICA): per això queda una mica per sobre del 15,1% de l'estudi
    obtingut = cr.pct(veritat, "mrc")
    assert obtingut == pytest.approx(cr.mrc_estandarditzada(veritat, cfg), abs=0.5)
    assert e["global"] - 1 <= obtingut <= e["global"] + 4
    homes = cr.pct([f for f in veritat if f["sexe"] == "H"], "mrc")
    dones = cr.pct([f for f in veritat if f["sexe"] == "D"], "mrc")
    assert homes == pytest.approx(e["homes"], abs=5) and dones == pytest.approx(e["dones"], abs=3)
    assert homes / dones == pytest.approx(e["homes"] / e["dones"], rel=0.2)  # la raó homes/dones de l'estudi


def test_mrc_s_acumula_amb_els_factors_de_risc(cfg, veritat):
    e = cfg["objectius"]["enrica"]
    assert cr.pct([f for f in veritat if f["n_factors"] <= 1], "mrc") == pytest.approx(e["factors_0_1"], abs=3.0)
    assert cr.pct([f for f in veritat if f["n_factors"] >= 4], "mrc") == pytest.approx(e["factors_molts"], abs=12.0)
    per_nombre = [cr.pct([f for f in veritat if f["n_factors"] == k], "mrc") for k in range(5)]
    assert per_nombre == sorted(per_nombre)
    # Els factors coincideixen en els mateixos pacients més del que ho farien per atzar
    p_hta, p_dm = cr.pct(veritat, "hta") / 100, cr.pct(veritat, "dm2") / 100
    assert mean(bool(f["hta"] and f["dm2"]) for f in veritat) > 1.5 * p_hta * p_dm


def test_mrc_sense_diagnostic_i_ic(cfg, veritat, dades):
    amb_mrc = [f for f in veritat if f["mrc"]]
    assert 100 - cr.pct(amb_mrc, "mrc_dx") == pytest.approx(100 * cfg["mrc"]["proporcio_sense_diagnostic"], abs=2.0)
    for f in veritat:  # el diagnòstic registrat coincideix amb la "veritat" (cap MRC diagnosticada sense ser-ho)
        assert dades[f["pacient_id"]].te_diagnostic(CIAP2["mrc"]) == bool(f["mrc_dx"])
        assert dades[f["pacient_id"]].te_diagnostic(CIAP2["ic"]) == bool(f["ic_dx"])
        assert f["mrc"] or not f["mrc_dx"]
    assert cr.pct(veritat, "ic") == pytest.approx(cfg["ic"]["prevalenca_global"], abs=0.3)


def test_parametres_configurables(cfg):
    canviada = copy.deepcopy(cfg)
    canviada["mrc"]["proporcio_sense_diagnostic"] = 0.3
    canviada["ic"]["prevalenca_global"] = 5.0
    perfils = cr.genera_perfils(canviada, n=600)
    assert len(perfils) == 600
    amb_mrc = [p for p in perfils if p.mrc]
    assert mean(not p.mrc_dx for p in amb_mrc) == pytest.approx(0.3, abs=0.03)
    assert 100 * mean(p.ic for p in perfils) == pytest.approx(5.0, abs=0.3)


# --- Coherència de cada pacient -------------------------------------------------------------

def test_cada_pacient_te_el_seu_historial_coherent(veritat, dades):
    for f in veritat:
        d = dades[f["pacient_id"]]
        assert d.pacient.edat == f["edat"] and d.pacient.fumador == bool(f["fumador"])
        for clau in ("hta", "dm2", "dislipemia"):
            assert d.te_diagnostic(CIAP2[clau]) == bool(f[clau])
        dxs = {clau for clau, codi in CIAP2.items() if d.te_diagnostic(codi)}
        for m in d.medicacions:  # cap fàrmac sense un diagnòstic que el justifiqui (tret de l'AAS)
            assert m.grup == "AAS" or JUSTIFICACIO_GRUP[m.grup] & dxs, (f["pacient_id"], m.nom)
        dates = {a.data for a in d.analitiques}
        assert len(dates) == f["n_visites"] and all(a.data >= date_inici() for a in d.analitiques)
        if f["seguiment"] == "cap":
            assert not d.analitiques
        # MRC per filtrat: l'últim FGe (CKD-EPI 2009, el del motor) és inferior a 60
        creat = d.ultima(LOINC["creatinina"])
        if creat and f["mrc_tipus"] in ("filtrat", "ambdues"):
            assert ckd_epi_2009(creat.valor, edat_en(d.pacient.data_naixement, creat.data), f["sexe"]) < 60
        if creat and not f["mrc"] and not f["fra"]:
            assert ckd_epi_2009(creat.valor, edat_en(d.pacient.data_naixement, creat.data), f["sexe"]) >= 60
            uacr = d.ultima(LOINC["uacr"])
            assert uacr is None or uacr.valor < 30
    assert mean(f["n_visites"] for f in veritat if f["seguiment"] == "cronic") > 4
    assert sum(f["seguiment"] == "cap" for f in veritat) > 50


def date_inici():
    from scripts.generate_patients import INICI
    return INICI


# --- El motor sobre la cohort realista ------------------------------------------------------

def test_el_motor_avalua_tota_la_cohort(cupo, veritat):
    assert len(cupo) == N
    per_id = {r.pacient_id: r for r in cupo}
    v = {f["pacient_id"]: f for f in veritat}
    ordre = [(r.grup_ordre, -r.puntuacio_prioritat) for r in cupo]
    assert ordre == sorted(ordre) and {r.grup_ordre for r in cupo} == {1, 2, 3, 4}
    for r in cupo:
        assert r.text_risc_cv and (r.categoria_risc_cv is None) == (r.estat_risc_cv in ("no_aplicable_edat", "falten_dades"))
        if r.edat < 40:
            assert r.text_risc_cv == "Escala SCORE2 no aplicable (<40 años)"
            assert not r.regles_actives() & {"risc_cardiovascular", "possible_ic", "aas_prevencio_primaria"}
    assert sum(r.edat < 40 for r in cupo) == sum(f["edat"] < 40 for f in veritat) > 300
    assert sum(r.estat_risc_cv == "falten_dades" for r in cupo) > 20
    # Cap fals positiu de MRC: tota alerta "ERC no diagnosticada" correspon a una MRC real sense diagnòstic
    detectades = [r.pacient_id for r in cupo if "mrc_no_diagnosticada" in r.regles_actives()]
    assert detectades and all(v[i]["mrc"] and not v[i]["mrc_dx"] for i in detectades)
    sense_dx = [f for f in veritat if f["mrc"] and not f["mrc_dx"]]
    assert 0.5 < len(detectades) / len(sense_dx) < 1  # la resta no té prou analítiques per confirmar-la
    assert all("possible_fra" in per_id[f["pacient_id"]].regles_actives() for f in veritat if f["fra"])
