"""Escales de risc cardiovascular: peça intercanviable del motor.

Cada escala és una funció `(EntradaRisc, regio) -> ResultatEscala | None` registrada a ESCALES.
Afegir una escala = afegir una funció i una entrada al registre; el motor no canvia.

- score2:  SCORE2 (40-69 anys), SCORE2-Diabetes (diabètics 40-69) i SCORE2-OP (>= 70 anys).
           Risc a 10 anys d'esdeveniment CV mortal o no mortal. Espanya = regió de risc baix.
- regicor: Framingham calibrada per a Espanya (Marrugat 2003), 35-74 anys. Risc coronari a 10 anys.

`ckd_addon` aplica el SCORE2 CKD Add-on (Matsushita et al., Eur J Prev Cardiol 2023): recalcula el
risc SCORE2/SCORE2-OP segons el FGe i l'UACR observats respecte dels esperats pel perfil.

Verificació: els coeficients de SCORE2, SCORE2-OP, SCORE2-Diabetes i del CKD Add-on s'han contrastat
amb el paquet R de codi obert RiskScorescvd (CRAN). Els de REGICOR estan transcrits de la publicació
original i verificats amb tests (vegeu docs/decisions.md).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

MGDL_PER_MMOL_COLESTEROL = 38.67


@dataclass(frozen=True)
class EntradaRisc:
    edat: int
    sexe: str  # "H" | "D"
    fumador: bool
    diabetis: bool
    pas: float  # mmHg
    pad: float | None  # mmHg (només REGICOR)
    colesterol_total: float  # mg/dL
    hdl: float  # mg/dL
    hba1c: float | None = None  # % (SCORE2-Diabetes)
    fge: float | None = None  # mL/min/1,73m² (SCORE2-Diabetes)
    edat_dx_diabetis: int | None = None  # anys (SCORE2-Diabetes)


@dataclass(frozen=True)
class ResultatEscala:
    model: str  # nom que es mostra: "SCORE2", "SCORE2-Diabetes", "SCORE2-OP", "REGICOR"
    risc: float  # % a 10 anys


# --- SCORE2 / SCORE2-Diabetes / SCORE2-OP ------------------------------------------------------

# Coeficients SCORE2 (Eur Heart J 2021;42:2439). Edat centrada a 60 (per 5 anys), PAS a 120 (per 20),
# colesterol total a 6 mmol/L, HDL a 1,3 (per 0,5).
_SCORE2 = {
    "H": dict(edat=0.3742, fum=0.6012, pas=0.2777, dm=0.6457, col=0.1458, hdl=-0.2698,
              fum_e=-0.0755, pas_e=-0.0255, col_e=-0.0281, hdl_e=0.0426, dm_e=-0.0983, s0=0.9605),
    "D": dict(edat=0.4648, fum=0.7744, pas=0.3131, dm=0.8096, col=0.1002, hdl=-0.2606,
              fum_e=-0.1088, pas_e=-0.0277, col_e=-0.0226, hdl_e=0.0613, dm_e=-0.1272, s0=0.9776),
}
# Coeficients SCORE2-Diabetes (Eur Heart J 2023;44:2544). Afegeix edat al diagnòstic (centrada a 50,
# per 5), HbA1c (mmol/mol, centrada a 31, per 9,34) i ln(FGe) (centrat a 4,5, per 0,15).
_SCORE2_DM = {
    "H": dict(edat=0.5368, fum=0.4774, pas=0.1322, dm=0.6457, col=0.1102, hdl=-0.1087,
              fum_e=-0.0672, pas_e=-0.0268, col_e=-0.0181, hdl_e=0.0095, dm_e=-0.0983,
              edat_dx=-0.0998, hba1c=0.0955, fge=-0.0591, fge2=0.0058, hba1c_e=-0.0134, fge_e=0.0115, s0=0.9605),
    "D": dict(edat=0.6624, fum=0.6139, pas=0.1421, dm=0.8096, col=0.1127, hdl=-0.1568,
              fum_e=-0.1122, pas_e=-0.0167, col_e=-0.0200, hdl_e=0.0186, dm_e=-0.1272,
              edat_dx=-0.1180, hba1c=0.1173, fge=-0.0640, fge2=0.0062, hba1c_e=-0.0196, fge_e=0.0169, s0=0.9776),
}
# Calibratge regional (escala1, escala2): risc = 1 - exp(-exp(e1 + e2 * ln(-ln(1 - risc_sense_calibrar))))
_CALIBRATGE = {
    "baix": {"H": (-0.5699, 0.7476), "D": (-0.7380, 0.7019)},
    "moderat": {"H": (-0.1565, 0.8009), "D": (-0.3143, 0.7701)},
    "alt": {"H": (0.3207, 0.9360), "D": (0.5710, 0.9369)},
    "molt_alt": {"H": (0.5836, 0.8294), "D": (0.9412, 0.8329)},
}
# Coeficients SCORE2-OP (Eur Heart J 2021;42:2455). Edat centrada a 73, PAS a 150, colesterol a 6, HDL a 1,4.
_SCORE2_OP = {
    "H": dict(edat=0.0634, dm=0.4245, fum=0.3524, pas=0.0094, col=0.0850, hdl=-0.3564,
              dm_e=-0.0174, fum_e=-0.0247, pas_e=-0.0005, col_e=0.0073, hdl_e=0.0091, s0=0.7576, mitjana=0.0929),
    "D": dict(edat=0.0789, dm=0.6010, fum=0.4921, pas=0.0102, col=0.0605, hdl=-0.3040,
              dm_e=-0.0107, fum_e=-0.0255, pas_e=-0.0004, col_e=-0.0009, hdl_e=0.0154, s0=0.8082, mitjana=0.2290),
}
_CALIBRATGE_OP = {
    "baix": {"H": (-0.34, 1.19), "D": (-0.52, 1.01)},
    "moderat": {"H": (0.01, 1.25), "D": (-0.10, 1.10)},
    "alt": {"H": (0.08, 1.15), "D": (0.38, 1.09)},
    "molt_alt": {"H": (0.05, 0.70), "D": (0.38, 0.69)},
}


def _calibra(risc: float, escales: tuple[float, float]) -> float:
    e1, e2 = escales
    return 1 - math.exp(-math.exp(e1 + e2 * math.log(-math.log(1 - risc))))


def _score2_op(e: EntradaRisc, regio: str) -> ResultatEscala:
    c = _SCORE2_OP[e.sexe]
    edat, pas = e.edat - 73, e.pas - 150
    col = e.colesterol_total / MGDL_PER_MMOL_COLESTEROL - 6
    hdl = e.hdl / MGDL_PER_MMOL_COLESTEROL - 1.4
    lp = (c["edat"] * edat + c["dm"] * e.diabetis + c["fum"] * e.fumador + c["pas"] * pas + c["col"] * col
          + c["hdl"] * hdl + edat * (c["dm_e"] * e.diabetis + c["fum_e"] * e.fumador + c["pas_e"] * pas
                                     + c["col_e"] * col + c["hdl_e"] * hdl))
    risc = 1 - c["s0"] ** math.exp(lp - c["mitjana"])
    return ResultatEscala("SCORE2-OP", _calibra(risc, _CALIBRATGE_OP[regio][e.sexe]) * 100)


def score2(e: EntradaRisc, regio: str = "baix") -> ResultatEscala | None:
    """SCORE2 i variants segons edat i diabetis. None si l'edat és < 40 (fora de rang)."""
    if e.edat < 40:
        return None
    if e.edat >= 70:
        return _score2_op(e, regio)
    amb_dm = e.diabetis and None not in (e.hba1c, e.fge, e.edat_dx_diabetis)
    c = (_SCORE2_DM if amb_dm else _SCORE2)[e.sexe]
    edat = (e.edat - 60) / 5
    pas = (e.pas - 120) / 20
    col = e.colesterol_total / MGDL_PER_MMOL_COLESTEROL - 6
    hdl = (e.hdl / MGDL_PER_MMOL_COLESTEROL - 1.3) / 0.5
    lp = (c["edat"] * edat + c["fum"] * e.fumador + c["pas"] * pas + c["dm"] * e.diabetis + c["col"] * col
          + c["hdl"] * hdl + edat * (c["fum_e"] * e.fumador + c["pas_e"] * pas + c["dm_e"] * e.diabetis
                                     + c["col_e"] * col + c["hdl_e"] * hdl))
    if amb_dm:
        hba1c = (10.929 * (e.hba1c - 2.15) - 31) / 9.34  # % (NGSP) -> mmol/mol (IFCC)
        fge = (math.log(e.fge) - 4.5) / 0.15
        lp += (c["edat_dx"] * (e.edat_dx_diabetis - 50) / 5 + c["hba1c"] * hba1c + c["fge"] * fge
               + c["fge2"] * fge**2 + edat * (c["hba1c_e"] * hba1c + c["fge_e"] * fge))
    risc = 1 - c["s0"] ** math.exp(lp)
    model = "SCORE2-Diabetes" if amb_dm else "SCORE2"
    return ResultatEscala(model, _calibra(risc, _CALIBRATGE[regio][e.sexe]) * 100)


