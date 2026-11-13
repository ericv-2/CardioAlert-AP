"""Connector FHIR R4: llegeix una carpeta amb un Bundle JSON per pacient.

Recursos suportats: Patient, Observation, Condition, MedicationStatement.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from model import Analitica, DadesPacient, Diagnostic, Medicacio, Pacient
from model.cataleg import LOINC_TABAC, grup_per_atc
from model.formules import edat_en

from .base import Connector

SISTEMA_LOINC = "http://loinc.org"
SISTEMA_CIAP2 = "http://hl7.org/fhir/sid/icpc-2"
SISTEMA_CIE10 = "http://hl7.org/fhir/sid/icd-10"
SISTEMA_ATC = "http://www.whocc.no/atc"
SNOMED_FUMADORS = {"449868002", "77176002", "428041000124106", "428071000124103", "428061000124105"}


def _codi(concepte: dict, sistema: str) -> str:
    for c in concepte.get("coding", []):
        if c.get("system") == sistema:
            return c["code"]
    return ""


def _data(text: str) -> date:
    return date.fromisoformat(text[:10])


class FhirConnector(Connector):
    def __init__(self, carpeta: str | Path, data_referencia: date | None = None):
        """data_referencia: data per calcular l'edat (per defecte, el timestamp del bundle)."""
        self._dades: dict[str, DadesPacient] = {}
        for fitxer in sorted(Path(carpeta).glob("*.json")):
            bundle = json.loads(fitxer.read_text(encoding="utf-8"))
            ref = data_referencia or (_data(bundle["timestamp"]) if bundle.get("timestamp") else date.today())
            dades = self._llegeix_bundle(bundle, ref)
            self._dades[dades.pacient.id] = dades

    @staticmethod
    def _llegeix_bundle(bundle: dict, ref: date) -> DadesPacient:
        recursos = [e["resource"] for e in bundle.get("entry", [])]
        per_tipus: dict[str, list[dict]] = {}
        for r in recursos:
            per_tipus.setdefault(r["resourceType"], []).append(r)

        fumador = False
        analitiques = []
        for o in per_tipus.get("Observation", []):
            loinc = _codi(o["code"], SISTEMA_LOINC)
            if loinc == LOINC_TABAC:
                fumador = _codi(o.get("valueCodeableConcept", {}), "http://snomed.info/sct") in SNOMED_FUMADORS
            elif "valueQuantity" in o:
                q = o["valueQuantity"]
                analitiques.append(Analitica(
                    loinc, o["code"].get("text") or o["code"]["coding"][0].get("display", ""),
                    float(q["value"]), q.get("unit", ""), _data(o["effectiveDateTime"]),
                    next((x["display"] for x in o.get("performer", []) if x.get("display")), None)))

        p = per_tipus["Patient"][0]
        nom = p["name"][0]
        naixement = _data(p["birthDate"])
        pacient = Pacient(
            id=p["id"],
            nom=nom.get("text") or " ".join(nom.get("given", []) + [nom.get("family", "")]).strip(),
            edat=edat_en(naixement, ref),
            sexe="H" if p.get("gender") == "male" else "D",
            fumador=fumador,
            data_naixement=naixement,
        )
        diagnostics = [
            Diagnostic(_codi(c["code"], SISTEMA_CIAP2), _codi(c["code"], SISTEMA_CIE10),
                       c["code"].get("text", ""), _data(c.get("onsetDateTime") or c["recordedDate"]))
            for c in per_tipus.get("Condition", [])
        ]
        medicacions = []
        for m in per_tipus.get("MedicationStatement", []):
            concepte = m["medicationCodeableConcept"]
            atc = _codi(concepte, SISTEMA_ATC)
            inici = m.get("effectivePeriod", {}).get("start") or m["effectiveDateTime"]
            medicacions.append(Medicacio(concepte.get("text", ""), atc, grup_per_atc(atc), _data(inici)))
        return DadesPacient(pacient, analitiques, diagnostics, medicacions).ordena()

    def get_patients(self) -> list[Pacient]:
        return [self._dades[i].pacient for i in sorted(self._dades)]

    def get_patient_data(self, patient_id: str) -> DadesPacient:
        d = self._dades[patient_id]
        return DadesPacient(d.pacient, list(d.analitiques), list(d.diagnostics), list(d.medicacions))
