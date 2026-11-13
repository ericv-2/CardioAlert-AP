"""Fórmules clíniques compartides."""
from __future__ import annotations

from datetime import date


def edat_en(data_naixement: date, quan: date) -> int:
    """Edat en anys complerts en una data."""
    anys = quan.year - data_naixement.year
    if (quan.month, quan.day) < (data_naixement.month, data_naixement.day):
        anys -= 1
    return anys


def _params(sexe: str) -> tuple[float, float, float]:
    # (kappa, alfa, factor de sexe) de CKD-EPI 2021
    return (0.7, -0.241, 1.012) if sexe == "D" else (0.9, -0.302, 1.0)


def ckd_epi_2021(creatinina_mg_dl: float, edat: int, sexe: str) -> float:
    """FGe (mL/min/1,73m²) amb CKD-EPI 2021 (creatinina, sense coeficient de raça)."""
    kappa, alfa, f_sexe = _params(sexe)
    r = creatinina_mg_dl / kappa
    return 142 * min(r, 1) ** alfa * max(r, 1) ** -1.200 * 0.9938**edat * f_sexe


def creatinina_per_fge(fge: float, edat: int, sexe: str) -> float:
    """Inversa de CKD-EPI 2021: creatinina (mg/dL) que dona un FGe determinat."""
    kappa, alfa, f_sexe = _params(sexe)
    ratio = fge / (142 * 0.9938**edat * f_sexe)
    if ratio <= 1:
        return kappa * ratio ** (-1 / 1.200)
    return kappa * ratio ** (1 / alfa)
