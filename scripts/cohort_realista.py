"""Perfil "realista" del generador: un cupo d'atenció primària calibrat amb dades epidemiològiques.

    python scripts/generate_patients.py --perfil realista --n 1500

Genera PACIENTS INDIVIDUALS (cadascun amb el seu historial de 4 anys) de manera que les prevalences
agregades, estratificades per edat i sexe, s'acostin a:
- Factors de risc: cohort REGICOR (De Gano et al., Int J Epidemiol 2025, doi 10.1093/ije/dyaf116).
- Malaltia renal crònica: estudi ENRICA (Gorostidi et al., Nefrología 2018, doi 10.1016/j.nefro.2018.04.004).

Tots els paràmetres són a config/cohort_realista.yaml; fonts i resultats a docs/cohort_realista.md.
Sortida: data/realista/fhir, data/realista/csv i data/realista/veritat.csv (el que el generador "sap" de
cada pacient: MRC real, tipus, si està diagnosticada...). NOMÉS EN LOCAL: no es puja a cap servidor.
"""
from __future__ import annotations

import csv
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

ARREL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ARREL))

from model import Analitica, DadesPacient, Pacient  # noqa: E402
from model.cataleg import PROVES  # noqa: E402
from model.formules import ckd_epi_2009, ckd_epi_2021, edat_en  # noqa: E402
from scripts.generate_patients import (  # noqa: E402
    COGNOMS, DATA_REF, INICI, NOMS_D, NOMS_H, ORIGEN_AP, ORIGEN_HOSPITAL, _feiner, diagnostic, medicacio)

CONFIG = ARREL / "config" / "cohort_realista.yaml"
SORTIDA = ARREL / "data" / "realista"
ALTRES_COMUNITATS = ["DIRAYA - Andalucía", "SERGAS - Galicia", "Osabide - Euskadi", "Abucasis - Comunitat Valenciana"]
FACTORS = ("hta", "dm2", "dislipemia", "fumador")
IMC_OBESITAT = 30.0


@dataclass
class Perfil:
    """El que el generador decideix de cada pacient abans d'escriure'n l'historial (la "veritat")."""

    id: str
    nom: str
    edat: int
    sexe: str
    z: float  # predisposició cardiometabòlica latent: fa que els factors s'acumulin en els mateixos pacients
    hta: bool = False
    dm2: bool = False
    dislipemia: bool = False
    fumador: bool = False
    imc: float = 0.0
    mrc: bool = False  # MRC real (per filtrat i/o albuminúria)
    mrc_tipus: str = ""  # "filtrat" | "albuminuria" | "ambdues"
    mrc_estadi: str = ""  # G3a..G5 si és per filtrat
    mrc_dx: bool = False  # diagnòstic registrat
    ic: bool = False
    ic_dx: bool = False
    fra: bool = False  # caiguda aguda del FGe a l'última analítica
    seguiment: str = ""  # cronic | sa | nomes_pressio | cap
    n_visites: int = 0
    extres: dict = field(default_factory=dict)

    @property
    def n_factors(self) -> int:
        return self.hta + self.dm2 + self.dislipemia + self.fumador + (self.imc >= IMC_OBESITAT)

    @property
    def cronic(self) -> bool:
        return self.hta or self.dm2 or self.dislipemia or self.mrc_dx or self.ic_dx


def carrega_config(cami: Path = CONFIG) -> dict:
    return yaml.safe_load(cami.read_text(encoding="utf-8"))


def _tram(trams: list[dict], edat: int, clau: str):
    return next(t[clau] for t in trams if edat <= t["edat_max"])


def _quota(perfils: list[Perfil], puntuacio, k: int) -> list[Perfil]:
    """Els k pacients amb més puntuació (quota exacta, en lloc d'un sorteig independent per pacient)."""
    return sorted(perfils, key=puntuacio, reverse=True)[:max(0, min(k, len(perfils)))]


class _Repartidor:
    """Arrodoniment acumulat: reparteix quotes entre estrats sense que l'error d'arrodonir es vagi sumant."""

    def __init__(self):
        self.acumulat = 0.0
        self.assignats = 0

    def quota(self, esperat: float) -> int:
        self.acumulat += esperat
        k = round(self.acumulat) - self.assignats
        self.assignats += k
        return k


