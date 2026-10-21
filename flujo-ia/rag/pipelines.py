"""Los tres pipelines del prototipo: catalogo, equivalencia y QA.

Todos comparten la misma retrieval (densa + filtros) y, en el caso del LLM, el
mismo prompt base. La diferencia esta en **que se le pide** al modelo:

| Pipeline | Que recupera | Que hace el LLM |
|---|---|---|
| `catalogo` | productos que encajan con una descripcion | redacta la respuesta con los datos |
| `equivalencia` | candidatos de otra cadena | elige el equivalente (o dice que no hay) |
| `qa` | productos relevantes para una pregunta | responde usando solo el contexto |

Con `--llm none` los tres funcionan en modo solo-recuperacion: es la linea base
para medir cuanto aporta el LLM (ver `docs/03-evaluacion.md`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .ingest import Product
from .llm import BaseLLM, LLMError, extract_json
from .retriever import Filters, Retriever
from .store import Hit

# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------


def format_context(hits: list[Hit], max_items: int | None = None) -> str:
    """Contexto para el LLM: una linea por producto, con todo lo que hace falta.

    Se incluye el `pid` para que el modelo pueda citar (`[12345]`) y para que
    la evaluacion pueda comprobar que no inventa identificadores.
    """
    if max_items is not None:
        hits = hits[:max_items]
    lineas = []
    for h in hits:
        d = h.doc
        total = d.get("total") or "-"
        unit_price = d.get("unit_price")
        unit = d.get("unit") or ""
        up = f"{unit_price} EUR/{unit}" if unit_price else "-"
        size = f"{d.get('size', '-')} {d.get('size_format', '')}".strip()
        lineas.append(
            f"[{d.get('id')}] {d.get('name')} | cadena: {d.get('chain')} | "
            f"precio total: {total} EUR | precio unitario: {up} | "
            f"tamano: {size} | categoria: {d.get('category')} | url: {d.get('url')}"
        )
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------

SISTEMA_CATALOGO = (
    "Eres un buscador de supermercado. Respondes en español, en frases cortas, "
    "usando SOLO los productos del contexto. Cita cada producto con su "
    "identificador entre corchetes, por ejemplo [12345]. Si el contexto no "
    "contiene lo que se pide, dilo claramente y no inventes precios."
)

PEDIDO_CATALOGO = (
    "Dime que producto es el que mas encaja con la siguiente peticion y por que.\n\n"
    "Peticion: {query}\n\n"
    "Contexto:\n{context}\n\n"
    "Responde en este formato:\n"
    "MEJOR: [id] nombre - precio total X EUR (unitario Y EUR/unidad) - motivo en una frase\n"
    "ALTERNATIVAS: [id] nombre - precio total X EUR; [id] nombre - precio total X EUR"
)


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
    hits = retriever.search(query, k=k, filters=filters)
    res = CatalogoResult(query=query, hits=hits)
    if llm is None or not hits:
        return res
    try:
        r = llm.chat(
            SISTEMA_CATALOGO,
            PEDIDO_CATALOGO.format(query=query, context=format_context(hits)),
        )
        res.respuesta = r.text.strip()
        res.proveedor = r.provider
        res.latencia_s = r.latency_s
    except LLMError as e:
        res.error = str(e)
    return res


# ---------------------------------------------------------------------------
# Equivalencia
# ---------------------------------------------------------------------------

SISTEMA_EQUIVALENCIA = (
    "Eres un comparador de supermercado. Tu trabajo es decidir si un producto "
    "candidato es el MISMO producto que el original (otra marca, otro "
    "envase, presentacion parecida) o si es un producto distinto. La marca puede "
    "cambiar, pero el tipo de producto, el formato y el tamano deben "
    "corresponder. Respondes en español y solo con JSON."
)

PEDIDO_EQUIVALENCIA = """\
Producto original:
  id: {src_id}
  nombre: {src_name}
  categoria: {src_category}
  tamano: {src_size}
  precio: {src_total} EUR

Candidatos (otra cadena):
{candidates}

¿Cual de los candidatos es el mismo producto que el original?
Responde SOLO con este JSON (sin texto alrededor):
{{"pid": "<id del equivalente o null>", "confianza": <0.0-1.0>, "motivo": "<una frase>"}}

