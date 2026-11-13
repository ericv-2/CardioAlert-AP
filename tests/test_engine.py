"""Motor de regles: casos trampa, controls, escala de risc intercanviable i fórmules."""
from __future__ import annotations

import copy
import re
from datetime import date
from pathlib import Path

import pytest
import yaml

from connectors import CsvConnector, FhirConnector
from engine import RiskEngine
from engine import renal
from engine.escales import EntradaRisc, ckd_addon, regicor, score2
from model import Analitica, DadesPacient, Diagnostic, Medicacio, Pacient
from model.cataleg import LOINC
from model.formules import ckd_epi_2009, ckd_epi_2021

ARREL = Path(__file__).resolve().parent.parent
DADES = ARREL / "data" / "synthetic"
CONFIG = ARREL / "config" / "rules.yaml"
AVUI = date(2026, 11, 13)


@pytest.fixture(scope="module")
def connector() -> FhirConnector:
    return FhirConnector(DADES / "fhir")


@pytest.fixture(scope="module")
def motor(connector) -> RiskEngine:
    return RiskEngine(connector)


@pytest.fixture()
def config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def per_nom(motor: RiskEngine, nom: str):
    pid = next(p.id for p in motor.connector.get_patients() if p.nom == nom)
    return motor.avalua(pid)


# --- Fórmules -------------------------------------------------------------------------------

def test_ckd_epi_2009_sense_factor_racial():
    assert ckd_epi_2009(1.0, 60, "H") == pytest.approx(81.4, abs=0.2)
    assert ckd_epi_2009(0.7, 50, "D") == pytest.approx(141 * 0.993**50 * 1.018, rel=1e-9)
    # La 2021 dona valors més alts que la 2009 (sobreestima el filtrat a Europa)
    for creat, edat, sexe in [(0.8, 45, "D"), (1.1, 67, "D"), (1.0, 60, "H"), (1.6, 75, "H")]:
        assert ckd_epi_2021(creat, edat, sexe) > ckd_epi_2009(creat, edat, sexe)


def test_matriu_kdigo():
    assert [renal.categoria_g(v) for v in (95, 90, 89, 60, 59, 45, 44, 30, 29, 15, 14)] == \
        ["G1", "G1", "G2", "G2", "G3a", "G3a", "G3b", "G3b", "G4", "G4", "G5"]
    assert [renal.categoria_a(v) for v in (29, 30, 300, 301)] == ["A1", "A2", "A2", "A3"]
    assert renal.risc_kdigo("G2", "A1") == "verd"
    assert renal.risc_kdigo("G3a", "A1") == renal.risc_kdigo("G1", "A2") == "groc"
    assert renal.risc_kdigo("G3a", "A2") == renal.risc_kdigo("G3b", "A1") == renal.risc_kdigo("G2", "A3") == "taronja"
    assert renal.risc_kdigo("G3b", "A2") == renal.risc_kdigo("G4", "A1") == renal.risc_kdigo("G3a", "A3") == "vermell"
    assert renal.risc_kdigo("G2", None) == "verd"  # sense UACR s'assumeix A1


def test_cronicitat_i_pendent():
    def m(dia, v):
        return renal.Mesura(date.fromisoformat(dia), v)
    baix = lambda v: v < 60  # noqa: E731
    assert renal.confirmat([m("2025-10-14", 55), m("2026-04-14", 52)], baix, 2, 91)
    assert not renal.confirmat([m("2026-03-01", 55), m("2026-04-14", 52)], baix, 2, 91)  # < 3 mesos: no és crònic
    assert not renal.confirmat([m("2025-10-14", 55), m("2026-04-14", 64)], baix, 2, 91)  # l'última és normal
    serie = [m("2023-01-01", 80), m("2024-01-01", 73), m("2025-01-01", 66)]
    assert renal.pendent_anual(serie, 3, 365) == pytest.approx(-7.0, abs=0.05)
    assert renal.pendent_anual(serie[:2], 3, 365) is None
    assert renal.caiguda_recent_pct([m("2026-01-01", 80), m("2026-03-01", 50)], 540) == pytest.approx(37.5)


def test_kfre():
    assert 0 < renal.kfre_5_anys(70, "H", 55, 10) < 1
    assert renal.kfre_5_anys(70, "H", 25, 800) > 20
    assert renal.kfre_5_anys(70, "H", 40, 300) > renal.kfre_5_anys(70, "D", 40, 300) > renal.kfre_5_anys(70, "D", 40, 30)


