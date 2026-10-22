"""Construccion del indice: lineas limpias -> vectores -> indice persistido.

El indice se guarda en `.cache/index/<modelo>/` para poder regenerarlo y
comparar modelos sin repetir el calculo. Es el unico sitio donde se toca el
formato de linea limpia: `ingest.py` la parsea, aqui se embebe.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .embeddings import Embedder
from .ingest import Product, ParseStats, parse_clean_file
from .store import VectorStore


@dataclass
class IndexReport:
    n_productos: int = 0
    n_cadenas: int = 0
    cadenas: list[str] = field(default_factory=list)
    incompletos: int = 0
    lineas_no_parseadas: int = 0
    segundos: float = 0.0
    modelo: str = ""
    dim: int = 0
    stats: dict[str, dict] = field(default_factory=dict)
    destino: str = ""

    def as_dict(self) -> dict:
        return {
            "n_productos": self.n_productos,
            "n_cadenas": self.n_cadenas,
            "cadenas": self.cadenas,
            "incompletos": self.incompletos,
            "lineas_no_parseadas": self.lineas_no_parseadas,
            "segundos": round(self.segundos, 2),
            "modelo": self.modelo,
            "dim": self.dim,
            "destino": self.destino,
            "stats": self.stats,
        }


def index_dir_for(model_key: str) -> Path:
    return config.INDEX_DIR / model_key


def build_index(
    embedder: Embedder,
    paths: list[Path],
    destino: Path | None = None,
    verbose: bool = True,
) -> tuple[VectorStore, IndexReport]:
    """Indexa los ficheros de lineas limpias indicados."""
    t0 = time.perf_counter()
    productos: list[Product] = []
    report = IndexReport(modelo=embedder.spec.hf_id, dim=embedder.spec.dim)

    for path in paths:
        prods, stats = parse_clean_file(path)
        productos.extend(prods)
        report.stats[path.name] = stats.as_dict()
        report.incompletos += stats.incompletos
        report.lineas_no_parseadas += stats.errores
        if verbose:
            print(f"  {path.name}: {stats.productos} productos "
                  f"({stats.incompletos} incompletos, {stats.errores} lineas no parseadas)")

    report.n_productos = len(productos)
    report.cadenas = sorted({p.chain for p in productos})
    report.n_cadenas = len(report.cadenas)

    if not productos:
        raise ValueError("no hay productos que indexar")

    textos = [p.embed_text for p in productos]
    docs = [p.to_dict() for p in productos]
    if verbose:
        print(f"  embebiendo {len(textos)} productos con {embedder.spec.hf_id}...")
    vectores = embedder.encode(textos, is_query=False)

    store = VectorStore(dim=int(vectores.shape[1]))
    store.add(vectores, docs)

    destino = destino or index_dir_for(embedder.spec.key)
    store.save(destino)
    report.destino = str(destino)
    report.segundos = time.perf_counter() - t0
    return store, report


def load_index(embedder: Embedder, destino: Path | None = None) -> VectorStore:
    """Carga un indice ya construido."""
    destino = destino or index_dir_for(embedder.spec.key)
    if not (destino / "meta.json").exists():
        raise FileNotFoundError(
            f"No hay indice en {destino}. Generalo con: python -m rag.cli index"
        )
    return VectorStore.load(destino)


def index_info(destino: Path) -> dict:
    meta = json.loads((destino / "meta.json").read_text(encoding="utf-8"))
    return meta
