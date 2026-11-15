"""Estat de l'alerta de cada pacient ("Pendiente", "Citado", "Revisado", "Pospuesto hasta …") i log d'auditoria.

És l'única cosa que l'add-on desa: no són dades clíniques de l'estació, sinó el que el professional ha fet amb
cada alerta. Simula l'emmagatzematge dins de la infraestructura de Salut: un fitxer local per servidor FHIR
(cada estació clínica té els seus estats), a `<carpeta>/<servidor>/`:

    estats.json        estat actual de cada pacient que no és "pendent" (els que no hi són, són pendents)
    auditoria.jsonl    una línia per canvi: qui, quan, quin pacient, quin estat (i l'anterior); només s'hi afegeix

Regles:
    - Un pacient sense registre és "pendent".
    - "posposat" porta una data `fins`; quan la data de referència del motor hi arriba, torna a comptar com a
      pendent (es mostra com a posposició vençuda; el registre no s'esborra).
    - Cada registre guarda les alertes (`regles`) que tenia el pacient quan es va canviar l'estat. Si en un
      recàlcul (dades noves) apareix una alerta que no hi era, l'estat torna a "pendent" automàticament i el
      canvi queda al log amb l'add-on com a autor.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import date, datetime
from pathlib import Path

ESTATS = ("pendent", "citat", "revisat", "posposat")
TEXT_ESTAT = {"pendent": "Pendiente", "citat": "Citado", "revisat": "Revisado", "posposat": "Pospuesto"}
AUTOR_SISTEMA = {"id": None, "nom": "CardioAlert AP (recálculo automático)", "rol": None}


class ErrorEstat(ValueError):
    pass


def _ara() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def carpeta_servidor(servidor: str) -> str:
    """Nom de carpeta llegible i únic per a un servidor FHIR (o una font de proves)."""
    llegible = re.sub(r"[^A-Za-z0-9]+", "_", servidor).strip("_")[:60] or "servidor"
    return f"{llegible}_{hashlib.sha1(servidor.encode('utf-8')).hexdigest()[:8]}"


def efectiu(registre: dict | None, avui: date) -> dict:
    """Estat que compta ara: una posposició vençuda torna a ser pendent (amb `vencut` per explicar-ho)."""
    if not registre:
        return {"estat": "pendent", "fins": None, "quan": None, "qui": None, "vencut": False}
    estat, fins = registre["estat"], registre.get("fins")
    vencut = estat == "posposat" and fins is not None and date.fromisoformat(fins) <= avui
    return {"estat": "pendent" if vencut else estat, "fins": fins, "quan": registre.get("quan"),
            "qui": (registre.get("qui") or {}).get("nom"), "vencut": vencut,
            **({"estat_desat": estat} if vencut else {})}


class EstatsStore:
    def __init__(self, carpeta: str | Path):
        self.carpeta = Path(carpeta)
        self._pany = threading.RLock()
        self._cache: dict[str, dict] = {}  # servidor -> contingut d'estats.json (el fitxer mana: es llegeix un cop)

    # --- Fitxers ----------------------------------------------------------------------------

    def _dir(self, servidor: str) -> Path:
        return self.carpeta / carpeta_servidor(servidor)

    def _llegeix(self, servidor: str) -> dict:
        if servidor not in self._cache:
            cami = self._dir(servidor) / "estats.json"
            dades = json.loads(cami.read_text(encoding="utf-8")) if cami.is_file() else {}
            self._cache[servidor] = {"servidor": servidor, "pacients": dades.get("pacients", {})}
        return self._cache[servidor]

    def _desa(self, servidor: str, dades: dict) -> None:
        carpeta = self._dir(servidor)
        carpeta.mkdir(parents=True, exist_ok=True)
        temporal = carpeta / "estats.json.tmp"
        temporal.write_text(json.dumps(dades, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporal, carpeta / "estats.json")  # escriptura atòmica: mai un fitxer a mitges

    def _audita(self, servidor: str, entrada: dict) -> None:
        carpeta = self._dir(servidor)
        carpeta.mkdir(parents=True, exist_ok=True)
        with (carpeta / "auditoria.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")

    # --- Consulta ---------------------------------------------------------------------------

    def registres(self, servidor: str) -> dict[str, dict]:
        with self._pany:
            return dict(self._llegeix(servidor)["pacients"])

    def registre(self, servidor: str, pacient: str) -> dict | None:
        with self._pany:
            return self._llegeix(servidor)["pacients"].get(pacient)

    def auditoria(self, servidor: str, pacient: str | None = None, limit: int | None = None) -> list[dict]:
        """Entrades del log, de la més recent a la més antiga."""
        cami = self._dir(servidor) / "auditoria.jsonl"
        if not cami.is_file():
            return []
        with self._pany:
            linies = cami.read_text(encoding="utf-8").splitlines()
        entrades = [e for e in (json.loads(x) for x in reversed(linies) if x.strip())
                    if pacient is None or e["pacient"] == pacient]
        return entrades[:limit] if limit else entrades

    # --- Canvis -----------------------------------------------------------------------------

    def canvia(self, servidor: str, pacient: str, estat: str, professional: dict, regles: set[str],
               avui: date, fins: str | None = None) -> dict:
        """Canvi manual d'estat fet per un professional. `regles`: alertes que té ara el pacient."""
        if estat not in ESTATS:
            raise ErrorEstat(f"Estado no válido: {estat!r} ({', '.join(ESTATS)})")
        if not isinstance(professional, dict) or not str(professional.get("nom") or "").strip():
            raise ErrorEstat("Falta el profesional (contexto de lanzamiento): el cambio no se puede auditar")
        if estat == "posposat":
            try:
                data_fins = date.fromisoformat(str(fins))
            except ValueError:
                raise ErrorEstat("«Pospuesto» necesita una fecha válida (AAAA-MM-DD)") from None
            if data_fins <= avui:
                raise ErrorEstat(f"La fecha de «Pospuesto hasta» debe ser posterior a hoy ({avui.strftime('%d/%m/%Y')})")
            fins = data_fins.isoformat()
        elif fins:
            raise ErrorEstat("Solo «Pospuesto» lleva fecha")
        qui = {"id": professional.get("id"), "nom": str(professional["nom"]).strip(), "rol": professional.get("rol")}
        with self._pany:
            dades = self._llegeix(servidor)
            anterior = efectiu(dades["pacients"].get(pacient), avui)
            quan = _ara()
            if estat == "pendent":
                dades["pacients"].pop(pacient, None)
            else:
                dades["pacients"][pacient] = {"estat": estat, "fins": fins, "regles": sorted(regles), "quan": quan,
                                              "qui": qui}
            self._desa(servidor, dades)
            self._audita(servidor, {"quan": quan, "qui": qui, "pacient": pacient, "estat": estat, "fins": fins,
                                    "anterior": anterior["estat"], "origen": "manual", "motiu": None})
            return efectiu(dades["pacients"].get(pacient), avui)

    def sincronitza(self, servidor: str, regles_actuals: dict[str, set[str]]) -> list[str]:
        """Després d'un càlcul: els pacients amb una alerta que no tenien en canviar l'estat tornen a "pendent".
        `regles_actuals`: pacient -> alertes d'ara (els pacients que no hi són no es toquen). Retorna els tornats."""
        with self._pany:
            dades = self._llegeix(servidor)
            tornats = []
            for pacient, reg in list(dades["pacients"].items()):
                if pacient not in regles_actuals:
                    continue
                noves = sorted(regles_actuals[pacient] - set(reg.get("regles", [])))
                if noves:
                    del dades["pacients"][pacient]
                    tornats.append((pacient, reg["estat"], noves))
            if not tornats:
                return []
            self._desa(servidor, dades)
            quan = _ara()
            for pacient, anterior, noves in tornats:
                self._audita(servidor, {"quan": quan, "qui": AUTOR_SISTEMA, "pacient": pacient, "estat": "pendent",
                                        "fins": None, "anterior": anterior, "origen": "recalculo",
                                        "motiu": f"Alerta nueva tras el recálculo: {', '.join(noves)}"})
            return [p for p, _, _ in tornats]
