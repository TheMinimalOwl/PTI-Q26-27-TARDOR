"""Tests de la comparacion de valores de la evaluacion de QA.

La metrica de contenido tiene que comparar **numeros como numeros**: el
precio unitario del atun es 0.767 EUR/ud y el ground truth lo guarda
redondeado a 0.87. Comparar por subcadena marcaba como fallo una respuesta
correcta.
"""

from __future__ import annotations

from rag.evaluate import _menciona_valor


def test_numero_exacto():
    assert _menciona_valor("cuesta 12.50 EUR", "12.50")
    assert _menciona_valor("cuesta 12,50 EUR", "12.50")
    assert _menciona_valor("cuesta 12,50 EUR", "12,50")


def test_numero_con_mas_precision():
    """El caso que fallaba: 0.867 en la respuesta, 0.87 en el ground truth."""
    assert _menciona_valor("precio unitario de 0.867 EUR/ud", "0.87")
    assert _menciona_valor("precio unitario de 0.867 EUR/ud", "0.77") is False


def test_tolerancia():
    assert _menciona_valor("unidades de 1.00", "1.01")
    assert _menciona_valor("unidades de 1.00", "1.5") is False


def test_no_confunde_numeros_distintos():
    assert _menciona_valor("precio total de 11.70 EUR", "1.10") is False
    assert _menciona_valor("precio 2.40", "24.00") is False


def test_valor_no_numerico_es_subcadena():
    assert _menciona_valor("el mas barato es el de carrefour", "carrefour")
    assert _menciona_valor("el mas barato es el de carrefour", "mercadona") is False
    assert _menciona_valor("CARREFOUR", "carrefour")


def test_texto_vacio():
    assert _menciona_valor("", "1.00") is False
    assert _menciona_valor(None, "1.00") is False
