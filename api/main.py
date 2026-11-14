"""API de CardioAlert AP (FastAPI).

    uvicorn api.main:app --reload --port 8000        # docs interactives a http://localhost:8000/docs

Endpoints:
    GET  /api/cupo?source=local|remote&scale=score2|regicor   KPIs + cupo avaluat i ordenat per prioritat
    GET  /api/pacientes/{id}                                  fitxa: resultat, històric amb origen i sèries renals
    GET  /api/export/excel                                    descàrrega del cupo complet en .xlsx
    GET  /api/rules, POST /api/rules                          consulta i ajust dels llindars de rules.yaml

L'API no té lògica clínica: tot surt del motor (`engine/`) i de `config/rules.yaml`, que es rellegeix a
cada petició (un canvi de llindars es veu a l'instant).
"""
from __future__ import annotations

import threading
import time
from collections import Counter
from pathlib import Path
from typing import Callable, Literal

from fastapi import Body, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from connectors import Connector, FhirConnector, FhirRemoteConnector
from engine import ResultatPacient, RiskEngine
from engine.__main__ import meta_avaluacio
from engine.export_excel import bytes_cupo
from engine.risk_engine import ARREL, CONFIG_DEFECTE, NOM_EQUACIO

from .rules_store import ErrorValidacio, RulesStore

DADES_LOCALS = ARREL / "data" / "synthetic" / "fhir"
Font = Literal["local", "remote"]
Escala = Literal["score2", "regicor"]
ETIQUETA_FONT = {"local": "Local (eCAP / DIRAYA Demo)", "remote": "Servidor FHIR remoto"}
SEGONS_ENTRE_REINTENTS = 60  # després d'una fallada del servidor remot no s'hi torna fins passat aquest temps


def _kpis(cupo: list[ResultatPacient]) -> dict:
    nivells = Counter(r.nivell_risc for r in cupo)
    regles = Counter(regla for r in cupo for regla in r.regles_actives())
    return {
        "total": len(cupo),
        "alt": nivells["ALT"], "mitja": nivells["MITJA"], "baix": nivells["BAIX"],
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


def create_app(rules_path: str | Path = CONFIG_DEFECTE, dades_locals: str | Path = DADES_LOCALS,
               remote_factory: Callable[[], Connector] | None = None, remot_public: bool = False) -> FastAPI:
    """remote_factory: funció que retorna el connector remot (pot fallar o trigar: llavors es fa servir
    el local i la resposta porta un avís). remot_public=True: si no es passa cap factory, es fa servir el
    servidor públic de HAPI (FhirRemoteConnector)."""
    app = FastAPI(title="CardioAlert AP", version="1.0",
                  description="Cribado cardiorrenal-metabólico pasivo para Atención Primaria (datos sintéticos).")
    app.add_middleware(CORSMiddleware, allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
                       allow_methods=["GET", "POST"], allow_headers=["*"], expose_headers=["Content-Disposition"])
    store = RulesStore(rules_path)
    local = FhirConnector(dades_locals)
    if remote_factory is None and remot_public:
        def remote_factory() -> Connector:
            return FhirRemoteConnector(data_referencia=store.carrega()["motor"].get("data_referencia"))
    estat: dict = {"remot": None, "avis": None, "fallada": None}
    pany = threading.Lock()  # una sola descàrrega encara que arribin peticions alhora

    def connector(font: Font) -> tuple[Connector, str, str | None]:
        """Retorna (connector, font realment usada, avís). El remot es descarrega un cop i es desa en memòria;
        si falla o tarda massa, es torna a les dades locals amb un avís."""
        if font == "local":
            return local, "local", None
        if remote_factory is None:
            return local, "local", "El conector FHIR remoto no está configurado: se muestran los datos locales."
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
                return local, "local", estat["avis"]
        return estat["remot"], "remote", None

    def motor(font: Font, escala: Escala | None) -> tuple[RiskEngine, dict]:
        con, usada, avis = connector(font)
        m = RiskEngine(con, store.carrega(), escala=escala)
        meta = {"font_demanada": font, "font_usada": usada, "font_etiqueta": ETIQUETA_FONT[usada], "avis": avis,
                "escala": m.escala, "data_referencia": m.avui.isoformat(), "guia": m.motor["guia"],
                "equacio_fge": NOM_EQUACIO.get(m.nom_equacio, m.nom_equacio)}
        return m, meta

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/cupo")
    def cupo(source: Font = "local", scale: Escala | None = Query(None, description="Per defecte, la de rules.yaml")) -> dict:
        m, meta = motor(source, scale)
        resultats = m.avalua_cupo()
        pacients = []
        for r in resultats:
            fila = r.to_dict()
            del fila["nota_clinica_auto"], fila["volant_auto"]  # nota i volant només viatgen a la fitxa
            pacients.append(fila)
        return {"meta": meta, "kpis": _kpis(resultats), "pacients": pacients}

    @app.get("/api/pacientes/{pacient_id}")
    def pacient(pacient_id: str, source: Font = "local", scale: Escala | None = None) -> dict:
        m, meta = motor(source, scale)
        try:
            d = m.connector.get_patient_data(pacient_id)
        except KeyError:
            raise HTTPException(404, f"Paciente {pacient_id} no encontrado") from None
        series = m.series_renals(d)
        return {
            "meta": meta,
            "pacient": m.avalua_dades(d).to_dict(),
            "diagnostics": d.diagnostics,
            "medicacions": d.medicacions,
            "analitiques": d.analitiques,  # històric complet, cada registre amb el seu origen
            "series": series,
            # Llindars de rules.yaml que la gràfica dibuixa com a línies de referència
            "llindars": {"fge": m.regles["mrc_no_diagnosticada"]["fge_llindar"],
                         "uacr": m.regles["mrc_no_diagnosticada"]["uacr_llindar"]},
        }

    @app.get("/api/export/excel")
    def excel(source: Font = "local", scale: Escala | None = None) -> Response:
        """Descarrega el cupo complet (totes les columnes, textos sencers) en .xlsx."""
        m, meta = motor(source, scale)
        info = meta_avaluacio(m, meta["font_etiqueta"])
        if meta["avis"]:
            info["Aviso de la fuente"] = meta["avis"]
        return Response(
            bytes_cupo(m.avalua_cupo(), info),
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
            for escala in ("score2", "regicor"):
                RiskEngine(local, config, escala=escala).avalua_cupo()
        try:
            resultat = store.aplica(canvis, prova)
        except ErrorValidacio as exc:
            raise HTTPException(422, {"missatge": "Valores no válidos: no se ha guardado nada", "errors": exc.errors}) from None
        config = store.carrega()
        return {**resultat, "config": config, "editables": store.editables(config), "backups": len(store.backups())}

    return app


app = create_app(remot_public=True)
