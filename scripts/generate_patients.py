"""Generador de pacients sintètics (seed fixa) en FHIR R4 i CSV.

Ús:  python scripts/generate_patients.py

Criteris documentats a docs/dades_sintetiques.md (pendents de validar pel metge).
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ARREL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ARREL))

from model import Analitica, DadesPacient, Diagnostic, Medicacio, Pacient  # noqa: E402
from model.cataleg import (  # noqa: E402
    DIAGNOSTICS,
    LOINC_TABAC,
    PROVA_PER_LOINC,
    PROVES,
    grup_per_atc,
)
from model.formules import ckd_epi_2021, creatinina_per_fge, edat_en  # noqa: E402

SEED = 42
N_PACIENTS = 100
DATA_REF = date(2026, 11, 13)  # "avui" de la demo; final de l'històric
INICI = date(2022, 11, 1)  # inici de l'històric
SORTIDA = ARREL / "data" / "synthetic"

# Nombre total de pacients amb cada condició (sobre 100, casos trampa inclosos)
OBJECTIUS = {"hta": 40, "dislipemia": 43, "fumador": 24, "dm2": 30, "mrc": 20, "ic": 5}
N_SENSE_FACTORS = 25
PROPORCIO_CRONICS_AMB_BUIT = 0.25

NOMS_H = ["Juan", "Carlos", "Miguel", "Javier", "Luis", "Pedro", "Ángel", "Rafael", "Fernando", "Alberto",
          "Ramón", "Enrique", "Vicente", "Andrés", "Joaquín", "Santiago", "Eduardo", "Emilio", "Julio", "Salvador",
          "Tomás", "Agustín", "Ignacio", "Jesús", "Alfonso", "Ricardo", "Sergio", "Daniel", "Pablo", "Jorge"]
NOMS_D = ["María", "Carmen", "Ana", "Isabel", "Teresa", "Josefa", "Francisca", "Antonia", "Concepción", "Mercedes",
          "Cristina", "Elena", "Rosario", "Juana", "Manuela", "Encarnación", "Montserrat", "Beatriz", "Amparo", "Lucía",
          "Marta", "Julia", "Inmaculada", "Susana", "Raquel", "Silvia", "Margarita", "Esperanza", "Victoria", "Nuria"]
COGNOMS = ["González", "Rodríguez", "Pérez", "Gómez", "Martín", "Hernández", "Díaz", "Álvarez", "Muñoz", "Romero",
           "Alonso", "Gutiérrez", "Navarro", "Torres", "Domínguez", "Vázquez", "Ramos", "Gil", "Ramírez", "Serrano",
           "Blanco", "Molina", "Morales", "Suárez", "Ortega", "Delgado", "Castro", "Ortiz", "Rubio", "Marín",
           "Sanz", "Núñez", "Iglesias", "Medina", "Garrido", "Cortés", "Castillo", "Santos", "Lozano", "Guerrero"]


# ---------------------------------------------------------------------------
# Constructors bàsics
# ---------------------------------------------------------------------------

def analitica(clau: str, valor: float, data: date) -> Analitica:
    p = PROVES[clau]
    return Analitica(p.loinc, p.nom, float(valor), p.unitat, data)


def diagnostic(clau: str, data: date) -> Diagnostic:
    d = DIAGNOSTICS[clau]
    return Diagnostic(d.ciap2, d.cie10, d.nom, data)


def medicacio(nom: str, atc: str, data: date) -> Medicacio:
    return Medicacio(nom, atc, grup_per_atc(atc), data)


def visita(pac: Pacient, data: date, *, creatinina: float, pas: float, pad: float, ldl: float, hdl: float,
           tg: float, k: float, glucosa: float, hba1c: float | None = None, uacr: float | None = None,
           ntprobnp: float | None = None) -> list[Analitica]:
    """Analítica completa d'una visita. El FGe SEMPRE es calcula de la creatinina (CKD-EPI 2021)."""
    creatinina = round(creatinina, 2)
    fge = round(ckd_epi_2021(creatinina, edat_en(pac.data_naixement, data), pac.sexe))
    ldl, hdl, tg = round(ldl), round(hdl), round(tg)
    res = [
        analitica("creatinina", creatinina, data),
        analitica("fge", fge, data),
        analitica("glucosa", round(glucosa), data),
        analitica("colesterol_total", ldl + hdl + round(tg / 5), data),  # coherent amb Friedewald
        analitica("ldl", ldl, data),
        analitica("hdl", hdl, data),
        analitica("trigliceridos", tg, data),
        analitica("potasio", round(k, 1), data),
        analitica("pas", round(pas), data),
        analitica("pad", round(pad), data),
    ]
    if hba1c is not None:
        res.append(analitica("hba1c", round(hba1c, 1), data))
    if uacr is not None:
        res.append(analitica("uacr", round(uacr), data))
    if ntprobnp is not None:
        res.append(analitica("ntprobnp", round(ntprobnp), data))
    return res


