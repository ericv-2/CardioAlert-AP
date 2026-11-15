"""Actualització per esdeveniment i registre d'activitat (docs/decisions.md §17).

Amb el servidor FHIR REAL del simulador (Node): escriptura d'analítiques i pacients, Subscription R4 Backport,
notificació a /api/notificaciones (idempotència per meta.versionId, agrupació de notificacions seguides, salt
d'esdeveniments), substitució al cupo en llegir la fitxa o la targeta, i el registre AuditEvent.
Les notificacions que envia l'estació les recull un receptor HTTP local i el test les passa a l'add-on.
"""
from __future__ import annotations

import base64
import json
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import create_app

ARREL = Path(__file__).resolve().parents[1]
TEMA = "http://estacion-simulada.local/SubscriptionTopic/observacion-nueva-cupo"
CARMEN = {"id": "Practitioner/sim-0001", "nom": "Dra. Carmen Soler", "rol": "Medicina de familia"}
LAUNCH = base64.urlsafe_b64encode(json.dumps({
    "patient": None, "intent": "lista-trabajo", "fhirUser": CARMEN["id"],
    "practitioner": {"name": CARMEN["nom"], "role": CARMEN["rol"]}}).encode()).decode().rstrip("=")


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def estacio():
    """Una estació nova a cada test (el que s'hi escriu viu en memòria)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js no está instalado: no se puede arrancar el servidor FHIR del simulador")
    port = _port()
    proces = subprocess.Popen([node, str(ARREL / "simulador" / "servidor-fhir.js"), "--port", str(port), "--host", "127.0.0.1"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}/fhir"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/metadata", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            pytest.fail("El servidor FHIR del simulador no arranca")
        yield base
    finally:
        proces.terminate()
        proces.wait(timeout=10)


@pytest.fixture()
def receptor():
    """Fa de /api/notificaciones de l'add-on per a l'estació: desa els Bundles que rep."""
    rebuts: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            rebuts.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    servidor = HTTPServer(("127.0.0.1", _port()), Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_port}/api/notificaciones", rebuts
    servidor.shutdown()


def _app(estacio, tmp_path, retard=0.0):
    rules = shutil.copy(ARREL / "config" / "rules.yaml", tmp_path / "rules.yaml")
    app = create_app(rules_path=rules, url_fhir=estacio, fhir_permesos=r"http://127\.0\.0\.1:\d+/fhir",
                     dir_estats=tmp_path / "estats", retard_notificacions=retard)
    return TestClient(app), app


def _subscriu(estacio, endpoint) -> dict:
    r = httpx.post(f"{estacio}/Subscription", json={
        "resourceType": "Subscription", "status": "requested", "reason": "CardioAlert AP", "criteria": TEMA,
        "channel": {"type": "rest-hook", "endpoint": endpoint, "payload": "application/fhir+json"}})
    assert r.status_code == 201 and r.json()["status"] == "active"
    return r.json()


def _analitica(estacio, pid, loinc="9318-7", valor=450, unitat="mg/g", origen="DIRAYA - Andalucía") -> dict:
    r = httpx.post(f"{estacio}/Observation", json={
        "resourceType": "Observation", "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc}], "text": "Cociente albúmina/creatinina en orina"},
        "subject": {"reference": f"Patient/{pid}"}, "valueQuantity": {"value": valor, "unit": unitat},
        "performer": [{"display": origen}]})
    assert r.status_code == 201, r.text
    return r.json()


def _espera(rebuts, n):
    for _ in range(100):
        if len(rebuts) >= n:
            return rebuts[:n]
        time.sleep(0.05)
    pytest.fail(f"La estación no ha enviado {n} notificaciones (ha enviado {len(rebuts)})")


def _activitat(client, **filtres):
    return client.get("/api/actividad", params=filtres).json()


def _estat(client, pid, estat):
    r = client.post(f"/api/pacientes/{pid}/estado", json={"estat": estat, "professional": CARMEN})
    assert r.status_code == 200, r.text


# --- Escriptura a l'estació --------------------------------------------------------------------

def test_escriptura_analitica_i_pacient_nou(estacio):
    grup = httpx.get(f"{estacio}/Group").json()["entry"][0]["resource"]
    obs = _analitica(estacio, "P003")
    assert obs["effectiveDateTime"] == "2026-11-13"  # el "hoy" de la simulació = data de referència del motor
    assert obs["meta"]["versionId"] == "1" and obs["subject"] == {"reference": "Patient/P003"}
    grup2 = httpx.get(f"{estacio}/Group").json()["entry"][0]["resource"]
    assert grup2["meta"]["versionId"] != grup["meta"]["versionId"] and grup2["quantity"] == 100
    historia = httpx.get(f"{estacio}/Patient/P003/$everything").json()
    assert historia["entry"][-1]["resource"]["id"] == obs["id"]
    # Errors de validació (OperationOutcome)
    assert httpx.post(f"{estacio}/Observation", json={"resourceType": "Observation", "subject": {"reference": "Patient/P999"}}).status_code == 422
    # Pacient nou: entra al Group (cupo) i es pot llegir
    nou = httpx.post(f"{estacio}/Patient", json={"resourceType": "Patient", "name": [{"given": ["Ana"], "family": "Nueva Prueba"}],
                                                 "gender": "female", "birthDate": "1961-03-02"}).json()
    assert nou["id"] == "P101"
    assert httpx.get(f"{estacio}/Group").json()["entry"][0]["resource"]["quantity"] == 101
    assert httpx.get(f"{estacio}/Patient/P101/$everything").status_code == 200


def test_pacient_nou_entra_al_cupo_a_la_seguent_actualitzacio(estacio, tmp_path):
    client, _ = _app(estacio, tmp_path)
    assert len(client.get("/api/cupo").json()["pacients"]) == 100
    httpx.post(f"{estacio}/Patient", json={"resourceType": "Patient", "name": [{"given": ["Ana"], "family": "Nueva"}],
                                           "gender": "female", "birthDate": "1961-03-02"})
    cos = client.get("/api/cupo").json()
    assert len(cos["pacients"]) == 101 and "P101" in {p["pacient_id"] for p in cos["pacients"]}
    lectures = _activitat(client, tipo="lectura-cupo")["entrades"]
    assert len(lectures) == 2 and "Cambio de cupo o de pacientes" in lectures[0]["detall"]


# --- Notificació (Subscription) i recàlcul -----------------------------------------------------

def test_flux_complet_revisat_uacr_nou_torna_a_hoy(estacio, receptor, tmp_path):
    endpoint, rebuts = receptor
    client, _ = _app(estacio, tmp_path)
    abans = client.get("/api/cupo").json()
    pid = "P001"
    _estat(client, pid, "revisat")
    assert pid not in client.get("/api/estados").json()["llista_avui"]
    versio = client.get("/api/estados").json()["versio_cupo"]
    _subscriu(estacio, endpoint)
    obs = _analitica(estacio, pid)
    [notificacio] = _espera(rebuts, 1)
    r = client.post("/api/notificaciones", json=notificacio).json()
    assert r["eventos"] == [{"evento": "1", "paciente": pid, "duplicada": False, "recalculo": "hecho"}]
    estats = client.get("/api/estados").json()
    assert estats["estats"].get(pid) is None  # torna a «Pendiente» (alerta nova)
    assert pid in estats["llista_avui"] and estats["versio_cupo"] != versio
    # La llista té la dada nova i el seu origen, sense tornar a exportar el cupo
    cos = client.get("/api/cupo").json()
    fila = next(p for p in cos["pacients"] if p["pacient_id"] == pid)
    assert "derivacio_nefrologia" in {a["regla"] for a in fila["alertes_actives"]}
    assert fila["uacr_actual"] == 450 and "DIRAYA - Andalucía" in fila["fonts_dades"]
    assert len(_activitat(client, tipo="lectura-cupo")["entrades"]) == 1
    assert cos["meta"]["calculat_a"] == abans["meta"]["calculat_a"]
    fitxa = client.get(f"/api/pacientes/{pid}").json()
    assert any(a["data"] == "2026-11-13" and a["valor"] == 450 and a["origen"] == "DIRAYA - Andalucía" for a in fitxa["analitiques"])
    # Registre: notificació, recàlcul i tornada a pendent amb l'add-on com a autor
    tipus = [e["tipus"] for e in _activitat(client, paciente=pid)["entrades"]]
    assert {"notificacion", "recalculo", "cambio-estado"} <= set(tipus)
    tornada = next(e for e in _activitat(client, paciente=pid, tipo="cambio-estado")["entrades"])
    assert tornada["automatic"] and "Revisado → Pendiente" in tornada["detall"] and "derivacio_nefrologia" in tornada["detall"]
    assert obs["id"] in next(e for e in _activitat(client, tipo="notificacion")["entrades"])["detall"]


def test_la_mateixa_alerta_no_torna_a_pendiente(estacio, receptor, tmp_path):
    endpoint, rebuts = receptor
    client, _ = _app(estacio, tmp_path)
    client.get("/api/cupo")
    _subscriu(estacio, endpoint)
    _analitica(estacio, "P001")
    client.post("/api/notificaciones", json=_espera(rebuts, 1)[0])
    _estat(client, "P001", "revisat")  # revisat ja amb l'alerta nova
    _analitica(estacio, "P001", valor=460)  # una altra analítica: les mateixes alertes
    client.post("/api/notificaciones", json=_espera(rebuts, 2)[1])
    assert client.get("/api/estados").json()["estats"]["P001"]["estat"] == "revisat"


def test_idempotencia_i_agrupacio(estacio, receptor, tmp_path):
    endpoint, rebuts = receptor
    client, app = _app(estacio, tmp_path, retard=60)  # la cua no es buida sola durant el test
    client.get("/api/cupo")
    _subscriu(estacio, endpoint)
    for valor in (450, 470, 480):
        _analitica(estacio, "P001", valor=valor)
    notificacions = _espera(rebuts, 3)
    for n in notificacions:
        assert client.post("/api/notificaciones", json=n).json()["eventos"][0]["recalculo"] == "programado"
    # La mateixa notificació repetida (mateix focus amb _history): no es torna a recalcular
    repetida = client.post("/api/notificaciones", json=notificacions[0]).json()["eventos"][0]
    assert repetida["duplicada"] and repetida["recalculo"] is None
    app.state.cua_recalculs.buida()
    recalculs = _activitat(client, tipo="recalculo")["entrades"]
    assert len(recalculs) == 1 and "3 notificaciones agrupadas" in recalculs[0]["detall"]
    assert len(_activitat(client, tipo="notificacion")["entrades"]) == 4
    fila = next(p for p in client.get("/api/cupo").json()["pacients"] if p["pacient_id"] == "P001")
    assert fila["uacr_actual"] == 480  # el recàlcul té les tres analítiques
    assert len(_activitat(client, tipo="lectura-cupo")["entrades"]) == 1  # sense tornar a exportar


def test_un_esdeveniment_perdut_torna_a_exportar_el_cupo(estacio, receptor, tmp_path):
    endpoint, rebuts = receptor
    client, _ = _app(estacio, tmp_path)
    client.get("/api/cupo")
    _subscriu(estacio, endpoint)
    _analitica(estacio, "P001")
    _analitica(estacio, "P002")
    primera, segona = _espera(rebuts, 2)
    client.post("/api/notificaciones", json=primera)
    # L'add-on no rep la segona: la tercera arriba amb un salt a event-number (i porta la versió del Group
    # d'ara, que sense el salt donaria el cupo per vist)
    _analitica(estacio, "P003")
    tercera = _espera(rebuts, 3)[2]
    client.post("/api/notificaciones", json=tercera)
    cos = client.get("/api/cupo").json()
    assert len(_activitat(client, tipo="lectura-cupo")["entrades"]) == 2
    assert next(p for p in cos["pacients"] if p["pacient_id"] == "P002")["uacr_actual"] == 450


def test_notificacions_rebutjades(estacio, tmp_path):
    client, _ = _app(estacio, tmp_path)
    assert client.post("/api/notificaciones", json={"resourceType": "Bundle"}).status_code == 400
    forana = {"resourceType": "Bundle", "type": "history", "entry": [{"resource": {"resourceType": "Parameters", "parameter": [
        {"name": "subscription", "valueReference": {"reference": "http://malicioso.example/fhir/Subscription/x"}},
        {"name": "type", "valueCode": "event-notification"}]}}]}
    assert client.post("/api/notificaciones", json=forana).status_code == 403  # només estacions permeses


def test_desinstal_lar_esborra_la_subscription(estacio, receptor):
    sub = _subscriu(estacio, receptor[0])
    assert httpx.get(f"{estacio}/Subscription").json()["total"] == 1
    assert httpx.delete(f"{estacio}/Subscription/{sub['id']}").status_code == 204
    assert httpx.get(f"{estacio}/Subscription").json()["total"] == 0
    _analitica(estacio, "P003")
    time.sleep(0.3)
    assert receptor[1] == []  # sense subscripció, cap notificació


# --- Actualitzar en cada lectura ---------------------------------------------------------------

def test_la_fitxa_i_la_targeta_actualitzen_el_cupo(estacio, tmp_path):
    client, _ = _app(estacio, tmp_path)
    client.get("/api/cupo")
    versio = client.get("/api/estados").json()["versio_cupo"]
    _analitica(estacio, "P001")  # sense subscripció: l'add-on no se n'assabenta fins que llegeix el pacient
    client.get("/api/pacientes/P001")
    estats = client.get("/api/estados").json()
    assert estats["versio_cupo"] != versio
    fila = next(p for p in client.get("/api/cupo").json()["pacients"] if p["pacient_id"] == "P001")
    assert fila["uacr_actual"] == 450 and fila["grup_ordre"] == 1
    _analitica(estacio, "P002")
    client.post("/cds-services/cardioalert-patient-view", json={
        "hook": "patient-view", "hookInstance": "x", "fhirServer": estacio, "context": {"userId": CARMEN["id"], "patientId": "P002"}})
    fila = next(p for p in client.get("/api/cupo").json()["pacients"] if p["pacient_id"] == "P002")
    assert fila["uacr_actual"] == 450
    # Llegir una fitxa sense dades noves no canvia el cupo
    versio = client.get("/api/estados").json()["versio_cupo"]
    client.get("/api/pacientes/P050")
    assert client.get("/api/estados").json()["versio_cupo"] == versio


# --- Registre d'activitat ----------------------------------------------------------------------

def test_registre_d_activitat_audit_event(estacio, tmp_path):
    client, _ = _app(estacio, tmp_path)
    client.get("/api/cupo")
    client.get("/api/pacientes/P003", params={"launch": LAUNCH})
    client.post("/cds-services/cardioalert-patient-view", json={
        "hook": "patient-view", "hookInstance": "x", "fhirServer": estacio, "context": {"userId": CARMEN["id"], "patientId": "P003"}})
    client.post("/api/pacientes/P003/recalcular", params={"launch": LAUNCH})
    client.get("/api/export/excel", params={"launch": LAUNCH})
    client.get("/api/export/pruebas-pendientes", params={"launch": LAUNCH, "formato": "csv"})
    _estat(client, "P003", "citat")
    r = client.post("/api/rules", params={"launch": LAUNCH}, json={"canvis": {"rules.uacr_falta.max_mesos_sense_prova": 18}})
    assert r.status_code == 200
    tot = _activitat(client)
    tipus = [e["tipus"] for e in tot["entrades"]]
    assert set(tipus) == {"lectura-cupo", "consulta-ficha", "cds-hook", "recalculo", "exportacion", "cambio-estado",
                          "cambio-parametros"}
    assert {t["id"] for t in tot["tipus"]} >= set(tipus)
    # Qui: el professional del llançament (la targeta CDS només porta el userId, i se'n mostra el nom)
    assert {e["qui"] for e in tot["entrades"] if not e["automatic"]} == {"Dra. Carmen Soler"}
    assert next(e for e in tot["entrades"] if e["tipus"] == "lectura-cupo")["qui"] == "CardioAlert AP (automático)"
    assert next(e for e in tot["entrades"] if e["tipus"] == "cambio-parametros")["detall"].startswith(
        "rules.uacr_falta.max_mesos_sense_prova: ")
    # Filtres
    assert {e["tipus"] for e in _activitat(client, paciente="P003")["entrades"]} == {
        "consulta-ficha", "cds-hook", "recalculo", "cambio-estado"}
    assert _activitat(client, profesional=CARMEN["id"])["total"] == len([e for e in tot["entrades"] if not e["automatic"]])
    assert _activitat(client, tipo="exportacion")["total"] == 2
    # Estructura FHIR AuditEvent
    bundle = client.get("/api/actividad", params={"formato": "fhir", "tipo": "consulta-ficha"}).json()
    [ae] = [e["resource"] for e in bundle["entry"]]
    assert ae["resourceType"] == "AuditEvent" and ae["action"] == "R" and ae["recorded"]
    assert ae["agent"][0]["who"] == {"reference": CARMEN["id"], "display": CARMEN["nom"]} and ae["agent"][0]["requestor"]
    assert ae["entity"][0]["what"] == {"reference": "Patient/P003"}
    assert ae["source"]["site"] == estacio and ae["source"]["observer"]["display"] == "Estación clínica simulada"
    assert ae["subtype"][0]["code"] == "consulta-ficha"
