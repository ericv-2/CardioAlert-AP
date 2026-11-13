"""Connector CSV: llegeix patients.csv, observations.csv, conditions.csv i medications.csv."""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

from model import Analitica, DadesPacient, Diagnostic, Medicacio, Pacient
from model.cataleg import grup_per_atc

from .base import Connector


def _llegeix(cami: Path) -> list[dict]:
    with cami.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class CsvConnector(Connector):
    def __init__(self, carpeta: str | Path):
        carpeta = Path(carpeta)
        self._pacients: dict[str, Pacient] = {}
        for f in _llegeix(carpeta / "patients.csv"):
            self._pacients[f["id"]] = Pacient(
                id=f["id"],
                nom=f["nom"],
                edat=int(f["edat"]),
                sexe=f["sexe"],
                fumador=f["fumador"].strip().lower() in ("1", "true", "si", "sí"),
                data_naixement=date.fromisoformat(f["data_naixement"]) if f.get("data_naixement") else None,
            )
        self._analitiques: dict[str, list[Analitica]] = defaultdict(list)
        for f in _llegeix(carpeta / "observations.csv"):
            self._analitiques[f["pacient_id"]].append(Analitica(
                f["codi_loinc"], f["nom"], float(f["valor"]), f["unitat"], date.fromisoformat(f["data"])))
        self._diagnostics: dict[str, list[Diagnostic]] = defaultdict(list)
        for f in _llegeix(carpeta / "conditions.csv"):
            self._diagnostics[f["pacient_id"]].append(Diagnostic(
                f["codi_ciap2"], f["codi_cie10"], f["nom"], date.fromisoformat(f["data"])))
        self._medicacions: dict[str, list[Medicacio]] = defaultdict(list)
        for f in _llegeix(carpeta / "medications.csv"):
            self._medicacions[f["pacient_id"]].append(Medicacio(
                f["nom"], f["codi_atc"], f.get("grup") or grup_per_atc(f["codi_atc"]),
                date.fromisoformat(f["data_inici"])))

    def get_patients(self) -> list[Pacient]:
        return [self._pacients[i] for i in sorted(self._pacients)]

    def get_patient_data(self, patient_id: str) -> DadesPacient:
        return DadesPacient(
            pacient=self._pacients[patient_id],
            analitiques=list(self._analitiques.get(patient_id, [])),
            diagnostics=list(self._diagnostics.get(patient_id, [])),
            medicacions=list(self._medicacions.get(patient_id, [])),
        ).ordena()