def creatinina_objectiu(fge: int, pac: Pacient, data: date, exacte: bool = False) -> float:
    """Creatinina (2 decimals) el FGe calculat de la qual s'acosta més a l'objectiu."""
    edat = edat_en(pac.data_naixement, data)
    ideal = creatinina_per_fge(fge, edat, pac.sexe)
    candidats = [round(ideal + d / 100, 2) for d in range(-3, 4)]
    millor = min(candidats, key=lambda c: (abs(ckd_epi_2021(c, edat, pac.sexe) - fge), c))
    if exacte and round(ckd_epi_2021(millor, edat, pac.sexe)) != fge:
        raise ValueError(f"No hi ha creatinina que doni FGe {fge} per a {pac.nom} el {data}")
    return millor


# ---------------------------------------------------------------------------
# Casos trampa (deterministes, sense soroll)
# ---------------------------------------------------------------------------

def _trampa(pid: int, nom: str, edat: int, sexe: str, fumador: bool, naixement: date, dxs, meds, visites,
            fge_exacte: bool = False) -> DadesPacient:
    pac = Pacient(f"P{pid:03d}", nom, edat, sexe, fumador, naixement)
    assert edat_en(naixement, DATA_REF) == edat
    dades = DadesPacient(pac)
    dades.diagnostics = [diagnostic(c, date.fromisoformat(d)) for c, d in dxs]
    if fumador:
        dades.diagnostics.append(diagnostic("tabac", date(naixement.year + 30, 5, 10)))
    dades.medicacions = [medicacio(n, atc, date.fromisoformat(d)) for n, atc, d in meds]
    for v in visites:
        data = date.fromisoformat(v.pop("data"))
        creat = creatinina_objectiu(v.pop("fge"), pac, data, exacte=fge_exacte)
        dades.analitiques += visita(pac, data, creatinina=creat, **v)
    return dades.ordena()


def _v(data, fge, pas, pad, ldl, hdl, tg, k, glucosa, **extra) -> dict:
    return dict(data=data, fge=fge, pas=pas, pad=pad, ldl=ldl, hdl=hdl, tg=tg, k=k, glucosa=glucosa, **extra)


