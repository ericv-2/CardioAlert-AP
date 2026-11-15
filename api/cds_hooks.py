"""Servei CDS Hooks (HL7 CDS Hooks 2.0) per al hook `patient-view`.

Tradueix un `ResultatPacient` del motor a una targeta ("card") de l'especificació; no té lògica clínica.
Les rutes són a `api/main.py`:
    GET  /cds-services                              discovery
    POST /cds-services/cardioalert-patient-view     targeta del pacient de `context.patientId`

Les dades del pacient són de l'estació clínica: el servei les llegeix del `prefetch` de la petició (si
l'estació resol les plantilles que anuncia el discovery) o del seu servidor FHIR (`fhirServer`).
"""
from __future__ import annotations

import uuid
from collections import Counter

from connectors.fhir_ehr_connector import PREFETCH
from engine import ResultatPacient
from model.entitats import DadesPacient

SERVEI_ID = "cardioalert-patient-view"
HOOK = "patient-view"
SERVEI = {
    "hook": HOOK,
    "id": SERVEI_ID,
    "title": "CardioAlert AP",
    "description": ("Cribado cardiorrenal-metabólico pasivo al abrir la historia del paciente: riesgo, motivo, "
                    "origen del dato y acción preventiva sugerida (datos sintéticos)."),
    # Plantilles de prefetch: el que el servei necessita del pacient. Són opcionals per a l'estació.
    "prefetch": dict(PREFETCH),
    "usageRequirements": ("Solo datos sintéticos de demostración. Necesita los datos del paciente: o bien el prefetch "
                          "completo, o bien `fhirServer` con lectura de Patient/{id}/$everything (sin OAuth en esta "
                          "simulación). No escribe en la historia clínica."),
}
# Grup de l'ordre de la llista de treball -> indicador de la targeta (urgència visual que demana
# l'especificació; no és una classificació de risc): alerta urgent = critical, risc alt o molt alt sense
# tractament adequat = warning, la resta = info.
INDICADOR = {1: "critical", 2: "warning", 3: "warning", 4: "info"}
MAX_SUMMARY = 140  # l'especificació demana un summary de menys de 140 caràcters
EXTENSIO_APP = "cardioalert-app"  # clau de `extension` on el discovery anuncia la interfície de l'add-on
TEMA_OBSERVACIO = "http://estacion-simulada.local/SubscriptionTopic/observacion-nueva-cupo"
SUBSCRIPCIO = {"topic": TEMA_OBSERVACIO, "description": "Observation nueva de un paciente del cupo",
               "channelType": "rest-hook", "endpoint": "/api/notificaciones", "payload": "application/fhir+json",
               "content": "id-only"}


def servei(url_app: str | None = None) -> dict:
    """Definició del servei per al discovery. Si es coneix la URL de la interfície de l'add-on, s'anuncia
    al camp `extension` (previst per l'especificació) perquè l'estació clínica la pugui obrir incrustada
    amb el pacient i el professional com a context (llançament SMART on FHIR simulat)."""
    if not url_app:
        return dict(SERVEI)
    return {**SERVEI, "extension": {EXTENSIO_APP: {
        "title": SERVEI["title"],
        "launchUrl": url_app,
        "launchType": "smart-ehr-launch",
        "description": "Interfaz completa del add-on (lista «Hoy», cupo, ficha y parámetros). Lanzamiento simulado, sin OAuth.",
        # Suscripció que l'add-on demana a l'estació en instal·lar-lo (FHIR Subscriptions, R4 Backport IG):
        # Observation nova d'un pacient del cupo -> POST a `endpoint` (relatiu a la URL de l'add-on)
        "subscription": SUBSCRIPCIO,
    }}}


def id_pacient(peticio: dict) -> str | None:
    """`context.patientId` de la petició (accepta també la referència FHIR "Patient/P003")."""
    context = peticio.get("context")
    valor = context.get("patientId") if isinstance(context, dict) else None
    if not isinstance(valor, str) or not valor.strip():
        return None
    return valor.strip().removeprefix("Patient/")


def comunitat_habitual(d: DadesPacient) -> str | None:
    """Comunitat on el pacient té més analítiques (orígens amb format "Sistema - Comunitat")."""
    comunitats = Counter(a.origen.split(" - ", 1)[1] for a in d.analitiques if a.origen and " - " in a.origen)
    return comunitats.most_common(1)[0][0] if comunitats else None


def _summary(res: ResultatPacient) -> str:
    if res.alertes_actives:
        mes = len(res.alertes_actives) - 1
        # L'alerta principal (la urgent, si n'hi ha): la mateixa que encapçala el resum i la llista
        principal = next((a for a in res.alertes_actives if a.regla == res.alerta_principal), res.alertes_actives[0])
        text = principal.titol
        text += f" (+{mes} {'alerta' if mes == 1 else 'alertas'})" if mes else ""
    else:
        text = res.resum
    return text if len(text) < MAX_SUMMARY else text[:MAX_SUMMARY - 2].rstrip() + "…"


def _detail(res: ResultatPacient) -> str:
    """Markdown (GitHub Flavored, com demana l'especificació): motiu de cada alerta i origen de la dada."""
    fonts_pacient = ", ".join(res.fonts_dades) or "no informado"
    # Nivell de risc: la categoria de la taula 5 (ESC 2021) amb el % i el rang, o per què no n'hi ha
    risc = f"**Riesgo cardiovascular: {res.text_risc_cv}**"
    if res.risc_cv_percentatge is not None:
        risc += f" ({res.escala_usada} {str(res.risc_cv_percentatge).replace('.', ',')} % a 10 años"
        risc += f"; referencia {res.rang_referencia_cv})" if res.rang_referencia_cv else ")"
    linies = [risc + "."] if res.text_risc_cv else []
    if res.nota_calibracio:
        linies.append(f"*{res.nota_calibracio}.*")
    if linies:
        linies.append("")
    n_cap = len(linies)
    for a in res.alertes_actives:
        origen = ", ".join(a.fonts) or fonts_pacient
        linies.append(f"- **{a.titol}** ({a.evidencia}): {a.motiu}. *Origen del dato: {origen}.*")
    if len(linies) == n_cap:
        linies.append(f"{res.resum}. *Origen de los datos: {fonts_pacient}.*")
    if res.dades_creuades:
        linies.append("")
        linies.append("Incluye informes recuperados de otra comunidad autónoma.")
    return "\n".join(linies)


def targeta(res: ResultatPacient, guia: str, url_app: str | None = None) -> dict:
    """Una targeta per pacient: summary d'una línia, indicator segons el grup d'ordre, detail i suggestions.
    Amb `url_app`, la targeta porta un enllaç de tipus "smart" a la interfície de l'add-on."""
    card = {
        "uuid": str(uuid.uuid4()),
        "summary": _summary(res),
        "indicator": INDICADOR[res.grup_ordre],
        "detail": _detail(res),
        "source": {"label": f"CardioAlert AP · {guia}", "topic": {"code": "cardiorenal-screening", "display": "Cribado cardiorrenal-metabólico"}},
    }
    if res.accions_recomanades:
        # Suggeriments informatius (sense `actions`): el servei no escriu res a la història clínica
        card["suggestions"] = [{"label": a.text, "uuid": str(uuid.uuid4()), "isRecommended": i == 0}
                               for i, a in enumerate(res.accions_recomanades)]
        card["selectionBehavior"] = "any"
    if url_app:
        card["links"] = [{"label": "Abrir la ficha en CardioAlert AP", "url": url_app, "type": "smart"}]
    return card
