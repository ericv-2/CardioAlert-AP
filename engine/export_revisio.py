"""Full de revisió clínica de les regles (.xlsx): estat de validació de cada regla i llindar.

    python -m engine --rules-excel [FITXER]     # per defecte exports/revision_reglas.xlsx

Genera una fila per regla o llindar A PARTIR DE config/rules.yaml: els valors i les classes que es mostren
són sempre els que fa servir el motor. Recomanacions, llindars i classes d'evidència validats per David Cebotari
(metge de l'equip) el 15/11/2026: la columna "Estado" diu "Validado" a totes les files menys a les decisions
clíniques obertes per a la fase següent (full "Decisiones abiertas"). La columna "Fuente exacta" queda en blanc
a propòsit: cal omplir-la amb l'apartat concret de la guia, no s'ha d'escriure de memòria.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .risk_engine import ARREL, CONFIG_DEFECTE

CAMI_DEFECTE = ARREL / "exports" / "revision_reglas.xlsx"

ENUNCIAT = "Enunciado del reto (marco STAMP on CKD / ESC-ERA 2026)"
ESC2021 = "Guía ESC 2021 (tabla 5, figuras 3 y 6)"
EQUIP = "Decisión del equipo (sin fuente directa)"
KDIGO = "KDIGO (matriz G x A, cronicidad)"
PUBLI = "Publicación original (transcrita)"

VALIDAT = "Validado"  # per David Cebotari (metge de l'equip), 15/11/2026
OBERTA = "Decisión clínica abierta (siguiente fase)"
COLOR_CONFIANCA = {VALIDAT: "D4EDDA", OBERTA: "FFE8B3"}
OPCIONS_REVISIO = "Correcto,Corregir,Eliminar,No sé / consultar"
_CAPCALERA = dict(font=Font(bold=True, color="FFFFFF"), fill=PatternFill("solid", fgColor="005A9C"),
                  alignment=Alignment(vertical="center", wrap_text=True))


def _n(x) -> str:
    return str(x).replace(".", ",")


def _files(c: dict) -> list[dict]:
    """Totes les files de revisió: (bloc, regla, què fa, valors, classe, pes, origen, estat, notes)."""
    r, m = c["rules"], c["motor"]
    rcv, bt, op = r["risc_cardiovascular"], r["ben_tractat"], m["oportunitats"]
    ic = r["possible_ic"]
    edats = ic["llindars_per_edat"]

    def f(bloc, regla, que, valors, evid, pes, origen, confianca, dubte=""):
        return dict(bloc=bloc, regla=regla, que=que, valors=valors, evid=evid or "—", pes=pes if pes is not None else "—",
                    origen=origen, confianca=confianca, dubte=dubte)

    return [
        # --- Renal ---
        f("Renal", "UACR no medido (cribado dual)",
          "Avisa si un paciente con DM2, HTA o ERC no tiene UACR registrado en el último año",
          f"Sin UACR > {r['uacr_falta']['max_mesos_sense_prova']} meses; diagnósticos: DM2, HTA, ERC",
          r["uacr_falta"]["evidencia"], r["uacr_falta"]["pes"], ENUNCIAT, VALIDAT),
        f("Renal", "Creatinina no medida",
          "Avisa si un paciente crónico no tiene creatinina en el último año",
          f"Sin creatinina > {r['creatinina_falta']['max_mesos_sense_prova']} meses; diagnósticos: DM2, HTA, ERC, IC, dislipemia",
          r["creatinina_falta"]["evidencia"], r["creatinina_falta"]["pes"], EQUIP, VALIDAT,
          ""),
        f("Renal", "ERC no diagnosticada",
          "FGe o UACR alterados de forma crónica y sin diagnóstico de ERC",
          f"FGe < {r['mrc_no_diagnosticada']['fge_llindar']} o UACR >= {r['mrc_no_diagnosticada']['uacr_llindar']} mg/g; "
          f">= {r['mrc_no_diagnosticada']['min_mesures']} medidas separadas >= {r['mrc_no_diagnosticada']['min_mesos_separacio']} meses",
          r["mrc_no_diagnosticada"]["evidencia"], r["mrc_no_diagnosticada"]["pes"], KDIGO, VALIDAT),
        f("Renal", "Albuminuria sin tratamiento protector",
          "UACR elevada sin IECA/ARA-II ni iSGLT2",
          f"UACR >= {r['albuminuria_sense_accio']['uacr_llindar']} mg/g; protectores: {', '.join(r['albuminuria_sense_accio']['grups_protectors'])}",
          r["albuminuria_sense_accio"]["evidencia"], r["albuminuria_sense_accio"]["pes"], ENUNCIAT, VALIDAT),
        f("Renal", "Descenso rápido del FGe",
          "Pérdida de FGe por año superior al umbral (aunque la creatinina aislada parezca normal)",
          f"> {_n(r['fge_descens']['descens_anual_llindar'])} mL/min/1,73 m² por año; >= {r['fge_descens']['min_mesures']} medidas "
          f"y >= {r['fge_descens']['min_mesos_seguiment']} meses de seguimiento",
          r["fge_descens"]["evidencia"], r["fge_descens"]["pes"], ENUNCIAT, VALIDAT,
          "Umbral del enunciado del reto."),
        f("Renal", "Posible fracaso renal agudo (FRA)",
          "Caída brusca del FGe respecto a la medida anterior: repetir en días/semanas antes de etiquetar ERC",
          f"Caída >= {m['possible_fra']['caiguda_pct']}% en <= {m['possible_fra']['max_mesos_entre_mesures']} meses; "
          f"entre {m['possible_fra']['caiguda_esperada_min_pct']}% y {m['possible_fra']['caiguda_pct']}% tras iniciar iSGLT2/IECA/ARA-II: aviso 'esperada'",
          m["possible_fra"]["evidencia"], m["possible_fra"]["pes"], EQUIP, VALIDAT,
          ""),
        f("Renal", "Derivación a Nefrología",
          "Cumple algún criterio de derivación",
          f"KFRE 5 años >= {m['derivacio_nefrologia']['kfre_5a_pct']}%; FGe < {m['derivacio_nefrologia']['fge_max']}; "
          f"UACR >= {m['derivacio_nefrologia']['uacr_min']} mg/g; duplicación de UACR",
          m["derivacio_nefrologia"]["evidencia"], m["derivacio_nefrologia"]["pes"], ENUNCIAT, VALIDAT,
          "El enunciado dice KFRE 3-5%: hemos elegido 5%."),
        f("Renal", "Fórmula KFRE (4 variables)",
          "Riesgo de fallo renal a 5 años", "Coeficientes de la publicación original (4 variables)",
          None, None, PUBLI, VALIDAT, "Coeficientes transcritos de Tangri et al., JAMA 2016. Tests propios de rango y orden; sin ejemplo publicado."),
        f("Renal", "Ecuación del FGe",
          "Fórmula con la que el motor recalcula el FGe desde la creatinina",
          f"{m['equacio_fge']} (CKD-EPI 2009 sin factor racial); ignora el FGe informado por el laboratorio",
          None, None, ENUNCIAT, VALIDAT),
        # --- Cardiaco ---
        f("Cardíaco", "NT-proBNP elevado sin IC",
          "Posible insuficiencia cardiaca sin diagnóstico",
          "Umbral por edad: " + "; ".join(
              f"{'< 50' if e['edat_max'] == 49 else '50-75' if e['edat_max'] == 75 else '> 75'} años: >= {e['llindar']} pg/mL"
              for e in edats)
          + f". < {ic['llindar_descarta']} descarta IC. Con ERC avanzada (FGe < {ic['mrc_avancada']['fge_max']}): >= {ic['mrc_avancada']['llindar']}",
          ic["evidencia"], ic["pes"], ENUNCIAT, VALIDAT,
          "El enunciado da 125 y 500; los cortes por edad siguen el consenso HFA-ESC 2023."),
        # --- Riesgo CV ---
        f("Riesgo CV", "Cortes de riesgo por edad (ESC)",
          "Riesgo alto / muy alto a 10 años según SCORE2",
          "; ".join(f"{'< 50' if t['edat_max'] == 49 else '50-69' if t['edat_max'] == 69 else '>= 70'} años: "
                    f"alto >= {_n(t['alt'])}%, muy alto >= {_n(t['molt_alt'])}%" for t in rcv["talls_per_edat"]),
          None, None, ESC2021, VALIDAT, "Tabla 5 ESC 2021. No modificar sin validación."),
        f("Riesgo CV", "Región de riesgo SCORE2",
          "Calibración de SCORE2", f"Región de riesgo {rcv['regio_score2']} (España)", None, None, ESC2021, VALIDAT),
        f("Riesgo CV", "Edad mínima",
          "Por debajo, SCORE2 no se aplica: solo reglas renales y pruebas pendientes",
          f">= {rcv['edat_min']} años", None, None, ESC2021, VALIDAT),
        f("Riesgo CV", "Alerta RCV muy alto",
          "Riesgo muy alto sin tratamiento adecuado", f"Peso {rcv['alertes']['molt_alt']['pes']}",
          rcv["alertes"]["molt_alt"]["evidencia"], rcv["alertes"]["molt_alt"]["pes"], EQUIP, VALIDAT,
          "Peso (puntos) de prioridad definido por el equipo."),
        f("Riesgo CV", "Alerta RCV alto",
          "Riesgo alto sin tratamiento adecuado: decisión compartida", f"Peso {rcv['alertes']['alt']['pes']}",
          rcv["alertes"]["alt"]["evidencia"], rcv["alertes"]["alt"]["pes"], EQUIP, VALIDAT,
          ""),
        f("Riesgo CV", "Alerta en >= 70 años aparentemente sanos",
          "Valorar según fragilidad, polimedicación y preferencias",
          f">= {rcv['alertes']['gent_gran']['edat_min']} años", rcv["alertes"]["gent_gran"]["evidencia"], None,
          ESC2021, VALIDAT, ""),
        f("Riesgo CV", "SCORE2 CKD Add-on",
          "Reclasificación al alza cuando hay afectación renal",
          f"FGe < {rcv['ckd_addon']['fge_max']} o UACR >= {rcv['ckd_addon']['uacr_min']} mg/g; "
          f"se aplica a {', '.join(rcv['ckd_addon']['models'])}",
          None, None, ENUNCIAT, VALIDAT, "Coeficientes contrastados con el paquete R RiskScorescvd. Tests propios de coherencia; sin ejemplo publicado."),
        f("Riesgo CV", "SCORE2-Diabetes sin Add-on",
          "Los pacientes con DM2 de 40-69 años no reciben el Add-on",
          "Motivo: SCORE2-Diabetes ya incluye el FGe en su ecuación", None, None, EQUIP, VALIDAT,
          ""),
        f("Riesgo CV", "Reclasificación por KDIGO",
          "Con ERC, KDIGO naranja pasa a riesgo alto y rojo a muy alto",
          "Activada" if rcv["reclassificacio_kdigo"] else "Desactivada", None, None, KDIGO, VALIDAT),
        f("Riesgo CV", "REGICOR (solo referencia)",
          "Escala local mostrada junto a la ESC, sin reclasificar",
          f"Alto >= {rcv['talls_regicor']['alt']}%, muy alto >= {rcv['talls_regicor']['molt_alt']}%",
          None, None, EQUIP, VALIDAT, "Coeficientes transcritos de Marrugat et al. 2003; test con un caso calculado a mano."),
        f("Riesgo CV", "Enfermedad CV establecida",
          "Riesgo muy alto directo, sin escala", f"Diagnósticos: {', '.join(rcv['diagnostics_ecv'])}",
          None, None, EQUIP, VALIDAT, ""),
        # --- Objetivos ---
        f("Objetivos", "Paciente bien tratado (control positivo)",
          "No se alerta si el tratamiento y los objetivos son correctos",
          f"PAS < {bt['pressio_objectiu']['sistolica']}, PAD < {bt['pressio_objectiu']['diastolica']} mmHg; "
          f"LDL < {bt['ldl_objectiu']['base']} mg/dL; HbA1c < {_n(bt['hba1c_objectiu'])}%",
          None, None, EQUIP, VALIDAT),
        f("Objetivos", "Objetivo de PA intensivo",
          "Acción (no alerta) si se tolera", f"PAS < {bt['pressio_objectiu']['sistolica_optima']} mmHg",
          op["pressio"]["evidencia"], None, ENUNCIAT, VALIDAT,
          "El enunciado habla de 120-129 mmHg con IECA/ARA-II; la figura 6 ESC 2021, de < 130."),
        f("Objetivos", "Objetivo de LDL por riesgo",
          "Acción de intensificar el tratamiento hipolipemiante",
          f"Riesgo alto: LDL < {bt['ldl_objectiu']['alt']}; muy alto: LDL < {bt['ldl_objectiu']['molt_alt']} mg/dL",
          None, None, ESC2021, VALIDAT),
        # --- Oportunidades terapéuticas ---
        f("Terapéutica", "iSGLT2",
          "Sugerir si no lo toma", f"DM2 con FGe >= {op['isglt2']['fge_min']}; sin DM2: FGe >= {op['isglt2']['fge_min']} y UACR >= {op['isglt2']['uacr_min_sense_dm']} mg/g",
          op["isglt2"]["evidencia"], None, ENUNCIAT, VALIDAT, ""),
        f("Terapéutica", "Estatina",
          "Sugerir si no toma hipolipemiante", f"FGe < {op['estatina']['fge_max']} con ERC, con independencia del LDL",
          op["estatina"]["evidencia"], None, ENUNCIAT, VALIDAT),
        f("Terapéutica", "IECA / ARA-II",
          "Sugerir si no los toma", f"UACR >= {op['sraa']['uacr_min']} mg/g",
          op["sraa"]["evidencia"], None, ENUNCIAT, VALIDAT),
        f("Terapéutica", "Finerenona",
          "Sugerir si no la toma", f"DM2 con UACR >= {op['finerenona']['uacr_min']} mg/g y K <= {_n(op['finerenona']['potassi_max'])} mmol/L",
          op["finerenona"]["evidencia"], None, ENUNCIAT, VALIDAT, ""),
        f("Terapéutica", "Semaglutida (arGLP-1)",
          "Sugerir si no lo toma", f"DM2 con UACR >= {op['aglp1']['uacr_min']} mg/g",
          op["aglp1"]["evidencia"], None, ENUNCIAT, VALIDAT, ""),
        f("Terapéutica", "AAS en prevención primaria",
          "Alerta si toma AAS sin enfermedad CV establecida (no recomendado)", "< 40 años no se evalúa",
          op["aas_prevencio_primaria"]["evidencia"], op["aas_prevencio_primaria"]["pes"], ENUNCIAT, VALIDAT),
        # --- Prioridad ---
        f("Prioridad", "Peso del KDIGO en la puntuación",
          "Puntos que suma cada color de la matriz KDIGO",
          ", ".join(f"{k} {v}" for k, v in m["prioritat"]["kdigo"].items()), None, None, EQUIP, VALIDAT,
          "Pesos de prioridad (0-100) definidos por el equipo: solo ordenan dentro de cada grupo."),
        f("Prioridad", "Alertas urgentes",
          "Un paciente con una de ellas pasa al grupo 1 de la lista",
          ", ".join(m["prioritat"]["alertes_urgents"]), None, None, EQUIP, VALIDAT,
          "fge_descens es urgente por decisión del médico (15/11/2026)."),
        f("Prioridad", "Pacientes prioritarios hoy",
          "Tamaño del bloque 'Hoy'", str(m["prioritat"]["pacients_avui"]), None, None, EQUIP, VALIDAT),
        # --- Decisions clíniques obertes (fase següent): les úniques files no validades ---
        f("Abiertas", "Ventana de datos del NT-proBNP",
          "Años de NT-proBNP que usa la regla de posible IC",
          f"{m['finestra_dades']['proves']['ntprobnp']['anys']} años (usa el último valor dentro de la ventana)",
          None, None, EQUIP, OBERTA,
          "Un NT-proBNP de hace 4 años sigue disparando la alerta: ¿conviene una ventana más corta (1-2 años) y pedir uno nuevo?"),
        f("Abiertas", "Código de hipercolesterolemia familiar",
          "Con ese diagnóstico el riesgo sería alto directo, sin escala",
          f"Códigos configurados: {', '.join(rcv['diagnostics_hf']) or 'ninguno'}", None, None, EQUIP, OBERTA,
          "El catálogo actual no tiene ningún código: falta decidir cuál usar."),
        f("Abiertas", "Tarjeta CDS en pacientes sin alertas",
          "Hoy siempre se devuelve una tarjeta, también informativa", "Siempre hay tarjeta", None, None, EQUIP, OBERTA,
          "En un despliegue real quizá convenga no mostrarla para evitar fatiga de alertas."),
        f("Abiertas", "Criterios de generación de los datos sintéticos",
          "Prevalencias, proporciones y supuestos de las dos cohortes sintéticas",
          "docs/dades_sintetiques.md y docs/cohort_realista.md", None, None, EQUIP, OBERTA,
          "Incluye el bloque de insuficiencia cardíaca (supuesto) y la prevalencia global de ERC (17,5 % frente a 15,1 % de ENRICA)."),
    ]


COLUMNES = [
    ("Bloque", 12, "bloc"), ("Regla / parámetro", 34, "regla"), ("Qué hace", 50, "que"),
    ("Valor actual en el sistema", 62, "valors"), ("Clase de recomendación citada", 16, "evid"),
    ("Peso (puntos)", 9, "pes"), ("Origen del valor", 38, "origen"), ("Estado", 22, "confianca"),
    ("Notas", 50, "dubte"),
]
COLUMNES_METGE = [("Fuente exacta (apartado de la guía)", 30), ("Revisión", 16),
                  ("Valor propuesto", 22), ("Comentario", 40)]


def _full_revisio(full, files: list[dict]) -> None:
    titols = [(t, w) for t, w, _ in COLUMNES] + COLUMNES_METGE
    for i, (titol, amplada) in enumerate(titols, start=1):
        cela = full.cell(row=1, column=i, value=titol)
        cela.font, cela.fill, cela.alignment = _CAPCALERA["font"], _CAPCALERA["fill"], _CAPCALERA["alignment"]
        full.column_dimensions[get_column_letter(i)].width = amplada
    full.row_dimensions[1].height = 40
    ajust = Alignment(vertical="top", wrap_text=True)
    for fila in files:
        full.append([fila[k] for _, _, k in COLUMNES] + ["", "", "", ""])
        for cela in full[full.max_row]:
            cela.alignment = ajust
        full.cell(row=full.max_row, column=8).fill = PatternFill("solid", fgColor=COLOR_CONFIANCA[fila["confianca"]])
    n = len(titols)
    full.freeze_panes = "C2"
    full.auto_filter.ref = f"A1:{get_column_letter(n)}{full.max_row}"
    if full.max_row > 1:
        validacio = DataValidation(type="list", formula1=f'"{OPCIONS_REVISIO}"', allow_blank=True)
        full.add_data_validation(validacio)
        validacio.add(f"{get_column_letter(len(COLUMNES) + 2)}2:{get_column_letter(len(COLUMNES) + 2)}{full.max_row}")


def llibre_revisio(config: dict) -> Workbook:
    files = _files(config)
    llibre = Workbook()
    ajuda = llibre.active
    ajuda.title = "Instrucciones"
    text = [
        ("CardioAlert AP · revisión clínica de las reglas", None),
        ("Qué es", "Cada fila es una regla o umbral que usa el motor. Los valores se leen directamente de config/rules.yaml."),
        ("Estado de validación", "Recomendaciones, umbrales y clases de evidencia revisados y validados por David Cebotari "
                                 "(médico) el 15/11/2026."),
        ("Decisiones abiertas", "Hoja 'Decisiones abiertas': las únicas filas pendientes, marcadas como "
                                "'Decisión clínica abierta (siguiente fase)'. La hoja 'Revisión' tiene todas las filas."),
        ("Para una nueva revisión", "En la columna 'Revisión' elegir Correcto / Corregir / Eliminar / No sé. Si corrige, "
                                    "escribir el valor en 'Valor propuesto' y, si puede, la fuente."),
        ("Fórmulas", "Coeficientes transcritos de las publicaciones originales. SCORE2 tiene un test contra el ejemplo "
                     "publicado; CKD-EPI 2009 y REGICOR, contra casos calculados con la fórmula; el resto, tests propios "
                     "de coherencia."),
        ("Clase de recomendación", "I = recomendado; IIa = debe considerarse; IIb = puede considerarse; III = no recomendado. "
                                   "No es el nivel de evidencia (A/B/C), que no recogemos."),
                ("Importante", "'Fuente exacta' está vacía a propósito: no se han escrito apartados de la guía de memoria."),
        ("Aviso", "Datos sintéticos. Herramienta de ayuda a la decisión: no sustituye el juicio clínico."),
    ]
    for etiqueta, valor in text:
        ajuda.append([etiqueta, valor])
    ajuda["A1"].font = Font(bold=True, size=14, color="005A9C")
    for cela in ajuda["A"][1:]:
        cela.font = Font(bold=True)
    for cela in ajuda["B"]:
        cela.alignment = Alignment(wrap_text=True, vertical="top")
    ajuda.column_dimensions["A"].width = 26
    ajuda.column_dimensions["B"].width = 110

    _full_revisio(llibre.create_sheet("Decisiones abiertas"), [x for x in files if x["confianca"] == OBERTA])
    _full_revisio(llibre.create_sheet("Revisión"), files)
    return llibre


def exporta_revisio(cami: str | Path = CAMI_DEFECTE, config: str | Path | dict = CONFIG_DEFECTE) -> Path:
    if not isinstance(config, dict):
        config = yaml.safe_load(Path(config).read_text(encoding="utf-8"))
    cami = Path(cami)
    cami.parent.mkdir(parents=True, exist_ok=True)
    llibre_revisio(config).save(cami)
    return cami