# --- SCORE2 CKD Add-on --------------------------------------------------------------------------

def ckd_addon(e: EntradaRisc, risc_pct: float, fge: float, uacr: float | None) -> float:
    """Risc SCORE2/SCORE2-OP (%) corregit pel FGe i, si n'hi ha, per l'UACR (mg/g).

    Compara els valors observats amb els esperats per l'edat, el sexe i els factors de risc:
    un FGe inferior a l'esperat o una albuminúria superior a l'esperada pugen el risc.
    """
    edat5 = (e.edat - 60) / 5
    col = e.colesterol_total / MGDL_PER_MMOL_COLESTEROL - 6
    hdl = (e.hdl / MGDL_PER_MMOL_COLESTEROL - 1.3) / 0.5
    pas = (e.pas - 120) / 20
    dona = e.sexe == "D"
    fge_esperat = (87.8980 - 3.7891 * edat5 - 0.7023 * dona - 0.2941 * col + 1.0960 * hdl - 0.1364 * pas
                   + 0.1205 * e.diabetis + 1.3211 * e.fumador
                   + edat5 * (0.0555 * col + 0.1717 * hdl + 0.0059 * pas - 0.8994 * e.diabetis + 0.2181 * e.fumador))

    def tram_baix(v: float) -> float:  # part del FGe per sota de 60
        return min(v, 60) / -15

    def tram_mig(v: float) -> float:  # part del FGe entre 60 i 90
        return min(max(v - 60, 0), 30) / -15

    def tram_alt(v: float) -> float:  # part del FGe per sobre de 90
        return max(v - 90, 0) / -15

    d_baix = tram_baix(fge) - tram_baix(fge_esperat)
    d_mig = tram_mig(fge) - tram_mig(fge_esperat)
    if e.edat < 70:
        lp = 0.4713 * d_baix + 0.0956 * d_mig - 0.0802 * edat5 * d_baix + 0.0088 * edat5 * d_mig
        coef_uacr = 0.2432
    else:
        d_alt = tram_alt(fge) - tram_alt(fge_esperat)
        edat = e.edat - 73
        lp = (0.3072 * d_baix + 0.0942 * d_mig - 0.4616 * d_alt
              - 0.0127 * edat * d_baix - 0.0098 * edat * d_mig - 0.0075 * edat * d_alt)
        coef_uacr = 0.2370
    risc = 1 - (1 - risc_pct / 100) ** math.exp(lp)
    if uacr is not None and uacr > 0:
        log8_uacr_esperat = (1 - 0.0225 + 0.0159 * edat5 + 0.0308 * dona + 0.0185 * col - 0.0274 * hdl + 0.1339 * pas
                             + 0.2171 * e.diabetis + 0.0629 * e.fumador
                             + edat5 * (-0.0062 * col + 0.0003 * hdl + 0.0008 * pas - 0.0109 * e.diabetis
                                        + 0.0085 * e.fumador)
                             + 0.4057 * min(fge - 60, 0) / -15 + 0.0597 * tram_mig(fge) - 0.0916 * tram_alt(fge))
        risc = 1 - (1 - risc) ** math.exp(coef_uacr * (math.log(uacr, 8) - log8_uacr_esperat))
    return risc * 100


