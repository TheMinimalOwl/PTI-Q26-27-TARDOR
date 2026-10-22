"""Tests de los embeddings: prefijos, normalizacion y dimensionalidad.

El modelo por defecto (`multilingual-e5-small`) **exige** prefijos
asimetricos: sin `query: ` / `passage: ` el recall se hunde. Estos tests
comprueban que se aplican, sin descargar el modelo (se sustituye el encoder).
"""

from __future__ import annotations

import numpy as np
import pytest

from rag.config import EMBEDDINGS
from rag.embeddings import Embedder


class FakeModel:
    """Encoder falso que apunta que textos ha recibido."""

    def __init__(self):
        self.recibidos: list[str] = []
        self.max_seq_length = 512

    def encode(self, payloads, batch_size=32, convert_to_numpy=True,
               normalize_embeddings=True, show_progress_bar=False):
        self.recibidos.extend(payloads)
        vectores = np.array(
            [[float(len(p)), 1.0, 0.0] for p in payloads], dtype=np.float32
        )
        if normalize_embeddings:
            vectores = vectores / np.linalg.norm(vectores, axis=1, keepdims=True)
        return vectores


def _embedder(key: str) -> Embedder:
    emb = Embedder(key)
    emb._model = FakeModel()
    return emb


def test_e5_aplica_prefijo_de_consulta():
    emb = _embedder("e5-small")
    emb.encode_one("aceite de oliva", is_query=True)
    assert emb.model.recibidos == ["query: aceite de oliva"]


def test_e5_aplica_prefijo_de_documento():
    emb = _embedder("e5-small")
    emb.encode(["aceite de oliva"], is_query=False)
    assert emb.model.recibidos == ["passage: aceite de oliva"]


def test_bge_m3_no_usa_prefijos():
    emb = _embedder("bge-m3")
    emb.encode_one("aceite de oliva", is_query=True)
    emb.encode(["aceite de oliva"], is_query=False)
    assert emb.model.recibidos == ["aceite de oliva", "aceite de oliva"]


def test_nomic_usa_sus_prefijos():
    emb = _embedder("nomic-embed")
    emb.encode_one("q", is_query=True)
    emb.encode(["p"], is_query=False)
    assert emb.model.recibidos == ["search_query: q", "search_document: p"]


def test_texto_vacio_no_llama_al_modelo():
    emb = _embedder("e5-small")
    vectores = emb.encode([])
    assert vectores.shape == (0, EMBEDDINGS["e5-small"].dim)
    assert emb.model.recibidos == []


def test_default_es_e5_small(monkeypatch):
    """El modelo por defecto (si no se sobrescribe por entorno) es e5-small."""
    from rag import config

    monkeypatch.delenv("RAG_EMBED_MODEL", raising=False)
    assert config.embedding_spec().key == "e5-small"
    assert EMBEDDINGS["e5-small"].dim == 384
    assert EMBEDDINGS["bge-m3"].dim == 1024


def test_spec_de_hf_arbitrario():
    from rag.config import embedding_spec

    spec = embedding_spec("alguna/modelo-de-hf")
    assert spec.hf_id == "alguna/modelo-de-hf"
    assert spec.query_prefix == ""