Criterios:
- "Aceite de oliva virgen extra 1 l" y "Aceite de oliva 1 l" NO son el mismo producto.
- Un formato distinto (pack de 2 ud frente a 1 ud) NO es el mismo producto.
- Si ninguno encaja, responde con "pid": null.
"""


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
    if isinstance(producto, Product):
        src = producto.to_dict()
    else:
        src = dict(producto)

    origen_chain = src.get("chain")
    filtros = Filters(chain=chain_destino) if chain_destino else Filters()
    if not chain_destino and origen_chain:
        filtros = Filters(chains=[c for c in _cadenas(retriever) if c != origen_chain])

    # La consulta es el producto origen, no su nombre pelado: el texto de
    # embedding incluye categoria y tamano, que es justo lo que hay que
    # comparar.
    if vector is None:
        q = Product.from_dict(src).embed_text
        vector = retriever.embedder.encode_one(q, is_query=True)
    hits = retriever.store.search(vector, k=k, where=filtros.matches)

    res = EquivalenciaResult(origen=src, candidatos=hits)
    if llm is None or not hits:
        if hits:
            res.pid_elegido = hits[0].doc.get("id")
        return res

    candidatos = "\n".join(
        f"  id={h.doc.get('id')} | {h.doc.get('name')} | cadena: {h.doc.get('chain')} | "
        f"tamano: {h.doc.get('size')} {h.doc.get('size_format')} | "
        f"precio: {h.doc.get('total')} EUR"
        for h in hits
    )
    tam = f"{src.get('size')} {src.get('size_format')}".strip()
    try:
        r = llm.chat(
            SISTEMA_EQUIVALENCIA,
            PEDIDO_EQUIVALENCIA.format(
                src_id=src.get("id"),
                src_name=src.get("name"),
                src_category=src.get("category"),
                src_size=tam or "-",
                src_total=src.get("total") or "-",
                candidates=candidatos,
            ),
        )
        res.proveedor = r.provider
        res.latencia_s = r.latency_s
        data = extract_json(r.text)
        if isinstance(data, dict):
            pid = data.get("pid")
            res.pid_elegido = None if pid in (None, "", "null") else str(pid)
            conf = data.get("confianza")
            res.confianza = float(conf) if isinstance(conf, (int, float)) else None
            res.motivo = str(data.get("motivo") or "")
        else:
            res.error = "El LLM no devolvio JSON utilizable"
    except LLMError as e:
        res.error = str(e)
    return res


def _cadenas(retriever: Retriever) -> list[str]:
    return sorted({str(d.get("chain")) for d in retriever.store.docs if d.get("chain")})


# ---------------------------------------------------------------------------
# QA
# ---------------------------------------------------------------------------

SISTEMA_QA = (
    "Eres un asistente de un comparador de precios de supermercado. Respondes "
    "en español usando SOLO los datos del contexto. Cita los productos que "
    "usas con su identificador entre corchetes, por ejemplo [12345]. Si la "
    "respuesta no esta en el contexto, dilo: no inventes precios ni productos."
)

PEDIDO_QA = """\
Pregunta: {question}

Contexto (productos disponibles):
{context}

Responde a la pregunta con los datos del contexto.
Formato de la respuesta:
RESPUESTA: <respuesta directa, 1-3 frases>
FUENTES: [id] nombre - <motivo>; [id] nombre - <motivo>
"""


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
    if vector is None:
        vector = retriever.embedder.encode_one(question, is_query=True)
    hits = retriever.store.search(
        vector, k=k, where=filters.matches if filters else None
    )
    res = QAResult(question=question, hits=hits)
    if llm is None or not hits:
        return res
    try:
        r = llm.chat(
            SISTEMA_QA,
            PEDIDO_QA.format(question=question, context=format_context(hits)),
        )
        res.proveedor = r.provider
        res.latencia_s = r.latency_s
        texto = r.text.strip()
        # El prompt pide "RESPUESTA:" / "FUENTES:"; si el modelo no lo
        # respeta, la respuesta entera es la respuesta.
        if "RESPUESTA:" in texto:
            cuerpo, _, resto = texto.partition("RESPUESTA:")
            _ = cuerpo
            respuesta, _, fuentes = resto.partition("FUENTES:")
            res.respuesta = respuesta.strip().split("\n\n")[0].strip()
            res.fuentes = _ids_de_fuentes(fuentes)
        else:
            res.respuesta = texto
            res.fuentes = _ids_de_fuentes(texto)
    except LLMError as e:
        res.error = str(e)
    return res


def _ids_de_fuentes(texto: str) -> list[str]:
    """Extrae los identificadores citados `[12345]` de un texto."""
    import re

    return [m for m in re.findall(r"\[([^\[\]]+)\]", texto or "")]


def dumps(obj) -> str:
    """Serializa un resultado para imprimirlo por CLI."""
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