def casos_trampa() -> list[DadesPacient]:
    casos = []

    # 1) DM2 de 8 anys ben controlada, però l'últim UACR és de 2023
    casos.append(_trampa(
        1, "Antonio García", 64, "H", False, date(1962, 6, 15),
        [("dm2", "2018-10-09")],
        [("Metformina", "A10BA02", "2018-10-23")],
        [
            _v("2022-11-22", 90, 126, 76, 104, 48, 128, 4.3, 132, hba1c=6.9, uacr=9),
            _v("2023-05-16", 89, 124, 74, 108, 47, 135, 4.4, 136, hba1c=7.0),
            _v("2023-11-21", 89, 128, 78, 102, 49, 122, 4.2, 130, hba1c=6.8, uacr=12),
            _v("2024-06-11", 88, 122, 76, 106, 48, 130, 4.4, 134, hba1c=6.9),
            _v("2025-01-21", 87, 126, 74, 110, 46, 140, 4.3, 138, hba1c=7.0),
            _v("2025-09-16", 87, 124, 78, 105, 48, 126, 4.5, 131, hba1c=6.8),
            _v("2026-05-12", 86, 128, 76, 107, 47, 133, 4.4, 135, hba1c=6.9),
        ]))

    # 2) HTA amb FGe 85→78→71→64 i creatinina sempre dins del rang "normal"
    casos.append(_trampa(
        2, "Rosa Martínez", 71, "D", False, date(1955, 2, 20),
        [("hta", "2015-03-10")],
        [("Enalapril", "C09AA02", "2015-03-24")],
        [
            _v("2023-03-14", 85, 134, 82, 118, 58, 110, 4.4, 92, uacr=8),
            _v("2024-02-13", 78, 132, 80, 121, 57, 115, 4.5, 94, uacr=10),
            _v("2025-03-18", 71, 136, 84, 116, 59, 108, 4.6, 91, uacr=9),
            _v("2026-03-17", 64, 134, 82, 119, 58, 112, 4.6, 93, uacr=12),
        ], fge_exacte=True))

    # 3) DM2+HTA amb albuminúria confirmada (45 i 52) i només metformina
    casos.append(_trampa(
        3, "José Fernández", 58, "H", False, date(1968, 6, 15),
        [("dm2", "2019-05-14"), ("hta", "2020-02-11")],
        [("Metformina", "A10BA02", "2019-05-28")],
        [
            _v("2023-04-18", 93, 142, 88, 112, 44, 150, 4.3, 150, hba1c=7.3, uacr=18),
            _v("2023-10-17", 93, 144, 90, 115, 43, 158, 4.4, 148, hba1c=7.2),
            _v("2024-04-16", 92, 140, 88, 110, 45, 146, 4.3, 145, hba1c=7.1, uacr=24),
            _v("2024-10-15", 91, 146, 90, 114, 44, 152, 4.5, 151, hba1c=7.3),
            _v("2025-04-15", 91, 142, 86, 111, 44, 149, 4.4, 147, hba1c=7.2, uacr=45),
            _v("2025-10-14", 90, 144, 88, 116, 43, 155, 4.4, 153, hba1c=7.4),
            _v("2026-04-14", 89, 142, 88, 113, 44, 150, 4.5, 149, hba1c=7.2, uacr=52),
        ]))

    # 4) HTA amb FGe 55 i 52 (separats 6 mesos) i UACR 40, SENSE diagnòstic de MRC
    casos.append(_trampa(
        4, "Pilar López", 67, "D", False, date(1959, 6, 15),
        [("hta", "2014-09-16")],
        [("Amlodipino", "C08CA01", "2014-09-30")],
        [
            _v("2023-04-11", 68, 136, 84, 122, 60, 105, 4.5, 96, uacr=18),
            _v("2024-04-16", 64, 138, 84, 120, 61, 108, 4.5, 95, uacr=22),
            _v("2024-10-15", 62, 134, 82, 124, 59, 102, 4.6, 97),
            _v("2025-10-14", 55, 138, 86, 121, 60, 106, 4.7, 96, uacr=28),
            _v("2026-04-14", 52, 136, 84, 123, 60, 104, 4.7, 98, uacr=40),
        ], fge_exacte=True))

    # 5) Fumador amb HTA+DM2+dislipèmia: tot "acceptable" però risc alt i infratractat
    casos.append(_trampa(
        5, "Manuel Sánchez", 62, "H", True, date(1964, 6, 15),
        [("hta", "2016-04-12"), ("dm2", "2017-06-13"), ("dislipemia", "2018-02-20")],
        [("Metformina", "A10BA02", "2017-06-27"), ("Amlodipino", "C08CA01", "2016-04-26")],
        [
            _v("2023-02-14", 88, 136, 86, 128, 42, 165, 4.3, 134, hba1c=6.8, uacr=14),
            _v("2023-09-19", 87, 138, 88, 124, 41, 170, 4.4, 137, hba1c=6.9),
            _v("2024-03-12", 87, 136, 88, 127, 42, 162, 4.3, 133, hba1c=6.8, uacr=16),
            _v("2024-10-22", 86, 138, 86, 126, 41, 168, 4.4, 136, hba1c=6.9),
            _v("2025-04-15", 85, 136, 88, 123, 42, 160, 4.4, 135, hba1c=6.9, uacr=15),
            _v("2025-11-18", 85, 138, 88, 126, 41, 166, 4.5, 138, hba1c=7.0),
            _v("2026-05-19", 84, 138, 88, 125, 42, 164, 4.4, 136, hba1c=6.9, uacr=17),
        ]))

    # 6) HTA+DM2 amb NT-proBNP 450 sense diagnòstic d'IC
    casos.append(_trampa(
        6, "Dolores Ruiz", 74, "D", False, date(1952, 6, 15),
        [("hta", "2012-05-15"), ("dm2", "2015-11-10")],
        [("Enalapril", "C09AA02", "2012-05-29"), ("Metformina", "A10BA02", "2015-11-24")],
        [
            _v("2023-01-17", 74, 134, 78, 108, 55, 130, 4.5, 140, hba1c=7.0, uacr=18),
            _v("2023-09-12", 73, 132, 80, 112, 54, 136, 4.6, 144, hba1c=7.1),
            _v("2024-03-19", 73, 136, 78, 106, 56, 128, 4.5, 139, hba1c=6.9, uacr=20),
            _v("2024-11-12", 72, 134, 80, 110, 55, 133, 4.6, 142, hba1c=7.0),
            _v("2025-05-20", 71, 132, 78, 109, 55, 131, 4.6, 141, hba1c=7.0, uacr=19),
            _v("2026-02-17", 70, 136, 80, 111, 54, 135, 4.7, 143, hba1c=7.1, uacr=21, ntprobnp=450),
        ]))

    # 7) Control: mateix perfil que el 5, ben tractat i amb objectius assolits
    casos.append(_trampa(
        7, "Francisco Jiménez", 63, "H", True, date(1963, 6, 15),
        [("hta", "2016-03-15"), ("dm2", "2017-05-16"), ("dislipemia", "2018-01-23")],
        [("Metformina", "A10BA02", "2017-05-30"), ("Ramipril", "C09AA05", "2016-03-29"),
         ("Atorvastatina", "C10AA05", "2018-02-06"), ("Empagliflozina", "A10BK03", "2021-09-14")],
        [
            _v("2023-02-21", 87, 126, 78, 72, 46, 128, 4.4, 122, hba1c=6.7, uacr=13),
            _v("2023-09-26", 87, 124, 76, 70, 47, 122, 4.5, 120, hba1c=6.6),
            _v("2024-03-19", 86, 126, 76, 69, 46, 125, 4.4, 121, hba1c=6.6, uacr=12),
            _v("2024-10-29", 86, 122, 78, 71, 47, 120, 4.5, 119, hba1c=6.5),
            _v("2025-04-22", 85, 124, 76, 68, 46, 124, 4.5, 120, hba1c=6.6, uacr=11),
            _v("2025-11-25", 85, 126, 78, 70, 47, 121, 4.6, 122, hba1c=6.7),
            _v("2026-05-26", 84, 124, 76, 68, 46, 123, 4.5, 120, hba1c=6.6, uacr=12),
        ]))

    # 8) Control: dona sana amb analítiques normals
    casos.append(_trampa(
        8, "Laura Moreno", 45, "D", False, date(1981, 6, 15),
        [], [],
        [
            _v("2023-09-19", 104, 112, 70, 98, 64, 82, 4.2, 86),
            _v("2026-02-10", 102, 114, 72, 101, 63, 85, 4.3, 88),
        ]))
    return casos


