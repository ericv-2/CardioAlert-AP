"""Demo per consola: `python -m engine` (resum del cupo) o `python -m engine P003` (nota clínica)."""
from __future__ import annotations

import sys

from connectors import FhirConnector

from .risk_engine import ARREL, RiskEngine


def main(args: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    motor = RiskEngine(FhirConnector(ARREL / "data" / "synthetic" / "fhir"))
    if args:
        print(motor.avalua(args[0]).nota_clinica_auto)
        return
    cupo = motor.avalua_cupo()
    for nivell in ("ALT", "MITJA", "BAIX"):
        print(f"{nivell}: {sum(r.nivell_risc == nivell for r in cupo)} pacients")
    for r in cupo[:15]:
        print(f"{r.puntuacio_prioritat:3d} {r.nivell_risc:5s} {r.pacient_id} {r.nom:24s} {r.categoria_kdigo or '-':6s} {r.resum[:110]}")


main(sys.argv[1:])
