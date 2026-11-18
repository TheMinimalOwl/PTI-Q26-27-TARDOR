"""Tests del server MCP (rag.mcp_server).

Dos niveles: las tools se prueban llamandolas como funciones con la API y
la BD simuladas, y ademas hay una prueba de **protocolo real** que lanza
el proceso por stdio y habla con el con el cliente oficial de MCP.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
import requests

from rag import config, mcp_server, pgstore

RAIZ = Path(__file__).resolve().parent.parent

TOOLS_ESPERADAS = {
    "estado",
    "buscar",
    "preguntar",
    "equivalencia",
    "consulta_productos",
    "productos_similares",
}


class RespFalsa:
    def __init__(self, datos, status=200):
        self._datos = datos
        self.status_code = status

    def json(self):
        return self._datos


@pytest.fixture
def cliente_api(monkeypatch):
    """Instala una API simulada y devuelve un capturador de la ultima llamada."""

    def _instalar(datos, status=200):
        captura = {}

        def fake(metodo, url, json=None, timeout=None):
            captura.update(metodo=metodo, url=url, body=json)
            return RespFalsa(datos, status)

        monkeypatch.setattr(mcp_server.requests, "request", fake)
        return captura

    return _instalar


# -- tools sobre la API ---------------------------------------------------


def test_estado_con_fixture(cliente_api):
    datos = {"ok": True, "n_productos": 257, "store": "local"}
    captura = cliente_api(datos)
    assert mcp_server.estado() == datos
    assert captura["url"].endswith("/health")
    assert captura["metodo"] == "GET"


def test_buscar_pasa_query_y_filtros(cliente_api):
    captura = cliente_api({"resultados": []})
    res = mcp_server.buscar("aceite de oliva", k=3, chain="mercadona", max_total=5)
    assert captura["url"].endswith("/search")
    assert captura["body"] == {
        "query": "aceite de oliva",
        "k": 3,
        "chain": "mercadona",
        "category": None,
        "min_total": None,
        "max_total": 5,
    }
    assert "resultados" in res


def test_preguntar_usa_ask_con_estricto(cliente_api):
    captura = cliente_api({"answer": "x", "abstained": False})
    mcp_server.preguntar("¿cuanto cuesta?", k=4, estricto=False)
    assert captura["url"].endswith("/ask")
    assert captura["body"] == {"question": "¿cuanto cuesta?", "k": 4, "estricto": False}


def test_equivalencia_devuelve_el_error_de_la_api(cliente_api):
    """La API contesta 404 con su mensaje: se pasa tal cual al agente."""
    cliente_api({"error": "no se encuentra el producto origen"}, status=404)
    res = mcp_server.equivalencia(id="999")
    assert res == {"error": "no se encuentra el producto origen"}


def test_api_caida_da_error_amable(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("rechazado")

    monkeypatch.setattr(mcp_server.requests, "request", boom)
    res = mcp_server.estado()
    assert "error" in res and "rag.serve" in res["error"]


# -- tools sobre la BD ----------------------------------------------------


def test_consulta_productos_sin_dsn_explica_que_falta(monkeypatch):
    monkeypatch.setattr(config, "PG_DSN", "")
    res = mcp_server.consulta_productos()
    assert "error" in res and "RAG_PG_DSN" in res["error"]


def test_consulta_productos_usa_el_store(monkeypatch):
    monkeypatch.setattr(config, "PG_DSN", "postgresql://x")

    class PgStub:
        def __init__(self, *a, **k):
            pass

        def _columnas_reales(self):
            return {"id": "id"}

        def filtrar(self, filtros, limite=20):
            assert filtros.chain == "lidl"
            return [{"id": "1", "name": "Arroz", "chain": "lidl"}]

    monkeypatch.setattr(pgstore, "PgStore", PgStub)
    res = mcp_server.consulta_productos(chain="lidl", limite=1)
    assert res["n"] == 1 and res["productos"][0]["name"] == "Arroz"


def test_productos_similares_usa_el_store(monkeypatch):
    monkeypatch.setattr(config, "PG_DSN", "postgresql://x")

    class PgStub:
        def __init__(self, *a, **k):
            pass

        def _columnas_reales(self):
            return {"id": "id"}

        def similares(self, pid, k=5):
            assert pid == "10001" and k == 3
            return [{"id": "2", "name": "Otro", "score": 0.9}]

    monkeypatch.setattr(pgstore, "PgStore", PgStub)
    res = mcp_server.productos_similares("10001", k=3)
    assert res["n"] == 1 and res["productos"][0]["score"] == 0.9


def test_bucle_de_herramientas_registrado():
    nombres = set(mcp_server.mcp._tool_manager._tools)
    assert nombres == TOOLS_ESPERADAS


# -- protocolo real por stdio ---------------------------------------------


def test_server_stdio_responde_al_cliente_mcp():
    """Prueba de extremo a extremo: subprocess + cliente oficial de MCP."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def flujo():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "rag.mcp_server"],
            cwd=str(RAIZ),
        )
        async with stdio_client(params) as (leer, escribir):
            async with ClientSession(leer, escribir) as sesion:
                await sesion.initialize()
                tools = await sesion.list_tools()
                resultado = await sesion.call_tool("estado", {})
                return tools, resultado

    tools, resultado = asyncio.run(flujo())
    nombres = {t.name for t in tools.tools}
    assert nombres == TOOLS_ESPERADAS
    assert not resultado.is_error
    texto = "".join(getattr(c, "text", "") for c in (resultado.content or []))
    datos = json.loads(texto)
    # En tests no hay API en marcha: tiene que venir el error amable.
    assert "error" in datos or "ok" in datos