# ---------------------------------------------------------------------------
# Pacients aleatoris
# ---------------------------------------------------------------------------

def _mostra_ponderada(rng: random.Random, elements: list, pesos: list[float], n: int) -> list:
    """Mostra sense reemplaçament amb pesos (Efraimidis-Spirakis)."""
    claus = [(rng.random() ** (1 / p), i) for i, p in enumerate(pesos)]
    return [elements[i] for _, i in sorted(claus, reverse=True)[:n]]


def _feiner(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7 if d.weekday() >= 5 else 0)


def _soroll(rng: random.Random, sd: float, limit: float) -> float:
    return max(-limit, min(limit, rng.gauss(0, sd)))


def perfils_aleatoris(rng: random.Random, trampes: list[DadesPacient]) -> list[dict]:
    """Reparteix condicions perquè els totals (amb les trampes) quadrin amb OBJECTIUS."""
    n = N_PACIENTS - len(trampes)
    ja = {c: 0 for c in OBJECTIUS}
    sans_trampa = 0
    for t in trampes:
        claus = {c for c, d in DIAGNOSTICS.items() if t.te_diagnostic(d.ciap2)}
        for c in ("hta", "dislipemia", "dm2", "mrc", "ic"):
            ja[c] += c in claus
        ja["fumador"] += t.pacient.fumador
        sans_trampa += not claus and not t.pacient.fumador

    perfils = [dict.fromkeys(OBJECTIUS, False) for _ in range(n)]
    amb_risc = perfils[: n - (N_SENSE_FACTORS - sans_trampa)]
    for c in ("hta", "dislipemia", "fumador", "dm2"):
        for p in rng.sample(amb_risc, OBJECTIUS[c] - ja[c]):
            p[c] = True
    # Ningú del grup de risc es pot quedar sense cap factor: se li cedeix una dislipèmia
    basics = ("hta", "dislipemia", "fumador", "dm2")
    for p in amb_risc:
        if not any(p[c] for c in basics):
            donant = next(q for q in amb_risc if q["dislipemia"] and sum(q[c] for c in basics) >= 2)
            donant["dislipemia"], p["dislipemia"] = False, True
    # MRC i IC: més probables amb DM2/HTA
    pes_mrc = [0.3 + 2.0 * p["dm2"] + 2.0 * p["hta"] for p in amb_risc]
    for p in _mostra_ponderada(rng, amb_risc, pes_mrc, OBJECTIUS["mrc"] - ja["mrc"]):
        p["mrc"] = True
    pes_ic = [0.2 + 2.0 * p["hta"] + 1.5 * p["mrc"] for p in amb_risc]
    for p in _mostra_ponderada(rng, amb_risc, pes_ic, OBJECTIUS["ic"] - ja["ic"]):
        p["ic"] = True

    # Sexe (50% homes en total), edat i nom
    homes_trampa = sum(t.pacient.sexe == "H" for t in trampes)
    sexes = ["H"] * (N_PACIENTS // 2 - homes_trampa)
    sexes += ["D"] * (n - len(sexes))
    rng.shuffle(sexes)
    usats = {t.pacient.nom for t in trampes}
    for p, sexe in zip(perfils, sexes):
        p["sexe"] = sexe
        p["cronic"] = any(p[c] for c in ("hta", "dislipemia", "dm2", "mrc", "ic"))
        if p["mrc"] or p["ic"]:
            p["edat"] = rng.randint(60, 85)
        elif p["cronic"]:
            p["edat"] = rng.randint(48, 85)
        else:
            p["edat"] = rng.randint(40, 70)
        while True:
            nom = f"{rng.choice(NOMS_H if sexe == 'H' else NOMS_D)} {rng.choice(COGNOMS)}"
            if nom not in usats:
                usats.add(nom)
                p["nom"] = nom
                break

    # ~25% dels crònics amb alguna prova que falta (l'Antonio García ja n'és un)
    cronics = [p for p in perfils if p["cronic"]]
    total_cronics = len(cronics) + sum(1 for t in trampes if t.diagnostics)
    for p in rng.sample(cronics, round(PROPORCIO_CRONICS_AMB_BUIT * total_cronics) - 1):
        vol_uacr = p["dm2"] or p["hta"] or p["mrc"]
        p["buit"] = "uacr" if vol_uacr and rng.random() < 0.6 else "creatinina"
    rng.shuffle(perfils)
    return perfils


def _dates_visites(rng: random.Random, p: dict) -> list[date]:
    """Dates de visita, construïdes cap enrere des de l'última."""
    if p["cronic"]:
        if p.get("buit") == "creatinina":
            ultima = DATA_REF - timedelta(days=rng.randint(400, 650))
        else:
            ultima = DATA_REF - timedelta(days=rng.randint(10, 170))
        interval = (180, 365)  # cada 6-12 mesos
    else:
        ultima = DATA_REF - timedelta(days=rng.randint(30, 700))
        interval = (730, 1095)  # cada 2-3 anys
    dates = [ultima]
    while True:
        anterior = dates[-1] - timedelta(days=rng.randint(*interval))
        if anterior < INICI:
            break
        dates.append(anterior)
    return sorted(_feiner(d) for d in dates)


def _tractament(rng: random.Random, p: dict, dx_data: dict[str, date]) -> list[Medicacio]:
    """Fàrmacs coherents amb els diagnòstics (cap fàrmac sense diagnòstic que el justifiqui)."""
    meds: list[tuple[str, str, str]] = []  # (nom, atc, diagnòstic que el justifica)
    if p["dm2"]:
        if rng.random() < 0.88:
            meds.append(("Metformina", "A10BA02", "dm2"))
        if rng.random() < 0.12:
            meds.append(rng.choice([("Semaglutida", "A10BJ06"), ("Dulaglutida", "A10BJ05"),
                                    ("Liraglutida", "A10BJ02")]) + ("dm2",))
        if rng.random() < 0.12:
            meds.append(("Insulina glargina", "A10AE04", "dm2"))
    motiu_isglt2 = next((c for c in ("dm2", "mrc", "ic") if p[c]), None)
    if motiu_isglt2 and rng.random() < (0.55 if p["mrc"] or p["ic"] else 0.25):
        meds.append(rng.choice([("Empagliflozina", "A10BK03"), ("Dapagliflozina", "A10BK01")]) + (motiu_isglt2,))
    motiu_sraa = next((c for c in ("hta", "mrc", "ic") if p[c]), None)
    te_sraa = False
    if motiu_sraa and rng.random() < 0.72:
        te_sraa = True
        if rng.random() < 0.55:
            meds.append(rng.choice([("Enalapril", "C09AA02"), ("Ramipril", "C09AA05")]) + (motiu_sraa,))
        else:
            meds.append(rng.choice([("Losartán", "C09CA01"), ("Valsartán", "C09CA03"),
                                    ("Candesartán", "C09CA06")]) + (motiu_sraa,))
    if p["hta"]:
        tiazida = rng.random() < 0.25
        calci = rng.random() < 0.25
        if not te_sraa and not tiazida and not calci:  # tot hipertens rep algun antihipertensiu
            tiazida, calci = (True, False) if rng.random() < 0.5 else (False, True)
        if tiazida:
            meds.append(("Hidroclorotiazida", "C03AA03", "hta"))
        if calci:
            meds.append(("Amlodipino", "C08CA01", "hta"))
    if p["dislipemia"] and rng.random() < 0.70:
        meds.append(rng.choice([("Atorvastatina", "C10AA05"), ("Simvastatina", "C10AA01"),
                                ("Rosuvastatina", "C10AA07")]) + ("dislipemia",))
    if p["dm2"] and p["mrc"] and rng.random() < 0.15:
        meds.append(("Finerenona", "C03DA05", "mrc"))

    res = []
    for nom, atc, motiu in meds:
        inici = dx_data[motiu] + timedelta(days=rng.randint(7, 720))
        if atc.startswith("A10BK") or atc == "C03DA05":  # fàrmacs recents
            inici = max(inici, date(2021, 1, 1) + timedelta(days=rng.randint(0, 1500)))
        res.append(medicacio(nom, atc, _feiner(min(inici, DATA_REF - timedelta(days=30)))))
    return res


def pacient_aleatori(rng: random.Random, pid: int, p: dict) -> DadesPacient:
    naixement = DATA_REF - timedelta(days=round(p["edat"] * 365.25) + rng.randint(5, 355))
    pac = Pacient(f"P{pid:03d}", p["nom"], edat_en(naixement, DATA_REF), p["sexe"], p["fumador"], naixement)
    dades = DadesPacient(pac)

    # Diagnòstics (entre 1 i 15 anys d'antiguitat)
    dx_data = {}
    for c in ("hta", "dm2", "dislipemia", "mrc", "ic"):
        if p[c]:
            anys = rng.uniform(1, 6) if c in ("mrc", "ic") else rng.uniform(1, 15)
            dx_data[c] = _feiner(DATA_REF - timedelta(days=round(anys * 365)))
            dades.diagnostics.append(diagnostic(c, dx_data[c]))
    if p["fumador"]:
        dades.diagnostics.append(diagnostic("tabac", _feiner(DATA_REF - timedelta(days=rng.randint(700, 7000)))))
    dades.medicacions = _tractament(rng, p, dx_data)
    grups = {m.grup for m in dades.medicacions}
    tractat_dm = bool(grups & {"metformina", "iSGLT2", "aGLP-1", "insulina"})

    # Valors basals del pacient
    edat = pac.edat
    if p["mrc"] and rng.random() < 0.70:  # MRC per filtrat (G3)
        fge0 = rng.uniform(34, 57)
        descens = rng.uniform(5.5, 7.0) if rng.random() < 0.15 else rng.uniform(1.0, 3.5)
        uacr0 = rng.choice([rng.uniform(8, 25), rng.uniform(35, 400)])
    elif p["mrc"]:  # MRC per albuminúria amb filtrat conservat
        fge0, descens, uacr0 = rng.uniform(64, 85), rng.uniform(1.0, 2.5), rng.uniform(45, 350)
    else:
        fge0 = max(70.0, min(108.0, 112 - 0.55 * (edat - 40) + rng.uniform(-8, 8)))
        descens = rng.uniform(0.5, 1.0)  # descens fisiològic
        uacr0 = rng.uniform(4, 19)
    if p["dm2"]:
        hba1c0 = rng.uniform(6.4, 8.6) if tractat_dm else rng.uniform(6.8, 8.0)
    else:
        hba1c0 = rng.uniform(5.0, 5.9)
    glucosa0 = rng.uniform(80, 106)
    if p["dislipemia"]:
        ldl0 = rng.uniform(68, 118) if "estatina" in grups else rng.uniform(132, 185)
        tg0 = rng.uniform(120, 260)
    else:
        ldl0, tg0 = rng.uniform(82, 128), rng.uniform(65, 150)
    hdl0 = rng.uniform(38, 62) + (8 if pac.sexe == "D" else 0)
    if p["hta"]:
        pas0, pad0 = rng.uniform(122, 148), rng.uniform(72, 90)
    elif p["cronic"]:
        pas0, pad0 = rng.uniform(114, 132), rng.uniform(68, 82)
    else:
        pas0, pad0 = rng.uniform(106, 128), rng.uniform(64, 80)
    k0 = rng.uniform(3.9, 4.7) + (0.25 if p["mrc"] else 0)
    ntprobnp0 = rng.uniform(600, 2600) if p["ic"] else None

    # Visites i proves
    dates = _dates_visites(rng, p)
    vol_uacr = p["dm2"] or p["hta"] or p["mrc"]
    amb_uacr: set[date] = set()
    if vol_uacr:  # UACR anual: cap enrere des de l'última visita
        seguent = None
        for d in reversed(dates):
            if seguent is None or (seguent - d).days >= 300:
                amb_uacr.add(d)
                seguent = d
        if p.get("buit") == "uacr":  # se salten els UACR recents
            tall = DATA_REF - timedelta(days=rng.randint(400, 1100))
            amb_uacr = {d for d in amb_uacr if d <= tall}
    data_ntprobnp_normal = rng.choice(dates) if p["cronic"] and not p["ic"] and rng.random() < 0.12 else None

    for i, d in enumerate(dates):
        anys = (d - INICI).days / 365.25
        fge_obj = max(12.0, fge0 - descens * anys)
        creat = creatinina_per_fge(fge_obj, edat_en(naixement, d), pac.sexe) * (1 + _soroll(rng, 0.04, 0.10))
        hba1c = None
        if p["dm2"]:
            hba1c = hba1c0 + _soroll(rng, 0.15, 0.3)
            if not tractat_dm:
                hba1c = max(hba1c, 6.5)
            glucosa = 28.7 * hba1c - 46.7 + _soroll(rng, 8, 15)
        else:
            if p["cronic"] and rng.random() < 0.4:
                hba1c = min(6.2, hba1c0 + _soroll(rng, 0.1, 0.2))
            glucosa = min(118.0, glucosa0 + _soroll(rng, 5, 10))
        ntprobnp = None
        if ntprobnp0 and (i % 2 == 0 or i == len(dates) - 1):
            ntprobnp = ntprobnp0 * rng.uniform(0.8, 1.25)
        elif d == data_ntprobnp_normal:
            ntprobnp = rng.uniform(25, 110)
        dades.analitiques += visita(
            pac, d,
            creatinina=creat,
            pas=pas0 + _soroll(rng, 5, 10),
            pad=pad0 + _soroll(rng, 3.5, 7),
            ldl=ldl0 * (1 + _soroll(rng, 0.05, 0.12)),
            hdl=hdl0 * (1 + _soroll(rng, 0.04, 0.10)),
            tg=tg0 * (1 + _soroll(rng, 0.10, 0.25)),
            k=max(3.5, min(5.6, k0 + _soroll(rng, 0.15, 0.4))),
            glucosa=glucosa,
            hba1c=hba1c,
            uacr=max(2.0, uacr0 * (1 + rng.uniform(-0.28, 0.28))) if d in amb_uacr else None,
            ntprobnp=ntprobnp,
        )
    return dades.ordena()


def genera() -> list[DadesPacient]:
    rng = random.Random(SEED)
    trampes = casos_trampa()
    perfils = perfils_aleatoris(rng, trampes)
    return trampes + [pacient_aleatori(rng, len(trampes) + i + 1, p) for i, p in enumerate(perfils)]


# ---------------------------------------------------------------------------
# Sortida FHIR R4
# ---------------------------------------------------------------------------

SNOMED_FUMADOR = ("449868002", "Fumador actual")
SNOMED_NO_FUMADOR = ("8392000", "No fumador")


def _ref(pac: Pacient) -> dict:
    return {"reference": f"Patient/{pac.id}"}


def bundle_fhir(dades: DadesPacient) -> dict:
    pac = dades.pacient
    nom, cognom = pac.nom.split(" ", 1)
    recursos: list[dict] = [{
        "resourceType": "Patient",
        "id": pac.id,
        "name": [{"use": "official", "text": pac.nom, "given": [nom], "family": cognom}],
        "gender": "male" if pac.sexe == "H" else "female",
        "birthDate": pac.data_naixement.isoformat(),
    }]
    codi, text = SNOMED_FUMADOR if pac.fumador else SNOMED_NO_FUMADOR
    recursos.append({
        "resourceType": "Observation",
        "id": f"{pac.id}-tabac",
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                  "code": "social-history"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": LOINC_TABAC, "display": "Tobacco smoking status"}],
                 "text": "Hábito tabáquico"},
        "subject": _ref(pac),
        "effectiveDateTime": DATA_REF.isoformat(),
        "valueCodeableConcept": {"coding": [{"system": "http://snomed.info/sct", "code": codi, "display": text}],
                                 "text": text},
    })
    for i, a in enumerate(dades.analitiques, 1):
        prova = PROVA_PER_LOINC[a.codi_loinc]
        recursos.append({
            "resourceType": "Observation",
            "id": f"{pac.id}-obs-{i:04d}",
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                      "code": prova.categoria}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": a.codi_loinc, "display": a.nom}],
                     "text": a.nom},
            "subject": _ref(pac),
            "effectiveDateTime": a.data.isoformat(),
            "valueQuantity": {"value": a.valor, "unit": a.unitat, "system": "http://unitsofmeasure.org",
                              "code": prova.ucum},
        })
    for i, d in enumerate(dades.diagnostics, 1):
        recursos.append({
            "resourceType": "Condition",
            "id": f"{pac.id}-dx-{i:02d}",
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                           "code": "active"}]},
            "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                                               "code": "confirmed"}]},
            "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icpc-2", "code": d.codi_ciap2, "display": d.nom},
                                {"system": "http://hl7.org/fhir/sid/icd-10", "code": d.codi_cie10, "display": d.nom}],
                     "text": d.nom},
            "subject": _ref(pac),
            "onsetDateTime": d.data.isoformat(),
        })
    for i, m in enumerate(dades.medicacions, 1):
        recursos.append({
            "resourceType": "MedicationStatement",
            "id": f"{pac.id}-med-{i:02d}",
            "status": "active",
            "medicationCodeableConcept": {"coding": [{"system": "http://www.whocc.no/atc", "code": m.codi_atc,
                                                      "display": m.nom}], "text": m.nom},
            "subject": _ref(pac),
            "effectivePeriod": {"start": m.data_inici.isoformat()},
        })
    return {
        "resourceType": "Bundle",
        "id": f"bundle-{pac.id}",
        "type": "collection",
        "timestamp": f"{DATA_REF.isoformat()}T00:00:00+01:00",  # data de referència de l'extracció
        "entry": [{"fullUrl": f"urn:cardioalert:{r['resourceType']}/{r['id']}", "resource": r} for r in recursos],
    }


