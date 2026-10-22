"""Vector store del prototipo: coseno con numpy, persistido en disco.

Por que numpy y no FAISS/pgvector: el corpus del prototipo son cientos de
productos (una ejecucion real del scraper de Mercadona son ~4.6k). A esa
escala la similitud coseno sobre una matriz normalizada es milisegundos y no
justifica una dependencia mas. El `VectorStore` mantiene la API minima
(`add` / `search` / `save` / `load`) para que cambiar a FAISS o a pgvector sea
cambiar la implementacion, no el pipeline (ver `docs/02-prototipo-rag.md`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np


def l2_normalize(mat: np.ndarray) -> np.ndarray:
    """Normaliza filas a norma 1 (robusto ante vectores nulos)."""
    mat = np.asarray(mat, dtype=np.float32)
    if mat.ndim == 1:
        mat = mat.reshape(1, -1)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


@dataclass
class Hit:
    """Un documento recuperado con su puntaje."""

    doc: dict
    score: float
    rank: int = 0

    @property
    def id(self) -> str:
        return str(self.doc.get("id", ""))


class VectorStore:
    """Indice vectorial en memoria (matriz densa normalizada) + metadatos."""

    def __init__(self, dim: int, vectors: np.ndarray | None = None, docs: list[dict] | None = None):
        self.dim = dim
        self.vectors: np.ndarray = (
            vectors if vectors is not None else np.zeros((0, dim), dtype=np.float32)
        )
        self.docs: list[dict] = docs if docs is not None else []

    # -- escritura --------------------------------------------------------
    def add(self, vectors: np.ndarray, docs: Iterable[dict]) -> None:
        vectors = l2_normalize(np.asarray(vectors, dtype=np.float32))
        docs = list(docs)
        if len(vectors) != len(docs):
            raise ValueError(f"{len(vectors)} vectores != {len(docs)} documentos")
        if self.vectors.shape[0] == 0:
            self.vectors = vectors
        else:
            self.vectors = np.vstack([self.vectors, vectors])
        self.docs.extend(docs)

    # -- lectura ----------------------------------------------------------
    def search(
        self,
        query: np.ndarray,
        k: int = 5,
        where: Callable[[dict], bool] | None = None,
        exclude_ids: set[str] | None = None,
    ) -> list[Hit]:
        """Top-k por similitud coseno, con filtro de metadatos opcional.

        `where` filtra por metadatos (cadena, categoria, precio...) y se aplica
        *antes* de calcular el top-k, no despues: filtrar despues cambiaria el
        resultado de la consulta.
        """
        if self.vectors.shape[0] == 0:
            return []
        q = l2_normalize(np.asarray(query, dtype=np.float32).reshape(1, -1))[0]
        if q.shape[0] != self.vectors.shape[1]:
            raise ValueError(
                f"dimension de consulta {q.shape[0]} != dimension del indice {self.vectors.shape[1]}"
            )
        scores = self.vectors @ q

        idx = np.arange(self.vectors.shape[0])
        if where is not None:
            mask = np.array([bool(where(d)) for d in self.docs])
            idx = idx[mask]
        if exclude_ids:
            mask = np.array([str(d.get("id", "")) not in exclude_ids for d in self.docs])
            idx = np.intersect1d(idx, np.where(mask)[0])

        if idx.size == 0:
            return []
        k = min(k, idx.size)
        part = np.argpartition(-scores[idx], k - 1)[:k]
        order = part[np.argsort(-scores[idx][part])]
        chosen = idx[order]
        return [
            Hit(doc=self.docs[i], score=float(scores[i]), rank=r + 1)
            for r, i in enumerate(chosen)
        ]

    def get(self, product_id: str) -> dict | None:
        for d in self.docs:
            if str(d.get("id")) == str(product_id):
                return d
        return None

    def filter(self, where: Callable[[dict], bool]) -> list[dict]:
        return [d for d in self.docs if where(d)]

    # -- persistencia -----------------------------------------------------
    def save(self, directory: str | Path) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.vectors)
        with (directory / "docs.jsonl").open("w", encoding="utf-8") as fh:
            for d in self.docs:
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        (directory / "meta.json").write_text(
            json.dumps({"dim": self.dim, "n": len(self.docs)}, ensure_ascii=False),
            encoding="utf-8",
        )
        return directory

    @classmethod
    def load(cls, directory: str | Path) -> "VectorStore":
        directory = Path(directory)
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        vectors = np.load(directory / "vectors.npy")
        docs = [
            json.loads(line)
            for line in (directory / "docs.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(dim=int(meta["dim"]), vectors=vectors, docs=docs)

    def __len__(self) -> int:
        return len(self.docs)
