"""Lectura i edició segura de config/rules.yaml des de l'API.

Només es poden tocar els paràmetres de EDITABLES (llista blanca amb rang i tipus). Abans d'escriure:
1) es validen tipus i rangs, 2) es comprova la coherència (p. ex. tall "alt" < tall "molt alt"),
3) s'avalua tot el cupo amb la configuració nova i 4) es desa una còpia de seguretat del fitxer.
L'escriptura es fa amb ruamel.yaml per conservar els comentaris del fitxer.
"""
from __future__ import annotations

import io
import math
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml
from ruamel.yaml import YAML


@dataclass(frozen=True)
class Editable:
    cami: str  # camí amb punts dins de rules.yaml (els índexs de llista són números)
    grup: str
    etiqueta: str
    unitat: str = ""
    minim: float = 0
    maxim: float = 100
    pas: float = 1
    tipus: str = "numero"  # "numero" | "boolea"
    ajuda: str = ""


_RCV = "rules.risc_cardiovascular"
_G_RCV, _G_REN, _G_DER, _G_PRI = ("Cortes de riesgo cardiovascular", "Cribado renal", "Derivación a Nefrología",
                                  "Priorización del cupo")


def _talls(i: int, tram: str) -> list[Editable]:
    return [
        Editable(f"{_RCV}.talls_per_edat.{i}.alt", _G_RCV, f"{tram}: riesgo alto desde", "%", 0.5, 50, 0.5),
        Editable(f"{_RCV}.talls_per_edat.{i}.molt_alt", _G_RCV, f"{tram}: riesgo muy alto desde", "%", 0.5, 50, 0.5),
    ]


EDITABLES: list[Editable] = [
    *_talls(0, "< 50 años"), *_talls(1, "50-69 años"), *_talls(2, "≥ 70 años"),
    Editable(f"{_RCV}.talls_regicor.alt", _G_RCV, "REGICOR: riesgo alto desde", "%", 0.5, 50, 0.5),
    Editable(f"{_RCV}.talls_regicor.molt_alt", _G_RCV, "REGICOR: riesgo muy alto desde", "%", 0.5, 50, 0.5),
    Editable(f"{_RCV}.ckd_addon.enabled", _G_RCV, "Aplicar CKD Add-on si hay afectación renal", tipus="boolea"),
    Editable("rules.uacr_falta.max_mesos_sense_prova", _G_REN, "Meses máximos sin UACR", "meses", 3, 60, 1,
             ajuda="En DM2, HTA o ERC: alerta si el último UACR es más antiguo"),
    Editable("rules.creatinina_falta.max_mesos_sense_prova", _G_REN, "Meses máximos sin creatinina", "meses", 3, 60, 1),
    Editable("rules.fge_descens.descens_anual_llindar", _G_REN, "Pendiente del FGe: pérdida anual de alerta",
             "mL/min/1,73m²/año", 1, 20, 0.5, ajuda="Alerta si el FGe cae más rápido que este valor"),
    Editable("rules.albuminuria_sense_accio.uacr_llindar", _G_REN, "UACR que exige nefroprotección", "mg/g", 10, 300, 5),
    Editable("rules.mrc_no_diagnosticada.fge_llindar", _G_REN, "FGe criterio de ERC (por debajo de)",
             "mL/min/1,73m²", 30, 90, 1),
    Editable("motor.derivacio_nefrologia.kfre_5a_pct", _G_DER, "KFRE a 5 años para derivar", "%", 1, 50, 0.5),
    Editable("motor.derivacio_nefrologia.fge_max", _G_DER, "FGe para derivar (por debajo de)", "mL/min/1,73m²", 10, 45, 1),
    Editable("motor.derivacio_nefrologia.uacr_min", _G_DER, "UACR para derivar", "mg/g", 100, 3000, 50),
    Editable(f"{_RCV}.pes", _G_PRI, "Peso de la alerta de riesgo CV infratratado", "puntos", 0, 100, 1,
             ajuda="Puntos que suma a la prioridad del paciente (0-100)"),
    Editable("motor.prioritat.nivell_alt", _G_PRI, "Puntuación mínima del nivel ALT", "puntos", 1, 100, 1),
    Editable("motor.prioritat.nivell_mitja", _G_PRI, "Puntuación mínima del nivel MITJA", "puntos", 1, 100, 1),
]
_PER_CAMI = {e.cami: e for e in EDITABLES}


class ErrorValidacio(ValueError):
    """Canvis rebutjats: `errors` és un diccionari camí -> motiu (en castellà, per mostrar a la web)."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _node(arrel, cami: str):
    """Retorna (contenidor, clau) de l'últim element del camí."""
    parts = [int(p) if p.isdigit() else p for p in cami.split(".")]
    node = arrel
    for p in parts[:-1]:
        node = node[p]
    return node, parts[-1]


