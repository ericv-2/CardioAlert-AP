"""Servei CDS Hooks (HL7 CDS Hooks 2.0) per al hook `patient-view`.

Tradueix un `ResultatPacient` del motor a una targeta ("card") de l'especificació; no té lògica clínica.
Les rutes són a `api/main.py`:
    GET  /cds-services                              discovery
    POST /cds-services/cardioalert-patient-view     targeta del pacient de `context.patientId`
"""
from __future__ import annotations

import uuid
from collections import Counter

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
    "usageRequirements": "Solo datos sintéticos de demostración. No requiere prefetch ni acceso al servidor FHIR del cliente.",
}
# Grup de l'ordre de la llista de treball -> indicador de la targeta (urgència visual que demana
# l'especificació; no és una classificació de risc): alerta urgent = critical, risc alt o molt alt sense
# tractament adequat = warning, la resta = info.
INDICADOR = {1: "critical", 2: "warning", 3: "warning", 4: "info"}
MAX_SUMMARY = 140  # l'especificació demana un summary de menys de 140 caràcters


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
        text = res.alertes_actives[0].titol
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


def targeta(res: ResultatPacient, guia: str) -> dict:
    """Una targeta per pacient: summary d'una línia, indicator segons el grup d'ordre, detail i suggestions."""
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
    return card