def _per_sexe(prevalenca: float, rao: float, n_h: int, n_d: int) -> dict[str, float]:
    """Prevalença (0-1) d'homes i dones d'un grup, amb raó home/dona `rao` i mitjana del grup `prevalenca`."""
    if n_h + n_d == 0:
        return {"H": 0.0, "D": 0.0}
    p_d = prevalenca * (n_h + n_d) / (n_h * rao + n_d)
    p_h = p_d * rao
    if p_h > 0.97:  # el que no hi cap en els homes passa a les dones
        p_h = 0.97
        p_d = (prevalenca * (n_h + n_d) - p_h * n_h) / n_d if n_d else 0.0
    return {"H": p_h, "D": min(0.97, p_d)}


# ---------------------------------------------------------------------------
# 1) Demografia, factors de risc, MRC i IC
# ---------------------------------------------------------------------------

def _demografia(rng: random.Random, cfg: dict, n: int) -> list[Perfil]:
    rep = _Repartidor()
    total = sum(e["pes"] for e in cfg["edats"])
    perfils, usats = [], set()
    for e in cfg["edats"]:
        k = rep.quota(n * e["pes"] / total)
        dones = round(k * e["dones"] / 100)
        for i in range(k):
            sexe = "D" if i < dones else "H"
            while True:
                nom = f"{rng.choice(NOMS_D if sexe == 'D' else NOMS_H)} {rng.choice(COGNOMS)} {rng.choice(COGNOMS)}"
                if nom not in usats:
                    usats.add(nom)
                    break
            perfils.append(Perfil("", nom, rng.randint(e["min"], e["max"]), sexe, rng.gauss(0, 1)))
    rng.shuffle(perfils)
    for i, p in enumerate(perfils, 1):
        p.id = f"R{i:04d}"
    return perfils


def _factors_de_risc(rng: random.Random, cfg: dict, perfils: list[Perfil]) -> None:
    f = cfg["factors"]
    for factor in FACTORS:
        rho = f["correlacio_tabac"] if factor == "fumador" else f["correlacio"]
        rep = _Repartidor()
        for (emin, emax), prev in zip(f["bandes"], f[factor]["prevalenca"]):
            grup = [p for p in perfils if emin <= p.edat <= emax]
            mig = (emin + min(emax, 90)) / 2
            per_sexe = _per_sexe(prev / 100, f[factor]["rao_home_dona"], sum(p.sexe == "H" for p in grup),
                                 sum(p.sexe == "D" for p in grup))
            for sexe in ("H", "D"):
                estrat = [p for p in grup if p.sexe == sexe]
                # Dins del grup d'edat, més probable com més edat (tret del tabac) i més predisposició
                pendent = 0.0 if factor == "fumador" else 0.06
                punts = {p.id: rho * p.z + math.sqrt(1 - rho**2) * rng.gauss(0, 1) + pendent * (p.edat - mig)
                         for p in estrat}
                for p in _quota(estrat, lambda p: punts[p.id], rep.quota(len(estrat) * per_sexe[sexe])):
                    setattr(p, factor, True)


def _imc(rng: random.Random, cfg: dict, perfils: list[Perfil]) -> None:
    """IMC: 25,8 de mitjana en els sans de 35-54 anys; la resta es desplaça perquè el total doni l'objectiu."""
    obj = cfg["objectius"]
    base = obj["sans_35_54"]["imc"]
    for p in perfils:
        p.imc = base + 3.8 * (0.5 * p.z + math.sqrt(0.75) * rng.gauss(0, 1))
        if p.edat < 35:
            p.imc -= 0.07 * (35 - p.edat)
    referencia = [p for p in perfils if _es_sa_35_54(p)]
    desviacio = base - sum(p.imc for p in referencia) / len(referencia)
    for p in referencia:  # el grup de referència queda centrat a la xifra de la taula
        p.imc += desviacio
    resta = [p for p in perfils if not _es_sa_35_54(p)]
    for p in resta:
        p.imc += 1.6 * p.dm2 + 1.0 * p.hta + 0.5 * p.dislipemia
    falta = obj["regicor_global"]["imc"] * len(perfils) - sum(p.imc for p in perfils)
    for p in resta:
        p.imc += falta / len(resta)
    for p in perfils:
        p.imc = round(max(17.0, min(48.0, p.imc)), 1)


