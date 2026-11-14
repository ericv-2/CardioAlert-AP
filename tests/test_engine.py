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
from engine.__main__ import recompte
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
    assert r.puntuacio_prioritat >= 10 and r.grup_ordre in (1, 2, 3, 4)
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
    # 67 anys sense diabetis i amb afectació renal: SCORE2 + CKD Add-on; alt amb els talls de 50-69 anys
    assert r.escala_usada == "SCORE2 + CKD Add-on" and 5 <= r.risc_cv_percentatge < 10
    assert r.categoria_risc_cv == "Alto" and r.rang_referencia_cv.startswith("50-69 años")
    accions = {a.clau: a for a in r.accions_recomanades}
    assert "registrar_mrc" in accions and "G3aA2" in accions["registrar_mrc"].text
    assert "estatina" in accions  # FGe < 60 sense hipolipemiant


def test_cas5_risc_alt_infratractat(motor):
    r = per_nom(motor, "Manuel Sánchez")
    assert r.risc_cv["escala"] == "totes_dues" and list(r.risc_cv["valors"]) == ["SCORE2-Diabetes"]
    assert r.risc_cv["valor"] >= 10 and r.risc_cv["categoria"] == "molt_alt"  # 62 anys: molt alt si >= 10%
    assert (r.escala_usada, r.categoria_risc_cv, r.text_risc_cv) == ("SCORE2-Diabetes", "Muy alto", "Muy alto")
    assert {"sin IECA/ARA-II", "sin iSGLT2", "sin estatina", "LDL 125 mg/dL (objetivo < 100)"} <= set(r.objectius_pendents)
    accions = {a.clau: a for a in r.accions_recomanades}
    # PAS 138: pas 1 assolit (< 140); el pas 2 (< 130 si es tolera) és una acció, no un objectiu pendent
    assert {"estatina", "isglt2", "tabac", "pressio_optima"} <= set(accions) and "pressio" not in accions
    assert "objetivo LDL < 55 mg/dL por riesgo muy alto" in accions["estatina"].text
    alerta = next(a for a in r.alertes_actives if a.regla == "risc_cardiovascular")
    assert alerta.titol == "Riesgo cardiovascular muy alto: tratamiento generalmente recomendado"
    assert alerta.evidencia == "Clase I - ESC 2021" and r.grup_ordre == 2
    # REGICOR només com a referència: no canvia la categoria
    assert r.regicor_referencia == pytest.approx(14.8, abs=0.2)
    assert r.nota_calibracio == ("Las escalas europeas pueden sobreestimar el riesgo en población española. "
                                 f"REGICOR (calibrada para población catalana): {str(r.regicor_referencia).replace('.', ',')} %")


def test_cas6_possible_ic(motor):
    r = per_nom(motor, "Dolores Ruiz")
    alerta = next(a for a in r.alertes_actives if a.regla == "possible_ic")
    assert "450" in alerta.motiu and "250" in alerta.motiu  # llindar de 50-75 anys
    assert alerta.fonts == ("Lab. Hospital",)
    assert "cribratge_ic" in {a.clau for a in r.accions_recomanades}


# --- Controls -------------------------------------------------------------------------------

def test_cas7_control_ben_tractat(motor):
    r = per_nom(motor, "Francisco Jiménez")
    assert r.alertes_actives == []
    assert (r.grup_ordre, r.grup_ordre_text, r.puntuacio_prioritat) == (4, "Resto", 0)
    assert r.ben_tractat and r.objectius_pendents == []  # pas 1 de la figura 6: PAS < 140 i LDL < 100
    # Mateix perfil que el cas 5: el risc segueix sent molt alt, però no hi ha cap alerta
    assert r.risc_cv["categoria"] == "molt_alt" and r.categoria_risc_cv == "Muy alto"
    # Pas 2 de la figura 6: LDL 68 >= 55 (objectiu amb risc molt alt) és una acció opcional, no una alerta
    assert [a.clau for a in r.accions_recomanades] == ["ldl_intensificar"]
    assert "LDL 68 mg/dL (objetivo < 55 por riesgo muy alto" in r.accions_recomanades[0].text


