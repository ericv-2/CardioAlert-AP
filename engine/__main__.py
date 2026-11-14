"""Demo per consola.

    python -m engine                    resum del cupo prioritzat
    python -m engine P003               nota clínica d'un pacient
    python -m engine --excel            exporta el cupo a exports/cupo_evaluado.xlsx
    python -m engine --escala regicor   qualsevol de les anteriors amb REGICOR
"""
from __future__ import annotations

import argparse
import sys

from connectors import FhirConnector

from .risk_engine import ARREL, MODES_ESCALA, NOM_EQUACIO, RiskEngine


def meta_avaluacio(motor: RiskEngine, font: str) -> dict:
    """Paràmetres de l'avaluació per al full "Resumen" de l'Excel."""
    return {
        "Fuente de datos": font,
        "Calculadora CV": {"score2": "ESC automático (SCORE2 / SCORE2-OP / SCORE2-Diabetes + CKD Add-on)",
                           "regicor": "REGICOR", "totes_dues": "ESC automático + REGICOR"}[motor.escala],
        "Fecha de referencia": motor.avui.strftime("%d/%m/%Y"),
        "Guía": motor.motor["guia"],
        "Ecuación del FGe": NOM_EQUACIO.get(motor.nom_equacio, motor.nom_equacio),
    }


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m engine", description="Motor de regles de CardioAlert AP")
    parser.add_argument("pacient", nargs="?", help="ID del pacient (p. ex. P003) per imprimir-ne la nota clínica")
    parser.add_argument("--excel", nargs="?", const="", metavar="FITXER",
                        help="exporta el cupo a Excel (per defecte exports/cupo_evaluado.xlsx)")
    parser.add_argument("--escala", choices=MODES_ESCALA, help="escala de risc CV (per defecte, la de rules.yaml)")
    args = parser.parse_args(argv)

    motor = RiskEngine(FhirConnector(ARREL / "data" / "synthetic" / "fhir"), escala=args.escala)
    if args.pacient:
        print(motor.avalua(args.pacient).nota_clinica_auto)
        return
    cupo = motor.avalua_cupo()
    if args.excel is not None:
        from .export_excel import CAMI_DEFECTE, exporta_cupo
        cami = exporta_cupo(cupo, args.excel or CAMI_DEFECTE, meta_avaluacio(motor, "Local (eCAP / DIRAYA Demo)"))
        print(f"Excel escrit: {cami} ({len(cupo)} pacients)")
        return
    for nivell in ("ALT", "MITJA", "BAIX"):
        print(f"{nivell}: {sum(r.nivell_risc == nivell for r in cupo)} pacients")
    for r in cupo[:15]:
        print(f"{r.puntuacio_prioritat:3d} {r.nivell_risc:5s} {r.pacient_id} {r.nom:24s} {r.categoria_kdigo or '-':6s} {r.resum[:110]}")


if __name__ == "__main__":
    main(sys.argv[1:])