def _es_sa_35_54(p: Perfil) -> bool:
    """Grup de referència de la taula 1: 35-54 anys sense patologia (pot fumar)."""
    return 35 <= p.edat <= 54 and not (p.hta or p.dm2 or p.dislipemia or p.mrc or p.ic)


def _mrc(rng: random.Random, cfg: dict, perfils: list[Perfil]) -> None:
    m = cfg["mrc"]
    rep = _Repartidor()
    for banda in cfg["objectius"]["enrica"]["per_edat"]:
        grup = [p for p in perfils if banda["min"] <= p.edat <= banda["max"]]
        mig = (banda["min"] + min(banda["max"], 90)) / 2
        per_sexe = _per_sexe(banda["pct"] / 100, m["rao_home_dona"], sum(p.sexe == "H" for p in grup),
                             sum(p.sexe == "D" for p in grup))
        for sexe in ("H", "D"):
            estrat = [p for p in grup if p.sexe == sexe]
            # Els factors de risc s'acumulen: com més en té el pacient, més probable és la MRC
            punts = {p.id: m["pes_factors"] * p.n_factors + 0.05 * (p.edat - mig) + rng.gauss(0, 1) for p in estrat}
            for p in _quota(estrat, lambda p: punts[p.id], rep.quota(len(estrat) * per_sexe[sexe])):
                p.mrc = True
    amb_mrc = [p for p in perfils if p.mrc]
    estadis, pesos = list(m["estadis"]), list(m["estadis"].values())
    for p in amb_mrc:
        if rng.random() < _tram(m["prob_per_filtrat"], p.edat, "p"):
            p.mrc_tipus = "ambdues" if rng.random() < m["prob_filtrat_amb_albuminuria"] else "filtrat"
            p.mrc_estadi = rng.choices(estadis, pesos)[0]
        else:
            p.mrc_tipus = "albuminuria"
    # Diagnòstic registrat: com més avançada, més probable; el total queda fixat per la proporció configurada
    pes_dx = {"G5": 12.0, "G4": 8.0, "G3b": 3.0, "G3a": 1.0, "": 0.7}
    n_dx = round(len(amb_mrc) * (1 - m["proporcio_sense_diagnostic"]))
    claus = {p.id: rng.random() ** (1 / pes_dx[p.mrc_estadi]) for p in amb_mrc}
    for p in _quota(amb_mrc, lambda p: claus[p.id], n_dx):
        p.mrc_dx = True


def _ic(rng: random.Random, cfg: dict, perfils: list[Perfil]) -> None:
    c = cfg["ic"]
    pesos = {p.id: _tram(c["pes_per_edat"], p.edat, "pes") * (1 + 1.5 * p.hta + 1.5 * p.mrc + 1.0 * p.dm2)
             for p in perfils}
    claus = {p.id: rng.random() ** (1 / pesos[p.id]) for p in perfils}
    amb_ic = _quota(perfils, lambda p: claus[p.id], round(len(perfils) * c["prevalenca_global"] / 100))
    for p in amb_ic:
        p.ic = True
    for p in rng.sample(amb_ic, round(len(amb_ic) * (1 - c["proporcio_sense_diagnostic"]))):
        p.ic_dx = True


def genera_perfils(cfg: dict, n: int | None = None, llavor: int | None = None) -> list[Perfil]:
    rng = random.Random(cfg["llavor"] if llavor is None else llavor)
    perfils = _demografia(rng, cfg, n or cfg["n_pacients"])
    _factors_de_risc(rng, cfg, perfils)
    _imc(rng, cfg, perfils)
    _mrc(rng, cfg, perfils)
    _ic(rng, cfg, perfils)
    return perfils


# ---------------------------------------------------------------------------
# 2) Historial de cada pacient
# ---------------------------------------------------------------------------

def _gauss(rng: random.Random, mitjana: float, sd: float, minim: float, maxim: float) -> float:
    return max(minim, min(maxim, rng.gauss(mitjana, sd)))


def _soroll(rng: random.Random, sd: float, limit: float) -> float:
    return max(-limit, min(limit, rng.gauss(0, sd)))


