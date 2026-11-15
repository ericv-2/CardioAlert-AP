"""El motor contra els exemples publicats als articles originals de les escales.

Si un valor no coincideix, NO es toca cap fórmula: el test es marca com a xfail amb el valor obtingut.
"""
from __future__ import annotations

import pytest

from engine.escales import MGDL_PER_MMOL_COLESTEROL, EntradaRisc, score2

MMOL = MGDL_PER_MMOL_COLESTEROL  # el motor rep el colesterol en mg/dL; els articles el donen en mmol/L


@pytest.mark.parametrize("sexe, publicat", [("H", 5.9), ("D", 4.2)])
def test_score2_exemple_publicat(sexe, publicat):
    """SCORE2 working group, Eur Heart J 2021;42:2439-54 (doi 10.1093/eurheartj/ehab309): persona de 50 anys,
    fumadora, PAS 140 mmHg, colesterol total 5,5 mmol/L, HDL 1,3 mmol/L, regió de risc baix -> 5,9 % (home) i
    4,2 % (dona)."""
    e = EntradaRisc(edat=50, sexe=sexe, fumador=True, diabetis=False, pas=140, pad=None,
                    colesterol_total=5.5 * MMOL, hdl=1.3 * MMOL)
    r = score2(e, "baix")
    assert r.model == "SCORE2"
    assert r.risc == pytest.approx(publicat, abs=0.1)


@pytest.mark.skip(reason="Els «valors mitjans» dels factors de risc convencionals que fa servir l'exemple de "
                         "l'article (PAS, colesterol total i HDL) no són al repositori i no s'han d'inventar: "
                         "cal transcriure'ls de l'article abans d'activar el test.")
def test_score2_diabetes_exemple_publicat():
    """SCORE2-Diabetes, Eur Heart J 2023;44:2544-56 (doi 10.1093/eurheartj/ehad260): home de 60 anys, no fumador,
    factors de risc convencionals mitjans, HbA1c 50 mmol/mol, FGe 90, edat al diagnòstic 60 anys, regió de risc
    moderat -> 11 %. El motor admet la regió moderada (`score2(e, "moderat")`).

    Quan es coneguin els valors mitjans de l'article, cal omplir PAS, colesterol total i HDL i treure el skip."""
    pas = colesterol_mmol = hdl_mmol = None  # valors mitjans de l'article: pendents de transcriure
    hba1c_pct = 50 / 10.929 + 2.15  # 50 mmol/mol (IFCC) -> % (NGSP), la conversió inversa de la del motor
    e = EntradaRisc(edat=60, sexe="H", fumador=False, diabetis=True, pas=pas, pad=None,
                    colesterol_total=colesterol_mmol * MMOL, hdl=hdl_mmol * MMOL,
                    hba1c=hba1c_pct, fge=90, edat_dx_diabetis=60)
    r = score2(e, "moderat")
    assert r.model == "SCORE2-Diabetes"
    assert r.risc == pytest.approx(11, abs=0.5)
