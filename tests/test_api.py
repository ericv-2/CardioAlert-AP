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
    assert cos["meta"]["escala"] == "score2" and cos["meta"]["font_usada"] == "local" and cos["meta"]["avis"] is None
    assert len(cos["pacients"]) == cos["kpis"]["total"] == 100
    k = cos["kpis"]
    assert k["alt"] + k["mitja"] + k["baix"] == 100
    punts = [p["puntuacio_prioritat"] for p in cos["pacients"]]
    assert punts == sorted(punts, reverse=True)
    p = cos["pacients"][0]
    assert {"escala_usada", "risc_cv_percentatge", "categoria_risc_cv", "rang_referencia_cv", "dades_creuades",
            "nivell_risc", "resum", "alertes_actives"} <= set(p)
    assert "nota_clinica_auto" not in p
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
    assert cos["config"]["rules"]["risc_cardiovascular"]["escala_per_defecte"] == "score2"
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
    ({"motor.prioritat.nivell_mitja": 40}, "motor.prioritat.nivell_mitja"),                          # >= nivell_alt
    ({}, "canvis"),
])
def test_rules_canvi_invalid_no_toca_el_fitxer(client, rules, canvis, cami_error):
    original = rules.read_text(encoding="utf-8")
    r = client.post("/api/rules", json={"canvis": canvis})
    assert r.status_code == 422
    assert cami_error in r.json()["detail"]["errors"]
    assert rules.read_text(encoding="utf-8") == original
    assert not (rules.parent / "backups").exists()
