"""Exportació del cupo avaluat a Excel (.xlsx) amb openpyxl.

    python -m engine --excel            # escriu exports/cupo_evaluado.xlsx

Tres fulls: "Cupo" (una fila per pacient, totes les columnes i textos sencers), "Alertas" (una fila per
alerta) i "Resumen" (indicadors i paràmetres de l'avaluació). Capçaleres i textos en castellà.
"""
from __future__ import annotations

from collections import Counter
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .renal import RISC_KDIGO_TEXT
from .risk_engine import ARREL, ResultatPacient

CAMI_DEFECTE = ARREL / "exports" / "cupo_evaluado.xlsx"
ESTAT_RENAL = {"normal": "Normal", "mrc": "Enfermedad renal crónica", "pendent_confirmar": "Pendiente de confirmar",
               "possible_fra": "Posible FRA", "sense_dades": "Sin datos"}
COLOR_NIVELL = {"ALT": "F8D7DA", "MITJA": "FFE8B3", "BAIX": "D4EDDA"}
_CAPCALERA = dict(font=Font(bold=True, color="FFFFFF"), fill=PatternFill("solid", fgColor="005A9C"),
                  alignment=Alignment(vertical="center", wrap_text=True))


def _si_no(valor: bool) -> str:
    return "Sí" if valor else "No"


def _llista(elements) -> str:
    return "\n".join(f"- {e}" for e in elements)


# (capçalera, amplada de columna, funció que treu el valor d'un ResultatPacient)
COLUMNES = [
    ("Orden", 8, None),  # posició al cupo prioritzat (s'omple a part)
    ("Nivel de prioridad", 12, lambda r: r.nivell_risc),
    ("Puntuación de prioridad", 12, lambda r: r.puntuacio_prioritat),
    ("ID", 8, lambda r: r.pacient_id),
    ("Nombre", 24, lambda r: r.nom),
    ("Edad", 7, lambda r: r.edat),
    ("Sexo", 9, lambda r: "Hombre" if r.sexe == "H" else "Mujer"),
    ("Categoría KDIGO", 11, lambda r: r.categoria_kdigo),
    ("Riesgo KDIGO", 16, lambda r: RISC_KDIGO_TEXT.get(r.risc_kdigo)),
    ("Estado renal", 24, lambda r: ESTAT_RENAL.get(r.estat_renal, r.estat_renal)),
    ("FGe actual (mL/min/1,73m²)", 12, lambda r: r.fge_actual),
    ("UACR actual (mg/g)", 11, lambda r: r.uacr_actual),
    ("Pendiente del FGe (mL/min/1,73m²/año)", 14, lambda r: r.pendent_fge),
    ("KFRE a 5 años (%)", 10, lambda r: r.kfre_5a),
    ("Escala CV usada", 24, lambda r: r.escala_usada),
    ("Riesgo CV a 10 años (%)", 11, lambda r: r.risc_cv_percentatge),
    ("Categoría de riesgo CV", 20, lambda r: r.categoria_risc_cv),
    ("Rango de referencia aplicado", 44, lambda r: r.rang_referencia_cv),
    ("Reclasificado por ERC (KDIGO)", 13, lambda r: _si_no(bool(r.risc_cv and r.risc_cv["reclassificat_mrc"]))),
    ("N.º de alertas", 9, lambda r: len(r.alertes_actives)),
    ("Alertas (motivo y evidencia)", 90, lambda r: _llista(f"{a.titol}: {a.motiu} ({a.evidencia})" for a in r.alertes_actives)),
    ("Acciones recomendadas", 80, lambda r: _llista(
        f"{a.text} ({a.evidencia})" + (f" {a.nota}" if a.nota else "") for a in r.accions_recomanades)),
    ("Avisos", 50, lambda r: _llista(r.avisos)),
    ("Bien tratado", 9, lambda r: _si_no(r.ben_tractat)),
    ("Objetivos pendientes", 44, lambda r: _llista(r.objectius_pendents)),
    ("Datos cruzados entre comunidades", 12, lambda r: _si_no(r.dades_creuades)),
    ("Sistemas de origen", 34, lambda r: ", ".join(r.fonts_dades)),
    ("Resumen (por qué + acción)", 90, lambda r: r.resum),
    ("Nota clínica (borrador)", 110, lambda r: r.nota_clinica_auto),
    ("Volante (borrador)", 80, lambda r: r.volant_auto),
]