def test_escales_de_risc():
    base = dict(edat=62, sexe="H", fumador=True, diabetis=True, pas=138, pad=88, colesterol_total=200, hdl=42)
    e = EntradaRisc(**base, hba1c=6.9, fge=84, edat_dx_diabetis=53)
    # REGICOR calculat a mà: L = 0,04826*62 + 0,17692 + 0,24310 + 0,28320 + 0,42839 + 0,52337; 1 - 0,951^exp(L - 3,489)
    assert regicor(e).risc == pytest.approx(14.8, abs=0.2)
    assert regicor(EntradaRisc(**{**base, "edat": 80})) is None  # fora del rang 35-74
    assert score2(e).model == "SCORE2-Diabetes"
    assert score2(EntradaRisc(**base)).model == "SCORE2"  # sense HbA1c/FGe no es pot fer servir SCORE2-Diabetes
    assert score2(EntradaRisc(**{**base, "edat": 72})).model == "SCORE2-OP"
    assert score2(EntradaRisc(**{**base, "edat": 39})) is None
    sense_tabac = EntradaRisc(**{**base, "fumador": False}, hba1c=6.9, fge=84, edat_dx_diabetis=53)
    assert score2(e).risc > score2(sense_tabac).risc > 0
    assert score2(e, "alt").risc > score2(e, "baix").risc  # el calibratge regional canvia el risc
    # CKD Add-on: FGe baix i albuminúria pugen el risc; valors normals no
    nd = EntradaRisc(**{**base, "diabetis": False})
    r0 = score2(nd).risc
    assert ckd_addon(nd, r0, 40, 300) > ckd_addon(nd, r0, 40, 10) > r0 > ckd_addon(nd, r0, 95, 3)


# --- Casos trampa ---------------------------------------------------------------------------

@pytest.mark.parametrize("nom, regla", [
    ("Antonio García", "uacr_falta"),
    ("Rosa Martínez", "fge_descens"),
    ("José Fernández", "albuminuria_sense_accio"),
    ("Pilar López", "mrc_no_diagnosticada"),
    ("Manuel Sánchez", "risc_cardiovascular"),
    ("Dolores Ruiz", "possible_ic"),
])
def test_casos_trampa(motor, nom, regla):
    r = per_nom(motor, nom)
    assert regla in r.regles_actives()
    assert r.nivell_risc in ("ALT", "MITJA") and r.puntuacio_prioritat >= 10
    assert not r.ben_tractat
    assert r.accions_recomanades and r.resum and r.nota_clinica_auto


def test_cas1_uacr_antic(motor):
    r = per_nom(motor, "Antonio García")
    alerta = next(a for a in r.alertes_actives if a.regla == "uacr_falta")
    assert "21/11/2023" in alerta.motiu
    assert "sol_uacr" in {a.clau for a in r.accions_recomanades}
    assert "creatinina_falta" not in r.regles_actives()


def test_cas2_descens_amb_creatinina_normal(motor):
    r = per_nom(motor, "Rosa Martínez")
    assert r.pendent_fge < -5
    assert r.categoria_kdigo == "G2A1" and r.estat_renal == "normal"  # encara no és MRC: és el moment d'actuar
    assert "mrc_no_diagnosticada" not in r.regles_actives()


def test_cas3_creuament_interautonomic(motor):
    r = per_nom(motor, "José Fernández")
    alerta = next(a for a in r.alertes_actives if a.regla == "albuminuria_sense_accio")
    assert set(alerta.fonts) == {"DIRAYA - Andalucía", "eCAP - Catalunya"}
    assert "DIRAYA - Andalucía" in alerta.motiu
    assert {"DIRAYA - Andalucía", "eCAP - Catalunya"} <= set(r.fonts_dades)
    assert r.categoria_kdigo == "G2A2"
    # L'albuminúria només es confirma (2 mesures separades > 3 mesos) gràcies a la dada de DIRAYA
    assert "mrc_no_diagnosticada" in r.regles_actives()
    accions = {a.clau: a for a in r.accions_recomanades}
    assert {"sraa", "isglt2", "finerenona", "aglp1"} <= set(accions)
    assert "Sin analítica extra de control al iniciar iSGLT2" in accions["isglt2"].nota
    assert "Caída inicial de FGe <30% fisiológica: mantener fármaco" in accions["sraa"].nota
    assert "DIRAYA - Andalucía" in r.nota_clinica_auto


def test_cas4_mrc_sense_diagnostic(motor):
    r = per_nom(motor, "Pilar López")
    assert (r.categoria_kdigo, r.risc_kdigo, r.estat_renal) == ("G3aA2", "taronja", "mrc")
    assert r.fge_actual == 49  # CKD-EPI 2009 (el laboratori informava 52 amb la 2021)
    assert r.kfre_5a is not None
    assert r.risc_cv["reclassificat_mrc"] and r.risc_cv["categoria"] == "alt"
    assert "SCORE2 + CKD Add-on" in r.risc_cv["valors"]
    accions = {a.clau: a for a in r.accions_recomanades}
    assert "registrar_mrc" in accions and "G3aA2" in accions["registrar_mrc"].text
    assert "estatina" in accions  # FGe < 60 sense hipolipemiant


