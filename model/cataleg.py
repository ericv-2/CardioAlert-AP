"""Catàlegs de codis (LOINC, CIAP-2/CIE-10, ATC) compartits per generador, connectors i motor."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prova:
    loinc: str
    nom: str
    unitat: str  # unitat tal com es mostra a Espanya
    ucum: str  # codi UCUM per a FHIR
    categoria: str  # "laboratory" o "vital-signs"


PROVES: dict[str, Prova] = {
    "creatinina": Prova("2160-0", "Creatinina", "mg/dL", "mg/dL", "laboratory"),
    "fge": Prova("62238-1", "Filtrado glomerular estimado (CKD-EPI 2021)", "mL/min/1,73m²", "mL/min/{1.73_m2}", "laboratory"),
    "uacr": Prova("9318-7", "Cociente albúmina/creatinina en orina", "mg/g", "mg/g", "laboratory"),
    "hba1c": Prova("4548-4", "Hemoglobina glicada (HbA1c)", "%", "%", "laboratory"),
    "glucosa": Prova("1558-6", "Glucosa en ayunas", "mg/dL", "mg/dL", "laboratory"),
    "colesterol_total": Prova("2093-3", "Colesterol total", "mg/dL", "mg/dL", "laboratory"),
    "ldl": Prova("13457-7", "Colesterol LDL", "mg/dL", "mg/dL", "laboratory"),
    "hdl": Prova("2085-9", "Colesterol HDL", "mg/dL", "mg/dL", "laboratory"),
    "trigliceridos": Prova("2571-8", "Triglicéridos", "mg/dL", "mg/dL", "laboratory"),
    "potasio": Prova("2823-3", "Potasio", "mmol/L", "mmol/L", "laboratory"),
    "ntprobnp": Prova("33762-6", "NT-proBNP", "pg/mL", "pg/mL", "laboratory"),
    "pas": Prova("8480-6", "Presión arterial sistólica", "mmHg", "mm[Hg]", "vital-signs"),
    "pad": Prova("8462-4", "Presión arterial diastólica", "mmHg", "mm[Hg]", "vital-signs"),
}
LOINC = {clau: p.loinc for clau, p in PROVES.items()}
PROVA_PER_LOINC = {p.loinc: p for p in PROVES.values()}

# LOINC de l'estat tabàquic (a FHIR el tabaquisme viatja com a Observation)
LOINC_TABAC = "72166-2"


@dataclass(frozen=True)
class Dx:
    ciap2: str
    cie10: str
    nom: str


DIAGNOSTICS: dict[str, Dx] = {
    "dm2": Dx("T90", "E11", "Diabetes mellitus tipo 2"),
    "hta": Dx("K86", "I10", "Hipertensión arterial"),
    "mrc": Dx("U99.01", "N18", "Enfermedad renal crónica"),
    "ic": Dx("K77", "I50", "Insuficiencia cardíaca"),
    "dislipemia": Dx("T93", "E78", "Dislipemia"),
    "tabac": Dx("P17", "F17", "Tabaquismo"),
}
CIAP2 = {clau: d.ciap2 for clau, d in DIAGNOSTICS.items()}

# Grup terapèutic segons el prefix ATC (el prefix més llarg guanya)
GRUPS_ATC: dict[str, str] = {
    "A10BA02": "metformina",
    "A10BK": "iSGLT2",
    "A10BJ": "aGLP-1",
    "A10A": "insulina",
    "C09A": "IECA",
    "C09C": "ARA-II",
    "C03A": "tiazida",
    "C08C": "antagonista_calcio",
    "C10AA": "estatina",
    "C03DA05": "finerenona",
}

# Diagnòstics (claus de DIAGNOSTICS) que justifiquen cada grup terapèutic
JUSTIFICACIO_GRUP: dict[str, set[str]] = {
    "metformina": {"dm2"},
    "iSGLT2": {"dm2", "mrc", "ic"},
    "aGLP-1": {"dm2"},
    "insulina": {"dm2"},
    "IECA": {"hta", "mrc", "ic"},
    "ARA-II": {"hta", "mrc", "ic"},
    "tiazida": {"hta"},
    "antagonista_calcio": {"hta"},
    "estatina": {"dislipemia"},
    "finerenona": {"mrc"},
}


def grup_per_atc(codi_atc: str) -> str:
    """Retorna el grup terapèutic d'un codi ATC ("altres" si no és al catàleg)."""
    for prefix in sorted(GRUPS_ATC, key=len, reverse=True):
        if codi_atc.startswith(prefix):
            return GRUPS_ATC[prefix]
    return "altres"