def creatinina_per_fge_2009(fge: float, edat: int, sexe: str) -> float:
    """Creatinina (mg/dL) que dona un FGe determinat amb CKD-EPI 2009 (l'equació del motor), per bisecció."""
    baix, alt = 0.2, 15.0
    for _ in range(50):
        mig = (baix + alt) / 2
        if ckd_epi_2009(mig, edat, sexe) > fge:
            baix = mig
        else:
            alt = mig
    return (baix + alt) / 2


def _a(clau: str, valor: float, data: date, origen: str) -> Analitica:
    p = PROVES[clau]
    return Analitica(p.loinc, p.nom, float(valor), p.unitat, data, origen)


def _dates(rng: random.Random, cfg: dict, p: Perfil) -> list[date]:
    s = cfg["seguiment"]
    if p.cronic:
        p.seguiment = "cronic"
        antiga = rng.random() < s["cronics_amb_analitica_antiga"]
        ultima = DATA_REF - timedelta(days=rng.randint(400, 700) if antiga else rng.randint(10, 300))
        interval = (180, 365)
    else:
        if rng.random() < _tram(s["sense_cap_analitica"], p.edat, "p"):
            p.seguiment = "cap"
            return []
        p.seguiment = "nomes_pressio" if p.edat >= 40 and rng.random() < s["nomes_pressio"] else "sa"
        ultima = DATA_REF - timedelta(days=rng.randint(20, 900))
        interval = (500, 1000) if p.edat >= 50 else (700, 1400)
    dates = [ultima]
    while True:
        anterior = dates[-1] - timedelta(days=rng.randint(*interval))
        if anterior < INICI:
            break
        dates.append(anterior)
    return sorted(_feiner(d) for d in dates)


def _tractament(rng: random.Random, cfg: dict, p: Perfil, dx_data: dict[str, date]) -> list:
    t = cfg["tractament"]
    meds: list[tuple[str, str, str]] = []  # (nom, atc, diagnòstic que el justifica)
    if p.dm2:
        if rng.random() < t["dm2"]["metformina"]:
            meds.append(("Metformina", "A10BA02", "dm2"))
        if rng.random() < t["dm2"]["aglp1"]:
            meds.append(rng.choice([("Semaglutida", "A10BJ06"), ("Dulaglutida", "A10BJ05")]) + ("dm2",))
        if rng.random() < t["dm2"]["insulina"]:
            meds.append(("Insulina glargina", "A10AE04", "dm2"))
    p_isglt2, motiu_isglt2 = 0.0, None
    if p.dm2:
        p_isglt2, motiu_isglt2 = (t["dm2"]["isglt2_amb_mrc_o_ic"] if p.mrc_dx or p.ic_dx else t["dm2"]["isglt2"]), "dm2"
    elif p.ic_dx:
        p_isglt2, motiu_isglt2 = t["ic"]["isglt2"], "ic"
    elif p.mrc_dx:
        p_isglt2, motiu_isglt2 = t["mrc_diagnosticada"]["isglt2"], "mrc"
    if motiu_isglt2 and rng.random() < p_isglt2:
        meds.append(rng.choice([("Empagliflozina", "A10BK03"), ("Dapagliflozina", "A10BK01")]) + (motiu_isglt2,))
    p_sraa, motiu_sraa = max([(t["ic"]["sraa"], "ic")] * p.ic_dx + [(t["mrc_diagnosticada"]["sraa"], "mrc")] * p.mrc_dx
                             + [(t["hta"]["sraa"], "hta")] * p.hta + [(0.0, None)])
    te_sraa = bool(motiu_sraa) and rng.random() < p_sraa
    if te_sraa:
        ieca = rng.random() < 0.55
        meds.append(rng.choice([("Enalapril", "C09AA02"), ("Ramipril", "C09AA05")] if ieca else
                               [("Losartán", "C09CA01"), ("Valsartán", "C09CA03"), ("Candesartán", "C09CA06")])
                    + (motiu_sraa,))
    if p.hta:
        tiazida = rng.random() < t["hta"]["tiazida"]
        calci = rng.random() < t["hta"]["antagonista_calci"]
        p_cap = (1 - t["hta"]["sraa"]) * (1 - t["hta"]["tiazida"]) * (1 - t["hta"]["antagonista_calci"])
        if not (te_sraa or tiazida or calci) and rng.random() >= t["hta"]["sense_tractament"] / p_cap:
            tiazida = True  # només queda sense tractament la proporció configurada d'hipertensos
        if tiazida:
            meds.append(("Hidroclorotiazida", "C03AA03", "hta"))
        if calci:
            meds.append(("Amlodipino", "C08CA01", "hta"))
    if p.dislipemia and rng.random() < t["dislipemia"]["estatina"]:
        meds.append(rng.choice([("Atorvastatina", "C10AA05"), ("Simvastatina", "C10AA01"),
                                ("Rosuvastatina", "C10AA07")]) + ("dislipemia",))
    if p.dm2 and p.mrc_dx and rng.random() < t["mrc_diagnosticada"]["finerenona_amb_dm2"]:
        meds.append(("Finerenona", "C03DA05", "mrc"))
    if (p.dm2 or p.hta) and p.edat >= 60 and rng.random() < t["aas_prevencio_primaria"]:
        meds.append(("Ácido acetilsalicílico", "B01AC06", "dm2" if p.dm2 else "hta"))

    res = []
    for nom, atc, motiu in meds:
        inici = dx_data[motiu] + timedelta(days=rng.randint(7, 720))
        if atc.startswith("A10BK") or atc == "C03DA05":  # fàrmacs recents
            inici = max(inici, date(2021, 1, 1) + timedelta(days=rng.randint(0, 1500)))
        res.append(medicacio(nom, atc, _feiner(min(inici, DATA_REF - timedelta(days=30)))))
    return res


