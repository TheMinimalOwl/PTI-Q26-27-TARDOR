"""Los tres pipelines del prototipo: catalogo, equivalencia y QA.

La orquestacion vive en `chain.py`, que compone las cadenas con **LangChain
(LCEL)**; aqui solo se adaptan al formato de resultado que usan el resto del
prototipo (la CLI, la evaluacion y el servicio HTTP).

| Pipeline | Que recupera | Que hace el LLM |
|---|---|---|
| `catalogo` | productos que encajan con una descripcion | redacta la respuesta con los ids citados |
| `equivalencia` | candidatos de otra cadena | elige el equivalente (o dice que no hay) |
| `qa` | productos relevantes para una pregunta | responde **solo** con el contexto y cita `[id]` |

Con `--llm none` los tres funcionan en modo solo-recuperacion: es la linea base
para medir la calidad del retrieval (que es lo que decide el modelo de
embeddings) sin depender de ninguna API.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .chain import (
    cadena_catalogo,
    cadena_equivalencia,
    cadena_qa,
    format_context,
    ids_citados,
    separar_respuesta,
)
from .ingest import Product
from .llm import BaseLLM, LLMError
from .retriever import Filters, Retriever
from .store import Hit

__all__ = [
    "CatalogoResult",
    "EquivalenciaResult",
    "QAResult",
    "catalogo",
    "equivalencia",
    "format_context",
    "qa",
]


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------


@dataclass
class CatalogoResult:
    query: str
    hits: list[Hit] = field(default_factory=list)
    respuesta: str | None = None
    proveedor: str | None = None
    latencia_s: float = 0.0
    error: str | None = None


def catalogo(
    retriever: Retriever,
    llm: BaseLLM | None,
    query: str,
    k: int = 5,
    filters: Filters | None = None,
) -> CatalogoResult:
    """Busqueda de catalogo: 'aceite de oliva virgen extra de 1 l'."""
    if llm is None:
        hits = retriever.search(query, k=k, filters=filters)
        return CatalogoResult(query=query, hits=hits)

    cadena = cadena_catalogo(retriever, llm, k=k, filters=filters)
    try:
        estado = dict(cadena.invoke({"query": query}))
    except LLMError as e:
        # Si el LLM falla, se conserva la recuperacion.
        hits = retriever.search(query, k=k, filters=filters)
        return CatalogoResult(query=query, hits=hits, error=str(e))
    return CatalogoResult(
        query=query,
        hits=list(estado.get("hits", [])),
        respuesta=str(estado.get("respuesta", "")).strip() or None,
        proveedor=estado.get("proveedor"),
    )


# ---------------------------------------------------------------------------
# Equivalencia
# ---------------------------------------------------------------------------


@dataclass
class EquivalenciaResult:
    origen: dict
    candidatos: list[Hit] = field(default_factory=list)
    pid_elegido: str | None = None
    confianza: float | None = None
    motivo: str | None = None
    proveedor: str | None = None
    latencia_s: float = 0.0
    error: str | None = None

    @property
    def top1_recuperado(self) -> str | None:
        return self.candidatos[0].doc.get("id") if self.candidatos else None


def equivalencia(
    retriever: Retriever,
    llm: BaseLLM | None,
    producto: Product | dict,
    chain_destino: str | None = None,
    k: int = 8,
    vector=None,
) -> EquivalenciaResult:
    """Equivalencia entre cadenas: 'este de Mercadona, cual es en Carrefour?'.

    Sin LLM devuelve el primer candidato recuperado (baseline de solo retrieval).
    `vector` permite pasar el embedding ya calculado (evaluacion por lotes).
    """
    src = producto.to_dict() if isinstance(producto, Product) else dict(producto)

    if llm is None:
        origen = Product.from_dict(src)
        filtros = (
            Filters(chain=chain_destino)
            if chain_destino
            else Filters(chains=[c for c in _cadenas(retriever) if c != src.get("chain")])
        )
        if vector is None:
            vector = retriever.embedder.encode_one(origen.embed_text, is_query=True)
        hits = retriever.store.search(vector, k=k, where=filtros.matches)
        res = EquivalenciaResult(origen=src, candidatos=hits)
        if hits:
            res.pid_elegido = hits[0].doc.get("id")
        return res

    cadena = cadena_equivalencia(retriever, llm, k=k, chain_destino=chain_destino)
    entrada = {
        "src": src,
        "embed_text": Product.from_dict(src).embed_text,
        "vector": vector,
    }
    try:
        estado = dict(cadena.invoke(entrada))
    except LLMError as e:
        return EquivalenciaResult(origen=src, error=str(e))
    return EquivalenciaResult(
        origen=src,
        candidatos=list(estado.get("hits", [])),
        pid_elegido=estado.get("pid_elegido"),
        confianza=estado.get("confianza"),
        motivo=estado.get("motivo") or None,
        proveedor=estado.get("proveedor"),
    )


def _cadenas(retriever: Retriever) -> list[str]:
    return sorted({str(d.get("chain")) for d in retriever.store.docs if d.get("chain")})


# ---------------------------------------------------------------------------
# QA
# ---------------------------------------------------------------------------


@dataclass
class QAResult:
    question: str
    hits: list[Hit] = field(default_factory=list)
    respuesta: str | None = None
    fuentes: list[str] = field(default_factory=list)
    proveedor: str | None = None
    latencia_s: float = 0.0
    error: str | None = None


def qa(
    retriever: Retriever,
    llm: BaseLLM | None,
    question: str,
    k: int = 6,
    filters: Filters | None = None,
    vector=None,
) -> QAResult:
    """Pregunta en lenguaje natural sobre los datos del supermercado.

    `vector` permite pasar el embedding ya calculado (evaluacion por lotes).
    """
    if llm is None:
        if vector is None:
            hits = retriever.search(question, k=k, filters=filters)
        else:
            hits = retriever.store.search(
                vector, k=k, where=filters.matches if filters else None
            )
        return QAResult(question=question, hits=hits)

    cadena = cadena_qa(retriever, llm, k=k, filters=filters)
    try:
        estado = dict(cadena.invoke({"question": question, "vector": vector}))
    except LLMError as e:
        if vector is None:
            hits = retriever.search(question, k=k, filters=filters)
        else:
            hits = retriever.store.search(
                vector, k=k, where=filters.matches if filters else None
            )
        return QAResult(question=question, hits=hits, error=str(e))
    return QAResult(
        question=question,
        hits=list(estado.get("hits", [])),
        respuesta=estado.get("respuesta"),
        fuentes=list(estado.get("fuentes", [])),
        proveedor=estado.get("proveedor"),
    )
