"""Motor de regles clínic determinista (marc "STAMP on CKD", guies ESC/ERA 2026).

Sense IA generativa: cada resultat surt de fórmules publicades i de llindars de config/rules.yaml,
de manera que qualsevol alerta és auditable (regla, dades, sistema d'origen i classe de recomanació).

Ús:
    from connectors import FhirConnector
    from engine import RiskEngine
    motor = RiskEngine(FhirConnector("data/synthetic/fhir"))
    cupo = motor.avalua_cupo()          # llista de ResultatPacient ordenada per prioritat
    fitxa = motor.avalua("P003")

    python -m engine [ID]               # resum del cupo o nota clínica d'un pacient

El motor només coneix la interfície `Connector` i el model de `model/`. Els textos clínics de
sortida són en castellà (com les dades); identificadors i comentaris en català.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import yaml

from connectors import Connector
from model import DadesPacient
from model.cataleg import CIAP2, LOINC
from model.formules import EQUACIONS_FGE, edat_en

from . import renal
from .escales import ESCALES, EntradaRisc, ckd_addon
from .renal import Mesura

ARREL = Path(__file__).resolve().parent.parent
CONFIG_DEFECTE = ARREL / "config" / "rules.yaml"

ETIQUETA_DX = {CIAP2["dm2"]: "DM2", CIAP2["hta"]: "HTA", CIAP2["mrc"]: "ERC", CIAP2["ic"]: "IC",
               CIAP2["dislipemia"]: "dislipemia", CIAP2["tabac"]: "tabaquismo"}
GRUPS_INICI_AMB_CAIGUDA = ("iSGLT2", "IECA", "ARA-II")  # fàrmacs amb caiguda inicial esperada del FGe
NOM_EQUACIO = {"ckd_epi_2009": "CKD-EPI 2009", "ckd_epi_2021": "CKD-EPI 2021"}
ORDRE_CATEGORIA = ["baix_moderat", "alt", "molt_alt"]
TEXT_CATEGORIA = {"baix_moderat": "bajo-moderado", "alt": "alto", "molt_alt": "muy alto"}

# Accions recomanades: clau -> (text, nota d'estalvi de temps / anti-inèrcia)
ACCIONS: dict[str, tuple[str, str | None]] = {
    "sol_uacr": ("Solicitar cociente albúmina/creatinina (UACR) en orina", None),
    "sol_creatinina": ("Solicitar creatinina con FGe", None),
    "retest_fra": ("Repetir creatinina/FGe en 1-2 semanas; revisar AINE, contrastes, volemia y fármacos recientes",
                   None),
    "derivar_nefro": ("Derivar a Nefrología", None),
    "registrar_mrc": ("Registrar diagnóstico de ERC (CIE-10 N18 / CIAP-2 U99.01) con su categoría KDIGO", None),
    "confirmar_mrc": ("Repetir FGe y UACR en 3 meses para confirmar cronicidad", None),
    "cribratge_ic": ("Citar para cribado de IC: anamnesis dirigida, exploración, ECG y ecocardiograma", None),
    "revisar_descens": ("Revisar nefrotóxicos (AINE), optimizar PA y nefroprotección; nuevo FGe + UACR en 3-6 meses",
                        None),
    "sraa": ("Iniciar IECA o ARA-II a dosis máxima tolerada (objetivo PAS 120-129 mmHg)",
             "Caída inicial de FGe <30% fisiológica: mantener fármaco."),
    "isglt2": ("Valorar inicio de iSGLT2 (nefroprotección y cardioprotección)",
               "Sin analítica extra de control al iniciar iSGLT2. Caída inicial de FGe <30% fisiológica: "
               "mantener fármaco."),
    "estatina": ("Iniciar estatina", None),
    "pressio": ("Optimizar tratamiento antihipertensivo (objetivo PAS 120-129 mmHg)", None),
    "finerenona": ("Valorar finerenona (DM2 con albuminuria y potasio ≤ 4,8 mmol/L)", None),
    "aglp1": ("Valorar semaglutida (arGLP-1) por DM2 con albuminuria", None),
    "hba1c": ("Intensificar control glucémico", None),
    "tabac": ("Consejo breve y oferta de deshabituación tabáquica", None),
    "retirar_aas": ("Reevaluar AAS: sin ECV establecida no está indicado en prevención primaria", None),
}


@dataclass(frozen=True)
class Alerta:
    regla: str  # clau de la regla (config/rules.yaml)
    titol: str
    motiu: str  # el perquè, en una línia, amb les dades que la disparen
    evidencia: str  # p. ex. "Clase I - ESC/ERA 2026"
    pes: int  # punts que aporta a la prioritat
    fonts: tuple[str, ...] = ()  # sistemes d'origen de les dades que la disparen


@dataclass(frozen=True)
class Accio:
    clau: str
    text: str
    evidencia: str
    nota: str | None = None  # avís d'estalvi de temps o anti-inèrcia


@dataclass
class ResultatPacient:
    pacient_id: str
    nom: str
    edat: int
    sexe: str
    nivell_risc: str  # "ALT" | "MITJA" | "BAIX" (prioritat d'actuació)
    puntuacio_prioritat: int  # 0-100, per ordenar el cupo
    categoria_kdigo: str | None  # p. ex. "G3aA2"; "G2A?" si falta l'UACR; None sense creatinina
    risc_kdigo: str | None  # verd | groc | taronja | vermell
    estat_renal: str  # normal | mrc | pendent_confirmar | possible_fra | sense_dades
    fge_actual: float | None  # mL/min/1,73m² amb l'equació configurada
    uacr_actual: float | None  # mg/g
    pendent_fge: float | None  # mL/min/1,73m² per any (negatiu = pèrdua)
    kfre_5a: float | None  # % de risc de fallida renal a 5 anys (només si FGe < 60 i hi ha UACR)
    risc_cv: dict | None  # escala, valors (%), categoria i reclassificació per MRC
    alertes_actives: list[Alerta] = field(default_factory=list)
    accions_recomanades: list[Accio] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)  # notes informatives (anti-inèrcia, dades que falten)
    ben_tractat: bool = False  # control positiu: tractament i objectius correctes i cap alerta
    objectius_pendents: list[str] = field(default_factory=list)
    resum: str = ""  # una línia: per què + acció
    fonts_dades: list[str] = field(default_factory=list)  # sistemes d'origen integrats
    nota_clinica_auto: str = ""  # esborrany per enganxar a eCAP/DIRAYA

    def regles_actives(self) -> set[str]:
        return {a.regla for a in self.alertes_actives}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Fets:
    """Fets derivats d'un pacient, calculats una sola vegada i compartits per totes les regles."""

    fge: list[Mesura]
    uacr: list[Mesura]
    dm: bool
    hta: bool
    mrc_dx: bool
    grups: set[str]
    fge_cronic: bool = False
    alb_cronica: bool = False
    caiguda_pct: float | None = None
    possible_fra: bool = False

    @property
    def fge_ult(self) -> Mesura | None:
        return self.fge[-1] if self.fge else None

    @property
    def uacr_ult(self) -> Mesura | None:
        return self.uacr[-1] if self.uacr else None

    @property
    def te_mrc(self) -> bool:
        return self.mrc_dx or self.fge_cronic or self.alb_cronica

    @property
    def g(self) -> str | None:
        return renal.categoria_g(self.fge_ult.valor) if self.fge_ult else None

    @property
    def a(self) -> str | None:
        return renal.categoria_a(self.uacr_ult.valor) if self.uacr_ult else None

    @property
    def color(self) -> str | None:
        return renal.risc_kdigo(self.g, self.a) if self.g else None