def _valor(arrel, cami: str):
    node, clau = _node(arrel, cami)
    return node[clau]


class RulesStore:
    def __init__(self, cami: str | Path, carpeta_backups: str | Path | None = None):
        self.cami = Path(cami)
        self.carpeta_backups = Path(carpeta_backups) if carpeta_backups else self.cami.parent / "backups"

    def carrega(self) -> dict:
        return yaml.safe_load(self.cami.read_text(encoding="utf-8"))

    def editables(self, config: dict | None = None) -> list[dict]:
        config = config or self.carrega()
        return [{**asdict(e), "valor": _valor(config, e.cami)} for e in EDITABLES]

    def backups(self) -> list[str]:
        if not self.carpeta_backups.is_dir():
            return []
        return sorted(p.name for p in self.carpeta_backups.glob("rules_*.yaml"))

    def aplica(self, canvis: dict, prova: Callable[[dict], None] | None = None) -> dict:
        """Valida i desa els canvis ({camí: valor}). `prova(config)` ha de fallar si el motor no pot
        treballar amb la configuració nova. Retorna {"canviats": {...}, "backup": nom del fitxer}."""
        if not isinstance(canvis, dict) or not canvis:
            raise ErrorValidacio({"canvis": "No se ha enviado ningún cambio"})
        errors: dict[str, str] = {}
        nets: dict[str, float | bool] = {}
        for cami, valor in canvis.items():
            e = _PER_CAMI.get(cami)
            if e is None:
                errors[str(cami)] = "Parámetro no editable"
            elif e.tipus == "boolea":
                if isinstance(valor, bool):
                    nets[cami] = valor
                else:
                    errors[cami] = "Debe ser verdadero o falso"
            elif isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
                errors[cami] = "Debe ser un número"
            elif not e.minim <= valor <= e.maxim:
                errors[cami] = f"Fuera de rango ({e.minim:g} a {e.maxim:g} {e.unitat})".rstrip()
            else:
                nets[cami] = int(valor) if float(valor).is_integer() else float(valor)
        if errors:
            raise ErrorValidacio(errors)

        text_actual = self.cami.read_text(encoding="utf-8")
        rt = YAML()  # round-trip: conserva comentaris i format
        rt.preserve_quotes = True
        rt.width = 4096
        rt.indent(mapping=2, sequence=4, offset=2)  # el sagnat de llistes que ja fa servir rules.yaml
        document = rt.load(text_actual)
        canviats = {}
        for cami, valor in nets.items():
            node, clau = _node(document, cami)
            if node[clau] != valor:
                canviats[cami] = {"abans": node[clau], "ara": valor}
                node[clau] = valor
        sortida = io.StringIO()
        rt.dump(document, sortida)
        text_nou = sortida.getvalue()
        config = yaml.safe_load(text_nou)

        errors = self._coherencia(config)
        if errors:
            raise ErrorValidacio(errors)
        if prova:
            try:
                prova(config)
            except Exception as exc:  # el motor no pot treballar amb aquests valors: no es desa res
                raise ErrorValidacio({"motor": f"El motor no puede evaluar el cupo con estos valores: {exc}"}) from exc
        if not canviats:
            return {"canviats": {}, "backup": None}

        self.carpeta_backups.mkdir(parents=True, exist_ok=True)
        backup = self.carpeta_backups / f"rules_{datetime.now():%Y%m%d-%H%M%S-%f}.yaml"
        shutil.copy2(self.cami, backup)
        temporal = self.cami.with_suffix(".yaml.tmp")
        temporal.write_text(text_nou, encoding="utf-8", newline="\n")
        temporal.replace(self.cami)
        return {"canviats": canviats, "backup": backup.name}

    @staticmethod
    def _coherencia(config: dict) -> dict[str, str]:
        errors = {}
        r = config["rules"]["risc_cardiovascular"]
        for i, t in enumerate(r["talls_per_edat"]):
            if not t["alt"] < t["molt_alt"]:
                errors[f"{_RCV}.talls_per_edat.{i}.molt_alt"] = "El corte de riesgo muy alto debe ser mayor que el de riesgo alto"
        if not r["talls_regicor"]["alt"] < r["talls_regicor"]["molt_alt"]:
            errors[f"{_RCV}.talls_regicor.molt_alt"] = "El corte de riesgo muy alto debe ser mayor que el de riesgo alto"
        p = config["motor"]["prioritat"]
        if not p["nivell_mitja"] < p["nivell_alt"]:
            errors["motor.prioritat.nivell_mitja"] = "Debe ser menor que la puntuación del nivel ALT"
        return errors