def _mode_uacr(rng: random.Random, cfg: dict, p: Perfil) -> str:
    u = cfg["seguiment"]["uacr"]
    pesos = u["mrc_diagnosticada"] if p.mrc_dx else u["dm2"] if p.dm2 else u["hta"] if p.hta else None
    if pesos:
        return rng.choices(["anual", "antic", "mai"], pesos)[0]
    return "una" if rng.random() < u["altres_alguna_vegada"] else "mai"


def historial(rng: random.Random, cfg: dict, p: Perfil) -> DadesPacient:
    sans = cfg["objectius"]["sans_35_54"]
    s = cfg["seguiment"]
    m = cfg["mrc"]
    naixement = DATA_REF - timedelta(days=round(p.edat * 365.25) + rng.randint(5, 355))
    pac = Pacient(p.id, p.nom, edat_en(naixement, DATA_REF), p.sexe, p.fumador, naixement)
    assert pac.edat == p.edat
    dades = DadesPacient(pac)

    # Diagnòstics registrats (la MRC i la IC sense diagnosticar no hi consten) i tractament
    dx_data: dict[str, date] = {}
    for clau, te in (("hta", p.hta), ("dm2", p.dm2), ("dislipemia", p.dislipemia), ("mrc", p.mrc_dx), ("ic", p.ic_dx)):
        if te:
            maxim = min(6.0 if clau in ("mrc", "ic") else 15.0, max(1.5, p.edat - 18.0))
            dx_data[clau] = _feiner(DATA_REF - timedelta(days=round(rng.uniform(1, maxim) * 365)))
            dades.diagnostics.append(diagnostic(clau, dx_data[clau]))
    if p.fumador:
        anys = rng.uniform(2, max(3.0, min(20.0, p.edat - 16.0)))
        dades.diagnostics.append(diagnostic("tabac", _feiner(DATA_REF - timedelta(days=round(anys * 365)))))
    dades.medicacions = _tractament(rng, cfg, p, dx_data)
    grups = {x.grup for x in dades.medicacions}
    antihipertensiu = bool(grups & {"IECA", "ARA-II", "tiazida", "antagonista_calcio"})

    # Valors basals. Els sans de 35-54 anys queden centrats a la taula 1 de REGICOR (enquesta 2018).
    edat = p.edat
    if p.dislipemia:
        ldl0 = _gauss(rng, 100, 24, 45, 170) if "estatina" in grups else _gauss(rng, 165, 22, 120, 240)
        tg0 = 135 * math.exp(_soroll(rng, 0.35, 0.8))
    else:
        ldl0 = _gauss(rng, sans["ldl"] - 0.9 * max(0, 35 - edat) + 0.15 * max(0, min(edat, 80) - 54), 27, 60, 189)
        tg_sans = (sans["colesterol_total"] - sans["ldl"] - sans["hdl"]) * 5  # coherent amb Friedewald
        tg0 = tg_sans / math.exp(0.35**2 / 2) * math.exp(_soroll(rng, 0.35, 0.9)) * (1.4 if p.dm2 else 1.0)
    hdl0 = _gauss(rng, sans["hdl"] + (6 if p.sexe == "D" else -6) - (4 if p.dm2 else 0), 11, 28, 95)
    if p.hta:
        pas0, pad0 = ((_gauss(rng, 136, 12, 108, 178), _gauss(rng, 80, 8, 60, 104)) if antihipertensiu
                      else (_gauss(rng, 150, 10, 132, 185), _gauss(rng, 90, 7, 74, 110)))
    else:
        pas0 = _gauss(rng, sans["pas"] + 0.45 * (min(edat, 85) - 45), 10, 88, 150)
        pad0 = _gauss(rng, sans["pad"] + 0.10 * (min(edat, 85) - 45), 7, 54, 92)
    hba1c0 = _gauss(rng, 7.2, 1.0, 6.0, 11.0) if p.dm2 else _gauss(rng, 5.4, 0.3, 4.6, 6.3)
    glucosa0 = _gauss(rng, sans["glucosa"], 8, 70, 122)

    per_filtrat = p.mrc_tipus in ("filtrat", "ambdues")
    if per_filtrat:
        rang = {"G3a": (45, 55.5), "G3b": (30, 44), "G4": (16, 29), "G5": (9, 14)}[p.mrc_estadi]
        fge_ara = rng.uniform(*rang)
        descens = rng.uniform(5.5, 8.0) if rng.random() < m["prob_descens_rapid"] else rng.uniform(0.5, 3.0)
    else:
        fge_ara = _gauss(rng, 124 - 0.62 * edat, 9, 66, 122)
        descens = rng.uniform(0.3, 1.0)  # descens fisiològic
    if p.mrc_tipus in ("albuminuria", "ambdues"):
        uacr0 = (math.exp(rng.uniform(math.log(320), math.log(1800))) if rng.random() < m["prob_albuminuria_a3"]
                 else math.exp(rng.uniform(math.log(40), math.log(280))))
    else:
        uacr0 = min(22.0, max(2.5, 6 * math.exp(rng.gauss(0, 0.6))))
    k0 = _gauss(rng, 4.3 + (0.3 if per_filtrat else 0), 0.3, 3.6, 5.6)

    # Visites: quines proves es fan en cadascuna
    dates = _dates(rng, cfg, p)
    p.n_visites = len(dates)
    mode_uacr = _mode_uacr(rng, cfg, p)
    amb_uacr: set[date] = set()
    if mode_uacr in ("anual", "antic") and dates:
        seguent = None
        for d in reversed(dates):
            if seguent is None or (seguent - d).days >= 300:
                amb_uacr.add(d)
                seguent = d
        if mode_uacr == "antic":  # només se'n conserva l'últim de fa més de 14 mesos (si n'hi ha cap)
            antigues = [d for d in dates if (DATA_REF - d).days > 420]
            amb_uacr = {max(antigues)} if antigues else set()
    elif mode_uacr == "una" and dates:
        amb_uacr = {rng.choice(dates)}
    ntprobnp0, dates_nt = None, set()
    if p.ic and dates and (p.ic_dx or rng.random() < 0.6):  # IC sense diagnosticar: no sempre s'ha demanat
        ntprobnp0 = math.exp(rng.uniform(math.log(600), math.log(3500)))
        dates_nt = set(dates[-1:]) | ({d for i, d in enumerate(dates) if i % 2 == 0} if p.ic_dx else set())
    elif p.cronic and edat >= 60 and dates and rng.random() < s["ntprobnp_en_cronics_60"]:
        ntprobnp0 = 60 * math.exp(rng.gauss(0, 0.5)) if rng.random() < 0.9 else rng.uniform(130, 420)
        dates_nt = {rng.choice(dates)}
    altra = rng.choice(dates) if len(dates) >= 2 and rng.random() < s["altra_comunitat"] else None
    altra_origen = rng.choice(ALTRES_COMUNITATS)
    p.fra = (not per_filtrat and len(dates) >= 2 and (dates[-1] - dates[-2]).days < 500
             and rng.random() < s["caiguda_aguda"])

    for i, d in enumerate(dates):
        origen = altra_origen if d == altra else ORIGEN_AP
        edat_d = edat_en(naixement, d)
        res = [_a("pas", round(pas0 + _soroll(rng, 5, 10)), d, origen),
               _a("pad", round(pad0 + _soroll(rng, 3.5, 7)), d, origen),
               _a("imc", round(p.imc + _soroll(rng, 0.3, 0.6), 1), d, origen)]
        if p.seguiment != "nomes_pressio":
            anys_fins_ara = (DATA_REF - d).days / 365.25
            fge_obj = max(7.0, fge_ara + descens * anys_fins_ara)
            creat = creatinina_per_fge_2009(fge_obj, edat_d, p.sexe) * (1 + _soroll(rng, 0.015, 0.03))
            if p.fra and i == len(dates) - 1:
                creat *= rng.uniform(1.6, 2.1)
            creat = round(creat, 2)
            ldl = round(ldl0 * (1 + _soroll(rng, 0.05, 0.12)))
            hdl = round(hdl0 * (1 + _soroll(rng, 0.04, 0.10)))
            tg = round(tg0 * (1 + _soroll(rng, 0.10, 0.25)))
            if p.dm2:
                hba1c = max(5.8, hba1c0 + _soroll(rng, 0.2, 0.4))
                glucosa = 28.7 * hba1c - 46.7 + _soroll(rng, 8, 15)
            else:
                hba1c = hba1c0 + _soroll(rng, 0.1, 0.2) if (p.cronic or edat >= 45) and rng.random() < 0.3 else None
                glucosa = min(124.0, glucosa0 + _soroll(rng, 5, 10))
            res += [
                _a("creatinina", creat, d, origen),
                _a("fge", round(ckd_epi_2021(creat, edat_d, p.sexe)), d, origen),  # el que informa el laboratori
                _a("glucosa", round(glucosa), d, origen),
                _a("colesterol_total", ldl + hdl + round(tg / 5), d, origen),
                _a("ldl", ldl, d, origen),
                _a("hdl", hdl, d, origen),
                _a("trigliceridos", tg, d, origen),
                _a("potasio", round(max(3.4, min(5.8, k0 + _soroll(rng, 0.15, 0.4))), 1), d, origen),
            ]
            if hba1c is not None:
                res.append(_a("hba1c", round(hba1c, 1), d, origen))
            if d in amb_uacr:
                res.append(_a("uacr", round(max(2.0, uacr0 * (1 + rng.uniform(-0.2, 0.2)))), d, origen))
            if d in dates_nt:
                res.append(_a("ntprobnp", round(ntprobnp0 * rng.uniform(0.8, 1.25)), d, ORIGEN_HOSPITAL))
        dades.analitiques += res
    p.extres = {"uacr": mode_uacr, "ntprobnp": bool(dates_nt)}
    return dades.ordena()