# --- REGICOR ------------------------------------------------------------------------------------

# Coeficients de Framingham per categories (Wilson 1998) amb el calibratge REGICOR
# (Marrugat et al., Rev Esp Cardiol 2003;56:253): mitjana G i supervivència basal de Girona.
_REGICOR = {
    "H": dict(edat=0.04826, edat2=0.0, dm=0.42839, fum=0.52337, g=3.489, s0=0.951,
              col=[(160, -0.65945), (200, 0.0), (240, 0.17692), (280, 0.50539), (math.inf, 0.65713)],
              hdl=[(35, 0.49744), (45, 0.24310), (50, 0.0), (60, -0.05107), (math.inf, -0.48660)],
              pa=[-0.00226, 0.0, 0.28320, 0.52168, 0.61859]),
    "D": dict(edat=0.33766, edat2=-0.00268, dm=0.59626, fum=0.29246, g=10.279, s0=0.978,
              col=[(160, -0.26138), (200, 0.0), (240, 0.20771), (280, 0.24385), (math.inf, 0.53513)],
              hdl=[(35, 0.84312), (45, 0.37796), (50, 0.19785), (60, 0.0), (math.inf, -0.42951)],
              pa=[-0.53363, 0.0, -0.06773, 0.26288, 0.46573]),
}


def _tram(valor: float, trams: list[tuple[float, float]]) -> float:
    return next(coef for limit, coef in trams if valor < limit)


def _categoria_pa(pas: float, pad: float | None) -> int:
    """0 òptima (<120/80), 1 normal, 2 normal-alta, 3 grau I, 4 grau II o més. Mana la pitjor."""
    cat_s = sum(pas >= t for t in (120, 130, 140, 160))
    cat_d = sum(pad >= t for t in (80, 85, 90, 100)) if pad is not None else 0
    return max(cat_s, cat_d)


def regicor(e: EntradaRisc, regio: str = "baix") -> ResultatEscala | None:
    """REGICOR (risc coronari a 10 anys). None fora del rang validat (35-74 anys)."""
    if not 35 <= e.edat <= 74:
        return None
    c = _REGICOR[e.sexe]
    lp = (c["edat"] * e.edat + c["edat2"] * e.edat**2 + _tram(e.colesterol_total, c["col"])
          + _tram(e.hdl, c["hdl"]) + c["pa"][_categoria_pa(e.pas, e.pad)] + c["dm"] * e.diabetis
          + c["fum"] * e.fumador)
    return ResultatEscala("REGICOR", (1 - c["s0"] ** math.exp(lp - c["g"])) * 100)


Escala = Callable[[EntradaRisc, str], "ResultatEscala | None"]
ESCALES: dict[str, Escala] = {"score2": score2, "regicor": regicor}
