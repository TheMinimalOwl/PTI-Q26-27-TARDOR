"""Prototipo de RAG para el comparador de precios TARDOR.

Parte de IA del proyecto: elige modelo de embeddings y de LLM, y monta el
prototipo de RAG (catalogo + equivalencia entre cadenas + QA) sobre las lineas
limpias que produce el normalizador del equipo de ingesta.

Ver `docs/01-decision-modelos.md` para el por que de cada eleccion.
"""

__all__ = [
    "config",
    "embeddings",
    "evaluate",
    "indexer",
    "ingest",
    "llm",
    "pipelines",
    "retriever",
    "store",
]
