"""Configuracion comun de los tests.

El servicio usa por defecto la BD real (`RAG_STORE=api`). Los tests no
deben depender de la red: trabajan con el indice local de data/raw (los
datos de prueba), salvo los que cambian `config.STORE_BACKEND` a proposito.
"""

from __future__ import annotations

import pytest

from rag import config


@pytest.fixture(autouse=True)
def _store_de_prueba(monkeypatch):
    monkeypatch.setattr(config, "STORE_BACKEND", "local")