def test_cas5_risc_alt_infratractat(motor):
    r = per_nom(motor, "Manuel Sánchez")
    assert r.risc_cv["escala"] == "score2" and list(r.risc_cv["valors"]) == ["SCORE2-Diabetes"]
    assert r.risc_cv["valor"] >= 10 and r.risc_cv["categoria"] == "alt"
    assert {"sin IECA/ARA-II", "sin iSGLT2", "sin estatina"} <= set(r.objectius_pendents)
    assert {"estatina", "isglt2", "tabac", "pressio"} <= {a.clau for a in r.accions_recomanades}


def test_cas6_possible_ic(motor):
    r = per_nom(motor, "Dolores Ruiz")
    alerta = next(a for a in r.alertes_actives if a.regla == "possible_ic")
    assert "450" in alerta.motiu and "250" in alerta.motiu  # llindar de 50-75 anys
    assert alerta.fonts == ("Lab. Hospital",)
    assert "cribratge_ic" in {a.clau for a in r.accions_recomanades}


# --- Controls -------------------------------------------------------------------------------

def test_cas7_control_ben_tractat(motor):
    r = per_nom(motor, "Francisco Jiménez")
    assert r.alertes_actives == [] and r.accions_recomanades == []
    assert (r.nivell_risc, r.puntuacio_prioritat) == ("BAIX", 0)
    assert r.ben_tractat and r.objectius_pendents == []
    # Mateix perfil que el cas 5: el risc segueix sent alt, però no hi ha res a fer
    assert r.risc_cv["categoria"] == "alt"


def test_cas8_control_sana(motor):
    r = per_nom(motor, "Laura Moreno")
    assert r.alertes_actives == [] and r.accions_recomanades == []
    assert (r.nivell_risc, r.puntuacio_prioritat) == ("BAIX", 0)
    assert not r.ben_tractat  # no té res a tractar: la regla no li aplica
    assert r.risc_cv["categoria"] == "baix_moderat" and r.estat_renal == "normal"


# --- Configuració (rules.yaml) --------------------------------------------------------------

def test_canvi_d_escala_des_de_rules_yaml(connector, config, tmp_path):
    def motor_amb(escala: str) -> RiskEngine:
        cfg = copy.deepcopy(config)
        cfg["rules"]["risc_cardiovascular"]["escala"] = escala
        fitxer = tmp_path / f"rules_{escala}.yaml"
        fitxer.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        return RiskEngine(connector, fitxer)

    s2 = per_nom(motor_amb("score2"), "Manuel Sánchez")
    reg = per_nom(motor_amb("regicor"), "Manuel Sánchez")
    dues = per_nom(motor_amb("totes_dues"), "Manuel Sánchez")
    assert list(s2.risc_cv["valors"]) == ["SCORE2-Diabetes"]
    assert list(reg.risc_cv["valors"]) == ["REGICOR"] and reg.risc_cv["escala"] == "regicor"
    assert reg.risc_cv["valor"] == pytest.approx(14.8, abs=0.2) != s2.risc_cv["valor"]
    assert set(dues.risc_cv["valors"]) == {"SCORE2-Diabetes", "REGICOR"}
    assert dues.risc_cv["valor"] == max(s2.risc_cv["valor"], reg.risc_cv["valor"])
    for r in (s2, reg, dues):
        assert "risc_cardiovascular" in r.regles_actives()
    # Amb REGICOR el control segueix sense alertes
    assert per_nom(motor_amb("regicor"), "Francisco Jiménez").alertes_actives == []
    with pytest.raises(ValueError):
        motor_amb("framingham")


def test_regla_desactivada_i_llindars(connector, config):
    config["rules"]["uacr_falta"]["enabled"] = False
    config["rules"]["possible_ic"]["llindars_per_edat"] = [{"edat_max": 200, "llindar": 500}]
    m = RiskEngine(connector, config)
    assert "uacr_falta" not in per_nom(m, "Antonio García").regles_actives()
    assert "possible_ic" not in per_nom(m, "Dolores Ruiz").regles_actives()  # 450 < 500


def test_equacio_fge_configurable(connector, config):
    config["motor"]["equacio_fge"] = "ckd_epi_2021"
    assert per_nom(RiskEngine(connector, config), "Pilar López").fge_actual == 52


