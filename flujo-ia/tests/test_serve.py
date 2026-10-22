"""Tests del servicio HTTP.

Se comprueba con el cliente de test de Flask (no hace falta ni modelo ni
LLM) y tambien que el modulo se puede arrancar como script, que es lo que
hace la unidad systemd.
"""

from __future__ import annotations

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


def test_equiv_por_nombre(cliente):
    r = cliente.post("/equiv", json={"nombre": "aceite de oliva", "chain": "carrefour"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["origen"]["id"]
    assert isinstance(d["candidatos"], list)


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
