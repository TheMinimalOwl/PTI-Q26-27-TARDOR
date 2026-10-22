"""Tests de los tres pipelines con un LLM simulado.

No se llama a ningun modelo: se comprueba que el pipeline monta bien el
contexto, que sabe leer la respuesta del LLM y que degrada con elegancia
cuando el LLM falla.
"""

from __future__ import annotations

import numpy as np
import pytest

from rag.llm import BaseLLM, LLMError, LLMResponse
from rag.pipelines import catalogo, equivalencia, format_context, qa
from rag.retriever import Filters, Retriever
from rag.store import VectorStore


class FakeLLM(BaseLLM):
    """Devuelve una respuesta fija y cuenta las llamadas."""

    provider = "fake"
    model = "fake-1b"

    def __init__(self, respuesta: str = "", error: Exception | None = None):
        self.respuesta = respuesta
        self.error = error
        self.llamadas: list[tuple[str, str]] = []

    def chat(self, system: str, user: str) -> LLMResponse:
        self.llamadas.append((system, user))
        if self.error:
            raise self.error
        return LLMResponse(text=self.respuesta, provider=self.provider, model=self.model)


class FakeEmbedder:
    """Embedder que devuelve vectores fijos segun el texto."""

    spec = type("Spec", (), {"key": "fake", "hf_id": "fake", "dim": 3, "note": ""})()

    def encode_one(self, text: str, is_query: bool = True) -> np.ndarray:
        v = np.zeros(3, dtype=np.float32)
        v[0] = 1.0 if "aceite" in text.lower() else 0.0
        v[1] = 1.0 if "leche" in text.lower() else 0.0
        v[2] = 1.0 if "mercadona" in text.lower() else 0.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode(self, texts, is_query=False):
        return np.array([self.encode_one(t, is_query) for t in texts], dtype=np.float32)

    def describe(self):
        return {"key": "fake"}


@pytest.fixture
def retriever() -> Retriever:
    docs = [
        {"id": "1", "name": "Aceite de oliva 1 l", "chain": "mercadona", "category": "Aceites", "total": "12.50", "unit_price": "12.50", "unit": "l", "size": "1", "size_format": "l", "url": "u1"},
        {"id": "2", "name": "Aceite de oliva 0.5 l", "chain": "carrefour", "category": "Aceites", "total": "6.80", "unit_price": "13.60", "unit": "l", "size": "0.5", "size_format": "l", "url": "u2"},
        {"id": "3", "name": "Leche entera 1 l", "chain": "mercadona", "category": "Leche", "total": "1.15", "unit_price": "1.15", "unit": "l", "size": "1", "size_format": "l", "url": "u3"},
    ]
    vectores = np.array(
        [[1.0, 0.0, 1.0], [0.95, 0.0, 0.0], [0.0, 1.0, 1.0]], dtype=np.float32
    )
    store = VectorStore(dim=3)
    store.add(vectores, docs)
    return Retriever(FakeEmbedder(), store)


def test_contexto_incluye_el_id_para_poder_citar(retriever):
    hits = retriever.search("aceite", k=2)
    contexto = format_context(hits)
    assert "[1]" in contexto
    assert "Aceite de oliva 1 l" in contexto
    assert "EUR/l" in contexto


def test_catalogo_sin_llm_devuelve_hits(retriever):
    res = catalogo(retriever, None, "aceite de oliva", k=2)
    assert len(res.hits) == 2
    assert res.respuesta is None


def test_catalogo_con_llm(retriever):
    llm = FakeLLM("MEJOR: [1] Aceite de oliva 1 l - precio total 12.50 EUR")
    res = catalogo(retriever, llm, "aceite de oliva", k=2)
    assert res.respuesta is not None
    assert "[1]" in res.respuesta
    # El prompt lleva el contexto con los ids.
    assert "[1]" in llm.llamadas[0][1]


def test_catalogo_degrada_si_el_llm_falla(retriever):
    llm = FakeLLM(error=LLMError("sin conexion"))
    res = catalogo(retriever, llm, "aceite", k=2)
    assert res.respuesta is None
    assert res.error is not None
    assert len(res.hits) == 2  # la recuperacion no se pierde


def test_qa_parte_la_respuesta_y_las_fuentes(retriever):
    llm = FakeLLM(
        "RESPUESTA: El aceite de 1 l cuesta 12.50 EUR.\n"
        "FUENTES: [1] Aceite de oliva 1 l - el mas barato por litro"
    )
    res = qa(retriever, llm, "¿cuanto cuesta el aceite de 1 l?")
    assert "12.50" in res.respuesta
    assert res.fuentes == ["1"]


def test_qa_sin_llm(retriever):
    res = qa(retriever, None, "aceite")
    assert res.respuesta is None
    assert res.hits


def test_equivalencia_elige_el_candidato_del_llm(retriever):
    llm = FakeLLM('{"pid": "2", "confianza": 0.82, "motivo": "mismo producto, misma marca propia"}')
    origen = retriever.get("1")
    res = equivalencia(retriever, llm, origen, chain_destino="carrefour")
    assert res.pid_elegido == "2"
    assert res.confianza == 0.82
    assert "mismo producto" in res.motivo


def test_equivalencia_sin_llm_devuelve_el_primero(retriever):
    origen = retriever.get("1")
    res = equivalencia(retriever, None, origen, chain_destino="carrefour")
    assert res.pid_elegido == res.top1_recuperado
    assert res.proveedor is None


def test_equivalencia_filtra_por_cadena_destino(retriever):
    origen = retriever.get("1")
    res = equivalencia(retriever, None, origen, chain_destino="carrefour", k=5)
    for h in res.candidatos:
        assert h.doc["chain"] == "carrefour"


def test_equivalencia_sin_candidato_devuelve_none(retriever):
    origen = retriever.get("1")
    res = equivalencia(retriever, None, origen, chain_destino="cadena-inexistente")
    assert res.candidatos == []
    assert res.pid_elegido is None