# --- Propietats de tot el cupo --------------------------------------------------------------

def test_cupo_ordenat_i_auditable(motor):
    cupo = motor.avalua_cupo()
    assert len(cupo) == 100
    punts = [r.puntuacio_prioritat for r in cupo]
    assert punts == sorted(punts, reverse=True) and all(0 <= p <= 100 for p in punts)
    cita = re.compile(r"^Clase (I|IIa|IIb|III) - ESC/ERA 2026$")
    for r in cupo:
        assert r.nivell_risc in ("ALT", "MITJA", "BAIX")
        assert r.nota_clinica_auto.startswith("[CardioAlert AP")
        assert all(cita.match(a.evidencia) and a.motiu for a in r.alertes_actives), r.pacient_id
        assert all(cita.match(a.evidencia) for a in r.accions_recomanades), r.pacient_id
        if r.alertes_actives:
            assert r.accions_recomanades and not r.ben_tractat, r.pacient_id
        assert r.to_dict()["pacient_id"] == r.pacient_id
    assert {r.nivell_risc for r in cupo} == {"ALT", "MITJA", "BAIX"}
    assert any(r.ben_tractat for r in cupo)


def test_determinista_i_independent_del_connector(connector, motor):
    per_csv = RiskEngine(CsvConnector(DADES / "csv"))
    assert [r.to_dict() for r in motor.avalua_cupo()] == [r.to_dict() for r in RiskEngine(connector).avalua_cupo()]
    assert [r.to_dict() for r in motor.avalua_cupo()] == [r.to_dict() for r in per_csv.avalua_cupo()]
    assert motor.avui == AVUI


# --- Pacients construïts a mà (regles sense cas trampa al dataset) --------------------------

def _pacient(creatinines: list[tuple[str, float]], dxs=(), meds=(), extres=()) -> DadesPacient:
    d = DadesPacient(Pacient("X001", "Paciente Prueba", 60, "H", False, date(1966, 6, 15)))
    for dia, creat in creatinines:
        d.analitiques.append(Analitica(LOINC["creatinina"], "Creatinina", creat, "mg/dL", date.fromisoformat(dia)))
    for clau, valor, dia in extres:
        d.analitiques.append(Analitica(LOINC[clau], clau, valor, "", date.fromisoformat(dia)))
    d.diagnostics = [Diagnostic(c, "", c, date(2020, 1, 1)) for c in dxs]
    d.medicacions = [Medicacio(nom, "", grup, date.fromisoformat(dia)) for nom, grup, dia in meds]
    return d.ordena()


def test_possible_fra_i_caiguda_esperada(motor):
    aguda = motor.avalua_dades(_pacient([("2026-03-10", 1.0), ("2026-09-10", 1.5)]))  # FGe 81 -> 50 (-38%)
    assert "possible_fra" in aguda.regles_actives() and aguda.estat_renal == "possible_fra"
    assert "retest_fra" in {a.clau for a in aguda.accions_recomanades}
    # Caiguda del 20% just després d'iniciar un iSGLT2: esperada, cap alerta de FRA
    esperada = motor.avalua_dades(_pacient([("2026-03-10", 1.0), ("2026-09-10", 1.2)], dxs=["T90"],
                                           meds=[("Empagliflozina", "iSGLT2", "2026-05-01")]))
    assert "possible_fra" not in esperada.regles_actives()
    assert any("esperado" in a and "Empagliflozina" in a for a in esperada.avisos)


def test_ntprobnp_amb_mrc_avancada_i_derivacio(motor):
    creat = [("2025-09-10", 2.7), ("2026-09-10", 2.8)]  # FGe ~24: MRC avançada (G4)
    r400 = motor.avalua_dades(_pacient(creat, dxs=["U99.01"], extres=[("ntprobnp", 400, "2026-09-10")]))
    r600 = motor.avalua_dades(_pacient(creat, dxs=["U99.01"], extres=[("ntprobnp", 600, "2026-09-10")]))
    assert r400.categoria_kdigo == "G4A?"
    assert "possible_ic" not in r400.regles_actives()  # 400 >= 250 (edat) però < 500 (MRC avançada)
    assert "possible_ic" in r600.regles_actives()
    assert "derivacio_nefrologia" in r400.regles_actives()  # FGe < 30


def test_aas_en_prevencio_primaria(motor):
    r = motor.avalua_dades(_pacient([("2026-09-10", 1.0)], dxs=["K86"], meds=[("Ácido acetilsalicílico", "AAS", "2020-01-01")]))
    alerta = next(a for a in r.alertes_actives if a.regla == "aas_prevencio_primaria")
    assert alerta.evidencia == "Clase III - ESC/ERA 2026"