def test_cas8_control_sana(motor):
    r = per_nom(motor, "Laura Moreno")
    assert r.alertes_actives == [] and r.accions_recomanades == []
    assert (r.grup_ordre, r.puntuacio_prioritat) == (4, 0)
    assert not r.ben_tractat  # no té res a tractar: la regla no li aplica
    assert r.risc_cv["categoria"] == "baix_moderat" and r.estat_renal == "normal"
    assert r.categoria_risc_cv == r.text_risc_cv == "Bajo-moderado" and r.escala_usada == "SCORE2"


# --- Configuració (rules.yaml) --------------------------------------------------------------

def test_canvi_d_escala_des_de_rules_yaml(connector, config, tmp_path):
    def motor_amb(escala: str) -> RiskEngine:
        cfg = copy.deepcopy(config)
        cfg["rules"]["risc_cardiovascular"]["escala_per_defecte"] = escala
        fitxer = tmp_path / f"rules_{escala}.yaml"
        fitxer.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        return RiskEngine(connector, fitxer)

    s2 = per_nom(motor_amb("score2"), "Manuel Sánchez")
    reg = per_nom(motor_amb("regicor"), "Manuel Sánchez")
    dues = per_nom(motor_amb("totes_dues"), "Manuel Sánchez")
    assert list(s2.risc_cv["valors"]) == ["SCORE2-Diabetes"]
    assert list(reg.risc_cv["valors"]) == ["REGICOR"] and reg.risc_cv["escala"] == "regicor"
    assert reg.risc_cv["valor"] == pytest.approx(14.8, abs=0.2) != s2.risc_cv["valor"]
    assert (reg.escala_usada, reg.categoria_risc_cv) == ("REGICOR", "Alto")  # REGICOR: alt de 10% a < 15%
    assert reg.rang_referencia_cv.startswith("REGICOR:")
    # Amb les dues escales la categoria surt SEMPRE de l'escala ESC; REGICOR és només una referència
    assert list(dues.risc_cv["valors"]) == ["SCORE2-Diabetes"]
    assert (dues.escala_usada, dues.risc_cv_percentatge, dues.categoria_risc_cv) == \
        ("SCORE2-Diabetes", s2.risc_cv_percentatge, s2.categoria_risc_cv)
    assert dues.regicor_referencia == reg.risc_cv_percentatge and "REGICOR" in dues.nota_calibracio
    assert s2.regicor_referencia is None and s2.nota_calibracio is None
    assert reg.regicor_referencia is None
    for r in (s2, reg, dues):
        assert "risc_cardiovascular" in r.regles_actives()
    # Amb REGICOR el control segueix sense alertes
    assert per_nom(motor_amb("regicor"), "Francisco Jiménez").alertes_actives == []
    with pytest.raises(ValueError):
        motor_amb("framingham")


