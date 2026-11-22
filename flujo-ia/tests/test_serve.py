"""Tests del servicio HTTP.

Se comprueba con el cliente de test de Flask (no hace falta ni modelo ni
LLM) y tambien que el modulo se puede arrancar como script, que es lo que
hace la unidad systemd.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from rag import serve

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def cliente():
    serve.inicializar("e5-small", "none")
    serve.app.config["TESTING"] = True
    with serve.app.test_client() as c:
        yield c


def test_health(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert d["n_productos"] > 0
    assert d["store"] == "local"  # los tests fijan RAG_STORE=local (conftest)
    assert d["llm"]["provider"] == "none"


def test_search_devuelve_productos(cliente):
    r = cliente.post("/search", json={"query": "aceite de oliva", "k": 3})
    assert r.status_code == 200
    d = r.get_json()
    assert d["resultados"]
    assert "id" in d["resultados"][0]
    assert "score" in d["resultados"][0]


def test_search_sin_query_da_400(cliente):
    assert cliente.post("/search", json={}).status_code == 400


def test_ask_sin_llm_devuelve_json_del_esquema(cliente):
    """Sin LLM hay respuesta de retrieval, pero la forma es la del esquema."""
    r = cliente.post("/ask", json={"question": "¿cuanto cuesta el aceite?"})
    assert r.status_code == 200
    d = r.get_json()
    for clave in ("question", "answer", "sources", "confidence", "abstained", "guardrails", "provider"):
        assert clave in d
    assert d["guardrails"]["ok"] in (True, False)
    assert isinstance(d["guardrails"]["warnings"], list)


def test_ask_sin_question_da_400(cliente):
    assert cliente.post("/ask", json={}).status_code == 400


def test_stream_sin_llm_da_400(cliente):
    assert cliente.post("/ask/stream", json={"question": "x"}).status_code == 400


def test_stream_fin_es_json_util_con_guardrails(cliente):
    """El fin del streaming tiene que ser JSON util para la app.

    Antes 'hits' salia como repr() de los objetos Python (un string
    inservible), el texto traia las cabeceras 'RESPUESTA:'/'FUENTES:' del
    prompt y no habia guardrails. Ahora el contrato es el de /ask.
    """
    from rag.llm import BaseLLM, LLMResponse

    class LLMFalso(BaseLLM):
        provider = "fake"
        model = "fake-1b"

        def chat(self, system: str, user: str) -> LLMResponse:
            return LLMResponse(text="", provider=self.provider, model=self.model)

        def chat_stream(self, system: str, user: str):
            trozo = "RESPUESTA: cuesta 12.50 EUR en [1].\nFUENTES: [1] Aceite"
            for i in range(0, len(trozo), 5):
                yield trozo[i : i + 5]

    serve._ESTADO["llm"] = LLMFalso()
    r = cliente.post("/ask/stream", json={"question": "¿cuanto cuesta el aceite?"})
    assert r.status_code == 200

    eventos = {}
    for bloque in r.get_data(as_text=True).split("\n\n"):
        if not bloque.strip():
            continue
        lineas = bloque.split("\n")
        ev = next((l[7:] for l in lineas if l.startswith("event: ")), "")
        data = next((l[6:] for l in lineas if l.startswith("data: ")), "")
        if ev:
            eventos[ev] = json.loads(data)

    assert "token" in eventos
    fin = eventos["fin"]
    assert isinstance(fin["hits"], list) and fin["hits"]
    assert isinstance(fin["hits"][0], dict) and "id" in fin["hits"][0]
    assert "RESPUESTA:" not in fin["respuesta"]
    assert "FUENTES:" not in fin["respuesta"]
    assert fin["fuentes"] == ["1"]
    assert fin["abstained"] in (True, False)
    assert "ok" in fin["guardrails"]


def test_equiv_por_nombre(cliente):
    r = cliente.post("/equiv", json={"nombre": "aceite de oliva", "chain": "carrefour"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["origen"]["id"]
    assert isinstance(d["candidatos"], list)


def test_cors_permite_otro_origen(cliente):
    """La app llama desde otro origen: todas las respuestas llevan CORS."""
    r = cliente.get("/health")
    assert r.headers["Access-Control-Allow-Origin"] == "*"


def test_cors_preflight_options(cliente):
    """El preflight del navegador (OPTIONS) tiene que contestar 200 con CORS."""
    r = cliente.open("/ask", method="OPTIONS")
    assert r.status_code == 200
    assert r.headers["Access-Control-Allow-Origin"] == "*"
    assert "POST" in r.headers["Access-Control-Allow-Methods"]


def test_docs_devuelve_html(cliente):
    r = cliente.get("/docs")
    assert r.status_code == 200
    assert "text/html" in r.headers["Content-Type"]
    assert "/ask/stream" in r.get_data(as_text=True)


def test_probar_devuelve_html(cliente):
    """La pagina de prueba en vivo es el cliente de referencia de la app."""
    r = cliente.get("/probar")
    assert r.status_code == 200
    assert "text/html" in r.headers["Content-Type"]
    html = r.get_data(as_text=True)
    assert "/ask/stream" in html
    assert "10.4.41.108" in html  # default de la base URL al abrirlo como fichero


def test_el_modulo_se_puede_arrancar_como_script():
    """`python -m rag.serve --help` tiene que funcionar: lo usa la unidad systemd."""
    r = subprocess.run(
        [sys.executable, "-m", "rag.serve", "--help"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0
    assert "--port" in r.stdout
