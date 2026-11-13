"""Càlculs renals purs (sense estat ni configuració): KDIGO, cronicitat, pendent del FGe i KFRE.

Tots els llindars configurables arriben com a paràmetres des de config/rules.yaml.
Els talls de la matriu KDIGO són la definició de les categories i per això són constants.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Callable


@dataclass(frozen=True)
class Mesura:
    data: date
    valor: float
    origen: str | None = None  # sistema d'origen (eCAP, DIRAYA, Lab. Hospital...)


def categoria_g(fge: float) -> str:
    """Categoria KDIGO de filtrat (G1-G5)."""
    if fge >= 90:
        return "G1"
    if fge >= 60:
        return "G2"
    if fge >= 45:
        return "G3a"
    if fge >= 30:
        return "G3b"
    if fge >= 15:
        return "G4"
    return "G5"


def categoria_a(uacr: float) -> str:
    """Categoria KDIGO d'albuminúria (A1 < 30, A2 30-300, A3 > 300 mg/g)."""
    if uacr < 30:
        return "A1"
    if uacr <= 300:
        return "A2"
    return "A3"


# Risc de la matriu KDIGO (mapa de colors): verd < groc < taronja < vermell
_MATRIU = {
    "G1": ("verd", "groc", "taronja"),
    "G2": ("verd", "groc", "taronja"),
    "G3a": ("groc", "taronja", "vermell"),
    "G3b": ("taronja", "vermell", "vermell"),
    "G4": ("vermell", "vermell", "vermell"),
    "G5": ("vermell", "vermell", "vermell"),
}
RISC_KDIGO_TEXT = {"verd": "riesgo bajo", "groc": "riesgo moderado", "taronja": "riesgo alto",
                   "vermell": "riesgo muy alto"}


def risc_kdigo(g: str, a: str | None) -> str:
    """Color de la matriu KDIGO. Sense UACR (a=None) s'assumeix A1 (el risc real pot ser superior)."""
    return _MATRIU[g][("A1", "A2", "A3").index(a or "A1")]


def confirmat(serie: list[Mesura], anormal: Callable[[float], bool], min_mesures: int, min_dies: int) -> bool:
    """Cronicitat: l'última mesura és anormal i n'hi ha prou d'anormals separades >= min_dies."""
    if not serie or not anormal(serie[-1].valor):
        return False
    anormals = [m for m in serie if anormal(m.valor)]
    return len(anormals) >= min_mesures and (anormals[-1].data - anormals[0].data).days >= min_dies


def pendent_anual(serie: list[Mesura], min_mesures: int, min_dies: int) -> float | None:
    """Pendent del FGe (mL/min/1,73m² per any) per regressió lineal de mínims quadrats.

    Retorna None si no hi ha prou mesures o prou seguiment. Negatiu = pèrdua de filtrat.
    """
    if len(serie) < min_mesures or (serie[-1].data - serie[0].data).days < min_dies:
        return None
    xs = [(m.data - serie[0].data).days / 365.25 for m in serie]
    ys = [m.valor for m in serie]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else None


def caiguda_recent_pct(serie: list[Mesura], max_dies: int) -> float | None:
    """Caiguda (%) de l'última mesura respecte de l'anterior, si estan separades <= max_dies."""
    if len(serie) < 2:
        return None
    anterior, ultima = serie[-2], serie[-1]
    if (ultima.data - anterior.data).days > max_dies or anterior.valor <= 0:
        return None
    return (anterior.valor - ultima.valor) / anterior.valor * 100


def kfre_5_anys(edat: int, sexe: str, fge: float, uacr: float) -> float:
    """KFRE de 4 variables: risc (%) de fallida renal a 5 anys (Tangri 2016, calibratge no nord-americà).

    Només té sentit amb FGe < 60. uacr en mg/g.
    """
    lp = (-0.2201 * (edat / 10 - 7.036)
          + 0.2467 * ((1 if sexe == "H" else 0) - 0.5642)
          - 0.5567 * (fge / 5 - 7.222)
          + 0.4510 * (math.log(max(uacr, 1.0)) - 5.137))
    return (1 - 0.9365 ** math.exp(lp)) * 100