def genera(cfg: dict | None = None, n: int | None = None, llavor: int | None = None
           ) -> tuple[list[DadesPacient], list[Perfil]]:
    cfg = cfg or carrega_config()
    perfils = genera_perfils(cfg, n, llavor)
    rng = random.Random((cfg["llavor"] if llavor is None else llavor) + 1)
    return [historial(rng, cfg, p) for p in perfils], perfils


# ---------------------------------------------------------------------------
# 3) Sortida i resum
# ---------------------------------------------------------------------------

CAMPS_VERITAT = ["pacient_id", "edat", "sexe", "hta", "dm2", "dislipemia", "fumador", "imc", "n_factors", "mrc",
                 "mrc_tipus", "mrc_estadi", "mrc_dx", "ic", "ic_dx", "fra", "seguiment", "n_visites"]


def escriu_veritat(perfils: list[Perfil], cami: Path) -> None:
    with cami.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(CAMPS_VERITAT)
        for p in perfils:
            w.writerow([p.id, p.edat, p.sexe, int(p.hta), int(p.dm2), int(p.dislipemia), int(p.fumador), p.imc,
                        p.n_factors, int(p.mrc), p.mrc_tipus, p.mrc_estadi, int(p.mrc_dx), int(p.ic), int(p.ic_dx),
                        int(p.fra), p.seguiment, p.n_visites])


