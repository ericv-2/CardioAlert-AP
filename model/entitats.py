"""Model de dades comú. Tots els connectors retornen aquestes dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Pacient:
    id: str
    nom: str
    edat: int
    sexe: str  # "H" (home) o "D" (dona)
    fumador: bool
    data_naixement: date | None = None  # per calcular l'edat en una data concreta


@dataclass(frozen=True)
class Analitica:
    codi_loinc: str
    nom: str
    valor: float
    unitat: str
    data: date


@dataclass(frozen=True)
class Diagnostic:
    codi_ciap2: str
    codi_cie10: str
    nom: str
    data: date


@dataclass(frozen=True)
class Medicacio:
    nom: str
    codi_atc: str
    grup: str
    data_inici: date


@dataclass
class DadesPacient:
    """Tot el que se sap d'un pacient, ordenat cronològicament."""

    pacient: Pacient
    analitiques: list[Analitica] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    medicacions: list[Medicacio] = field(default_factory=list)

    def ordena(self) -> "DadesPacient":
        self.analitiques.sort(key=lambda a: (a.data, a.codi_loinc))
        self.diagnostics.sort(key=lambda d: (d.data, d.codi_ciap2))
        self.medicacions.sort(key=lambda m: (m.data_inici, m.codi_atc))
        return self

    # Ajudes de consulta (les farà servir el motor de regles)
    def serie(self, codi_loinc: str) -> list[Analitica]:
        return [a for a in self.analitiques if a.codi_loinc == codi_loinc]

    def ultima(self, codi_loinc: str) -> Analitica | None:
        serie = self.serie(codi_loinc)
        return serie[-1] if serie else None

    def te_diagnostic(self, codi_ciap2: str) -> bool:
        return any(d.codi_ciap2 == codi_ciap2 for d in self.diagnostics)

    def te_grup(self, grup: str) -> bool:
        return any(m.grup == grup for m in self.medicacions)
