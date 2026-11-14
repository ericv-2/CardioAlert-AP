"""API: cupo, fitxa i edició de rules.yaml (sempre sobre una còpia temporal de la configuració)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from api.main import create_app

ARREL = Path(__file__).resolve().parent.parent
CONFIG = ARREL / "config" / "rules.yaml"


@pytest.fixture()
def rules(tmp_path) -> Path:
    return Path(shutil.copy(CONFIG, tmp_path / "rules.yaml"))


@pytest.fixture()
def client(rules) -> TestClient:
    return TestClient(create_app(rules_path=rules))


def test_cupo_per_defecte(client):
    r = client.get("/api/cupo")
    assert r.status_code == 200
    cos = r.json()
    assert cos["meta"]["escala"] == "totes_dues" and cos["meta"]["font_usada"] == "local" and cos["meta"]["avis"] is None
    assert cos["meta"]["pacients_avui"] == 10 and cos["meta"]["guia_risc_cv"] == "ESC 2021"
    assert len(cos["pacients"]) == cos["kpis"]["total"] == 100
    k = cos["kpis"]
    # Categories de la taula 5 (ESC 2021) i grups de l'ordre de la llista: cap nivell ALT/MITJA/BAIX
    assert set(k["categories"]) == {"Bajo-moderado", "Alto", "Muy alto"}
    assert sum(k["categories"].values()) + k["sense_categoria"] == 100
    assert set(k["grups"]) == {"1", "2", "3", "4"} and sum(k["grups"].values()) == 100
    assert not {"alt", "mitja", "baix"} & set(k)
    ordre = [(p["grup_ordre"], -p["puntuacio_prioritat"]) for p in cos["pacients"]]
    assert ordre == sorted(ordre)
    p = cos["pacients"][0]
    assert {"escala_usada", "risc_cv_percentatge", "categoria_risc_cv", "rang_referencia_cv", "dades_creuades",
            "grup_ordre", "grup_ordre_text", "text_risc_cv", "regicor_referencia", "nota_calibracio", "resum",
            "alertes_actives"} <= set(p)
    assert "nota_clinica_auto" not in p and "nivell_risc" not in p
    assert p["grup_ordre"] == 1 and p["categoria_risc_cv"] in ("Bajo-moderado", "Alto", "Muy alto")
    creuats = [p["pacient_id"] for p in cos["pacients"] if p["dades_creuades"]]
    assert "P003" in creuats and k["dades_creuades"] == len(creuats)  # José Fernández: eCAP + DIRAYA


def test_cupo_amb_regicor_i_parametres_invalids(client):
    reg = client.get("/api/cupo", params={"scale": "regicor"}).json()
    assert reg["meta"]["escala"] == "regicor"
    assert {p["escala_usada"] for p in reg["pacients"]} == {"REGICOR", None}
    esc = client.get("/api/cupo", params={"scale": "score2"}).json()
    assert {p["escala_usada"] for p in esc["pacients"]} >= {"SCORE2", "SCORE2-OP", "SCORE2-Diabetes",
                                                           "SCORE2 + CKD Add-on", "SCORE2-OP + CKD Add-on"}
    assert client.get("/api/cupo", params={"scale": "framingham"}).status_code == 422
    assert client.get("/api/cupo", params={"source": "ftp"}).status_code == 422


def test_font_remota_sense_connector_torna_a_local_amb_avis(client):
    cos = client.get("/api/cupo", params={"source": "remote"}).json()
    assert (cos["meta"]["font_demanada"], cos["meta"]["font_usada"]) == ("remote", "local")
    assert "datos locales" in cos["meta"]["avis"] and len(cos["pacients"]) == 100


def test_font_remota_que_falla_torna_a_local_amb_avis(rules):
    def falla():
        raise TimeoutError("sin respuesta")
    cos = TestClient(create_app(rules_path=rules, remote_factory=falla)).get("/api/cupo?source=remote").json()
    assert cos["meta"]["font_usada"] == "local" and "sin respuesta" in cos["meta"]["avis"]
    assert len(cos["pacients"]) == 100


def test_fitxa_del_pacient(client):
    r = client.get("/api/pacientes/P003")
    assert r.status_code == 200
    cos = r.json()
    assert cos["pacient"]["nom"] == "José Fernández" and cos["pacient"]["nota_clinica_auto"].startswith("[CardioAlert AP")
    orígens = {a["origen"] for a in cos["analitiques"]}
    assert {"eCAP - Catalunya", "DIRAYA - Andalucía"} <= orígens
    assert all(a["data"] and a["codi_loinc"] for a in cos["analitiques"])
    assert len(cos["series"]["fge"]) >= 3 and {"data", "valor", "origen"} <= set(cos["series"]["fge"][0])
    assert any(m["origen"] == "DIRAYA - Andalucía" for m in cos["series"]["uacr"])
    assert cos["diagnostics"] and cos["medicacions"]
    assert cos["llindars"] == {"fge": 60, "uacr": 30}
    assert cos["pacient"]["volant_auto"] == ""  # sense peticions de laboratori ni interconsultes
    assert client.get("/api/pacientes/P001").json()["pacient"]["volant_auto"].startswith("[CardioAlert AP")
    assert client.get("/api/pacientes/P999").status_code == 404


def test_fitxa_marca_la_comunitat_habitual(client):
    cos = client.get("/api/pacientes/P003").json()
    assert cos["comunitat_habitual"] == "Catalunya"  # la de DIRAYA - Andalucía és la recuperada de fora
    assert cos["demografia"]["id"] == "P003" and cos["demografia"]["sexe"] == "H"


def test_rules_consulta(client):
    cos = client.get("/api/rules").json()
    assert cos["config"]["rules"]["risc_cardiovascular"]["escala_per_defecte"] == "totes_dues"
    assert {"rules.risc_cardiovascular.alertes.alt.pes", "rules.risc_cardiovascular.alertes.molt_alt.pes",
            "motor.prioritat.pacients_avui", "rules.possible_ic.pes"} <= {e["cami"] for e in cos["editables"]}
    camins = {e["cami"]: e for e in cos["editables"]}
    assert camins["rules.uacr_falta.max_mesos_sense_prova"]["valor"] == 12
    assert camins["rules.fge_descens.descens_anual_llindar"]["valor"] == 5.0
    assert camins["rules.risc_cardiovascular.talls_per_edat.1.alt"]["valor"] == 5
    assert cos["backups"] == 0


def test_rules_canvi_valid_fa_backup_i_recalcula(client, rules):
    original = rules.read_text(encoding="utf-8")
    abans = client.get("/api/cupo").json()["kpis"]
    r = client.post("/api/rules", json={"canvis": {"rules.uacr_falta.max_mesos_sense_prova": 48,
                                                   "rules.risc_cardiovascular.talls_per_edat.1.alt": 9.5}})
    assert r.status_code == 200, r.text
    cos = r.json()
    assert cos["canviats"]["rules.uacr_falta.max_mesos_sense_prova"] == {"abans": 12, "ara": 48}
    # Còpia de seguretat amb el contingut anterior, i el fitxer nou conserva els comentaris
    backup = rules.parent / "backups" / cos["backup"]
    assert backup.read_text(encoding="utf-8") == original and cos["backups"] == 1
    nou = rules.read_text(encoding="utf-8")
    assert "PENDENTS DE VALIDACIÓ PEL METGE" in nou and "# UACR" in nou
    cfg = yaml.safe_load(nou)
    assert cfg["rules"]["uacr_falta"]["max_mesos_sense_prova"] == 48
    assert cfg["rules"]["risc_cardiovascular"]["talls_per_edat"][1] == {"edat_max": 69, "alt": 9.5, "molt_alt": 10}
    assert cfg["motor"]["data_referencia"].isoformat() == "2026-11-13"
    # El cupo es recalcula a l'instant amb els llindars nous
    despres = client.get("/api/cupo").json()["kpis"]
    assert despres["uacr_pendent"] < abans["uacr_pendent"]
    assert despres["risc_cv_alt"] < abans["risc_cv_alt"]
    # Sense canvis reals no es fa cap backup nou
    r2 = client.post("/api/rules", json={"canvis": {"rules.uacr_falta.max_mesos_sense_prova": 48}}).json()
    assert r2["canviats"] == {} and r2["backup"] is None and r2["backups"] == 1


@pytest.mark.parametrize("canvis, cami_error", [
    ({"rules.uacr_falta.max_mesos_sense_prova": -3}, "rules.uacr_falta.max_mesos_sense_prova"),      # fora de rang
    ({"rules.uacr_falta.max_mesos_sense_prova": "doce"}, "rules.uacr_falta.max_mesos_sense_prova"),  # no és un número
    ({"rules.uacr_falta.max_mesos_sense_prova": True}, "rules.uacr_falta.max_mesos_sense_prova"),
    ({"rules.risc_cardiovascular.ckd_addon.enabled": 1}, "rules.risc_cardiovascular.ckd_addon.enabled"),
    ({"motor.guia": "Otra guía"}, "motor.guia"),                                                     # no editable
    ({"rules.uacr_falta.prova": "1234-5"}, "rules.uacr_falta.prova"),
    ({"rules.risc_cardiovascular.talls_per_edat.1.alt": 12}, "rules.risc_cardiovascular.talls_per_edat.1.molt_alt"),
    ({"rules.risc_cardiovascular.alertes.alt.pes": 40}, "rules.risc_cardiovascular.alertes.molt_alt.pes"),  # alt >= molt alt
    ({"motor.prioritat.pacients_avui": 0}, "motor.prioritat.pacients_avui"),
    ({}, "canvis"),
])
def test_rules_canvi_invalid_no_toca_el_fitxer(client, rules, canvis, cami_error):
    original = rules.read_text(encoding="utf-8")
    r = client.post("/api/rules", json={"canvis": canvis})
    assert r.status_code == 422
    assert cami_error in r.json()["detail"]["errors"]
    assert rules.read_text(encoding="utf-8") == original
    assert not (rules.parent / "backups").exists()


def test_punts_i_pacients_d_avui_editables(client):
    abans = client.get("/api/cupo").json()
    r = client.post("/api/rules", json={"canvis": {"rules.risc_cardiovascular.alertes.molt_alt.pes": 60,
                                                   "motor.prioritat.pacients_avui": 5}})
    assert r.status_code == 200, r.text
    despres = client.get("/api/cupo").json()
    assert despres["meta"]["pacients_avui"] == 5
    # Els punts canvien la puntuació, però no la categoria de risc ni el grup de cap pacient
    assert despres["kpis"]["categories"] == abans["kpis"]["categories"]
    assert despres["kpis"]["grups"] == abans["kpis"]["grups"]
    punts = lambda cos: {p["pacient_id"]: p["puntuacio_prioritat"] for p in cos["pacients"]}  # noqa: E731
    assert punts(despres)["P005"] == punts(abans)["P005"] + 25


# --- Cohorts i resultats en memòria ---------------------------------------------------------

def test_cohorts_disponibles(client):
    cohorts = {c["id"]: c for c in client.get("/api/cohorts").json()["cohorts"]}
    assert (cohorts["demo"]["pacients"], cohorts["demo"]["disponible"]) == (100, True)
    assert (cohorts["realista"]["pacients"], cohorts["realista"]["disponible"]) == (1500, True)
    assert cohorts["realista"]["fonts"] == ["local"]  # la cohort realista no es puja al servidor FHIR públic
    assert client.get("/api/cupo", params={"cohort": "inventada"}).status_code == 422


def test_cohort_realista_i_fitxa(client):
    cos = client.get("/api/cupo", params={"cohort": "realista"}).json()
    assert (cos["meta"]["cohort"], cos["meta"]["cohort_etiqueta"]) == ("realista", "Cupo realista (1.500)")
    assert len(cos["pacients"]) == cos["kpis"]["total"] == 1500
    k = cos["kpis"]
    assert sum(k["categories"].values()) + k["sense_categoria"] == 1500
    assert k["menors_edat_minima"] > 300 and k["falten_dades"] > 20 and k["mrc_no_diagnosticada"] > 50
    ordre = [(p["grup_ordre"], -p["puntuacio_prioritat"]) for p in cos["pacients"]]
    assert ordre == sorted(ordre)
    assert cos["pacients"][0]["pacient_id"].startswith("R")
    # La demo segueix sent la cohort per defecte i no es barreja amb la realista
    assert client.get("/api/cupo").json()["meta"]["cohort_etiqueta"] == "Demo (100)"
    primer = cos["pacients"][0]["pacient_id"]
    fitxa = client.get(f"/api/pacientes/{primer}", params={"cohort": "realista"}).json()
    assert fitxa["pacient"]["pacient_id"] == primer and fitxa["pacient"]["nota_clinica_auto"].startswith("[CardioAlert AP")
    assert fitxa["analitiques"] and fitxa["series"]["fge"]
    assert client.get("/api/pacientes/P003", params={"cohort": "realista"}).status_code == 404
    assert client.get(f"/api/pacientes/{primer}").status_code == 404  # no és a la demo
    card = client.post("/cds-services/cardioalert-patient-view", params={"cohort": "realista"},
                       json={"hook": "patient-view", "hookInstance": "x", "context": {"patientId": primer}}).json()["cards"][0]
    assert card["indicator"] == "critical"  # el primer de la llista té una alerta urgent
    excel = client.get("/api/export/excel", params={"cohort": "realista"})
    assert excel.status_code == 200 and len(excel.content) > 200_000


def test_el_cupo_es_calcula_un_sol_cop_i_es_guarda_en_memoria(client, monkeypatch):
    from engine import RiskEngine

    crides = []
    original = RiskEngine.avalua_cupo
    monkeypatch.setattr(RiskEngine, "avalua_cupo", lambda self: crides.append(1) or original(self))
    primera = client.get("/api/cupo", params={"cohort": "realista"}).json()
    assert primera["meta"]["en_memoria"] is False and primera["meta"]["segons_calcul"] > 0
    for _ in range(3):
        cos = client.get("/api/cupo", params={"cohort": "realista"}).json()
        assert cos["meta"]["en_memoria"] is True and cos["pacients"] == primera["pacients"]
    client.get("/api/pacientes/R0001", params={"cohort": "realista"})
    client.get("/api/export/excel", params={"cohort": "realista"})
    assert len(crides) == 1  # fitxa, Excel i llista surten del mateix càlcul
    # Un canvi a rules.yaml invalida el que hi ha guardat (el desament ja avalua la demo per validar-lo)
    crides.clear()
    assert client.post("/api/rules", json={"canvis": {"motor.prioritat.pacients_avui": 7}}).status_code == 200
    crides.clear()
    cos = client.get("/api/cupo", params={"cohort": "realista"}).json()
    assert cos["meta"]["en_memoria"] is False and cos["meta"]["pacients_avui"] == 7 and len(crides) == 1


def test_cohort_realista_nomes_en_local(client):
    cos = client.get("/api/cupo", params={"cohort": "realista", "source": "remote"}).json()
    assert (cos["meta"]["cohort"], cos["meta"]["font_usada"]) == ("realista", "local")
    assert "solo está disponible en local" in cos["meta"]["avis"] and len(cos["pacients"]) == 1500


def test_cohort_realista_sense_generar_torna_a_la_demo(rules, tmp_path):
    client = TestClient(create_app(rules_path=rules, dades_realista=tmp_path / "no_hi_es"))
    cohorts = {c["id"]: c for c in client.get("/api/cohorts").json()["cohorts"]}
    assert cohorts["realista"]["disponible"] is False
    cos = client.get("/api/cupo", params={"cohort": "realista"}).json()
    assert cos["meta"]["cohort"] == "demo" and "generate_patients.py --perfil realista" in cos["meta"]["avis"]
    assert len(cos["pacients"]) == 100