def test_escala_per_defecte_i_seleccio_en_calent(connector, config):
    """Per defecte, ESC automàtic + REGICOR de referència; REGICOR es pot triar per paràmetre (comparacions)."""
    assert config["rules"]["risc_cardiovascular"]["escala_per_defecte"] == "totes_dues"
    assert RiskEngine(connector).escala == "totes_dues"
    reg = RiskEngine(connector, escala="regicor")
    cupo = reg.avalua_cupo()
    assert {r.escala_usada for r in cupo} == {"REGICOR", None}  # None: fora del rang 35-74 anys
    assert all(r.escala_usada == "REGICOR" for r in cupo if 35 <= r.edat <= 74)
    with pytest.raises(ValueError):
        RiskEngine(connector, escala="framingham")


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
    # Ordre de la llista de treball: per grup i, dins de cada grup, per puntuació del motor
    ordre = [(r.grup_ordre, -r.puntuacio_prioritat) for r in cupo]
    assert ordre == sorted(ordre) and all(0 <= r.puntuacio_prioritat <= 100 for r in cupo)
    urgents = {"possible_ic", "possible_fra", "derivacio_nefrologia"}
    cita = re.compile(r"^Clase (I|IIa|IIb|III) - (ESC/ERA 2026|ESC 2021)$")
    for r in cupo:
        assert "nivell_risc" not in r.to_dict()  # cap classificació ALT/MITJA/BAIX
        assert r.categoria_risc_cv in ("Bajo-moderado", "Alto", "Muy alto") and r.text_risc_cv == r.categoria_risc_cv
        regles = r.regles_actives()
        esperat = (1 if regles & urgents else 4 if "risc_cardiovascular" not in regles
                   else 2 if r.categoria_risc_cv == "Muy alto" else 3)
        assert r.grup_ordre == esperat, r.pacient_id
        for a in r.alertes_actives:
            if a.regla == "risc_cardiovascular":
                assert a.evidencia.endswith("ESC 2021") and a.pes == (35 if r.categoria_risc_cv == "Muy alto" else 20)
                assert a.titol in (
                    "Riesgo cardiovascular alto: valorar tratamiento (decisión compartida)",
                    "Riesgo cardiovascular muy alto: tratamiento generalmente recomendado",
                    "Valorar tratamiento considerando fragilidad, polimedicación y preferencias del paciente (clase IIb)")
        assert r.nota_clinica_auto.startswith("[CardioAlert AP")
        assert all(cita.match(a.evidencia) and a.motiu for a in r.alertes_actives), r.pacient_id
        # Les accions dels objectius de la figura 6 citen la guia sense classe (no se n'inventa cap)
        assert all(cita.match(a.evidencia) or a.evidencia == "ESC 2021" for a in r.accions_recomanades), r.pacient_id
        if r.alertes_actives:
            assert r.accions_recomanades and not r.ben_tractat, r.pacient_id
        assert r.to_dict()["pacient_id"] == r.pacient_id
    assert {r.grup_ordre for r in cupo} == {1, 2, 3, 4}
    assert any(r.ben_tractat for r in cupo)
    n = recompte(cupo)
    assert sum(n["categories"].values()) == 100 and sum(n["grups"].values()) == 100
    assert (n["sense_categoria"], n["menors_edat_minima"], n["falten_dades"]) == (0, 0, 0)


def test_determinista_i_independent_del_connector(connector, motor):
    per_csv = RiskEngine(CsvConnector(DADES / "csv"))
    assert [r.to_dict() for r in motor.avalua_cupo()] == [r.to_dict() for r in RiskEngine(connector).avalua_cupo()]
    assert [r.to_dict() for r in motor.avalua_cupo()] == [r.to_dict() for r in per_csv.avalua_cupo()]
    assert motor.avui == AVUI


# --- Pacients construïts a mà (regles sense cas trampa al dataset) --------------------------

def _pacient(creatinines: list[tuple[str, float]], dxs=(), meds=(), extres=(), edat: int = 60) -> DadesPacient:
    d = DadesPacient(Pacient("X001", "Paciente Prueba", edat, "H", False, date(2026 - edat, 6, 15)))
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


# --- Selecció automàtica d'escala ESC, CKD Add-on i talls per edat -------------------------

LIPIDS = [("pas", 130, "2026-09-10"), ("pad", 80, "2026-09-10"), ("colesterol_total", 200, "2026-09-10"),
          ("hdl", 50, "2026-09-10")]
FGE_NORMAL = [("2025-09-10", 0.9), ("2026-09-10", 0.9)]
FGE_REDUIT = [("2025-09-10", 1.5), ("2026-09-10", 1.5)]  # FGe ~50 mantingut (no és una caiguda aguda)


