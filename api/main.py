"""API de CardioAlert AP (FastAPI).

    uvicorn api.main:app --reload --port 8000        # docs interactives a http://localhost:8000/docs

Endpoints (tots accepten `cohort=demo|realista`, `source=local|remote` i `scale=totes_dues|score2|regicor`):
    GET  /api/cohorts                                         cohorts disponibles ("Demo (100)", "Cupo realista (1.500)")
    GET  /api/cupo                                            KPIs + cupo avaluat en l'ordre de la llista de treball
    GET  /api/pacientes/{id}                                  fitxa: resultat, històric amb origen i sèries renals
    GET  /api/export/excel                                    descàrrega del cupo complet en .xlsx
    GET  /api/rules, POST /api/rules                          consulta i ajust dels llindars de rules.yaml
    GET  /cds-services                                        CDS Hooks: discovery (anuncia també la interfície)
    POST /cds-services/cardioalert-patient-view               CDS Hooks: targeta del hook patient-view

L'API no té lògica clínica: tot surt del motor (`engine/`) i de `config/rules.yaml`. Cada cupo s'avalua UN
sol cop i es guarda en memòria (resultats i JSON ja serialitzat); només es torna a calcular si canvia
`rules.yaml` (es compara el contingut a cada petició), la cohort, la font o l'escala.

Aquesta API és l'ADD-ON: no depèn de cap estació clínica. La interfície (frontend/) corre al seu propi port;
la seva URL s'anuncia al discovery (variable d'entorn CARDIOALERT_UI_URL, per defecte http://localhost:5173).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from fastapi import Body, FastAPI, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from connectors import Connector, CsvConnector, FhirConnector, FhirRemoteConnector
from engine import ResultatPacient, RiskEngine
from engine.__main__ import meta_avaluacio, recompte
from engine.export_excel import bytes_cupo
from engine.risk_engine import ARREL, CONFIG_DEFECTE, GRUPS_ORDRE, NOM_EQUACIO

from . import cds_hooks
from .rules_store import ErrorValidacio, RulesStore

DADES_LOCALS = ARREL / "simulador" / "datos" / "demo" / "fhir"
DADES_REALISTA = ARREL / "simulador" / "datos" / "realista" / "csv"  # cohort realista: només local, mai al servidor remot
Font = Literal["local", "remote"]
Escala = Literal["score2", "regicor", "totes_dues"]
Cohort = Literal["demo", "realista"]
ETIQUETA_FONT = {"local": "Local (eCAP / DIRAYA Demo)", "remote": "Servidor FHIR remoto"}
ETIQUETA_COHORT = {"demo": "Demo", "realista": "Cupo realista"}
SEGONS_ENTRE_REINTENTS = 60  # després d'una fallada del servidor remot no s'hi torna fins passat aquest temps
ORDRE_GENERAR = "python scripts/generate_patients.py --perfil realista --n 1500"
URL_INTERFICIE = "http://localhost:5173"  # on corre la interfície de l'add-on si no es diu res més


def _kpis(cupo: list[ResultatPacient]) -> dict:
    regles = Counter(regla for r in cupo for regla in r.regles_actives())
    return {
        "total": len(cupo),
        **recompte(cupo),  # categories (taula 5 ESC 2021), sense categoria i grups de l'ordre de la llista
        "alertes": sum(len(r.alertes_actives) for r in cupo),
        "mrc_no_diagnosticada": regles["mrc_no_diagnosticada"],
        "uacr_pendent": regles["uacr_falta"],
        "risc_cv_alt": sum(bool(r.risc_cv and r.risc_cv["categoria"] in ("alt", "molt_alt")) for r in cupo),
        "risc_cv_infratractat": regles["risc_cardiovascular"],
        "ben_tractats": sum(r.ben_tractat for r in cupo),
        "dades_creuades": sum(r.dades_creuades for r in cupo),
        "fonts": sorted({f for r in cupo for f in r.fonts_dades}),
        "per_regla": dict(regles),
    }


@dataclass
class Avaluacio:
    """Un cupo ja avaluat, guardat en memòria."""

    motor: RiskEngine
    resultats: list[ResultatPacient]  # en l'ordre de la llista de treball
    per_id: dict[str, ResultatPacient]
    json_cos: bytes  # '"kpis": {...}, "pacients": [...]' ja serialitzat (el que més triga a generar)
    segons_calcul: float


def create_app(rules_path: str | Path = CONFIG_DEFECTE, dades_locals: str | Path = DADES_LOCALS,
               remote_factory: Callable[[], Connector] | None = None, remot_public: bool = False,
               dades_realista: str | Path = DADES_REALISTA, url_interficie: str | None = None) -> FastAPI:
    """remote_factory: funció que retorna el connector remot (pot fallar o trigar: llavors es fa servir
    el local i la resposta porta un avís). remot_public=True: si no es passa cap factory, es fa servir el
    servidor públic de HAPI (FhirRemoteConnector). dades_realista: carpeta CSV de la cohort realista.
    url_interficie: URL de la interfície de l'add-on que s'anuncia al discovery de CDS Hooks i a l'enllaç
    de la targeta (per defecte, CARDIOALERT_UI_URL o http://localhost:5173; cadena buida = no s'anuncia)."""
    if url_interficie is None:
        url_interficie = os.environ.get("CARDIOALERT_UI_URL", URL_INTERFICIE)
    url_interficie = url_interficie.strip().rstrip("/")
    app = FastAPI(title="CardioAlert AP", version="1.1",
                  description="Cribado cardiorrenal-metabólico pasivo para Atención Primaria (datos sintéticos).")
    app.add_middleware(CORSMiddleware, allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
                       allow_methods=["GET", "POST"], allow_headers=["*"], expose_headers=["Content-Disposition"])
    app.add_middleware(GZipMiddleware, minimum_size=20_000)  # el cupo realista són uns quants MB de JSON
    store = RulesStore(rules_path)
    local = FhirConnector(dades_locals)
    dades_realista = Path(dades_realista)
    if remote_factory is None and remot_public:
        def remote_factory() -> Connector:
            return FhirRemoteConnector(data_referencia=store.carrega()["motor"].get("data_referencia"))
    estat: dict = {"remot": None, "avis": None, "fallada": None, "realista": None}
    memoria: dict = {"empremta": None, "avaluacions": {}}
    pany = threading.Lock()  # una sola descàrrega i un sol càlcul encara que arribin peticions alhora

    def hi_ha_realista() -> bool:
        return (dades_realista / "patients.csv").is_file()

    def connector(font: Font, cohort: Cohort) -> tuple[Connector, str, str, str | None]:
        """Retorna (connector, cohort usada, font usada, avís). El remot es descarrega un cop i es desa en
        memòria; si falla o tarda massa, es torna a les dades locals amb un avís. La cohort realista només
        existeix en local."""
        if cohort == "realista":
            if not hi_ha_realista():
                return local, "demo", "local", (f"La cohorte realista no está generada (ejecute `{ORDRE_GENERAR}`): "
                                                "se muestra la cohorte demo.")
            with pany:
                if estat["realista"] is None:
                    estat["realista"] = CsvConnector(dades_realista)
            avis = ("La cohorte realista solo está disponible en local (no se sube al servidor FHIR público)."
                    if font == "remote" else None)
            return estat["realista"], "realista", "local", avis
        if font == "local":
            return local, "demo", "local", None
        if remote_factory is None:
            return local, "demo", "local", "El conector FHIR remoto no está configurado: se muestran los datos locales."
        with pany:
            recent = estat["fallada"] is not None and time.monotonic() - estat["fallada"] < SEGONS_ENTRE_REINTENTS
            if estat["remot"] is None and not recent:
                try:
                    estat["remot"] = remote_factory()
                except Exception as exc:
                    estat["fallada"] = time.monotonic()
                    estat["avis"] = (f"No se pudo leer el servidor FHIR remoto ({type(exc).__name__}: {exc}). "
                                     "Se muestran los datos locales.")
            if estat["remot"] is None:
                return local, "demo", "local", estat["avis"]
        return estat["remot"], "demo", "remote", None

    def avaluacio(font: Font, escala: Escala | None, cohort: Cohort) -> tuple[Avaluacio, dict]:
        """El cupo avaluat (de la memòria si ja s'havia calculat amb aquesta configuració) i el `meta`."""
        inici = time.perf_counter()
        con, cohort_usada, font_usada, avis = connector(font, cohort)
        text = store.cami.read_bytes()
        empremta = hashlib.sha1(text).hexdigest()
        with pany:
            if memoria["empremta"] != empremta:  # rules.yaml ha canviat: res del que hi ha guardat serveix
                memoria.update(empremta=empremta, avaluacions={})
            clau = (cohort_usada, font_usada, escala)
            av = memoria["avaluacions"].get(clau)
            en_memoria = av is not None
            if av is None:
                m = RiskEngine(con, store.carrega(), escala=escala)
                resultats = m.avalua_cupo()
                pacients = []
                for r in resultats:
                    fila = r.to_dict()
                    del fila["nota_clinica_auto"], fila["volant_auto"]  # nota i volant només viatgen a la fitxa
                    pacients.append(fila)
                cos = json.dumps(jsonable_encoder({"kpis": _kpis(resultats), "pacients": pacients}),
                                 ensure_ascii=False, separators=(",", ":"))[1:-1].encode("utf-8")
                av = Avaluacio(m, resultats, {r.pacient_id: r for r in resultats}, cos,
                               round(time.perf_counter() - inici, 3))
                memoria["avaluacions"][clau] = av
        m = av.motor
        local_text = ETIQUETA_FONT[font_usada] if cohort_usada == "demo" else "Local (cupo realista sintético)"
        meta = {"font_demanada": font, "font_usada": font_usada, "font_etiqueta": local_text, "avis": avis,
                "cohort_demanada": cohort, "cohort": cohort_usada,
                "cohort_etiqueta": f"{ETIQUETA_COHORT[cohort_usada]} ({len(av.resultats):,})".replace(",", "."),
                "escala": m.escala, "data_referencia": m.avui.isoformat(), "guia": m.motor["guia"],
                "guia_risc_cv": m.regles["risc_cardiovascular"].get("guia"),
                "pacients_avui": m.motor["prioritat"].get("pacients_avui", 10),
                "grups_ordre": GRUPS_ORDRE,
                "equacio_fge": NOM_EQUACIO.get(m.nom_equacio, m.nom_equacio),
                "en_memoria": en_memoria, "segons_calcul": av.segons_calcul}
        return av, meta

    def resultat(av: Avaluacio, pacient_id: str) -> ResultatPacient:
        try:
            return av.per_id[pacient_id]
        except KeyError:
            raise HTTPException(404, f"Paciente {pacient_id} no encontrado") from None

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/cohorts")
    def cohorts() -> dict:
        """Cohorts que es poden triar. La realista només hi és si s'ha generat (i només en local)."""
        n_realista = None
        if hi_ha_realista():
            with (dades_realista / "patients.csv").open(encoding="utf-8") as f:
                n_realista = sum(1 for _ in f) - 1
        return {"cohorts": [
            {"id": "demo", "nom": ETIQUETA_COHORT["demo"], "pacients": len(local.get_patients()), "disponible": True,
             "fonts": ["local", "remote"], "descripcio": "100 pacientes sintéticos con los 8 casos trampa"},
            {"id": "realista", "nom": ETIQUETA_COHORT["realista"], "pacients": n_realista,
             "disponible": n_realista is not None, "fonts": ["local"],
             "descripcio": "Cupo sintético calibrado con prevalencias reales (REGICOR y ENRICA); solo en local"},
        ]}

    @app.get("/api/cupo")
    def cupo(source: Font = "local", scale: Escala | None = Query(None, description="Per defecte, la de rules.yaml"),
             cohort: Cohort = "demo") -> Response:
        av, meta = avaluacio(source, scale, cohort)
        cap = json.dumps({"meta": meta}, ensure_ascii=False, separators=(",", ":"))[:-1].encode("utf-8")
        return Response(cap + b"," + av.json_cos + b"}", media_type="application/json")

    @app.get("/api/pacientes/{pacient_id}")
    def pacient(pacient_id: str, source: Font = "local", scale: Escala | None = None, cohort: Cohort = "demo") -> dict:
        av, meta = avaluacio(source, scale, cohort)
        res = resultat(av, pacient_id)
        m = av.motor
        d = m.connector.get_patient_data(pacient_id)
        return {
            "meta": meta,
            "pacient": res.to_dict(),
            "diagnostics": d.diagnostics,
            "medicacions": d.medicacions,
            "analitiques": d.analitiques,  # històric complet, cada registre amb el seu origen
            "demografia": d.pacient,
            # Un origen "Sistema - Comunitat" d'una altra comunitat és un informe recuperat de fora
            "comunitat_habitual": cds_hooks.comunitat_habitual(d),
            "series": m.series_renals(d),
            # Llindars de rules.yaml que la gràfica dibuixa com a línies de referència
            "llindars": {"fge": m.regles["mrc_no_diagnosticada"]["fge_llindar"],
                         "uacr": m.regles["mrc_no_diagnosticada"]["uacr_llindar"]},
        }

    @app.get("/api/export/excel")
    def excel(source: Font = "local", scale: Escala | None = None, cohort: Cohort = "demo") -> Response:
        """Descarrega el cupo complet (totes les columnes, textos sencers) en .xlsx."""
        av, meta = avaluacio(source, scale, cohort)
        info = meta_avaluacio(av.motor, meta["font_etiqueta"])
        info["Cohorte"] = meta["cohort_etiqueta"]
        if meta["avis"]:
            info["Aviso de la fuente"] = meta["avis"]
        return Response(
            bytes_cupo(av.resultats, info),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="cupo_evaluado.xlsx"'})

    @app.get("/api/rules")
    def rules() -> dict:
        config = store.carrega()
        return {"config": config, "editables": store.editables(config), "backups": len(store.backups())}

    @app.post("/api/rules")
    def desa_rules(canvis: dict = Body(..., embed=True, examples=[{"rules.uacr_falta.max_mesos_sense_prova": 18}])) -> dict:
        """Cos: {"canvis": {"<camí>": <valor>, ...}}. Només els paràmetres de `editables`."""
        def prova(config: dict) -> None:
            for escala in ("totes_dues", "regicor"):
                RiskEngine(local, config, escala=escala).avalua_cupo()
        try:
            resultat_desa = store.aplica(canvis, prova)
        except ErrorValidacio as exc:
            raise HTTPException(422, {"missatge": "Valores no válidos: no se ha guardado nada", "errors": exc.errors}) from None
        config = store.carrega()
        return {**resultat_desa, "config": config, "editables": store.editables(config), "backups": len(store.backups())}

    @app.get("/cds-services")
    def cds_discovery() -> dict:
        """CDS Hooks: serveis disponibles. `extension` anuncia la interfície de l'add-on (extensió pròpia)."""
        return {"services": [cds_hooks.servei(url_interficie)]}

    @app.post(f"/cds-services/{cds_hooks.SERVEI_ID}")
    def cds_patient_view(peticio: dict = Body(..., examples=[{
            "hook": "patient-view", "hookInstance": "d1577c69-dfbe-44ad-ba6d-3e05e953b2ea",
            "context": {"userId": "Practitioner/demo", "patientId": "P003"}}]),
            source: Font = "local", scale: Escala | None = None, cohort: Cohort = "demo") -> dict:
        """CDS Hooks `patient-view`: una targeta amb el resum, el motiu, l'origen de la dada i les accions.
        `source`, `scale` i `cohort` són una extensió pròpia (els mateixos selectors que la resta de l'API)."""
        if peticio.get("hook") != cds_hooks.HOOK:
            raise HTTPException(400, f"Este servicio solo atiende el hook '{cds_hooks.HOOK}'")
        pacient_id = cds_hooks.id_pacient(peticio)
        if pacient_id is None:
            raise HTTPException(400, "Falta context.patientId")
        av, _ = avaluacio(source, scale, cohort)
        return {"cards": [cds_hooks.targeta(resultat(av, pacient_id), av.motor.motor["guia"], url_interficie)]}

    return app


app = create_app(remot_public=True)
