"""API de CardioAlert AP (FastAPI).

    uvicorn api.main:app --reload --port 8000        # docs interactives a http://localhost:8000/docs

L'ADD-ON NO TÉ DADES PRÒPIES: les llegeix del servidor FHIR de l'estació clínica (connector `fhir_ehr`).
L'estació li diu on és aquest servidor de tres maneres, totes estàndard:
    - CDS Hooks: camp `fhirServer` de la petició del hook (i `prefetch`, si l'estació l'envia).
    - Llançament SMART on FHIR (simulat, sense OAuth): paràmetre `iss`, que la interfície reenvia a aquesta API.
    - Cupo sencer: exportació FHIR Bulk Data del Group del cupo (`Group/{id}/$export` -> NDJSON).
Sense `iss` ni `fhirServer` es fa servir l'estació per defecte (CARDIOALERT_FHIR_URL, http://localhost:5174/fhir).

Endpoints:
    GET  /api/cupo                                            KPIs + cupo avaluat en l'ordre de la llista de treball
    GET  /api/pacientes/{id}                                  fitxa: resultat, històric amb origen i sèries renals
    GET  /api/export/excel                                    descàrrega del cupo complet en .xlsx
    GET  /api/rules, POST /api/rules                          consulta i ajust dels llindars de rules.yaml
    GET  /cds-services                                        CDS Hooks: discovery (anuncia també la interfície)
    POST /cds-services/cardioalert-patient-view               CDS Hooks: targeta del hook patient-view
Paràmetres dels tres primers: `iss` (servidor FHIR de l'estació), `scale=totes_dues|score2|regicor` i, a
/api/cupo, `refresh=true` (torna a llegir el cupo de l'estació).

Altres fonts (per als tests i com a exemple; NO són el camí de la demo): `source=local` llegeix fitxers
(`cohort=demo|realista`, llistades a GET /api/cohorts) i `source=remote`, el servidor FHIR públic de HAPI.

L'API no té lògica clínica: tot surt del motor (`engine/`) i de `config/rules.yaml`. El cupo de cada servidor
FHIR es llegeix i s'avalua UN sol cop i es guarda en memòria (resultats i JSON ja serialitzat); es torna a
llegir si l'estació canvia de cupo o de dades (ho diu el seu recurs Group) o amb `refresh=true`, i es torna
a avaluar si canvia `rules.yaml` (es compara el contingut a cada petició). La fitxa i la targeta CDS llegeixen
el pacient de l'estació a cada petició (`Patient/{id}/$everything`).

La interfície (frontend/) corre al seu propi port; la seva URL s'anuncia al discovery (variable d'entorn
CARDIOALERT_UI_URL, per defecte http://localhost:5173).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import httpx
from fastapi import Body, FastAPI, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from connectors import Connector, CsvConnector, FhirConnector, FhirEhrConnector, FhirRemoteConnector
from connectors.fhir_ehr_connector import CupoEhr, ErrorFhirEhr, dades_de_prefetch
from engine import ResultatPacient, RiskEngine
from engine.__main__ import meta_avaluacio, recompte
from engine.export_excel import bytes_cupo
from engine.risk_engine import ARREL, CONFIG_DEFECTE, GRUPS_ORDRE, NOM_EQUACIO
from model import DadesPacient

from . import cds_hooks
from .rules_store import ErrorValidacio, RulesStore

# Fitxers de l'estació simulada, llegits directament: només per a `source=local` (tests i exemple d'una altra font)
DADES_LOCALS = ARREL / "simulador" / "datos" / "demo" / "fhir"
DADES_REALISTA = ARREL / "simulador" / "datos" / "realista" / "csv"  # cohort realista: mai al servidor remot
Font = Literal["ehr", "local", "remote"]
Escala = Literal["score2", "regicor", "totes_dues"]
Cohort = Literal["demo", "realista"]
ETIQUETA_FONT = {"local": "Local (eCAP / DIRAYA Demo)", "remote": "Servidor FHIR remoto"}
ETIQUETA_COHORT = {"demo": "Demo", "realista": "Cupo realista"}
SEGONS_ENTRE_REINTENTS = 60  # després d'una fallada del servidor remot no s'hi torna fins passat aquest temps
ORDRE_GENERAR = "python scripts/generate_patients.py --perfil realista --n 1500"
URL_INTERFICIE = "http://localhost:5173"  # on corre la interfície de l'add-on si no es diu res més
URL_FHIR_ESTACIO = "http://localhost:5174/fhir"  # servidor FHIR de l'estació si la petició no en porta cap
# Servidors FHIR dels quals l'add-on accepta llegir (expressió regular sobre la URL sencera). Per defecte,
# només estacions d'aquest ordinador: el `fhirServer` / `iss` arriba de fora i no s'ha de seguir a cegues.
FHIR_PERMESOS = r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(/.*)?"


def _milers(n: int) -> str:
    return f"{n:,}".replace(",", ".")


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


def _meta_motor(m: RiskEngine) -> dict:
    return {"escala": m.escala, "data_referencia": m.avui.isoformat(), "guia": m.motor["guia"],
            "guia_risc_cv": m.regles["risc_cardiovascular"].get("guia"),
            "pacients_avui": m.motor["prioritat"].get("pacients_avui", 10),
            "grups_ordre": GRUPS_ORDRE,
            "equacio_fge": NOM_EQUACIO.get(m.nom_equacio, m.nom_equacio)}


def _meta_estacio(url: str, sistema: str, cupo: CupoEhr, pacients: int | None = None) -> dict:
    """D'on es llegeix: el sistema (CapabilityStatement) i el cupo actiu (Group) de l'estació."""
    n = pacients if pacients is not None else cupo.pacients
    cohort = f"{cupo.nom} ({_milers(n)})" if n is not None else cupo.nom
    return {"font_usada": "ehr", "font_etiqueta": sistema, "cohort": cupo.id, "cohort_etiqueta": cohort,
            "dades_de": f"{sistema} – {cohort}", "fhir_server": url, "centre": cupo.centre, "avis": None}


@dataclass
class Avaluacio:
    """Un cupo ja avaluat, guardat en memòria."""

    motor: RiskEngine
    resultats: list[ResultatPacient]  # en l'ordre de la llista de treball
    per_id: dict[str, ResultatPacient]
    json_cos: bytes  # '"kpis": {...}, "pacients": [...]' ja serialitzat (el que més triga a generar)
    segons_calcul: float  # tot plegat: lectura de la font + motor + serialització
    segons_lectura: float | None = None  # només amb l'estació: exportació Bulk Data (descàrrega + lectura)
    estacio: dict | None = None  # només amb l'estació: `_meta_estacio` del cupo que s'ha avaluat


def create_app(rules_path: str | Path = CONFIG_DEFECTE, dades_locals: str | Path = DADES_LOCALS,
               remote_factory: Callable[[], Connector] | None = None, remot_public: bool = False,
               dades_realista: str | Path = DADES_REALISTA, url_interficie: str | None = None,
               font_per_defecte: Font = "ehr", url_fhir: str | None = None, fhir_permesos: str | None = None,
               client_fhir: httpx.Client | None = None) -> FastAPI:
    """font_per_defecte: d'on es llegeix si la petició no porta `source` ("ehr" = el servidor FHIR de
    l'estació; "local" i "remote" queden per als tests i com a exemple d'altres fonts).
    url_fhir: servidor FHIR de l'estació si la petició no porta `iss` / `fhirServer` (per defecte,
    CARDIOALERT_FHIR_URL o http://localhost:5174/fhir). fhir_permesos: expressió regular dels servidors FHIR
    acceptats (per defecte, CARDIOALERT_FHIR_PERMITIDOS o només aquest ordinador). client_fhir: client HTTP
    per parlar amb l'estació (tests).
    remote_factory: funció que retorna el connector remot (pot fallar o trigar: llavors es fa servir
    el local i la resposta porta un avís). remot_public=True: si no es passa cap factory, es fa servir el
    servidor públic de HAPI (FhirRemoteConnector). dades_realista: carpeta CSV de la cohort realista.
    url_interficie: URL de la interfície de l'add-on que s'anuncia al discovery de CDS Hooks i a l'enllaç
    de la targeta (per defecte, CARDIOALERT_UI_URL o http://localhost:5173; cadena buida = no s'anuncia)."""
    if url_interficie is None:
        url_interficie = os.environ.get("CARDIOALERT_UI_URL", URL_INTERFICIE)
    url_interficie = url_interficie.strip().rstrip("/")
    url_fhir = (url_fhir or os.environ.get("CARDIOALERT_FHIR_URL") or URL_FHIR_ESTACIO).strip().rstrip("/")
    patro_fhir = re.compile(fhir_permesos or os.environ.get("CARDIOALERT_FHIR_PERMITIDOS") or FHIR_PERMESOS)
    client_fhir = client_fhir or httpx.Client(timeout=30.0, follow_redirects=True)
    app = FastAPI(title="CardioAlert AP", version="1.2",
                  description="Cribado cardiorrenal-metabólico pasivo para Atención Primaria (datos sintéticos). "
                              "Lee los datos del servidor FHIR de la estación clínica.")
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
    memoria: dict = {"empremta": None, "config": None, "avaluacions": {}}
    estacions: dict[str, FhirEhrConnector] = {}  # un connector per servidor FHIR, amb el seu cupo en memòria
    pany = threading.RLock()  # una sola descàrrega i un sol càlcul encara que arribin peticions alhora

    def config_actual() -> dict:
        """rules.yaml tal com és ara. Si ha canviat, cap avaluació guardada serveix (les dades llegides, sí)."""
        empremta = hashlib.sha1(store.cami.read_bytes()).hexdigest()
        with pany:
            if memoria["empremta"] != empremta:
                memoria.update(empremta=empremta, config=store.carrega(), avaluacions={})
            return memoria["config"]

    # --- L'estació clínica (connector fhir_ehr) -------------------------------------------------

    def url_estacio(url: str | None) -> str:
        url = (url or url_fhir).strip().rstrip("/")
        if not patro_fhir.fullmatch(url):
            raise HTTPException(403, f"Servidor FHIR no autorizado: {url}. Este add-on solo lee de las estaciones "
                                     "clínicas configuradas (CARDIOALERT_FHIR_PERMITIDOS).")
        return url

    def estacio(url: str) -> FhirEhrConnector:
        with pany:
            if url not in estacions:
                estacions[url] = FhirEhrConnector(url, client=client_fhir)
            return estacions[url]

    def error_estacio(url: str, exc: Exception, estat_http: int = 502) -> HTTPException:
        return HTTPException(estat_http, f"No se pueden leer los datos de la estación clínica ({url}): {exc}. "
                                         "Compruebe que la estación está arrancada (start_simulador).")

    def cupo_estacio(url: str, refresca: bool) -> tuple[FhirEhrConnector, dict]:
        """El connector de l'estació amb el cupo actiu en memòria. Es torna a exportar (Bulk Data) si
        l'estació ha canviat de cupo o de dades, o si es demana."""
        con = estacio(url)
        try:
            cupo, sistema = con.cupo(), con.sistema()
            with pany:
                if refresca or con.cupo_carregat is None or con.cupo_carregat.empremta != cupo.empremta:
                    con.carrega_cupo(cupo)
                    for clau in [c for c in memoria["avaluacions"] if c[:2] == ("ehr", url)]:
                        del memoria["avaluacions"][clau]
                return con, _meta_estacio(url, sistema, con.cupo_carregat, len(con.get_patients()))
        except ErrorFhirEhr as exc:
            raise error_estacio(url, exc) from None

    def pacient_estacio(url: str, pacient_id: str, estat_http: int = 502) -> DadesPacient:
        """Un pacient llegit ara mateix de l'estació (`Patient/{id}/$everything`)."""
        try:
            return estacio(url).llegeix_pacient(pacient_id)
        except KeyError:
            raise HTTPException(404, f"Paciente {pacient_id} no encontrado en la estación clínica") from None
        except ErrorFhirEhr as exc:
            raise error_estacio(url, exc, estat_http) from None

    # --- Altres fonts: fitxers locals i servidor FHIR remot --------------------------------------

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

    # --- El cupo avaluat ------------------------------------------------------------------------

    def avaluacio(font: Font | None, escala: Escala | None, cohort: Cohort = "demo", iss: str | None = None,
                  refresca: bool = False) -> tuple[Avaluacio, dict]:
        """El cupo avaluat (de la memòria si ja s'havia calculat amb aquestes dades i aquesta configuració)
        i el `meta`."""
        inici = time.perf_counter()
        font = font or font_per_defecte
        config = config_actual()
        info_estacio = None
        if font == "ehr":
            url = url_estacio(iss)
            con, info_estacio = cupo_estacio(url, refresca)
            clau = ("ehr", url, escala)
        else:
            con, cohort_usada, font_usada, avis = connector(font, cohort)
            clau = (cohort_usada, font_usada, escala)
        with pany:
            av = memoria["avaluacions"].get(clau)
            en_memoria = av is not None
            if av is None:
                m = RiskEngine(con, config, escala=escala)
                resultats = m.avalua_cupo()
                pacients = []
                for r in resultats:
                    fila = r.to_dict()
                    del fila["nota_clinica_auto"], fila["volant_auto"]  # nota i volant només viatgen a la fitxa
                    pacients.append(fila)
                cos = json.dumps(jsonable_encoder({"kpis": _kpis(resultats), "pacients": pacients}),
                                 ensure_ascii=False, separators=(",", ":"))[1:-1].encode("utf-8")
                av = Avaluacio(m, resultats, {r.pacient_id: r for r in resultats}, cos,
                               round(time.perf_counter() - inici, 3),
                               con.segons_lectura if font == "ehr" else None, info_estacio)
                memoria["avaluacions"][clau] = av
        if font == "ehr":
            origen = dict(av.estacio)
        else:
            etiqueta = ETIQUETA_FONT[font_usada] if cohort_usada == "demo" else "Local (cupo realista sintético)"
            cohort_text = f"{ETIQUETA_COHORT[cohort_usada]} ({_milers(len(av.resultats))})"
            origen = {"font_usada": font_usada, "font_etiqueta": etiqueta, "cohort": cohort_usada,
                      "cohort_etiqueta": cohort_text, "dades_de": f"{etiqueta} – {cohort_text}", "fhir_server": None,
                      "centre": None, "avis": avis}
        meta = {"font_demanada": font, "cohort_demanada": cohort if font != "ehr" else None, **origen,
                **_meta_motor(av.motor), "en_memoria": en_memoria, "segons_calcul": av.segons_calcul,
                "segons_lectura": av.segons_lectura}
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
        """Cohorts de `source=local` (fitxers; no és el camí de la demo). Amb l'estació, el cupo és el que
        l'estació té actiu. La realista només hi és si s'ha generat."""
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

    q_iss = Query(None, description="Servidor FHIR de la estación clínica (el `iss` del lanzamiento SMART). "
                                    "Por defecto, CARDIOALERT_FHIR_URL")
    q_source = Query(None, description="Otras fuentes, para pruebas: local (ficheros) o remote (HAPI). "
                                       "Por defecto, ehr: el servidor FHIR de la estación")
    q_scale = Query(None, description="Por defecto, la de rules.yaml")

    @app.get("/api/cupo")
    def cupo(iss: str | None = q_iss, scale: Escala | None = q_scale,
             refresh: bool = Query(False, description="Vuelve a leer el cupo de la estación (Bulk Data)"),
             source: Font | None = q_source, cohort: Cohort = "demo") -> Response:
        av, meta = avaluacio(source, scale, cohort, iss, refresh)
        cap = json.dumps({"meta": meta}, ensure_ascii=False, separators=(",", ":"))[:-1].encode("utf-8")
        return Response(cap + b"," + av.json_cos + b"}", media_type="application/json")

    @app.get("/api/pacientes/{pacient_id}")
    def pacient(pacient_id: str, iss: str | None = q_iss, scale: Escala | None = q_scale,
                source: Font | None = q_source, cohort: Cohort = "demo") -> dict:
        if (source or font_per_defecte) == "ehr":
            # La fitxa llegeix el pacient de l'estació ara mateix: no espera l'exportació del cupo sencer
            inici = time.perf_counter()
            url = url_estacio(iss)
            con = estacio(url)
            d = pacient_estacio(url, pacient_id)
            try:
                origen = _meta_estacio(url, con.sistema(), con.cupo())
            except ErrorFhirEhr as exc:
                raise error_estacio(url, exc) from None
            m = RiskEngine(con, config_actual(), escala=scale)
            res = m.avalua_dades(d)
            meta = {"font_demanada": "ehr", "cohort_demanada": None, **origen, **_meta_motor(m), "en_memoria": False,
                    "segons_calcul": round(time.perf_counter() - inici, 3), "segons_lectura": None}
        else:
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
    def excel(iss: str | None = q_iss, scale: Escala | None = q_scale, source: Font | None = q_source,
              cohort: Cohort = "demo") -> Response:
        """Descarrega el cupo complet (totes les columnes, textos sencers) en .xlsx."""
        av, meta = avaluacio(source, scale, cohort, iss)
        font = meta["font_etiqueta"] + (f" (servidor FHIR: {meta['fhir_server']})" if meta["fhir_server"] else "")
        info = meta_avaluacio(av.motor, font)
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
            # Banc de proves de la configuració nova: els fitxers de la cohort demo i els cupos d'estació
            # que hi hagi en memòria (no es torna a llegir res de l'estació)
            with pany:
                connectors = [local] + [c for c in estacions.values() if c.cupo_carregat is not None]
            for con in connectors:
                for escala in ("totes_dues", "regicor"):
                    RiskEngine(con, config, escala=escala).avalua_cupo()
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
            "fhirServer": URL_FHIR_ESTACIO, "context": {"userId": "Practitioner/demo", "patientId": "P003"}}]),
            source: Font | None = None, scale: Escala | None = None, cohort: Cohort = "demo") -> dict:
        """CDS Hooks `patient-view`: una targeta amb el resum, el motiu, l'origen de la dada i les accions.

        Les dades del pacient surten, per aquest ordre: del `prefetch` de la petició (si hi és tot), del
        servidor FHIR de l'estació (`fhirServer`: `Patient/{id}/$everything`) o de l'estació per defecte.
        Si no es poden llegir, 412 (com demana l'especificació). `source`, `scale` i `cohort` són una
        extensió pròpia per a proves."""
        if peticio.get("hook") != cds_hooks.HOOK:
            raise HTTPException(400, f"Este servicio solo atiende el hook '{cds_hooks.HOOK}'")
        pacient_id = cds_hooks.id_pacient(peticio)
        if pacient_id is None:
            raise HTTPException(400, "Falta context.patientId")
        config = config_actual()
        servidor = peticio.get("fhirServer")
        servidor = servidor.strip() if isinstance(servidor, str) and servidor.strip() else None
        d = con = None
        if source is None:
            d = dades_de_prefetch(peticio.get("prefetch"), pacient_id, config["motor"].get("data_referencia"))
        if d is None and (source or ("ehr" if servidor else font_per_defecte)) == "ehr":
            url = url_estacio(servidor)
            con = estacio(url)
            d = pacient_estacio(url, pacient_id, estat_http=412)
        if d is not None:  # el motor només fa servir el connector per llegir; aquí les dades ja hi són
            m = RiskEngine(con, config, escala=scale)
            return {"cards": [cds_hooks.targeta(m.avalua_dades(d), m.motor["guia"], url_interficie)]}
        av, _ = avaluacio(source, scale, cohort)
        return {"cards": [cds_hooks.targeta(resultat(av, pacient_id), av.motor.motor["guia"], url_interficie)]}

    return app


app = create_app(remot_public=True)
