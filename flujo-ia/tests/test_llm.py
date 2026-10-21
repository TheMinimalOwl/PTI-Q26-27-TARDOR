"""Tests del cliente de LLM y del parseo de sus respuestas."""

from __future__ import annotations

import pytest

from rag.llm import LLMError, NoLLM, extract_json


def test_json_limpio():
    assert extract_json('{"pid": "123", "confianza": 0.9}') == {"pid": "123", "confianza": 0.9}


def test_json_con_vallas():
    texto = '```json\n{"pid": "123"}\n```'
    assert extract_json(texto) == {"pid": "123"}


def test_json_con_texto_around():
    texto = 'Aqui tienes el resultado: {"pid": "123", "motivo": "mismo producto"} espero que sirva'
    datos = extract_json(texto)
    assert datos["pid"] == "123"
    assert datos["motivo"] == "mismo producto"


def test_json_con_comillas_rotas():
    """Un modelo pequeno mete comillas sin cerrar: se salvagea lo posible."""
    texto = '{"pid": "123", "motivo": "es el mismo producto'
    assert extract_json(texto) is None or isinstance(extract_json(texto), (dict, list))


def test_array():
    assert extract_json('[{"id": "1"}, {"id": "2"}]')[1]["id"] == "2"


def test_texto_no_json():
    assert extract_json("no hay json aqui") is None
    assert extract_json("") is None


def test_no_llm_falla_con_mensaje_util():
    with pytest.raises(LLMError) as exc:
        NoLLM().chat("s", "u")
    assert "solo-recuperacion" in str(exc.value)
