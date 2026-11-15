"""Puja els pacients SINTÈTICS de simulador/datos/demo/fhir a un servidor FHIR R4 (per defecte, el públic de HAPI).

    python scripts/upload_to_fhir.py                 # puja (o actualitza) els 100 pacients
    python scripts/upload_to_fhir.py --esborra       # esborra del servidor tot el que hem pujat
    python scripts/upload_to_fhir.py --base URL      # un altre servidor FHIR R4

NOMÉS DADES SINTÈTIQUES: el servidor de HAPI és públic i qualsevol hi pot llegir. L'script només llegeix
de simulador/datos/demo/fhir (generat per scripts/generate_patients.py) i no accepta cap altra carpeta.

Cada recurs es puja amb:
- la nostra etiqueta a `meta.tag` (urn:cardioalert-ap | the-goats-hackathon), que és el que filtra
  connectors/fhir_remote_connector.py, i l'etiqueta de seguretat HTEST (dades de prova);
- un id propi amb prefix ("thegoats-P001", "thegoats-P001-obs-0001"...) i PUT, de manera que tornar a
  executar l'script actualitza els recursos en lloc de duplicar-los;
- al Patient, un `identifier` amb el nostre id (P001...) perquè el connector el recuperi.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ARREL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ARREL))

from connectors.fhir_remote_connector import (  # noqa: E402
    BASE_PER_DEFECTE, ETIQUETA, SISTEMA_ETIQUETA, SISTEMA_ID_PACIENT)

CARPETA = ARREL / "simulador" / "datos" / "demo" / "fhir"
PREFIX = "thegoats-"
META = {
    "tag": [{"system": SISTEMA_ETIQUETA, "code": ETIQUETA, "display": "The GOATS - datos sintéticos de hackathon"}],
    "security": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActReason", "code": "HTEST",
                  "display": "test health data"}],
}


def transaccio(bundle: dict, esborra: bool = False) -> dict:
    """Converteix un bundle "collection" del generador en una transacció PUT (o DELETE) amb ids i etiqueta propis."""
    entrades = []
    for e in bundle["entry"]:
        r = copy.deepcopy(e["resource"])
        url = f"{r['resourceType']}/{PREFIX}{r['id']}"
        if esborra:
            entrades.append({"request": {"method": "DELETE", "url": url}})
            continue
        if r["resourceType"] == "Patient":
            r["identifier"] = [{"system": SISTEMA_ID_PACIENT, "value": r["id"]}]
        r["id"] = PREFIX + r["id"]
        r["meta"] = META
        subjecte = r.get("subject", {}).get("reference")
        if subjecte:
            tipus, _, ident = subjecte.partition("/")
            r["subject"]["reference"] = f"{tipus}/{PREFIX}{ident}"
        entrades.append({"fullUrl": f"urn:cardioalert:{url}", "resource": r, "request": {"method": "PUT", "url": url}})
    if esborra:  # primer els recursos que apunten al pacient, al final el pacient
        entrades.sort(key=lambda x: x["request"]["url"].startswith("Patient/"))
    return {"resourceType": "Bundle", "type": "transaction", "entry": entrades}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Puja els pacients sintètics a un servidor FHIR R4")
    parser.add_argument("--base", default=BASE_PER_DEFECTE, help=f"URL base del servidor (per defecte {BASE_PER_DEFECTE})")
    parser.add_argument("--esborra", action="store_true", help="esborra del servidor els recursos que hem pujat")
    parser.add_argument("--fils", type=int, default=4, help="peticions en paral·lel (per defecte 4)")
    args = parser.parse_args()

    fitxers = sorted(CARPETA.glob("*.json"))
    if not fitxers:
        print(f"No hi ha bundles a {CARPETA}: executa abans scripts/generate_patients.py")
        return 1
    accio = "Esborrant" if args.esborra else "Pujant"
    print(f"{accio} {len(fitxers)} pacients sintètics a {args.base} amb l'etiqueta '{ETIQUETA}'...")

    capcaleres = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}
    with httpx.Client(timeout=120, headers=capcaleres, follow_redirects=True) as client:
        def envia(fitxer: Path) -> tuple[str, int, str]:
            cos = transaccio(json.loads(fitxer.read_text(encoding="utf-8")), args.esborra)
            for intent in range(3):  # el servidor públic falla de tant en tant: es reintenta
                try:
                    r = client.post(args.base.rstrip("/"), json=cos)
                    if r.status_code < 500:
                        return fitxer.stem, len(cos["entry"]), "" if r.is_success else f"HTTP {r.status_code}: {r.text[:300]}"
                    error = f"HTTP {r.status_code}"
                except httpx.HTTPError as exc:
                    error = f"{type(exc).__name__}: {exc}"
            return fitxer.stem, len(cos["entry"]), error

        errors, recursos = [], 0
        with ThreadPoolExecutor(max_workers=max(1, args.fils)) as fils:
            for n, (pacient, entrades, error) in enumerate(fils.map(envia, fitxers), start=1):
                if error:
                    errors.append((pacient, error))
                else:
                    recursos += entrades
                print(f"  [{n:3d}/{len(fitxers)}] {pacient} {'ERROR ' + error if error else 'ok'}")

    print(f"Fet: {len(fitxers) - len(errors)} pacients ({recursos} recursos) {'esborrats' if args.esborra else 'pujats'}; "
          f"{len(errors)} amb error.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
