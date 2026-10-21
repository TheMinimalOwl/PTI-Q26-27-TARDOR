"""Recuperacion: busqueda densa sobre el indice con filtros de metadatos.

El filtro se aplica **antes** del top-k (ver `VectorStore.search`). Es
importante en este dominio: "el aceite mas barato" tiene que filtrar por
categoria y por precio *antes* de elegir los k mejores, no despues.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .embeddings import Embedder
from .ingest import Product
from .store import Hit, VectorStore


def _dec(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


@dataclass
class Filters:
    """Restricciones de la consulta."""

    chain: str | None = None
    chains: list[str] | None = None
    category: str | None = None
    min_total: Decimal | None = None
    max_total: Decimal | None = None
    min_unit_price: Decimal | None = None
    max_unit_price: Decimal | None = None

    def __post_init__(self) -> None:
        # Los importes pueden llegar como string (CLI, JSON): se normalizan a
        # Decimal para no comparar floats con Decimal en la fila.
        for campo in ("min_total", "max_total", "min_unit_price", "max_unit_price"):
            valor = getattr(self, campo)
            if valor is not None and not isinstance(valor, Decimal):
                setattr(self, campo, _dec(valor))

    def matches(self, doc: dict) -> bool:
        if self.chain and doc.get("chain") != self.chain:
            return False
        if self.chains and doc.get("chain") not in self.chains:
            return False
        if self.category:
            cat = str(doc.get("category", ""))
            if self.category.lower() not in cat.lower():
                return False
        total = _dec(doc.get("total"))
        if self.min_total is not None and (total is None or total < self.min_total):
            return False
        if self.max_total is not None and (total is None or total > self.max_total):
            return False
        up = _dec(doc.get("unit_price"))
        if self.min_unit_price is not None and (up is None or up < self.min_unit_price):
            return False
        if self.max_unit_price is not None and (up is None or up > self.max_unit_price):
            return False
        return True

    def describe(self) -> str:
        bits = []
        for label, value in (
            ("cadena", self.chain),
            ("cadenas", ",".join(self.chains) if self.chains else None),
            ("categoria", self.category),
            ("precio>= ", self.min_total),
            ("precio<= ", self.max_total),
            ("unitario>= ", self.min_unit_price),
            ("unitario<= ", self.max_unit_price),
        ):
            if value is not None:
                bits.append(f"{label}{value}")
        return ", ".join(bits) if bits else "sin filtros"


class Retriever:
    """Empaqueta embeddings + indice y ofrece busqueda con filtros."""

    def __init__(self, embedder: Embedder, store: VectorStore):
        self.embedder = embedder
        self.store = store

    def search(
        self,
        query: str,
        k: int = 5,
        filters: Filters | None = None,
        exclude_ids: set[str] | None = None,
    ) -> list[Hit]:
        qv = self.embedder.encode_one(query, is_query=True)
        return self.store.search(
            qv, k=k, where=filters.matches if filters else None, exclude_ids=exclude_ids
        )

    def search_product(
        self,
        product: Product,
        k: int = 5,
        filters: Filters | None = None,
        exclude_ids: set[str] | None = None,
    ) -> list[Hit]:
        """Busca usando el texto de un producto como consulta.

        Se usa para equivalencia: la consulta es el producto origen, no una
        frase escrita por una persona.
        """
        qv = self.embedder.encode_one(product.embed_text, is_query=True)
        return self.store.search(
            qv, k=k, where=filters.matches if filters else None, exclude_ids=exclude_ids
        )

    def search_vectors(
        self,
        vectors,
        k: int = 5,
        filters: Filters | None = None,
        exclude_ids: set[str] | None = None,
    ) -> list[list[Hit]]:
        """Busqueda por lote: **una** pasada de embedding para N consultas.

        Importante en CPU: codificar una consulta con bge-m3 (568M) cuesta
        ~1 s, asi que 510 consultas sueltas son casi 10 minutos. Codificando
        en lote, la misma evaluacion tarda segundos.
        """
        return [
            self.store.search(
                v, k=k, where=filters.matches if filters else None, exclude_ids=exclude_ids
            )
            for v in vectors
        ]

    def encode_products(self, products: list[Product]) -> list:
        """Codifica varios productos origen en una sola pasada."""
        return self.embedder.encode([p.embed_text for p in products], is_query=True)

    def get(self, product_id: str) -> dict | None:
        return self.store.get(product_id)