def escriu_fhir(pacients: list[DadesPacient], carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    for vell in carpeta.glob("*.json"):
        vell.unlink()
    for dades in pacients:
        text = json.dumps(bundle_fhir(dades), ensure_ascii=False, indent=1)
        (carpeta / f"{dades.pacient.id}.json").write_text(text + "\n", encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Sortida CSV
# ---------------------------------------------------------------------------

def _escriu_csv(cami: Path, capcalera: list[str], files: list[list]) -> None:
    with cami.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(capcalera)
        w.writerows(files)


def escriu_csv(pacients: list[DadesPacient], carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    _escriu_csv(carpeta / "patients.csv", ["id", "nom", "data_naixement", "edat", "sexe", "fumador"],
                [[d.pacient.id, d.pacient.nom, d.pacient.data_naixement.isoformat(), d.pacient.edat, d.pacient.sexe,
                  int(d.pacient.fumador)] for d in pacients])
    _escriu_csv(carpeta / "observations.csv", ["pacient_id", "codi_loinc", "nom", "valor", "unitat", "data"],
                [[d.pacient.id, a.codi_loinc, a.nom, a.valor, a.unitat, a.data.isoformat()]
                 for d in pacients for a in d.analitiques])
    _escriu_csv(carpeta / "conditions.csv", ["pacient_id", "codi_ciap2", "codi_cie10", "nom", "data"],
                [[d.pacient.id, x.codi_ciap2, x.codi_cie10, x.nom, x.data.isoformat()]
                 for d in pacients for x in d.diagnostics])
    _escriu_csv(carpeta / "medications.csv", ["pacient_id", "nom", "codi_atc", "grup", "data_inici"],
                [[d.pacient.id, m.nom, m.codi_atc, m.grup, m.data_inici.isoformat()]
                 for d in pacients for m in d.medicacions])


def resum(pacients: list[DadesPacient]) -> str:
    n = len(pacients)
    linies = [f"{n} pacients generats (seed {SEED}), històric {INICI} - {DATA_REF}"]
    linies.append(f"  homes: {sum(d.pacient.sexe == 'H' for d in pacients)}  "
                  f"edat: {min(d.pacient.edat for d in pacients)}-{max(d.pacient.edat for d in pacients)}  "
                  f"fumadors: {sum(d.pacient.fumador for d in pacients)}")
    for clau, dx in DIAGNOSTICS.items():
        linies.append(f"  {dx.nom}: {sum(d.te_diagnostic(dx.ciap2) for d in pacients)}")
    linies.append(f"  sense factors de risc: {sum(not d.diagnostics and not d.pacient.fumador for d in pacients)}")
    linies.append(f"  analítiques: {sum(len(d.analitiques) for d in pacients)}  "
                  f"medicacions: {sum(len(d.medicacions) for d in pacients)}")
    return "\n".join(linies)


def main() -> None:
    pacients = genera()
    escriu_fhir(pacients, SORTIDA / "fhir")
    escriu_csv(pacients, SORTIDA / "csv")
    print(resum(pacients))
    print(f"Sortida: {SORTIDA / 'fhir'} i {SORTIDA / 'csv'}")


if __name__ == "__main__":
    main()
