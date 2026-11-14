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

from .risk_engine import ARREL, GRUPS_ORDRE, MODES_ESCALA, NOM_EQUACIO, TEXT_CATEGORIA, ResultatPacient, RiskEngine


def recompte(cupo: list[ResultatPacient]) -> dict:
    """Pacients per categoria de la taula 5 (ESC 2021) i per grup de l'ordre de la llista de treball."""
    categories = {text: sum(r.categoria_risc_cv == text for r in cupo) for text in TEXT_CATEGORIA.values()}
    return {
        "categories": categories,
        "sense_categoria": len(cupo) - sum(categories.values()),
        "menors_edat_minima": sum(r.estat_risc_cv == "no_aplicable_edat" for r in cupo),
        "falten_dades": sum(r.estat_risc_cv == "falten_dades" for r in cupo),
        "grups": {g: sum(r.grup_ordre == g for r in cupo) for g in GRUPS_ORDRE},
    }


def meta_avaluacio(motor: RiskEngine, font: str) -> dict:
    """Paràmetres de l'avaluació per al full "Resumen" de l'Excel."""
    return {
        "Fuente de datos": font,
        "Calculadora CV": {"score2": "ESC automático (SCORE2 / SCORE2-OP / SCORE2-Diabetes + CKD Add-on)",
                           "regicor": "REGICOR (comparación manual; no es la tabla 5 de la ESC)",
                           "totes_dues": "ESC automático (SCORE2 / SCORE2-OP / SCORE2-Diabetes + CKD Add-on); "
                                         "REGICOR solo como referencia"}[motor.escala],
        "Clasificación de riesgo": "Tabla 5 de la guía ESC 2021 (calibración de región de riesgo bajo)",
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
    n = recompte(cupo)
    print("Categoria de risc CV (taula 5 ESC 2021):")
    for text, quants in n["categories"].items():
        print(f"  {text}: {quants}")
    print(f"  Sense categoria: {n['sense_categoria']} (menors de l'edat mínima: {n['menors_edat_minima']}; "
          f"falten dades: {n['falten_dades']})")
    print("Ordre de la llista de treball:")
    for g, text in GRUPS_ORDRE.items():
        print(f"  {g}. {text}: {n['grups'][g]}")
    for r in cupo[:15]:
        print(f"g{r.grup_ordre} {r.puntuacio_prioritat:3d} {r.pacient_id} {r.nom:24s} {r.text_risc_cv[:13]:13s} "
              f"{r.categoria_kdigo or '-':6s} {r.resum[:100]}")


if __name__ == "__main__":
    main(sys.argv[1:])