class _Sortida:
    def __init__(self, guia: str):
        self.guia = guia
        self.alertes: list[Alerta] = []
        self.accions: dict[str, Accio] = {}
        self.avisos: list[str] = []

    def cita(self, cfg: dict) -> str:
        return f"{cfg.get('evidencia', 'Clase I')} - {self.guia}"

    def alerta(self, regla: str, cfg: dict, titol: str, motiu: str, mesures: list[Mesura] = ()) -> None:
        fonts = tuple(dict.fromkeys(m.origen for m in mesures if m.origen))
        if len(fonts) > 1:
            motiu += f" [dato cruzado entre {' y '.join(fonts)}]"
        self.alertes.append(Alerta(regla, titol, motiu, self.cita(cfg), int(cfg.get("pes", 0)), fonts))

    def accio(self, clau: str, cfg: dict, detall: str = "") -> None:
        if clau not in self.accions:
            text, nota = ACCIONS[clau]
            self.accions[clau] = Accio(clau, text + detall, self.cita(cfg), nota)


def _n(x: float, decimals: int = 0) -> str:
    """Número amb coma decimal (format espanyol)."""
    return f"{x:.{decimals}f}".replace(".", ",")


def _d(data: date) -> str:
    return data.strftime("%d/%m/%Y")


def _dies(mesos: float) -> int:
    return round(mesos * 365.25 / 12)


