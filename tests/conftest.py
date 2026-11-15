"""Configuració comuna: cap test escriu estats d'alertes ni logs d'auditoria a la carpeta real de l'add-on."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _estats_temporals(tmp_path_factory):
    anterior = os.environ.get("CARDIOALERT_ESTADOS_DIR")
    os.environ["CARDIOALERT_ESTADOS_DIR"] = str(tmp_path_factory.mktemp("estat_addon"))
    yield
    if anterior is None:
        os.environ.pop("CARDIOALERT_ESTADOS_DIR", None)
    else:
        os.environ["CARDIOALERT_ESTADOS_DIR"] = anterior
