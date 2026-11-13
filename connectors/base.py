"""Interfície comuna dels connectors de dades.

Cada font (FHIR, CSV, i en el futur eCAP, DIRAYA...) implementa aquesta interfície
i retorna sempre el model de model/, de manera que el motor no sap d'on venen les dades.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from model import DadesPacient, Pacient


class Connector(ABC):
    @abstractmethod
    def get_patients(self) -> list[Pacient]:
        """Tots els pacients de la font, ordenats per id."""

    @abstractmethod
    def get_patient_data(self, patient_id: str) -> DadesPacient:
        """Pacient + analítiques, diagnòstics i medicació (ordenats per data).

        Llança KeyError si el pacient no existeix.
        """