@pytest.mark.parametrize("edat, dxs, creatinines, extres, esperada", [
    (60, [], FGE_NORMAL, [], "SCORE2"),
    (60, [], FGE_REDUIT, [], "SCORE2 + CKD Add-on"),                           # FGe reduït
    (60, [], FGE_NORMAL, [("uacr", 80, "2026-09-10")], "SCORE2 + CKD Add-on"),  # albuminúria elevada
    (60, ["T90"], FGE_NORMAL, [("hba1c", 7.2, "2026-09-10")], "SCORE2-Diabetes"),
    (60, ["T90"], FGE_REDUIT, [("hba1c", 7.2, "2026-09-10")], "SCORE2-Diabetes"),  # ja inclou el FGe: sense Add-on
    (75, [], FGE_NORMAL, [], "SCORE2-OP"),
    (75, [], FGE_REDUIT, [], "SCORE2-OP + CKD Add-on"),
    (75, ["T90"], FGE_NORMAL, [("hba1c", 7.2, "2026-09-10")], "SCORE2-OP"),    # >= 70 anys: SCORE2-OP encara que sigui diabètic
    (38, [], FGE_NORMAL, [], None),                                            # < 40 anys: no aplicable
])
def test_seleccio_automatica_de_variant_esc(motor, edat, dxs, creatinines, extres, esperada):
    r = motor.avalua_dades(_pacient(creatinines, dxs=dxs, extres=LIPIDS + extres, edat=edat))
    assert r.escala_usada == esperada
    if esperada is None:
        assert r.risc_cv_percentatge is None and r.categoria_risc_cv is None
    else:
        assert r.risc_cv_percentatge > 0 and r.categoria_risc_cv in ("Bajo-moderado", "Alto", "Muy alto")
        assert r.risc_cv["valors"] == {esperada: r.risc_cv_percentatge}


def test_ckd_addon_puja_el_risc_i_no_s_aplica_en_caiguda_aguda(motor, connector):
    sense = motor.avalua_dades(_pacient(FGE_NORMAL, extres=LIPIDS))
    amb = motor.avalua_dades(_pacient(FGE_REDUIT, extres=LIPIDS))
    assert amb.risc_cv_percentatge > sense.risc_cv_percentatge
    # Una caiguda aguda (possible FRA) no és un FGe fiable per reclassificar el risc crònic
    aguda = motor.avalua_dades(_pacient([("2026-03-10", 0.9), ("2026-09-10", 1.5)], extres=LIPIDS))
    assert aguda.estat_renal == "possible_fra" and aguda.escala_usada == "SCORE2"
    # REGICOR no porta Add-on encara que hi hagi afectació renal
    reg = RiskEngine(connector, escala="regicor").avalua_dades(_pacient(FGE_REDUIT, extres=LIPIDS))
    assert reg.escala_usada == "REGICOR"


def test_ckd_addon_configurable(connector, config):
    config["rules"]["risc_cardiovascular"]["ckd_addon"]["enabled"] = False
    r = RiskEngine(connector, config).avalua_dades(_pacient(FGE_REDUIT, extres=LIPIDS))
    assert r.escala_usada == "SCORE2"


TALLS_ESC = [(49, 2.5, 7.5, "< 50 años"), (69, 5, 10, "50-69 años"), (200, 7.5, 15, "≥ 70 años")]


def test_talls_per_edat_a_tot_el_cupo(motor):
    """La categoria de cada pacient surt del seu % i del tall del seu grup d'edat (talls ESC)."""
    vistes = set()
    for r in motor.avalua_cupo():
        if r.risc_cv_percentatge is None:
            continue
        _, alt, molt_alt, tram = next(t for t in TALLS_ESC if r.edat <= t[0])
        esperada = ("Muy alto" if r.risc_cv_percentatge >= molt_alt
                    else "Alto" if r.risc_cv_percentatge >= alt else "Bajo-moderado")
        assert r.rang_referencia_cv.startswith(tram + ":"), r.pacient_id
        if r.risc_cv["reclassificat_mrc"]:  # la MRC (KDIGO taronja/vermell) només pot pujar la categoria
            assert r.categoria_risc_cv != esperada and r.categoria_risc_cv != "Bajo-moderado", r.pacient_id
        else:
            assert r.categoria_risc_cv == esperada, r.pacient_id
        vistes.add((tram, r.categoria_risc_cv))
    assert {t for t, _ in vistes} == {"< 50 años", "50-69 años", "≥ 70 años"}
    assert {c for _, c in vistes} == {"Bajo-moderado", "Alto", "Muy alto"}


