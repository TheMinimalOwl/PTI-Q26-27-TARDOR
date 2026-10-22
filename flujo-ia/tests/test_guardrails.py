"""Tests de los guardrails y del JSON Schema de la respuesta.

Los guardrails son la red de seguridad del asistente: comprueban que la
respuesta no cite productos que no estan en el contexto y que no invente
cifras. En un comparador de precios, un precio inventado es el fallo mas
grave posible.
"""

from __future__ import annotations

import numpy as np
import pytest

from rag.guardrails import (
    aplicar_guardrails,
    construir_respuesta,
    validar,
)
from rag.retriever import Retriever
from rag.store import VectorStore


@pytest.fixture
def hits():
    docs = [
        {"id": "1", "name": "Aceite de oliva 1 l", "chain": "mercadona", "category": "Aceites", "total": "12.50", "unit_price": "12.50", "unit": "l", "size": "1", "size_format": "l", "url": "u1"},
        {"id": "2", "name": "Aceite 0.5 l", "chain": "carrefour", "category": "Aceites", "total": "6.80", "unit_price": "13.60", "unit": "l", "size": "0.5", "size_format": "l", "url": "u2"},
    ]
    vectores = np.array([[1.0, 0.0], [0.9, 0.1]], dtype=np.float32)
    store = VectorStore(dim=2)
    store.add(vectores, docs)

    class HitFalso:
        def __init__(self, doc):
            self.doc = doc
            self.score = 1.0
            self.rank = 1

    return [HitFalso(d) for d in docs]


def test_respuesta_correcta_pasa(hits):
    g = aplicar_guardrails("El mas barato es [1] Aceite de oliva 1 l, 12.50 EUR/l", hits)
    assert g.ok is True
    assert g.citas_validas is True
    assert g.cifras_validas is True
    assert g.advertencias == []


def test_cita_inventada_se_detecta_y_se_quita(hits):
    g = aplicar_guardrails("El mas barato es [999] Producto fantasma, 12.50 EUR/l", hits)
    assert g.ok is False
    assert g.citas_validas is False
    assert g.citas_inventadas == ["999"]
    assert "[999]" not in g.respuesta_corregida
    assert any("no estan en el contexto" in w for w in g.advertencias)


def test_cita_inventada_sin_estricto_no_se_toca(hits):
    g = aplicar_guardrails("El mas barato es [999] Fantasma", hits, estricto=False)
    assert g.ok is False
    assert "[999]" in g.respuesta_corregida


def test_precio_inventado_se_detecta(hits):
    g = aplicar_guardrails("El mas barato es [1] Aceite, cuesta 3.99 EUR/l", hits)
    assert g.ok is False
    assert g.cifras_validas is False
    assert any("3.99" in w for w in g.advertencias)


def test_precio_con_otra_decimale_se_acepta(hits):
    """12,5 y 12.50 son la misma cifra."""
    g = aplicar_guardrails("El mas barato es [1] Aceite, 12,5 EUR/l", hits)
    assert g.cifras_validas is True


def test_abstencion_es_valida(hits):
    g = aplicar_guardrails("No he encontrado ese producto", hits)
    assert g.abstention is True
    assert g.citas_validas is True


def test_sin_contexto_hay_abstencion_forzosa(hits):
    g = aplicar_guardrails("Te lo invento: 12,50 EUR", [])
    assert g.abstention is True
    assert g.ok is False
    assert "No he encontrado" in g.respuesta_corregida


def test_la_respuesta_cumple_el_json_schema(hits):
    g = aplicar_guardrails("El mas barato es [1] Aceite, 12.50 EUR/l", hits)
    respuesta = construir_respuesta(
        question="¿cual es el mas barato?",
        respuesta=g.respuesta_corregida,
        hits=hits,
        fuentes=["1"],
        confianza=0.8,
        guardrails=g,
        provider="ollama",
        model="qwen3:8b",
        latencia_s=1.234,
    )
    assert validar(respuesta) == []
    assert respuesta["sources"][0]["id"] == "1"
    assert respuesta["sources"][0]["price_unit"] == 12.5
    assert respuesta["guardrails"]["ok"] is True


def test_el_validador_coge_una_respuesta_rota():
    respuesta = {"question": "x", "answer": "y"}  # faltan campos obligatorios
    errores = validar(respuesta)
    assert errores
    assert any("sources" in e for e in errores)


def test_la_confianza_se_acota():
    respuesta = construir_respuesta(
        question="q", respuesta="r", hits=[], confianza=5.0, provider="ollama"
    )
    assert respuesta["confidence"] == 1.0
