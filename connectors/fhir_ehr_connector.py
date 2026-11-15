"""Connector "fhir_ehr": llegeix les dades del servidor FHIR R4 de l'estació clínica.

L'add-on no té dades pròpies. L'estació li diu on és el seu servidor FHIR (camp `fhirServer` de CDS Hooks,
paràmetre `iss` del llançament SMART) i aquest connector hi llegeix:

    GET {base}/metadata                       nom del sistema (CapabilityStatement.software.name)
    GET {base}/Group                          el cupo del professional (recurs Group) i la seva versió
    GET {base}/Patient/{id}/$everything       tota la història d'un pacient (fitxa i targeta CDS)
    GET {base}/Group/{id}/$export             tot el cupo amb FHIR Bulk Data: 202 + Content-Location ->
                                              manifest -> un fitxer NDJSON per tipus de recurs

El cupo sencer es descarrega un sol cop (`carrega_cupo`) i queda en memòria; `CupoEhr.empremta` permet a qui
el fa servir (l'API) saber si l'estació ha canviat de cupo o de dades i cal tornar-lo a llegir.

Sense OAuth: és una simulació (en un desplegament real, el token arribaria a `fhirAuthorization` o del
llançament SMART). Qui crida ha de comprovar abans que la URL és d'una estació autoritzada.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date

import httpx

from model import DadesPacient, Pacient

from .base import Connector
from .fhir_connector import FhirConnector

TIPUS = ("Patient", "Observation", "Condition", "MedicationStatement")
# Plantilles de prefetch de CDS Hooks: el que el servei necessita d'un pacient. Una estació que les resolgui
# pot enviar les dades dins de la petició i estalviar la lectura del seu servidor FHIR.
PREFETCH = {
    "patient": "Patient/{{context.patientId}}",
    "observations": "Observation?patient={{context.patientId}}",
    "conditions": "Condition?patient={{context.patientId}}",
    "medications": "MedicationStatement?patient={{context.patientId}}",
}


class ErrorFhirEhr(RuntimeError):
    """L'estació no respon, respon malament o no té el que es demana."""


@dataclass(frozen=True)
class CupoEhr:
    """El cupo actiu de l'estació (recurs Group)."""

    id: str
    nom: str
    pacients: int | None
    versio: str
    centre: str | None = None

    @property
    def empremta(self) -> str:
        """Canvia si l'estació canvia de cupo o si canvien les dades del cupo."""
        return f"{self.id}|{self.pacients}|{self.versio}"


def _data(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text[:10]) if text else None
    except ValueError:
        return None


def _recursos(valor: dict | None) -> list[dict]:
    """Recursos d'un element de prefetch: un recurs sol o un Bundle de cerca."""
    if not isinstance(valor, dict):
        return []
    if valor.get("resourceType") == "Bundle":
        return [e["resource"] for e in valor.get("entry", []) if isinstance(e.get("resource"), dict)]
    return [valor]


def dades_de_prefetch(prefetch: dict | None, pacient_id: str, data_referencia: date | None = None) -> DadesPacient | None:
    """Les dades del pacient a partir del `prefetch` d'una petició CDS Hooks, o None si no hi és tot
    (llavors cal llegir el servidor FHIR de l'estació)."""
    if not isinstance(prefetch, dict) or any(prefetch.get(clau) is None for clau in PREFETCH):
        return None
    recursos = [r for clau in PREFETCH for r in _recursos(prefetch[clau])]
    pacients = [r for r in recursos if r.get("resourceType") == "Patient"]
    if len(pacients) != 1 or pacients[0].get("id") != pacient_id:
        return None
    return FhirConnector._llegeix_bundle({"entry": [{"resource": r} for r in recursos]}, data_referencia or date.today())


