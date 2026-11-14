"""Connector FHIR remot: llegeix d'un servidor FHIR R4 només els nostres pacients sintètics.

El servidor públic https://hapi.fhir.org/baseR4 és compartit i NO té els nostres pacients fins que
s'executa `python scripts/upload_to_fhir.py`, que els puja amb l'etiqueta pròpia (`meta.tag`
"the-goats-hackathon"). Aquest connector només demana recursos amb aquesta etiqueta.

Les dades es descarreguen UN sol cop, en construir el connector, i queden en memòria. Si el servidor
falla, no té els pacients o tarda més que `temps_maxim`, el constructor llança una excepció i qui el
crida (l'API) torna a les dades locals.
"""
from __future__ import annotations

import time
from datetime import date

import httpx

from model import DadesPacient, Pacient

from .base import Connector
from .fhir_connector import FhirConnector

BASE_PER_DEFECTE = "https://hapi.fhir.org/baseR4"
SISTEMA_ETIQUETA = "urn:cardioalert-ap"
ETIQUETA = "the-goats-hackathon"
SISTEMA_ID_PACIENT = "urn:cardioalert-ap:pacient"  # Patient.identifier amb el nostre id (P001...)
TIPUS = ("Patient", "Observation", "Condition", "MedicationStatement")


class ErrorFhirRemot(RuntimeError):
    pass


class FhirRemoteConnector(Connector):
    def __init__(self, base_url: str = BASE_PER_DEFECTE, data_referencia: date | None = None,
                 temps_maxim: float = 60.0, temps_peticio: float = 20.0, mida_pagina: int = 500,
                 client: httpx.Client | None = None):
        """data_referencia: data per calcular l'edat (per defecte, avui). temps_maxim: segons per a tota
        la descàrrega; temps_peticio: segons per petició. client: per injectar un transport (tests)."""
        self.base_url = base_url.rstrip("/")
        self._limit = time.monotonic() + temps_maxim
        self._temps_maxim = temps_maxim
        propi = client is None
        client = client or httpx.Client(timeout=temps_peticio, headers={"Accept": "application/fhir+json"},
                                        follow_redirects=True)
        try:
            recursos = {tipus: self._cerca(client, tipus, mida_pagina) for tipus in TIPUS}
        except httpx.HTTPError as exc:
            raise ErrorFhirRemot(f"el servidor FHIR no responde correctamente ({type(exc).__name__})") from exc
        finally:
            if propi:
                client.close()
        if not recursos["Patient"]:
            raise ErrorFhirRemot(f"el servidor no tiene pacientes con la etiqueta '{ETIQUETA}' "
                                 "(ejecuta scripts/upload_to_fhir.py)")
        self._dades = self._agrupa(recursos, data_referencia or date.today())

    def _cerca(self, client: httpx.Client, tipus: str, mida_pagina: int) -> list[dict]:
        """Tots els recursos d'un tipus amb la nostra etiqueta, seguint la paginació del servidor."""
        url: str | None = f"{self.base_url}/{tipus}"
        params: dict | None = {"_tag": f"{SISTEMA_ETIQUETA}|{ETIQUETA}", "_count": str(mida_pagina)}
        recursos: list[dict] = []
        while url:
            if time.monotonic() > self._limit:
                raise ErrorFhirRemot(f"el servidor FHIR tarda demasiado (más de {self._temps_maxim:.0f} s)")
            resposta = client.get(url, params=params)
            resposta.raise_for_status()
            bundle = resposta.json()
            recursos += [e["resource"] for e in bundle.get("entry", []) if e.get("resource", {}).get("resourceType") == tipus]
            url = next((link["url"] for link in bundle.get("link", []) if link.get("relation") == "next"), None)
            params = None  # l'enllaç "next" ja porta tots els paràmetres
        return recursos

    @staticmethod
    def _agrupa(recursos: dict[str, list[dict]], ref: date) -> dict[str, DadesPacient]:
        """Reconstrueix un bundle per pacient i el llegeix igual que el connector de fitxers."""
        per_pacient: dict[str, list[dict]] = {}
        id_local: dict[str, str] = {}  # id al servidor -> el nostre id (P001...)
        for p in recursos["Patient"]:
            nostre = next((i["value"] for i in p.get("identifier", []) if i.get("system") == SISTEMA_ID_PACIENT), p["id"])
            id_local[p["id"]] = nostre
            per_pacient[p["id"]] = [{**p, "id": nostre}]
        for tipus in TIPUS[1:]:
            for r in recursos[tipus]:
                remot = r.get("subject", {}).get("reference", "").rsplit("/", 1)[-1]
                if remot in per_pacient:
                    per_pacient[remot].append(r)
        dades = {}
        for remot, llista in per_pacient.items():
            d = FhirConnector._llegeix_bundle({"entry": [{"resource": r} for r in llista]}, ref)
            dades[id_local[remot]] = d
        return dades

    def get_patients(self) -> list[Pacient]:
        return [self._dades[i].pacient for i in sorted(self._dades)]

    def get_patient_data(self, patient_id: str) -> DadesPacient:
        d = self._dades[patient_id]
        return DadesPacient(d.pacient, list(d.analitiques), list(d.diagnostics), list(d.medicacions))