class RiskEngine:
    def __init__(self, connector: Connector, config: str | Path | dict = CONFIG_DEFECTE,
                 data_referencia: date | None = None):
        """config: camí a rules.yaml o el diccionari ja carregat. data_referencia: "avui" (per defecte,
        motor.data_referencia de la config o, si és null, la data del sistema)."""
        if not isinstance(config, dict):
            config = yaml.safe_load(Path(config).read_text(encoding="utf-8"))
        self.connector = connector
        self.regles: dict = config["rules"]
        self.motor: dict = config["motor"]
        self.avui: date = data_referencia or self.motor.get("data_referencia") or date.today()
        self.nom_equacio = self.motor["equacio_fge"]
        self._equacio = EQUACIONS_FGE[self.nom_equacio]
        escala = self.regles["risc_cardiovascular"]["escala"]
        if escala != "totes_dues" and escala not in ESCALES:
            raise ValueError(f"Escala de risc desconeguda: {escala!r} (score2 | regicor | totes_dues)")

    # --- API pública ------------------------------------------------------------------------

    def avalua(self, patient_id: str) -> ResultatPacient:
        return self.avalua_dades(self.connector.get_patient_data(patient_id))

    def avalua_cupo(self) -> list[ResultatPacient]:
        """Tot el cupo, de més a menys prioritat."""
        resultats = [self.avalua(p.id) for p in self.connector.get_patients()]
        return sorted(resultats, key=lambda r: (-r.puntuacio_prioritat, r.pacient_id))

    def avalua_dades(self, d: DadesPacient) -> ResultatPacient:
        p = d.pacient
        f = self._fets(d)
        s = _Sortida(self.motor["guia"])

        self._possible_fra(d, f, s)
        self._derivacio_nefrologia(d, f, s)
        self._mrc_no_diagnosticada(f, s)
        self._albuminuria_sense_accio(d, f, s)
        self._fge_descens(f, s)
        self._possible_ic(d, f, s)
        risc_cv = self._risc_cv(d, f)
        risc_alt = bool(risc_cv and risc_cv["categoria"] in ("alt", "molt_alt"))
        pendents = self._objectius_pendents(d, f, risc_alt)
        self._risc_cardiovascular(d, f, s, risc_cv, risc_alt, pendents)
        self._prova_falta("uacr_falta", "UACR pendiente", "sol_uacr", d, s)
        self._prova_falta("creatinina_falta", "Creatinina/FGe pendiente", "sol_creatinina", d, s)
        self._oportunitats(d, f, s)
        self._avisos(d, f, s)

        pes_kdigo = self.motor["prioritat"]["kdigo"].get(f.color, 0) if f.color else 0
        puntuacio = min(100, sum(a.pes for a in s.alertes) + pes_kdigo)
        prioritat = self.motor["prioritat"]
        nivell = ("ALT" if puntuacio >= prioritat["nivell_alt"]
                  else "MITJA" if puntuacio >= prioritat["nivell_mitja"] else "BAIX")
        kfre = None
        if f.fge_ult and f.uacr_ult and f.fge_ult.valor < 60:
            kfre = round(renal.kfre_5_anys(p.edat, p.sexe, f.fge_ult.valor, f.uacr_ult.valor), 1)
        pendent = self._pendent(f)

        res = ResultatPacient(
            pacient_id=p.id, nom=p.nom, edat=p.edat, sexe=p.sexe,
            nivell_risc=nivell, puntuacio_prioritat=puntuacio,
            categoria_kdigo=f"{f.g}{f.a or 'A?'}" if f.g else None,
            risc_kdigo=f.color,
            estat_renal=self._estat_renal(f),
            fge_actual=f.fge_ult.valor if f.fge_ult else None,
            uacr_actual=f.uacr_ult.valor if f.uacr_ult else None,
            pendent_fge=round(pendent, 1) if pendent is not None else None,
            kfre_5a=kfre,
            risc_cv=risc_cv,
            alertes_actives=s.alertes,
            accions_recomanades=list(s.accions.values()),
            avisos=s.avisos,
            ben_tractat=pendents == [] and not s.alertes,
            objectius_pendents=pendents or [],
            fonts_dades=sorted({a.origen for a in d.analitiques if a.origen}),
        )
        res.resum = self._resum(res)
        res.nota_clinica_auto = self._nota_clinica(d, f, res)
        return res

    # --- Fets -------------------------------------------------------------------------------

    def _activa(self, regla: str) -> bool:
        return bool(self.regles[regla].get("enabled"))

    def _fets(self, d: DadesPacient) -> _Fets:
        p = d.pacient

        def edat_a(data: date) -> int:
            return edat_en(p.data_naixement, data) if p.data_naixement else p.edat

        # El FGe es recalcula SEMPRE de la creatinina amb l'equació configurada (no es fa servir el
        # valor informat pel laboratori, que pot venir d'una altra equació segons el sistema d'origen).
        fge = [Mesura(a.data, float(round(self._equacio(a.valor, edat_a(a.data), p.sexe))), a.origen)
               for a in d.serie(LOINC["creatinina"])]
        uacr = [Mesura(a.data, a.valor, a.origen) for a in d.serie(LOINC["uacr"])]
        r = self.regles["mrc_no_diagnosticada"]
        f = _Fets(fge=fge, uacr=uacr, dm=d.te_diagnostic(CIAP2["dm2"]), hta=d.te_diagnostic(CIAP2["hta"]),
                  mrc_dx=d.te_diagnostic(r["diagnostic_excloent"]), grups={m.grup for m in d.medicacions})
        n, dies = r["min_mesures"], _dies(r["min_mesos_separacio"])
        f.fge_cronic = renal.confirmat(fge, lambda v: v < r["fge_llindar"], n, dies)
        f.alb_cronica = renal.confirmat(uacr, lambda v: v >= r["uacr_llindar"], n, dies)
        fra = self.motor["possible_fra"]
        f.caiguda_pct = renal.caiguda_recent_pct(fge, _dies(fra["max_mesos_entre_mesures"]))
        f.possible_fra = bool(fra.get("enabled")) and f.caiguda_pct is not None and f.caiguda_pct >= fra["caiguda_pct"]
        return f

    def _pendent(self, f: _Fets) -> float | None:
        r = self.regles["fge_descens"]
        return renal.pendent_anual(f.fge, r["min_mesures"], _dies(r["min_mesos_seguiment"]))

    def _estat_renal(self, f: _Fets) -> str:
        r = self.regles["mrc_no_diagnosticada"]
        if not f.fge_ult:
            return "sense_dades"
        if f.possible_fra:
            return "possible_fra"
        if f.te_mrc:
            return "mrc"
        if f.fge_ult.valor < r["fge_llindar"] or (f.uacr_ult and f.uacr_ult.valor >= r["uacr_llindar"]):
            return "pendent_confirmar"
        return "normal"

    # --- Regles renals ----------------------------------------------------------------------

    def _possible_fra(self, d: DadesPacient, f: _Fets, s: _Sortida) -> None:
        if not f.possible_fra:
            return
        ant, ult = f.fge[-2], f.fge[-1]
        s.alerta("possible_fra", self.motor["possible_fra"], "Caída aguda de FGe (posible FRA)",
                 f"FGe {_n(ant.valor)} → {_n(ult.valor)} mL/min/1,73m² (−{_n(f.caiguda_pct)}%) entre {_d(ant.data)} y "
                 f"{_d(ult.data)}: caída inesperada, descartar fracaso renal agudo antes de etiquetar ERC",
                 [ant, ult])
        s.accio("retest_fra", self.motor["possible_fra"])

    def _derivacio_nefrologia(self, d: DadesPacient, f: _Fets, s: _Sortida) -> None:
        cfg = self.motor["derivacio_nefrologia"]
        if not cfg.get("enabled") or not f.fge_ult:
            return
        motius, mesures = [], [f.fge_ult]
        fge, uacr = f.fge_ult.valor, f.uacr_ult.valor if f.uacr_ult else None
        if fge < cfg["fge_max"]:
            motius.append(f"FGe {_n(fge)} < {cfg['fge_max']}")
        if uacr is not None:
            mesures.append(f.uacr_ult)
            if fge < 60:
                kfre = renal.kfre_5_anys(d.pacient.edat, d.pacient.sexe, fge, uacr)
                if kfre >= cfg["kfre_5a_pct"]:
                    motius.append(f"KFRE a 5 años {_n(kfre, 1)}% (≥ {cfg['kfre_5a_pct']}%)")
            if uacr >= cfg["uacr_min"]:
                motius.append(f"UACR {_n(uacr)} mg/g (≥ {cfg['uacr_min']})")
            if cfg.get("duplicacio_uacr") and len(f.uacr) >= 2:
                ant = f.uacr[-2]
                if uacr >= 2 * ant.valor and uacr >= self.regles["mrc_no_diagnosticada"]["uacr_llindar"]:
                    motius.append(f"UACR duplicado ({_n(ant.valor)} → {_n(uacr)} mg/g)")
                    mesures.append(ant)
        if motius:
            s.alerta("derivacio_nefrologia", cfg, "Criterio de derivación a Nefrología", "; ".join(motius), mesures)
            s.accio("derivar_nefro", cfg)

    def _mrc_no_diagnosticada(self, f: _Fets, s: _Sortida) -> None:
        r = self.regles["mrc_no_diagnosticada"]
        if not self._activa("mrc_no_diagnosticada") or f.mrc_dx or not (f.fge_cronic or f.alb_cronica):
            return
        parts, mesures = [], []
        for cronic, serie, anormal, nom, unitat in (
                (f.fge_cronic, f.fge, lambda v: v < r["fge_llindar"], f"FGe < {r['fge_llindar']}", ""),
                (f.alb_cronica, f.uacr, lambda v: v >= r["uacr_llindar"], f"UACR ≥ {r['uacr_llindar']} mg/g", "")):
            if cronic:
                anormals = [m for m in serie if anormal(m.valor)]
                primera, ultima = anormals[0], anormals[-1]
                parts.append(f"{nom} mantenido ≥ {r['min_mesos_separacio']} meses ({_n(primera.valor)} el "
                             f"{_d(primera.data)} y {_n(ultima.valor)} el {_d(ultima.data)})")
                mesures += [primera, ultima]
        s.alerta("mrc_no_diagnosticada", r, "ERC no diagnosticada",
                 f"{' y '.join(parts)}: criterios KDIGO de ERC ({f.g}{f.a or 'A?'}) sin diagnóstico registrado",
                 mesures)
        s.accio("registrar_mrc", r, f": {f.g}{f.a or 'A?'}")
        if not f.uacr_ult:
            s.accio("sol_uacr", r)

    def _albuminuria_sense_accio(self, d: DadesPacient, f: _Fets, s: _Sortida) -> None:
        r = self.regles["albuminuria_sense_accio"]
        if not self._activa("albuminuria_sense_accio") or not f.uacr_ult or f.uacr_ult.valor < r["uacr_llindar"]:
            return
        if f.grups & set(r["grups_protectors"]):
            return
        alterades = [m for m in f.uacr if m.valor >= r["uacr_llindar"]]
        previa = f", ya alterado el {_d(alterades[0].data)} ({_n(alterades[0].valor)} mg/g)" if len(alterades) > 1 else ""
        s.alerta("albuminuria_sense_accio", r, "Albuminuria sin nefroprotección",
                 f"UACR {_n(f.uacr_ult.valor)} mg/g ({f.a}) el {_d(f.uacr_ult.data)}{previa}, sin "
                 f"{', '.join(r['grups_protectors'][:-1])} ni {r['grups_protectors'][-1]}", alterades)
        s.accio("sraa", r)
        if not f.te_mrc:
            s.accio("confirmar_mrc", r)

    def _fge_descens(self, f: _Fets, s: _Sortida) -> None:
        r = self.regles["fge_descens"]
        pendent = self._pendent(f)
        if not self._activa("fge_descens") or pendent is None or -pendent <= r["descens_anual_llindar"]:
            return
        ini, fi = f.fge[0], f.fge[-1]
        fis = r["descens_fisiologic"]
        s.alerta("fge_descens", r, "Pérdida rápida de filtrado glomerular",
                 f"FGe en descenso de {_n(-pendent, 1)} mL/min/1,73m²/año ({_n(ini.valor)} en {ini.data.year} → "
                 f"{_n(fi.valor)} en {fi.data.year}; fisiológico {_n(fis[0], 1)}-{_n(fis[1], 1)}), aunque la "
                 f"creatinina aislada parezca normal", [ini, fi])
        s.accio("revisar_descens", r)
        if not f.uacr_ult:
            s.accio("sol_uacr", r)

    # --- Regla cardíaca ---------------------------------------------------------------------

    def _possible_ic(self, d: DadesPacient, f: _Fets, s: _Sortida) -> None:
        r = self.regles["possible_ic"]
        nt = d.ultima(r["prova"])
        if not self._activa("possible_ic") or nt is None or d.te_diagnostic(r["diagnostic_excloent"]):
            return
        edat = d.pacient.edat
        trams = sorted(r["llindars_per_edat"], key=lambda t: t["edat_max"])
        llindar = next((t["llindar"] for t in trams if edat <= t["edat_max"]), trams[-1]["llindar"])
        ajust = ""
        avancada = r.get("mrc_avancada")
        if avancada and f.fge_ult and f.fge_ult.valor < avancada["fge_max"] and avancada["llindar"] > llindar:
            llindar, ajust = avancada["llindar"], f", elevado a {avancada['llindar']} por ERC avanzada"
        if nt.valor < llindar:
            return
        s.alerta("possible_ic", r, "Posible insuficiencia cardíaca no diagnosticada",
                 f"NT-proBNP {_n(nt.valor)} pg/mL el {_d(nt.data)} (umbral {llindar} pg/mL para {edat} años{ajust}; "
                 f"< {r.get('llindar_descarta', 125)} descartaría IC) sin diagnóstico de IC",
                 [Mesura(nt.data, nt.valor, nt.origen)])
        s.accio("cribratge_ic", r)

    # --- Risc cardiovascular ----------------------------------------------------------------

    def _entrada_risc(self, d: DadesPacient, f: _Fets) -> EntradaRisc | None:
        p = d.pacient
        pas, pad, col, hdl, hba1c = (d.ultima(LOINC[k]) for k in ("pas", "pad", "colesterol_total", "hdl", "hba1c"))
        if None in (pas, col, hdl):
            return None
        edat_dx = None
        dx_dm = next((x for x in d.diagnostics if x.codi_ciap2 == CIAP2["dm2"]), None)
        if dx_dm:
            edat_dx = (edat_en(p.data_naixement, dx_dm.data) if p.data_naixement
                       else p.edat - (self.avui - dx_dm.data).days // 365)
        return EntradaRisc(
            edat=p.edat, sexe=p.sexe, fumador=p.fumador, diabetis=f.dm, pas=pas.valor,
            pad=pad.valor if pad else None, colesterol_total=col.valor, hdl=hdl.valor,
            hba1c=hba1c.valor if hba1c else None, fge=f.fge_ult.valor if f.fge_ult else None,
            edat_dx_diabetis=edat_dx)

    def _risc_cv(self, d: DadesPacient, f: _Fets) -> dict | None:
        """Risc CV amb l'escala configurada. Es calcula encara que el pacient estigui ben tractat."""
        r = self.regles["risc_cardiovascular"]
        if not self._activa("risc_cardiovascular"):
            return None
        res = {"escala": r["escala"], "valors": {}, "valor": None, "categoria": None,
               "reclassificat_mrc": False, "ecv_establerta": False}
        if any(d.te_diagnostic(c) for c in r.get("diagnostics_ecv", [])):
            res.update(categoria="molt_alt", ecv_establerta=True)
            return res
        entrada = self._entrada_risc(d, f)
        if entrada:
            for nom in (list(ESCALES) if r["escala"] == "totes_dues" else [r["escala"]]):
                x = ESCALES[nom](entrada, r.get("regio_score2", "baix"))
                if x is None:  # fora del rang d'edat de l'escala
                    continue
                model, risc = x.model, x.risc
                # SCORE2-Diabetes ja inclou el FGe: l'Add-on només s'aplica a SCORE2 i SCORE2-OP
                if nom == "score2" and r.get("ckd_addon") and f.te_mrc and f.fge_ult and model != "SCORE2-Diabetes":
                    risc = ckd_addon(entrada, risc, f.fge_ult.valor, f.uacr_ult.valor if f.uacr_ult else None)
                    model += " + CKD Add-on"
                res["valors"][model] = round(risc, 1)
        if res["valors"]:
            res["valor"] = max(res["valors"].values())
            res["categoria"] = "alt" if res["valor"] >= r["llindar_risc_alt"] else "baix_moderat"
        if r.get("reclassificacio_kdigo") and f.te_mrc:
            minima = {"taronja": "alt", "vermell": "molt_alt"}.get(f.color)
            actual = res["categoria"] or "baix_moderat"
            if minima and ORDRE_CATEGORIA.index(minima) > ORDRE_CATEGORIA.index(actual):
                res.update(categoria=minima, reclassificat_mrc=True)
        return res

    @staticmethod
    def _text_risc(risc_cv: dict) -> str:
        parts = [f"{model} {_n(v, 1)}%" for model, v in risc_cv["valors"].items()]
        if risc_cv["ecv_establerta"]:
            parts.append("ECV establecida")
        if risc_cv["reclassificat_mrc"]:
            parts.append("reclasificado al alza por ERC (KDIGO)")
        return f"{', '.join(parts) or 'no calculable'}: riesgo {TEXT_CATEGORIA.get(risc_cv['categoria'], 'no calculable')}"

    def _risc_cardiovascular(self, d: DadesPacient, f: _Fets, s: _Sortida, risc_cv: dict | None, risc_alt: bool,
                             pendents: list[str] | None) -> None:
        if not risc_alt or pendents == []:  # sense risc alt, o risc alt però ben tractat (control positiu)
            return
        r = self.regles["risc_cardiovascular"]
        motiu = f"RCV a 10 años {self._text_risc(risc_cv)} (umbral {r['llindar_risc_alt']}%)"
        if pendents:
            motiu += f"; pendiente: {', '.join(pendents)}"
        s.alerta("risc_cardiovascular", r, "Riesgo cardiovascular alto infratratado", motiu)
        if "estatina" not in f.grups:
            s.accio("estatina", r)
        if d.pacient.fumador:
            s.accio("tabac", r)
        b = self.regles["ben_tractat"]
        hba1c = d.ultima(LOINC["hba1c"])
        if f.dm and hba1c and hba1c.valor >= b["hba1c_objectiu"]:
            s.accio("hba1c", r, f" (HbA1c {_n(hba1c.valor, 1)}%, objetivo < {_n(b['hba1c_objectiu'], 1)}%)")
        obj = b["pressio_objectiu_diabetics"] if f.dm else b["pressio_objectiu"]
        pas, pad = d.ultima(LOINC["pas"]), d.ultima(LOINC["pad"])
        if pas and pad and (pas.valor >= obj["sistolica"] or pad.valor >= obj["diastolica"]):
            s.accio("pressio", r, f": PA actual {_n(pas.valor)}/{_n(pad.valor)} mmHg")

    # --- Control positiu: ben tractat -------------------------------------------------------

    def _objectius_pendents(self, d: DadesPacient, f: _Fets, risc_alt: bool) -> list[str] | None:
        """Llista d'objectius no assolits ([] = ben tractat). None si la regla no aplica al pacient."""
        b = self.regles["ben_tractat"]
        cronic = any(d.te_diagnostic(c) for c in self.regles["creatinina_falta"]["diagnostics"])
        if not self._activa("ben_tractat") or not (cronic or risc_alt):
            return None
        pendents = []
        if any(d.te_diagnostic(c) for c in b["ieca_ara2_i_isglt2_si"]) or f.te_mrc:
            if not f.grups & set(b["grups_bloqueig_sraa"]):
                pendents.append("sin IECA/ARA-II")
            if b["grup_isglt2"] not in f.grups:
                pendents.append("sin iSGLT2")
        dislipemia = d.te_diagnostic(CIAP2["dislipemia"])
        if "estatina" not in f.grups and ((b["estatina_si_risc_alt"] and risc_alt)
                                          or (b["estatina_si_dislipemia"] and dislipemia)):
            pendents.append("sin estatina")
        hba1c = d.ultima(LOINC["hba1c"])
        if f.dm and hba1c and hba1c.valor >= b["hba1c_objectiu"]:
            pendents.append(f"HbA1c {_n(hba1c.valor, 1)}% (objetivo < {_n(b['hba1c_objectiu'], 1)}%)")
        obj = b["pressio_objectiu_diabetics"] if f.dm else b["pressio_objectiu"]
        pas, pad = d.ultima(LOINC["pas"]), d.ultima(LOINC["pad"])
        if pas and pad and (pas.valor >= obj["sistolica"] or pad.valor >= obj["diastolica"]):
            pendents.append(f"PA {_n(pas.valor)}/{_n(pad.valor)} mmHg (objetivo < {obj['sistolica']}/{obj['diastolica']})")
        for loinc in b["proves_recents"]:
            # La prova només és exigible si el pacient té un diagnòstic que la fa periòdica
            dxs = [c for nom in ("uacr_falta", "creatinina_falta") if self.regles[nom]["prova"] == loinc
                   for c in self.regles[nom]["diagnostics"]]
            if dxs and not any(d.te_diagnostic(c) for c in dxs):
                continue
            ult = d.ultima(loinc)
            if ult is None or (self.avui - ult.data).days > _dies(b["max_mesos_proves"]):
                nom = "UACR" if loinc == LOINC["uacr"] else "creatinina" if loinc == LOINC["creatinina"] else loinc
                pendents.append(f"{nom} no actualizado en {b['max_mesos_proves']} meses")
        return pendents

    # --- Proves que falten ------------------------------------------------------------------

    def _prova_falta(self, regla: str, titol: str, accio: str, d: DadesPacient, s: _Sortida) -> None:
        r = self.regles[regla]
        dxs = [ETIQUETA_DX.get(c, c) for c in r["diagnostics"] if d.te_diagnostic(c)]
        if not self._activa(regla) or not dxs:
            return
        nom = "UACR" if r["prova"] == LOINC["uacr"] else "creatinina"
        ult = d.ultima(r["prova"])
        if ult is None:
            motiu = f"Paciente con {' + '.join(dxs)} sin ninguna determinación de {nom} registrada"
        elif (self.avui - ult.data).days > _dies(r["max_mesos_sense_prova"]):
            mesos = round((self.avui - ult.data).days / 30.44)
            motiu = (f"Último {nom} hace {mesos} meses ({_d(ult.data)}); control al menos cada "
                     f"{r['max_mesos_sense_prova']} meses en {' + '.join(dxs)}")
        else:
            return
        s.alerta(regla, r, titol, motiu, [Mesura(ult.data, ult.valor, ult.origen)] if ult else [])
        s.accio(accio, r)

    # --- Oportunitats terapèutiques ---------------------------------------------------------

    def _oportunitats(self, d: DadesPacient, f: _Fets, s: _Sortida) -> None:
        o = self.motor["oportunitats"]
        fge = f.fge_ult.valor if f.fge_ult else None
        uacr = f.uacr_ult.valor if f.uacr_ult else None

        def activa(clau: str) -> dict | None:
            return o[clau] if o.get(clau, {}).get("enabled") else None

        if (c := activa("sraa")) and uacr is not None and uacr >= c["uacr_min"] and not f.grups & {"IECA", "ARA-II"}:
            s.accio("sraa", c)
        if (c := activa("isglt2")) and "iSGLT2" not in f.grups and fge is not None and fge >= c["fge_min"]:
            if f.dm or (uacr is not None and uacr >= c["uacr_min_sense_dm"]):
                s.accio("isglt2", c)
        if (c := activa("estatina")) and "estatina" not in f.grups and fge is not None and fge < c["fge_max"] \
                and f.te_mrc:
            s.accio("estatina", c, f" (FGe < {c['fge_max']}: indicada con independencia del LDL)")
        pas = d.ultima(LOINC["pas"])
        if (c := activa("pressio")) and (f.dm or f.te_mrc) and pas and pas.valor > c["pas_objectiu"][1]:
            s.accio("pressio", c, f": PAS actual {_n(pas.valor)} mmHg")
        k = d.ultima(LOINC["potasio"])
        if (c := activa("finerenona")) and f.dm and "finerenona" not in f.grups and uacr is not None \
                and uacr >= c["uacr_min"] and k and k.valor <= c["potassi_max"]:
            s.accio("finerenona", c, f": K actual {_n(k.valor, 1)} mmol/L")
        if (c := activa("aglp1")) and f.dm and "aGLP-1" not in f.grups and uacr is not None and uacr >= c["uacr_min"]:
            s.accio("aglp1", c)
        ecv = any(d.te_diagnostic(x) for x in self.regles["risc_cardiovascular"].get("diagnostics_ecv", []))
        if (c := activa("aas_prevencio_primaria")) and c["grup"] in f.grups and not ecv:
            s.alerta("aas_prevencio_primaria", c, "AAS en prevención primaria",
                     "Toma AAS sin enfermedad cardiovascular establecida: no recomendado")
            s.accio("retirar_aas", c)

    def _avisos(self, d: DadesPacient, f: _Fets, s: _Sortida) -> None:
        fra = self.motor["possible_fra"]
        if f.caiguda_pct is not None and fra["caiguda_esperada_min_pct"] <= f.caiguda_pct < fra["caiguda_pct"]:
            ant, ult = f.fge[-2], f.fge[-1]
            nous = [m.nom for m in d.medicacions
                    if m.grup in GRUPS_INICI_AMB_CAIGUDA and ant.data <= m.data_inici <= ult.data]
            if nous:
                s.avisos.append(f"Descenso de FGe del {_n(f.caiguda_pct)}% tras iniciar {', '.join(nous)}: esperado "
                                f"(< {fra['caiguda_pct']}%), no requiere suspender el fármaco.")
        if self._estat_renal(f) == "pendent_confirmar" and "confirmar_mrc" not in s.accions:
            s.accio("confirmar_mrc", self.regles["mrc_no_diagnosticada"])
        if f.fge_ult and not f.uacr_ult:
            s.avisos.append("Sin UACR registrado: categoría de albuminuria KDIGO desconocida (A?).")

    # --- Textos -----------------------------------------------------------------------------

    @staticmethod
    def _resum(res: ResultatPacient) -> str:
        if res.alertes_actives:
            principal = max(res.alertes_actives, key=lambda a: a.pes)  # en empat, la primera
            accio = f" → {res.accions_recomanades[0].text}" if res.accions_recomanades else ""
            mes = f" (+{len(res.alertes_actives) - 1} alertas)" if len(res.alertes_actives) > 1 else ""
            return f"{principal.titol}: {principal.motiu}{accio}{mes}"
        if res.ben_tractat:
            return "Bien tratado: tratamiento y objetivos correctos, sin acciones pendientes"
        if res.accions_recomanades:
            return f"Sin alertas. Oportunidad: {res.accions_recomanades[0].text}"
        return "Sin alertas ni acciones pendientes"

    def _nota_clinica(self, d: DadesPacient, f: _Fets, res: ResultatPacient) -> str:
        p = d.pacient
        dxs = [ETIQUETA_DX.get(x.codi_ciap2, x.nom) for x in d.diagnostics]
        meds = [m.nom for m in d.medicacions]
        linies = [
            f"[CardioAlert AP · {_d(self.avui)} · borrador automático: revisar antes de firmar]",
            f"{'Varón' if p.sexe == 'H' else 'Mujer'} de {p.edat} años. Antecedentes: {', '.join(dxs) or 'sin diagnósticos crónicos'}."
            f" Tratamiento: {', '.join(meds) or 'ninguno'}.",
        ]
        if f.fge_ult:
            renal_txt = (f"Función renal: FGe {_n(f.fge_ult.valor)} mL/min/1,73m² ({NOM_EQUACIO.get(self.nom_equacio, self.nom_equacio)}, "
                         f"{_d(f.fge_ult.data)})")
            renal_txt += (f", UACR {_n(f.uacr_ult.valor)} mg/g ({_d(f.uacr_ult.data)})" if f.uacr_ult
                          else ", UACR no disponible")
            renal_txt += f". KDIGO {res.categoria_kdigo} ({renal.RISC_KDIGO_TEXT[res.risc_kdigo]})."
            estat = {"mrc": " ERC " + ("diagnosticada" if f.mrc_dx else "con criterios de cronicidad, sin diagnóstico registrado") + ".",
                     "pendent_confirmar": " Alteración aislada pendiente de confirmar a los 3 meses.",
                     "possible_fra": " Caída aguda: descartar FRA."}.get(res.estat_renal, "")
            renal_txt += estat
            if res.pendent_fge is not None:
                renal_txt += f" Pendiente de FGe {_n(res.pendent_fge, 1)} mL/min/1,73m²/año."
            if res.kfre_5a is not None:
                renal_txt += f" KFRE a 5 años {_n(res.kfre_5a, 1)}%."
            linies.append(renal_txt)
        if res.risc_cv:
            linies.append(f"RCV a 10 años: {self._text_risc(res.risc_cv)}.")
        if res.alertes_actives:
            linies.append("Alertas:")
            linies += [f"- {a.titol}: {a.motiu} ({a.evidencia})." for a in res.alertes_actives]
        elif res.ben_tractat:
            linies.append("Sin alertas: tratamiento y objetivos correctos.")
        else:
            linies.append("Sin alertas activas.")
        if res.accions_recomanades:
            linies.append("Plan propuesto:")
            for a in res.accions_recomanades:
                linies.append(f"- {a.text} ({a.evidencia})." + (f" {a.nota}" if a.nota else ""))
        linies += [f"Nota: {x}" for x in res.avisos]
        if res.fonts_dades:
            linies.append(f"Fuentes integradas (HL7 FHIR): {', '.join(res.fonts_dades)}.")
        return "\n".join(linies)