def _capcalera(full, titols_i_amplades: list[tuple[str, int]]) -> None:
    for i, (titol, amplada) in enumerate(titols_i_amplades, start=1):
        cela = full.cell(row=1, column=i, value=titol)
        cela.font, cela.fill, cela.alignment = _CAPCALERA["font"], _CAPCALERA["fill"], _CAPCALERA["alignment"]
        full.column_dimensions[get_column_letter(i)].width = amplada
    full.row_dimensions[1].height = 45
    full.freeze_panes = "A2"
    full.auto_filter.ref = f"A1:{get_column_letter(len(titols_i_amplades))}1"


def llibre_cupo(resultats: list[ResultatPacient], meta: dict | None = None) -> Workbook:
    """Llibre d'Excel del cupo. `meta`: parelles etiqueta -> valor que s'afegeixen al full "Resumen"."""
    llibre = Workbook()
    cupo = llibre.active
    cupo.title = "Cupo"
    _capcalera(cupo, [(titol, amplada) for titol, amplada, _ in COLUMNES])
    ajust = Alignment(vertical="top", wrap_text=True)
    for ordre, r in enumerate(resultats, start=1):
        fila = [ordre] + [f(r) for _, _, f in COLUMNES[1:]]
        cupo.append(fila)
        for cela in cupo[cupo.max_row]:
            cela.alignment = ajust
        cupo.cell(row=cupo.max_row, column=2).fill = PatternFill("solid", fgColor=COLOR_NIVELL[r.nivell_risc])
    cupo.freeze_panes = "F2"  # nivell, punts, id i nom sempre visibles
    cupo.auto_filter.ref = cupo.dimensions

    alertes = llibre.create_sheet("Alertas")
    _capcalera(alertes, [("ID", 8), ("Nombre", 24), ("Nivel de prioridad", 12), ("Regla", 26), ("Alerta", 38),
                         ("Motivo", 110), ("Evidencia", 24), ("Peso (puntos)", 10), ("Sistemas de origen del dato", 40)])
    for r in resultats:
        for a in r.alertes_actives:
            alertes.append([r.pacient_id, r.nom, r.nivell_risc, a.regla, a.titol, a.motiu, a.evidencia, a.pes,
                            ", ".join(a.fonts)])
            for cela in alertes[alertes.max_row]:
                cela.alignment = ajust
    alertes.auto_filter.ref = alertes.dimensions

    resum = llibre.create_sheet("Resumen")
    nivells = Counter(r.nivell_risc for r in resultats)
    files = [("CardioAlert AP · cupo evaluado", None), *(meta or {}).items(),
             ("Pacientes evaluados", len(resultats)),
             ("Prioridad ALT", nivells["ALT"]), ("Prioridad MITJA", nivells["MITJA"]), ("Prioridad BAIX", nivells["BAIX"]),
             ("Alertas activas", sum(len(r.alertes_actives) for r in resultats)),
             ("Riesgo CV alto o muy alto", sum(bool(r.risc_cv and r.risc_cv["categoria"] in ("alt", "molt_alt")) for r in resultats)),
             ("Bien tratados (sin alerta)", sum(r.ben_tractat for r in resultats)),
             ("Con datos cruzados entre comunidades", sum(r.dades_creuades for r in resultats)),
             ("Aviso", "Datos sintéticos. Herramienta de ayuda a la decisión: no sustituye el juicio clínico.")]
    for etiqueta, valor in files:
        resum.append([etiqueta, valor])
    resum["A1"].font = Font(bold=True, size=14, color="005A9C")
    for cela in resum["A"][1:]:
        cela.font = Font(bold=True)
    for cela in resum["B"]:
        cela.alignment = Alignment(horizontal="left", wrap_text=True, vertical="top")
    resum.column_dimensions["A"].width = 40
    resum.column_dimensions["B"].width = 70
    return llibre


def bytes_cupo(resultats: list[ResultatPacient], meta: dict | None = None) -> bytes:
    sortida = BytesIO()
    llibre_cupo(resultats, meta).save(sortida)
    return sortida.getvalue()


def exporta_cupo(resultats: list[ResultatPacient], cami: str | Path = CAMI_DEFECTE, meta: dict | None = None) -> Path:
    cami = Path(cami)
    cami.parent.mkdir(parents=True, exist_ok=True)
    cami.write_bytes(bytes_cupo(resultats, meta))
    return cami