def test_mateix_risc_categoria_diferent_segons_edat(connector, config):
    """Els talls viuen a rules.yaml: movent-los, el mateix pacient canvia de categoria."""
    base = RiskEngine(connector, config).avalua_dades(_pacient(FGE_NORMAL, extres=LIPIDS))
    pct = base.risc_cv_percentatge
    assert base.rang_referencia_cv == "50-69 años: bajo-moderado < 5% | alto 5% a < 10% | muy alto ≥ 10%"

    def categoria(alt: float, molt_alt: float) -> str:
        cfg = copy.deepcopy(config)
        cfg["rules"]["risc_cardiovascular"]["talls_per_edat"][1].update(alt=alt, molt_alt=molt_alt)
        return RiskEngine(connector, cfg).avalua_dades(_pacient(FGE_NORMAL, extres=LIPIDS)).categoria_risc_cv

    assert categoria(pct + 1, pct + 2) == "Bajo-moderado"
    assert categoria(pct, pct + 1) == "Alto"       # el tall és inclusiu (>=)
    assert categoria(pct - 1, pct) == "Muy alto"


def test_sense_etiquetes_d_evidencia_inventades(connector, config):
    """Si una regla no té "evidencia" a rules.yaml, el motor cita només la guia (no s'inventa cap classe)."""
    del config["rules"]["uacr_falta"]["evidencia"]
    r = per_nom(RiskEngine(connector, config), "Antonio García")
    alerta = next(a for a in r.alertes_actives if a.regla == "uacr_falta")
    assert alerta.evidencia == "ESC/ERA 2026"


# --- Guia ESC 2021: calibració, àmbit, menors de 40, dades que falten i objectius ----------

def test_calibracio_de_la_regio_de_risc_baix():
    """Espanya és un país de risc baix (figura 3, ESC 2021): el motor demana aquesta calibració."""
    e = EntradaRisc(edat=55, sexe="H", fumador=True, diabetis=False, pas=140, pad=85, colesterol_total=213, hdl=50)
    regions = ["baix", "moderat", "alt", "molt_alt"]
    riscos = [score2(e, regio).risc for regio in regions]
    assert riscos == sorted(riscos) and score2(e).risc == riscos[0]  # per defecte, la de risc baix
    gran = EntradaRisc(edat=75, sexe="D", fumador=False, diabetis=False, pas=150, pad=85, colesterol_total=213, hdl=55)
    assert score2(gran, "baix").risc < score2(gran, "moderat").risc < score2(gran, "alt").risc


def test_el_motor_fa_servir_la_regio_configurada(connector, config):
    base = RiskEngine(connector, config).avalua_dades(_pacient(FGE_NORMAL, extres=LIPIDS)).risc_cv_percentatge
    config["rules"]["risc_cardiovascular"]["regio_score2"] = "alt"
    assert RiskEngine(connector, config).avalua_dades(_pacient(FGE_NORMAL, extres=LIPIDS)).risc_cv_percentatge > base


def test_menor_de_40_nomes_regles_renals_i_proves_pendents(motor):
    # 38 anys, HTA, FGe ~50 mantingut, NT-proBNP alt i AAS: només han de saltar les regles renals i les proves
    r = motor.avalua_dades(_pacient(FGE_REDUIT, dxs=["K86"], edat=38, meds=[("Ácido acetilsalicílico", "AAS", "2020-01-01")],
                                    extres=LIPIDS + [("ntprobnp", 900, "2026-09-10")]))
    assert (r.estat_risc_cv, r.text_risc_cv) == ("no_aplicable_edat", "Escala SCORE2 no aplicable (<40 años)")
    assert r.categoria_risc_cv is None and r.risc_cv_percentatge is None and r.nota_calibracio is None
    assert r.regles_actives() == {"mrc_no_diagnosticada", "uacr_falta"}
    assert "Escala SCORE2 no aplicable (<40 años)" in r.nota_clinica_auto
    # El mateix pacient amb 45 anys sí que rep les regles cardíaques
    r45 = motor.avalua_dades(_pacient(FGE_REDUIT, dxs=["K86"], edat=45, meds=[("Ácido acetilsalicílico", "AAS", "2020-01-01")],
                                      extres=LIPIDS + [("ntprobnp", 900, "2026-09-10")]))
    assert {"possible_ic", "aas_prevencio_primaria"} <= r45.regles_actives() and r45.grup_ordre == 1
    # El resum l'encapçala l'alerta urgent, encara que una altra alerta sumi els mateixos punts o més
    assert r45.alerta_principal == "possible_ic" and r45.resum.startswith("Posible insuficiencia cardíaca")


