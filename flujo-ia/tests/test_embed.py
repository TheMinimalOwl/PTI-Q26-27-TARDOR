"""Tests de POST /embed (embeddings para la columna products.embedding).

Casi todos usan un modelo simulado (rapido, sin descargas); uno usa el
e5-small real para comprobar la dimension y la norma.
"""

from __future__ import annotations

import numpy as np
import pytest

from rag import config, serve

CLAVE = "clave-de-test"


class _EmbedderFalso:
    """Imita a `Embedder`: guarda lo que recibe y devuelve vectores de norma 1."""

    def __init__(self):
        self.spec = config.embedding_spec("e5-small")
        self.llamadas: list[tuple[list[str], bool]] = []

    def encode(self, texts, is_query=False, normalize=True):
        self.llamadas.append((list(texts), is_query))
        prefijo = self.spec.query_prefix if is_query else self.spec.passage_prefix
        out = []
        for i, t in enumerate(texts):
            v = np.zeros(self.spec.dim, dtype=np.float32)
            v[(len(prefijo + t) + i) % self.spec.dim] = 1.0
            out.append(v)
        return np.asarray(out, dtype=np.float32).reshape(len(texts), self.spec.dim)


@pytest.fixture
def falso(monkeypatch):
    f = _EmbedderFalso()
    monkeypatch.setenv("RAG_EMBED_API_KEY", CLAVE)
    monkeypatch.setitem(serve._ESTADO, "embed", f)
    serve.app.config["TESTING"] = True
    return f


@pytest.fixture
def cliente(falso):
    with serve.app.test_client() as c:
        yield c


def _post(c, body, clave=CLAVE):
    headers = {"X-API-Key": clave} if clave is not None else {}
    return c.post("/embed", json=body, headers=headers)


def test_sin_clave_da_401(cliente):
    assert _post(cliente, {"texts": ["hola"]}, clave=None).status_code == 401


def test_clave_incorrecta_da_401(cliente):
    assert _post(cliente, {"texts": ["hola"]}, clave="otra").status_code == 401


def test_servicio_sin_clave_configurada_da_503(cliente, monkeypatch):
    monkeypatch.delenv("RAG_EMBED_API_KEY", raising=False)
    assert _post(cliente, {"texts": ["hola"]}).status_code == 503


def test_devuelve_384_floats_en_orden(cliente, falso):
    r = _post(cliente, {"texts": ["leche entera", "aceite de oliva"]})
    assert r.status_code == 200
    embs = r.get_json()["embeddings"]
    assert len(embs) == 2
    assert all(len(v) == 384 for v in embs)
    assert falso.llamadas == [(["leche entera", "aceite de oliva"], False)]


def test_kind_por_defecto_passage_y_query(cliente, falso):
    _post(cliente, {"texts": ["a"]})
    _post(cliente, {"texts": ["b"], "kind": "query"})
    assert [q for _, q in falso.llamadas] == [False, True]


def test_no_duplica_el_prefijo(cliente, falso):
    _post(cliente, {"texts": ["passage: leche", "query: agua"], "kind": "passage"})
    assert falso.llamadas[0][0] == ["leche", "agua"]


def test_lista_vacia(cliente, falso):
    r = _post(cliente, {"texts": []})
    assert r.status_code == 200
    assert r.get_json() == {"embeddings": []}
    assert falso.llamadas == []


@pytest.mark.parametrize(
    "body",
    [None, [], {"texts": "hola"}, {"texts": [1, 2]}, {}, {"texts": ["a"], "kind": "doc"}],
)
def test_cuerpo_invalido_da_400(cliente, body):
    if body is None:
        r = cliente.post("/embed", data="no-json", headers={"X-API-Key": CLAVE, "Content-Type": "application/json"})
    else:
        r = _post(cliente, body)
    assert r.status_code == 400


def test_demasiados_textos_da_413(cliente):
    assert _post(cliente, {"texts": ["x"] * (serve.EMBED_MAX_TEXTS + 1)}).status_code == 413


def test_texto_demasiado_largo_da_413(cliente):
    assert _post(cliente, {"texts": ["x" * (serve.EMBED_MAX_CHARS + 1)]}).status_code == 413


def test_health_publica_el_bloque_embed(cliente):
    d = cliente.get("/health").get_json()
    assert d["embed"] == {"model": "e5-small", "dim": 384, "key_configured": True}


def test_modelo_fijo_aunque_el_indice_use_otro(monkeypatch):
    """Si el retriever usa otro modelo, /embed carga e5-small aparte."""
    otro = type("E", (), {"spec": config.embedding_spec("bge-m3")})()
    monkeypatch.setitem(serve._ESTADO, "embed", None)
    monkeypatch.setitem(serve._ESTADO, "retriever", type("R", (), {"embedder": otro})())
    emb = serve._embedder_embed()
    assert emb is not otro
    assert emb.spec.key == "e5-small"


def test_reutiliza_el_modelo_del_indice(monkeypatch):
    propio = type("E", (), {"spec": config.embedding_spec("e5-small")})()
    monkeypatch.setitem(serve._ESTADO, "embed", None)
    monkeypatch.setitem(serve._ESTADO, "retriever", type("R", (), {"embedder": propio})())
    assert serve._embedder_embed() is propio


def test_e5_small_real(monkeypatch):
    """Con el modelo real: 384 dimensiones y norma 1."""
    monkeypatch.setenv("RAG_EMBED_API_KEY", CLAVE)
    serve.inicializar("e5-small", "none")
    with serve.app.test_client() as c:
        r = _post(c, {"texts": ["leche entera 1 l", "agua mineral"], "kind": "passage"})
    assert r.status_code == 200
    embs = np.asarray(r.get_json()["embeddings"])
    assert embs.shape == (2, 384)
    assert np.allclose(np.linalg.norm(embs, axis=1), 1.0, atol=1e-4)
