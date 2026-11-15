"""Vista «Pruebas pendientes»: pacients amb uacr_falta o creatinina_falta, i la seva exportació com a petició
conjunta de laboratori (CSV o Excel).

Una fila per pacient i prova, ordenades: primer les que no s'han fet mai, després les més antigues.
"""
from __future__ import annotations

import csv
import io
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .risk_engine import ResultatPacient

COLUMNES = [  # (capçalera, amplada, clau de la fila)
    ("ID paciente", 11, "pacient_id"), ("Nombre", 26, "nom"), ("Edad", 7, "edat"), ("Sexo", 9, "sexe"),
    ("Prueba solicitada", 44, "peticio"), ("Código LOINC", 12, "loinc"),
    ("Última determinación", 14, "ultima"), ("Meses sin la prueba", 11, "mesos"),
    ("Control cada (meses)", 11, "max_mesos"), ("Motivo (diagnósticos)", 22, "motiu"),
    ("Estado de la alerta", 16, "estat"),
]


def files_proves(resultats: list[ResultatPacient], estats: dict | None = None) -> list[dict]:
    """Una fila per prova pendent. `estats`: estat efectiu de l'alerta per pacient (de l'API), si n'hi ha."""
    estats = estats or {}
    files = []
    for r in resultats:
        for p in r.proves_pendents:
            ultima = p["ultima_data"]
            estat = estats.get(r.pacient_id, {}).get("estat", "pendent")
            files.append({
                "pacient_id": r.pacient_id, "nom": r.nom, "edat": r.edat, "sexe": "Hombre" if r.sexe == "H" else "Mujer",
                "prova": p["prova"], "peticio": p["peticio"], "loinc": p["loinc"], "regla": p["regla"],
                "ultima_data": ultima.isoformat() if isinstance(ultima, date) else ultima,
                "ultima": ultima.strftime("%d/%m/%Y") if isinstance(ultima, date) else "Nunca registrada",
                "ultim_valor": p["ultim_valor"], "unitat": p["unitat"], "origen": p["origen"],
                "mesos_sense": p["mesos_sense"], "mesos": p["mesos_sense"] if p["mesos_sense"] is not None else "—",
                "max_mesos": p["max_mesos"], "diagnostics": p["diagnostics"], "motiu": " + ".join(p["diagnostics"]),
                "estat": {"pendent": "Pendiente", "citat": "Citado", "revisat": "Revisado",
                          "posposat": "Pospuesto"}.get(estat, estat),
            })
    # Mai fetes primer; després, de més a menys mesos sense la prova
    return sorted(files, key=lambda f: (f["mesos_sense"] is not None, -(f["mesos_sense"] or 0), f["pacient_id"], f["prova"]))


def csv_proves(files: list[dict]) -> bytes:
    """CSV amb separador «;» i BOM UTF-8 (s'obre bé amb l'Excel en castellà)."""
    sortida = io.StringIO()
    w = csv.writer(sortida, delimiter=";", lineterminator="\r\n")
    w.writerow([titol for titol, _, _ in COLUMNES])
    for f in files:
        w.writerow([f[clau] for _, _, clau in COLUMNES])
    return ("﻿" + sortida.getvalue()).encode("utf-8")


def excel_proves(files: list[dict], meta: dict) -> bytes:
    """Petició conjunta: capçalera (centre, data, totals) i una fila per pacient i prova."""
    llibre = Workbook()
    full = llibre.active
    full.title = "Petición conjunta"
    full.append(["Petición conjunta de laboratorio · CardioAlert AP"])
    full["A1"].font = Font(bold=True, size=14, color="005A9C")
    n_pacients = len({f["pacient_id"] for f in files})
    per_prova = {}
    for f in files:
        per_prova[f["peticio"]] = per_prova.get(f["peticio"], 0) + 1
    for etiqueta, valor in [*meta.items(), ("Pacientes", n_pacients), ("Pruebas", len(files)),
                            *((f"  {prova}", n) for prova, n in sorted(per_prova.items())),
                            ("Aviso", "Datos sintéticos. Revise la petición antes de tramitarla.")]:
        full.append([etiqueta, valor])
        full.cell(row=full.max_row, column=1).font = Font(bold=True)
    full.append([])
    inici = full.max_row + 1
    for i, (titol, amplada, _) in enumerate(COLUMNES, start=1):
        cela = full.cell(row=inici, column=i, value=titol)
        cela.font = Font(bold=True, color="FFFFFF")
        cela.fill = PatternFill("solid", fgColor="005A9C")
        cela.alignment = Alignment(vertical="center", wrap_text=True)
        full.column_dimensions[get_column_letter(i)].width = amplada
    for f in files:
        full.append([f[clau] for _, _, clau in COLUMNES])
    full.freeze_panes = full.cell(row=inici + 1, column=1)
    if files:
        full.auto_filter.ref = f"A{inici}:{get_column_letter(len(COLUMNES))}{full.max_row}"
    sortida = io.BytesIO()
    llibre.save(sortida)
    return sortida.getvalue()