@pytest.mark.parametrize("extres, dxs, accions", [
    ([("colesterol_total", 200, "2026-09-10"), ("hdl", 50, "2026-09-10")], [], {"sol_pas"}),
    ([("pas", 130, "2026-09-10"), ("hdl", 50, "2026-09-10")], [], {"sol_lipids"}),
    ([("pas", 130, "2026-09-10"), ("colesterol_total", 200, "2026-09-10")], [], {"sol_lipids"}),
    ([], [], {"sol_pas", "sol_lipids"}),
    (LIPIDS, ["T90"], {"sol_hba1c"}),  # diabètic de 60 anys sense HbA1c: SCORE2 no és per a diabètics
])
def test_falten_dades_per_calcular_el_risc(motor, extres, dxs, accions):
    r = motor.avalua_dades(_pacient(FGE_NORMAL, dxs=dxs, extres=extres))
    assert (r.estat_risc_cv, r.text_risc_cv) == ("falten_dades", "Faltan datos para calcular el riesgo")
    assert r.categoria_risc_cv is None and r.escala_usada is None
    assert accions <= {a.clau for a in r.accions_recomanades}
    assert "risc_cardiovascular" not in r.regles_actives()
    if "sol_lipids" in accions:
        assert "Perfil lipídico" in r.volant_auto


def test_ambit_d_aplicacio_de_score2(connector, config):
    """SCORE2 / SCORE2-OP són per a persones aparentment sanes: MCV, HF, diabetis i MRC van per una altra via."""
    m = RiskEngine(connector, config)
    ecv = m.avalua_dades(_pacient(FGE_NORMAL, dxs=["K75"], extres=LIPIDS))  # infart: molt alt sense escala
    assert (ecv.estat_risc_cv, ecv.categoria_risc_cv, ecv.escala_usada) == ("ecv_establerta", "Muy alto", None)
    dm = m.avalua_dades(_pacient(FGE_NORMAL, dxs=["T90"], extres=LIPIDS + [("hba1c", 7.2, "2026-09-10")]))
    assert dm.escala_usada == "SCORE2-Diabetes" and not dm.risc_cv["aparentment_sa"]
    mrc = m.avalua_dades(_pacient(FGE_REDUIT, extres=LIPIDS))  # FGe ~50 mantingut: mai SCORE2 "pelat"
    assert mrc.escala_usada == "SCORE2 + CKD Add-on" and not mrc.risc_cv["aparentment_sa"]
    assert m.avalua_dades(_pacient(FGE_NORMAL, extres=LIPIDS)).risc_cv["aparentment_sa"]
    # Hipercolesterolèmia familiar: risc alt directe, sense escala (el codi es configura a rules.yaml)
    config["rules"]["risc_cardiovascular"]["diagnostics_hf"] = ["T93.HF"]
    hf = RiskEngine(connector, config).avalua_dades(_pacient(FGE_NORMAL, dxs=["T93.HF"], extres=LIPIDS))
    assert (hf.estat_risc_cv, hf.categoria_risc_cv, hf.escala_usada) == ("hf", "Alto", None)


