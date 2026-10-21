"""Tests de las cadenas RAG montadas con LangChain (LCEL)."""

from __future__ import annotations

import numpy as np
import pytest
from langchain_core.runnables import Runnable

from rag.chain import (
    PROMPT_QA,
    cadena_catalogo,
    cadena_equivalencia,
    cadena_qa,
    flujo_qa,
    format_context,
    partir_mensajes,
    separar_respuesta,
)
from rag.llm import BaseLLM, LLMResponse
from rag.retriever import Retriever
from rag.store import VectorStore


class FakeLLM(BaseLLM):
    provider = "fake"
    model = "fake-1b"

    def __init__(self, respuesta: str = "RESPUESTA: hola\nFUENTES: [1] Aceite - motivo"):
        self.respuesta = respuesta
        self.llamadas: list[tuple[str, str]] = []

    def chat(self, system: str, user: str) -> LLMResponse:
        self.llamadas.append((system, user))
        return LLMResponse(text=self.respuesta, provider=self.provider, model=self.model)


@pytest.fixture
def retriever() -> Retriever:
    docs = [
        {"id": "1", "name": "Aceite de oliva 1 l", "chain": "mercadona", "category": "Aceites", "total": "12.50", "unit_price": "12.50", "unit": "l", "size": "1", "size_format": "l", "url": "u1"},
        {"id": "2", "name": "Aceite de oliva 0.5 l", "chain": "carrefour", "category": "Aceites", "total": "6.80", "unit_price": "13.60", "unit": "l", "size": "0.5", "size_format": "l", "url": "u2"},
        {"id": "3", "name": "Leche entera 1 l", "chain": "mercadona", "category": "Leche", "total": "1.15", "unit_price": "1.15", "unit": "l", "size": "1", "size_format": "l", "url": "u3"},
    ]
    vectores = np.array([[1.0, 0.0, 1.0], [0.95, 0.0, 0.0], [0.0, 1.0, 1.0]], dtype=np.float32)
    store = VectorStore(dim=3)
    store.add(vectores, docs)
    return Retriever(_FakeEmbedder(), store)


class _FakeEmbedder:
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


def test_las_cadenas_son_runnables_de_langchain(retriever):
    llm = FakeLLM()
    for cadena in (
        cadena_qa(retriever, llm),
        cadena_catalogo(retriever, llm),
        cadena_equivalencia(retriever, llm),
    ):
        assert isinstance(cadena, Runnable)


def test_cadena_qa_devuelve_respuesta_y_fuentes(retriever):
    llm = FakeLLM()
    estado = cadena_qa(retriever, llm).invoke({"question": "¿cuanto cuesta el aceite?"})
    assert estado["respuesta"] == "hola"
    assert estado["fuentes"] == ["1"]
    assert estado["proveedor"] == "fake"
    # Los hits sobreviven a la cadena (de ahi salen las fuentes).
    ids = [h.doc["id"] for h in estado["hits"]]
    assert set(ids) == {"1", "2", "3"}
    assert ids[0] in {"1", "2"}  # los dos aceites van delante de la leche


def test_cadena_qa_pasa_el_contexto_al_prompt(retriever):
    llm = FakeLLM()
    cadena_qa(retriever, llm).invoke({"question": "¿cuanto cuesta el aceite?"})
    sistema, usuario = llm.llamadas[0]
    assert "precio unitario" in usuario
    assert "[1]" in usuario  # el contexto lleva los ids para poder citar
    assert "ACEITES" in usuario.upper()


def test_cadena_equivalencia_elige_el_candidato(retriever):
    llm = FakeLLM('{"pid": "2", "confianza": 0.9, "motivo": "mismo producto"}')
    origen = retriever.get("1")
    estado = cadena_equivalencia(retriever, llm, chain_destino="carrefour").invoke(
        {"src": origen, "embed_text": "Aceite de oliva 1 l", "vector": None}
    )
    assert estado["pid_elegido"] == "2"
    assert estado["confianza"] == 0.9
    assert estado["motivo"] == "mismo producto"


def test_separar_respuesta_con_el_formato_del_prompt():
    texto = "RESPUESTA: 12,50 EUR/l.\nFUENTES: [1] Aceite - el mas barato; [2] Aceite - otro"
    respuesta, fuentes = separar_respuesta(texto)
    assert respuesta == "12,50 EUR/l."
    assert fuentes == ["1", "2"]


def test_separar_respuesta_sin_formato():
    respuesta, fuentes = separar_respuesta("El mas barato es [1] Aceite")
    assert respuesta == "El mas barato es [1] Aceite"
    assert fuentes == ["1"]


def test_partir_mensajes():
    mensajes = PROMPT_QA.format_messages(question="q", context="c")
    sistema, usuario = partir_mensajes(mensajes)
    assert "comparador de precios" in sistema
    assert "Pregunta: q" in usuario


def test_flujo_qa_emite_eventos(retriever):
    llm = FakeLLM("RESPUESTA: hola\nFUENTES: [1] Aceite")
    eventos = list(flujo_qa(retriever, llm, "¿cuanto cuesta el aceite?"))
    tipos = [t for t, _ in eventos]
    assert tipos[0] == "fuentes"
    assert tipos[-1] == "fin"
    assert "token" in tipos
    ids = eventos[0][1]
    assert "1" in ids
    fin = eventos[-1][1]
    assert "hola" in fin["respuesta"]


def test_contexto_incluye_los_campos_que_hacen_falta():
    class HitFalso:
        def __init__(self, doc):
            self.doc = doc
            self.score = 1.0

    doc = {"id": "9", "name": "Leche", "chain": "mercadona", "category": "Leche", "total": "1.15", "unit_price": "1.15", "unit": "l", "size": "1", "size_format": "l", "url": "u9"}
    ctx = format_context([HitFalso(doc)])
    assert "[9]" in ctx
    assert "1.15 EUR/l" in ctx
    assert "mercadona" in ctx
