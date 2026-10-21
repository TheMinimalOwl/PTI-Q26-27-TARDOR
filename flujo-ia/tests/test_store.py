"""Tests del vector store y de la recuperacion con filtros."""

from __future__ import annotations

import numpy as np
import pytest

from rag.retriever import Filters
from rag.store import VectorStore


def _store() -> VectorStore:
    docs = [
        {"id": "1", "name": "Aceite 1 l", "chain": "mercadona", "category": "Aceites", "total": "10.00", "unit_price": "10.00", "unit": "l"},
        {"id": "2", "name": "Aceite 0.5 l", "chain": "carrefour", "category": "Aceites", "total": "6.00", "unit_price": "12.00", "unit": "l"},
        {"id": "3", "name": "Leche 1 l", "chain": "mercadona", "category": "Leche", "total": "1.10", "unit_price": "1.10", "unit": "l"},
        {"id": "4", "name": "Leche 1 l pack", "chain": "carrefour", "category": "Leche", "total": "2.20", "unit_price": "2.20", "unit": "l"},
    ]
    vectores = np.array(
        [
            [1.0, 0.0],
            [0.9, 0.1],
            [0.0, 1.0],
            [0.1, 0.9],
        ],
        dtype=np.float32,
    )
    store = VectorStore(dim=2)
    store.add(vectores, docs)
    return store


def test_search_devuelve_el_mas_similar():
    store = _store()
    hits = store.search(np.array([1.0, 0.0], dtype=np.float32), k=2)
    assert hits[0].id == "1"
    assert hits[0].score >= hits[1].score
    assert hits[0].rank == 1


def test_filtro_se_aplica_antes_del_top_k():
    """Filtrar despues cambiaria el resultado: aqui se comprueba."""
    store = _store()
    filtros = Filters(chain="carrefour")
    hits = store.search(np.array([1.0, 0.0], dtype=np.float32), k=2, where=filtros.matches)
    assert [h.id for h in hits] == ["2", "4"]


def test_filtro_por_categoria_y_precio():
    store = _store()
    filtros = Filters(category="Leche", max_total="1.50")
    hits = store.search(np.array([0.0, 1.0], dtype=np.float32), k=4, where=filtros.matches)
    assert [h.id for h in hits] == ["3"]


def test_exclude_ids():
    store = _store()
    hits = store.search(np.array([1.0, 0.0], dtype=np.float32), k=4, exclude_ids={"1"})
    assert "1" not in [h.id for h in hits]


def test_guards_de_dimension():
    store = _store()
    with pytest.raises(ValueError):
        store.search(np.array([1.0, 0.0, 0.0], dtype=np.float32), k=1)


def test_save_y_load(tmp_path):
    store = _store()
    destino = tmp_path / "idx"
    store.save(destino)
    cargado = VectorStore.load(destino)
    assert len(cargado) == len(store)
    assert cargado.docs == store.docs
    assert np.allclose(cargado.vectors, store.vectors)


def test_tienda_vacia_no_revienta():
    store = VectorStore(dim=4)
    assert store.search(np.array([1.0, 0, 0, 0], dtype=np.float32), k=3) == []