def test_textos_de_l_alerta_segons_la_taula_5(motor):
    def alerta(edat, pas, dxs=(), col=240):
        extres = [("pas", pas, "2026-09-10"), ("pad", 85, "2026-09-10"), ("colesterol_total", col, "2026-09-10"),
                  ("hdl", 42, "2026-09-10"), ("ldl", col - 70, "2026-09-10")]
        r = motor.avalua_dades(_pacient(FGE_NORMAL, dxs=list(dxs), extres=extres, edat=edat))
        return r, next(a for a in r.alertes_actives if a.regla == "risc_cardiovascular")

    r, a = alerta(55, 138)
    assert (r.categoria_risc_cv, r.grup_ordre) == ("Alto", 3)
    assert (a.titol, a.evidencia, a.pes) == ("Riesgo cardiovascular alto: valorar tratamiento (decisión compartida)",
                                             "Clase IIa - ESC 2021", 20)
    r, a = alerta(68, 165)
    assert (r.categoria_risc_cv, r.grup_ordre) == ("Muy alto", 2)
    assert (a.titol, a.evidencia, a.pes) == ("Riesgo cardiovascular muy alto: tratamiento generalmente recomendado",
                                             "Clase I - ESC 2021", 35)
    assert "referencia 50-69 años: bajo-moderado < 5% | alto 5% a < 10% | muy alto ≥ 10%" in a.motiu
    # >= 70 anys aparentment sans: text i classe propis; els punts segueixen la categoria
    r, a = alerta(76, 150)
    assert r.categoria_risc_cv in ("Alto", "Muy alto") and r.escala_usada == "SCORE2-OP"
    assert a.titol == ("Valorar tratamiento considerando fragilidad, polimedicación y preferencias del paciente "
                       "(clase IIb)")
    assert a.evidencia == "Clase IIb - ESC 2021" and a.pes == (35 if r.categoria_risc_cv == "Muy alto" else 20)


def test_punts_de_l_alerta_configurables(connector, config):
    config["rules"]["risc_cardiovascular"]["alertes"]["molt_alt"]["pes"] = 50
    r = per_nom(RiskEngine(connector, config), "Manuel Sánchez")
    assert next(a for a in r.alertes_actives if a.regla == "risc_cardiovascular").pes == 50


def test_objectius_de_tractament_figura_6(motor):
    def pacient(pas, ldl, meds):
        extres = [("pas", pas, "2026-09-10"), ("pad", 80, "2026-09-10"), ("colesterol_total", 230, "2026-09-10"),
                  ("hdl", 40, "2026-09-10"), ("ldl", ldl, "2026-09-10")]
        return motor.avalua_dades(_pacient(FGE_NORMAL, extres=extres, meds=meds, edat=66))

    estatina = [("Atorvastatina", "estatina", "2020-01-01")]
    base = pacient(128, 95, estatina)
    assert base.categoria_risc_cv in ("Alto", "Muy alto")
    objectiu = 70 if base.categoria_risc_cv == "Alto" else 55
    # Pas 1 assolit (PAS < 140, LDL < 100, amb estatina): ben tractat, cap alerta; el pas 2 és una acció
    assert base.ben_tractat and base.alertes_actives == []
    assert [a.clau for a in base.accions_recomanades] == ["ldl_intensificar"]
    assert f"objetivo < {objectiu} por riesgo" in base.accions_recomanades[0].text
    # LDL >= 100 o PAS >= 140: objectiu pendent i alerta
    ldl_alt = pacient(128, 112, estatina)
    assert "LDL 112 mg/dL (objetivo < 100)" in ldl_alt.objectius_pendents
    assert "risc_cardiovascular" in ldl_alt.regles_actives()
    pas_alta = pacient(146, 60, estatina)
    assert "PA 146/80 mmHg (objetivo < 140/90)" in pas_alta.objectius_pendents
    accio = next(a for a in pas_alta.accions_recomanades if a.clau == "pressio")
    assert "objetivo PAS < 140; < 130 si se tolera" in accio.text
    # Sense estatina: l'acció porta l'objectiu d'LDL de la seva categoria
    sense = pacient(128, 95, [])
    assert f"objetivo LDL < {objectiu} mg/dL" in next(a for a in sense.accions_recomanades if a.clau == "estatina").text


# --- Volant -----------------------------------------------------------------------------------

def test_volant_amb_peticions_i_sense(motor):
    antonio = per_nom(motor, "Antonio García")  # UACR pendent
    assert antonio.volant_auto.startswith("[CardioAlert AP")
    assert "Laboratorio:" in antonio.volant_auto and "UACR" in antonio.volant_auto
    assert "Motivo de la petición:" in antonio.volant_auto
    dolores = per_nom(motor, "Dolores Ruiz")  # possible IC
    assert "Interconsultas y pruebas:" in dolores.volant_auto and "ecocardiograma" in dolores.volant_auto
    assert per_nom(motor, "Francisco Jiménez").volant_auto == ""  # ben tractat: res a demanar