def llegeix_veritat(cami: Path = SORTIDA / "veritat.csv") -> list[dict]:
    """La "veritat" del generador, amb els tipus convertits (per als tests i per a docs/cohort_realista.md)."""
    enters = {"edat", "hta", "dm2", "dislipemia", "fumador", "n_factors", "mrc", "mrc_dx", "ic", "ic_dx", "fra",
              "n_visites"}
    with cami.open(encoding="utf-8", newline="") as f:
        return [{k: int(v) if k in enters else float(v) if k == "imc" else v for k, v in fila.items()}
                for fila in csv.DictReader(f)]


def pct(files: list[dict], clau: str) -> float:
    return 100 * sum(bool(f[clau]) for f in files) / len(files) if files else 0.0


def prevalences(veritat: list[dict], cfg: dict) -> list[tuple[str, float | None, float, int]]:
    """Files (indicador, objectiu, obtingut, n del grup) que es comparen a la documentació i als tests."""
    o = cfg["objectius"]
    g3554 = [f for f in veritat if 35 <= f["edat"] <= 54]
    noms = {"dm2": "Diabetis", "hta": "HTA", "dislipemia": "Hipercolesterolèmia", "fumador": "Fumadors actuals"}
    files = [(f"{noms[c]}, 35-54 anys (%)", o["regicor_35_54"][c], pct(g3554, c), len(g3554)) for c in noms]
    files += [(f"{noms[c]}, tota la cohort (%)", o["regicor_global"][c], pct(veritat, c), len(veritat)) for c in noms]
    files.append(("IMC mitjà, tota la cohort", o["regicor_global"]["imc"],
                  sum(f["imc"] for f in veritat) / len(veritat), len(veritat)))
    e = o["enrica"]
    for b in e["per_edat"]:
        grup = [f for f in veritat if b["min"] <= f["edat"] <= b["max"]]
        nom = f"{b['min']}-{b['max']} anys" if b["max"] < 100 else f"≥ {b['min']} anys"
        files.append((f"MRC, {nom} (%)", b["pct"], pct(grup, "mrc"), len(grup)))
    homes, dones = [f for f in veritat if f["sexe"] == "H"], [f for f in veritat if f["sexe"] == "D"]
    files.append(("MRC, homes (%)", e["homes"], pct(homes, "mrc"), len(homes)))
    files.append(("MRC, dones (%)", e["dones"], pct(dones, "mrc"), len(dones)))
    files.append(("MRC, tota la cohort (%)", e["global"], pct(veritat, "mrc"), len(veritat)))
    pocs = [f for f in veritat if f["n_factors"] <= 1]
    molts = [f for f in veritat if f["n_factors"] >= 4]
    files.append(("MRC amb 0-1 factors de risc (%)", e["factors_0_1"], pct(pocs, "mrc"), len(pocs)))
    files.append(("MRC amb 4-5 factors de risc (%)", e["factors_molts"], pct(molts, "mrc"), len(molts)))
    amb_mrc = [f for f in veritat if f["mrc"]]
    files.append(("MRC sense diagnòstic registrat (% de les MRC)", 100 * cfg["mrc"]["proporcio_sense_diagnostic"],
                  100 - pct(amb_mrc, "mrc_dx"), len(amb_mrc)))
    files.append(("Insuficiència cardíaca (%)", cfg["ic"]["prevalenca_global"], pct(veritat, "ic"), len(veritat)))
    return files


def mrc_estandarditzada(veritat: list[dict], cfg: dict) -> float:
    """MRC global esperada si s'apliquen les taxes per edat d'ENRICA a l'estructura d'edat d'aquesta cohort."""
    total = 0.0
    for b in cfg["objectius"]["enrica"]["per_edat"]:
        total += b["pct"] * sum(b["min"] <= f["edat"] <= b["max"] for f in veritat)
    return total / len(veritat)


def resum(veritat: list[dict], cfg: dict) -> str:
    linies = [f"{len(veritat)} pacients (llavor {cfg['llavor']}), històric {INICI} - {DATA_REF}",
              f"{'Indicador':52s} {'objectiu':>9s} {'obtingut':>9s} {'n':>6s}"]
    for nom, objectiu, obtingut, n in prevalences(veritat, cfg):
        linies.append(f"{nom:52s} {objectiu:9.1f} {obtingut:9.1f} {n:6d}")
    linies.append(f"MRC global esperada amb les taxes per edat d'ENRICA i aquesta estructura d'edat: "
                  f"{mrc_estandarditzada(veritat, cfg):.1f}%")
    return "\n".join(linies)
