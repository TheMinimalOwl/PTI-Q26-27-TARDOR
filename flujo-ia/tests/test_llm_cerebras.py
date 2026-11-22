"""Tests del cliente de Cerebras (`RAG_LLM=cerebras`), sin red."""

from __future__ import annotations

import json

import pytest

from rag import config, llm
from rag.llm import CerebrasLLM, LLMError, build_llm


class Resp:
    def __init__(self, status, datos=None, lineas=None, texto=""):
        self.status_code = status
        self._datos = datos
        self._lineas = lineas or []
        self.text = texto or json.dumps(datos or {})

    def json(self):
        return self._datos

    def iter_lines(self, decode_unicode=True):
        yield from self._lineas

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def llamadas(monkeypatch):
    registro: list[dict] = []

    def montar(*respuestas):
        cola = list(respuestas)

        def post(url, json=None, headers=None, timeout=None, stream=False):
            registro.append({"url": url, "json": json, "headers": headers, "stream": stream})
            return cola.pop(0)

        monkeypatch.setattr(llm.requests, "post", post)
        return registro

    return montar


def _ok(contenido="RESPUESTA: hola\nFUENTES: [1]"):
    return Resp(200, {
        "choices": [{"message": {"content": "\n\n" + contenido, "reasoning": "pienso..."}, "finish_reason": "stop"}],
        "usage": {"total_tokens": 42},
        "time_info": {"total_time": 0.08},
    })


def test_sin_clave_explica_de_donde_sacarla(monkeypatch):
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    with pytest.raises(LLMError, match="CEREBRAS_API_KEY"):
        CerebrasLLM()


def test_build_llm_cerebras(monkeypatch):
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk-test")
    c = build_llm("cerebras")
    assert isinstance(c, CerebrasLLM)
    assert c.describe() == {"provider": "cerebras", "model": config.CEREBRAS_MODEL}
    assert "cerebras" in config.LLM_PROVIDERS


def test_chat_limpia_contenido_y_no_mezcla_el_razonamiento(llamadas):
    registro = llamadas(_ok())
    r = CerebrasLLM(model="gpt-oss-120b", api_key="csk-test").chat("sistema", "pregunta")
    assert r.text == "RESPUESTA: hola\nFUENTES: [1]"
    assert "pienso" not in r.text
    assert (r.provider, r.model, r.tokens) == ("cerebras", "gpt-oss-120b", 42)
    peticion = registro[0]
    assert peticion["url"].endswith("/chat/completions")
    assert peticion["headers"]["Authorization"] == "Bearer csk-test"
    assert peticion["json"]["messages"][0] == {"role": "system", "content": "sistema"}
    assert peticion["json"]["temperature"] == config.TEMPERATURE
    assert peticion["json"]["reasoning_effort"] == config.CEREBRAS_REASONING


def test_si_rechaza_reasoning_effort_reintenta_sin_el(llamadas):
    registro = llamadas(Resp(400, texto='{"message": "reasoning_effort not supported"}'), _ok())
    r = CerebrasLLM(api_key="csk-test").chat("s", "u")
    assert r.text.startswith("RESPUESTA")
    assert "reasoning_effort" not in registro[1]["json"]


def test_error_http_es_llmerror(llamadas):
    llamadas(Resp(401, texto='{"message": "Wrong API Key"}'))
    with pytest.raises(LLMError, match="Cerebras 401"):
        CerebrasLLM(api_key="csk-mala").chat("s", "u")


def test_stream_emite_solo_el_contenido(llamadas):
    def evento(delta):
        return "data: " + json.dumps({"choices": [{"delta": delta}]})

    llamadas(Resp(200, lineas=[
        evento({"role": "assistant"}),
        evento({"reasoning": "pienso"}),
        evento({"content": "\n\nRESPUESTA:"}),
        "",
        evento({"content": " hola"}),
        "data: [DONE]",
    ]))
    trozos = list(CerebrasLLM(api_key="csk-test").chat_stream("s", "u"))
    assert trozos == ["RESPUESTA:", " hola"]