class FhirEhrConnector(Connector):
    def __init__(self, base_url: str, data_referencia: date | None = None, client: httpx.Client | None = None,
                 temps_peticio: float = 30.0, temps_maxim: float = 120.0):
        """base_url: servidor FHIR de l'estació (`fhirServer` / `iss`). data_referencia: data per calcular
        l'edat (per defecte, la de les dades que envia l'estació). client: per compartir connexions o
        injectar un transport (tests). temps_maxim: segons per a tota l'exportació del cupo."""
        self.base_url = base_url.rstrip("/")
        self._ref = data_referencia
        self._client = client or httpx.Client(timeout=temps_peticio, follow_redirects=True)
        self._temps_maxim = temps_maxim
        self._sistema: str | None = None
        self._dades: dict[str, DadesPacient] | None = None  # el cupo sencer, quan s'ha exportat
        self.cupo_carregat: CupoEhr | None = None
        self.segons_lectura: float | None = None  # el que ha trigat l'última exportació (descàrrega + lectura)

    # --- Peticions ---------------------------------------------------------------------------

    def _get(self, url: str, accept: str = "application/fhir+json", **kwargs) -> httpx.Response:
        self._mateix_servidor(url)
        try:
            resposta = self._client.get(url, headers={"Accept": accept, **kwargs.pop("headers", {})}, **kwargs)
        except httpx.HTTPError as exc:
            raise ErrorFhirEhr(f"el servidor FHIR de la estación no responde en {self.base_url} "
                               f"({type(exc).__name__})") from exc
        if resposta.status_code >= 400 and resposta.status_code != 404:
            raise ErrorFhirEhr(f"el servidor FHIR de la estación ha respondido {resposta.status_code} "
                               f"a {url}{self._diagnostic(resposta)}")
        return resposta

    def _mateix_servidor(self, url: str) -> None:
        """Les URL que retorna l'estació (estat i fitxers de l'exportació) han de ser del mateix servidor."""
        a, b = httpx.URL(url), httpx.URL(self.base_url)
        if (a.scheme, a.host, a.port) != (b.scheme, b.host, b.port):
            raise ErrorFhirEhr(f"la estación ha devuelto una dirección de otro servidor ({url})")

    @staticmethod
    def _diagnostic(resposta: httpx.Response) -> str:
        try:
            text = resposta.json()["issue"][0]["diagnostics"]
        except Exception:
            return ""
        return f": {text}"

    def _json(self, resposta: httpx.Response) -> dict:
        try:
            cos = resposta.json()
        except ValueError as exc:
            raise ErrorFhirEhr(f"{resposta.request.url} no ha devuelto JSON: no parece un servidor FHIR") from exc
        if not isinstance(cos, dict):
            raise ErrorFhirEhr(f"{resposta.request.url} no ha devuelto un recurso FHIR")
        return cos

    # --- Informació de l'estació --------------------------------------------------------------

    def sistema(self) -> str:
        """Nom del sistema que hi ha darrere del servidor FHIR (per dir d'on es llegeixen les dades)."""
        if self._sistema is None:
            resposta = self._get(f"{self.base_url}/metadata")
            cap = self._json(resposta) if resposta.status_code == 200 else {}
            self._sistema = ((cap.get("software") or {}).get("name") or (cap.get("implementation") or {}).get("description")
                             or "Estación clínica")
        return self._sistema

    def cupo(self) -> CupoEhr:
        """El cupo actiu de l'estació: el recurs Group que retorna `GET Group` (una petició lleugera)."""
        resposta = self._get(f"{self.base_url}/Group")
        if resposta.status_code == 404:
            raise ErrorFhirEhr("el servidor FHIR de la estación no ofrece el cupo como recurso Group")
        grups = [r for r in _recursos(self._json(resposta)) if r.get("resourceType") == "Group"]
        if not grups:
            raise ErrorFhirEhr("la estación no tiene ningún cupo (Group) activo")
        g = grups[0]
        meta = g.get("meta") or {}
        return CupoEhr(id=g["id"], nom=g.get("name") or g["id"], pacients=g.get("quantity"),
                       versio=str(meta.get("versionId") or meta.get("lastUpdated") or ""),
                       centre=(g.get("managingEntity") or {}).get("display"))

    # --- Un pacient --------------------------------------------------------------------------

    def llegeix_pacient(self, patient_id: str) -> DadesPacient:
        """Tota la història d'un pacient, llegida ara mateix de l'estació (`Patient/{id}/$everything`).
        Llança KeyError si l'estació no té el pacient."""
        resposta = self._get(f"{self.base_url}/Patient/{patient_id}/$everything")
        if resposta.status_code == 404:
            raise KeyError(patient_id)
        bundle = self._json(resposta)
        if not any(r.get("resourceType") == "Patient" for r in _recursos(bundle)):
            raise ErrorFhirEhr(f"la estación no ha devuelto el paciente {patient_id}")
        return FhirConnector._llegeix_bundle(bundle, self._ref or _data(bundle.get("timestamp")) or date.today())

    # --- El cupo sencer (FHIR Bulk Data) -------------------------------------------------------

    def carrega_cupo(self, cupo: CupoEhr | None = None) -> CupoEhr:
        """Exporta el cupo sencer amb Bulk Data (`Group/{id}/$export`) i el deixa en memòria."""
        inici = time.perf_counter()
        limit = time.monotonic() + self._temps_maxim
        cupo = cupo or self.cupo()
        resposta = self._get(f"{self.base_url}/Group/{cupo.id}/$export", params={"_type": ",".join(TIPUS)},
                             headers={"Prefer": "respond-async"})
        if resposta.status_code == 404:
            raise ErrorFhirEhr(f"la estación no permite exportar el cupo {cupo.id}{self._diagnostic(resposta)}")
        if resposta.status_code == 202:  # arrencada asíncrona: l'estat és a Content-Location
            url_estat = resposta.headers.get("Content-Location")
            if not url_estat:
                raise ErrorFhirEhr("la estación ha aceptado la exportación pero no dice dónde consultar su estado")
            while True:
                resposta = self._get(url_estat, accept="application/json")
                if resposta.status_code != 202:
                    break
                if time.monotonic() > limit:
                    raise ErrorFhirEhr(f"la exportación del cupo tarda demasiado (más de {self._temps_maxim:.0f} s)")
                time.sleep(min(float(resposta.headers.get("Retry-After") or 1), 5.0))
        if resposta.status_code != 200:
            raise ErrorFhirEhr(f"la exportación del cupo ha fallado ({resposta.status_code}){self._diagnostic(resposta)}")
        manifest = self._json(resposta)
        if manifest.get("error"):
            raise ErrorFhirEhr("la estación ha exportado el cupo con errores")

        per_pacient: dict[str, list[dict]] = {}
        altres: list[dict] = []
        for sortida in manifest.get("output", []):
            if sortida.get("type") not in TIPUS:
                continue
            fitxer = self._get(sortida["url"], accept="application/fhir+ndjson")
            if fitxer.status_code != 200:
                raise ErrorFhirEhr(f"no se puede descargar {sortida['url']} ({fitxer.status_code})")
            for linia in fitxer.content.split(b"\n"):
                if not linia.strip():
                    continue
                recurs = json.loads(linia)
                if recurs.get("resourceType") == "Patient":
                    per_pacient[recurs["id"]] = [recurs]
                else:
                    altres.append(recurs)
            if time.monotonic() > limit:
                raise ErrorFhirEhr(f"la exportación del cupo tarda demasiado (más de {self._temps_maxim:.0f} s)")
        for recurs in altres:
            llista = per_pacient.get(recurs.get("subject", {}).get("reference", "").rsplit("/", 1)[-1])
            if llista is not None:
                llista.append(recurs)
        if not per_pacient:
            raise ErrorFhirEhr(f"la exportación del cupo {cupo.id} no trae ningún paciente")
        ref = self._ref or _data(manifest.get("transactionTime")) or date.today()
        self._dades = {i: FhirConnector._llegeix_bundle({"entry": [{"resource": r} for r in llista]}, ref)
                       for i, llista in per_pacient.items()}
        self.cupo_carregat = cupo
        self.segons_lectura = round(time.perf_counter() - inici, 3)
        return cupo

    # --- Interfície Connector ------------------------------------------------------------------

    def get_patients(self) -> list[Pacient]:
        """Tots els pacients del cupo (l'exporta de l'estació si encara no s'ha fet)."""
        if self._dades is None:
            self.carrega_cupo()
        return [self._dades[i].pacient for i in sorted(self._dades)]

    def get_patient_data(self, patient_id: str) -> DadesPacient:
        """Del cupo en memòria si ja s'ha exportat; si no, es llegeix el pacient de l'estació."""
        if self._dades is None:
            return self.llegeix_pacient(patient_id)
        d = self._dades[patient_id]
        return DadesPacient(d.pacient, list(d.analitiques), list(d.diagnostics), list(d.medicacions))
