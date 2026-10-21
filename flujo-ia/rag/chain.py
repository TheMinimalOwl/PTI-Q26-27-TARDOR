"""Cadenas RAG con LangChain (LCEL).

La tarea 3 del plan pide la cadena en LangChain: **consulta -> busqueda ->
prompt -> respuesta**. Aqui la cadena se compone con los *runnables* de
`langchain-core` (que es la parte lightweight: sin loaders, sin memory, sin
tools) sobre los modulos que ya tenia:

- la recuperacion es la nuestra (`Retriever`), que hace busqueda densa con
  filtros de metadatos;
- el LLM es el nuestro (`BaseLLM`), con una interfaz comun para Ollama y
  Gemini;
- el prompt lo compone `ChatPromptTemplate` de LangChain.

El estado de la cadena es un `dict` que viaja por los pasos:

    {"question": str, "context": str, "hits": list[Hit], "mensajes": list,
     "respuesta": str, "fuentes": list[str]}

Se puede invocar con `.invoke({"question": ...})` o con `.stream(...)`.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough

from .llm import BaseLLM, extract_json
from .retriever import Filters, Retriever
from .store import Hit

# ---------------------------------------------------------------------------
# Prompts (los mismos textos que usaba el pipeline a mano)
# ---------------------------------------------------------------------------

PROMPT_CATALOGO = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Eres un buscador de supermercado. Respondes en español, en frases cortas, "
            "usando SOLO los productos del contexto. Cita cada producto con su "
            "identificador entre corchetes, por ejemplo [12345]. Si el contexto no "
            "contiene lo que se pide, dilo claramente y no inventes precios.",
        ),
        (
            "human",
            "Dime que producto es el que mas encaja con la siguiente peticion y por que.\n\n"
            "Peticion: {query}\n\n"
            "Contexto:\n{context}\n\n"
            "Responde en este formato:\n"
            "MEJOR: [id] nombre - precio total X EUR (unitario Y EUR/unidad) - motivo en una frase\n"
            "ALTERNATIVAS: [id] nombre - precio total X EUR; [id] nombre - precio total X EUR",
        ),
    ]
)

PROMPT_EQUIVALENCIA = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Eres un comparador de supermercado. Tu trabajo es decidir si un producto "
            "candidato es el MISMO producto que el original (otra marca, otro "
            "envase, presentacion parecida) o si es un producto distinto. La marca puede "
            "cambiar, pero el tipo de producto, el formato y el tamano deben "
            "corresponder. Respondes en español y solo con JSON.",
        ),
        (
            "human",
            "Producto original:\n"
            "  id: {src_id}\n"
            "  nombre: {src_name}\n"
            "  categoria: {src_category}\n"
            "  tamano: {src_size}\n"
            "  precio: {src_total} EUR\n\n"
            "Candidatos (otra cadena):\n{candidates}\n\n"
            "¿Cual de los candidatos es el mismo producto que el original?\n"
            "Responde SOLO con este JSON (sin texto alrededor):\n"
            '{{"pid": "<id del equivalente o null>", "confianza": <0.0-1.0>, "motivo": "<una frase>"}}\n\n'
            "Criterios:\n"
            '- "Aceite de oliva virgen extra 1 l" y "Aceite de oliva 1 l" NO son el mismo producto.\n'
            "- Un formato distinto (pack de 2 ud frente a 1 ud) NO es el mismo producto.\n"
            '- Si ninguno encaja, responde con "pid": null.\n',
        ),
    ]
)

PROMPT_QA = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Eres un asistente de un comparador de precios de supermercado. Respondes "
            "en español usando SOLO los datos del contexto. Cita los productos que "
            "usas con su identificador entre corchetes, por ejemplo [12345]. Si la "
            "respuesta no esta en el contexto, dilo: no inventes precios ni productos.",
        ),
        (
            "human",
            "Pregunta: {question}\n\n"
            "Contexto (productos disponibles):\n{context}\n\n"
            "Responde a la pregunta con los datos del contexto.\n"
            "Reglas:\n"
            "- Compara solo productos equivalentes (mismo tipo y mismo formato y tamaño). Si en el\n"
            "  contexto hay formatos distintos del mismo producto (por ejemplo 1 l y 0,5 l), compara\n"
            "  solo los del formato que pide la pregunta y no los presentes como si fueran el mismo\n"
            "  producto.\n"
            "- Da siempre las cifras: precio total y precio unitario, con su unidad (EUR, EUR/l,\n"
            "  EUR/kg, EUR/ud...). No digas \"el mas barato\" sin decir cuanto cuesta.\n"
            "- Si hay empate, di que hay empate y nombra las opciones.\n\n"
            "Formato de la respuesta:\n"
            "RESPUESTA: <respuesta directa, 1-3 frases, con las cifras>\n"
            "FUENTES: [id] nombre - <motivo>; [id] nombre - <motivo>\n",
        ),
    ]
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def partir_mensajes(mensajes: list[BaseMessage]) -> tuple[str, str]:
    """Divide los mensajes de LangChain en (sistema, usuario) para el cliente LLM."""
    sistema = ""
    usuario = ""
    for m in mensajes:
        if isinstance(m, AIMessage):
            usuario = m.content
        elif getattr(m, "type", "") == "system":
            sistema = m.content
        else:
            usuario = m.content
    return sistema, usuario


def format_context(hits: list[Hit], max_items: int | None = None) -> str:
    """Contexto para el LLM: una linea por producto, con su `id` para citar."""
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


def ids_citados(texto: str) -> list[str]:
    """Identificadores citados `[12345]` en un texto."""
    import re

    return re.findall(r"\[([^\[\]]+)\]", texto or "")


def separar_respuesta(texto: str) -> tuple[str, list[str]]:
    """Separa la respuesta de las fuentes segun el formato del prompt.

    Si el modelo no respeta el formato (`RESPUESTA:` / `FUENTES:`), la
    respuesta entera es la respuesta y las fuentes se buscan en el texto.
    """
    if "RESPUESTA:" in texto:
        _cabecera, _, resto = texto.partition("RESPUESTA:")
        respuesta, _, fuentes = resto.partition("FUENTES:")
        return respuesta.strip().split("\n\n")[0].strip(), ids_citados(fuentes or texto)
    return (texto or "").strip(), ids_citados(texto)


# ---------------------------------------------------------------------------
# Cadenas
# ---------------------------------------------------------------------------


def cadena_catalogo(
    retriever: Retriever, llm: BaseLLM, k: int = 5, filters: Filters | None = None
) -> Runnable:
    """Busqueda de catalogo: una descripcion en lenguaje natural."""

    def recuperar(state: dict) -> dict:
        hits = retriever.search(state["query"], k=k, filters=filters)
        return {**state, "context": format_context(hits), "hits": hits}

    def render(state: dict) -> dict:
        mensajes = PROMPT_CATALOGO.format_messages(query=state["query"], context=state["context"])
        return {**state, "mensajes": mensajes}

    def llamar(state: dict) -> dict:
        sistema, usuario = partir_mensajes(state["mensajes"])
        r = llm.chat(sistema, usuario)
        return {**state, "respuesta": r.text, "proveedor": r.provider, "modelo": r.model}

    # Cada paso recibe el estado (dict) y devuelve el estado nuevo: asi el
    # `hits` sobrevive a la cadena y se puede citar.
    return (
        RunnableLambda(recuperar)
        | RunnableLambda(render)
        | RunnableLambda(llamar)
    )


def cadena_equivalencia(
    retriever: Retriever,
    llm: BaseLLM,
    k: int = 8,
    chain_destino: str | None = None,
) -> Runnable:
    """Equivalencia entre cadenas: el original y un `src` de producto."""

    def recuperar(state: dict) -> dict:
        origen = state["src"]
        filtros = (
            Filters(chain=chain_destino)
            if chain_destino
            else Filters(chains=[c for c in _cadenas(retriever) if c != origen.get("chain")])
        )
        vector = state.get("vector")
        if vector is None:
            vector = retriever.embedder.encode_one(state["embed_text"], is_query=True)
        hits = retriever.store.search(vector, k=k, where=filtros.matches)
        return {**state, "context": format_context(hits), "hits": hits}

    def render(state: dict) -> dict:
        candidatos = "\n".join(
            f"  id={h.doc.get('id')} | {h.doc.get('name')} | cadena: {h.doc.get('chain')} | "
            f"tamano: {h.doc.get('size')} {h.doc.get('size_format')} | "
            f"precio: {h.doc.get('total')} EUR"
            for h in state["hits"]
        )
        src = state["src"]
        mensajes = PROMPT_EQUIVALENCIA.format_messages(
            src_id=src.get("id"),
            src_name=src.get("name"),
            src_category=src.get("category"),
            src_size=f"{src.get('size')} {src.get('size_format')}".strip() or "-",
            src_total=src.get("total") or "-",
            candidates=candidatos,
        )
        return {**state, "mensajes": mensajes}

    def llamar(state: dict) -> dict:
        sistema, usuario = partir_mensajes(state["mensajes"])
        r = llm.chat(sistema, usuario)
        return {**state, "respuesta": r.text, "proveedor": r.provider, "modelo": r.model}

    def parsear(state: dict) -> dict:
        data = extract_json(state["respuesta"])
        pid = None
        confianza = None
        motivo = ""
        if isinstance(data, dict):
            bruto = data.get("pid")
            pid = None if bruto in (None, "", "null") else str(bruto)
            conf = data.get("confianza")
            confianza = float(conf) if isinstance(conf, (int, float)) else None
            motivo = str(data.get("motivo") or "")
        return {
            **state,
            "pid_elegido": pid,
            "confianza": confianza,
            "motivo": motivo,
        }

    return (
        RunnableLambda(recuperar)
        | RunnableLambda(render)
        | RunnableLambda(llamar)
        | RunnableLambda(parsear)
    )


def cadena_qa(
    retriever: Retriever, llm: BaseLLM, k: int = 6, filters: Filters | None = None
) -> Runnable:
    """Pregunta en lenguaje natural sobre los datos del supermercado."""

    def recuperar(state: dict) -> dict:
        vector = state.get("vector")
        if vector is None:
            hits = retriever.search(state["question"], k=k, filters=filters)
        else:
            hits = retriever.store.search(
                vector, k=k, where=filters.matches if filters else None
            )
        return {**state, "context": format_context(hits), "hits": hits}

    def render(state: dict) -> dict:
        mensajes = PROMPT_QA.format_messages(
            question=state["question"], context=state["context"]
        )
        return {**state, "mensajes": mensajes}

    def llamar(state: dict) -> dict:
        sistema, usuario = partir_mensajes(state["mensajes"])
        r = llm.chat(sistema, usuario)
        return {**state, "respuesta": r.text, "proveedor": r.provider, "modelo": r.model}

    def parsear(state: dict) -> dict:
        respuesta, fuentes = separar_respuesta(state["respuesta"])
        return {**state, "respuesta": respuesta, "fuentes": fuentes}

    return (
        RunnableLambda(recuperar)
        | RunnableLambda(render)
        | RunnableLambda(llamar)
        | RunnableLambda(parsear)
    )


def _cadenas(retriever: Retriever) -> list[str]:
    return sorted({str(d.get("chain")) for d in retriever.store.docs if d.get("chain")})


def flujo_qa(
    retriever: Retriever,
    llm: BaseLLM,
    question: str,
    k: int = 6,
    filters: Filters | None = None,
):
    """Genera la respuesta por eventos, para el streaming por SSE.

    Eventos emitidos:
      ("fuentes", [id, ...])  los productos del contexto, antes de responder
      ("token", "texto")      un trozo de la respuesta
      ("fin", {...})          la respuesta completa y el estado
    """
    hits = retriever.search(question, k=k, filters=filters)
    contexto = format_context(hits)
    mensajes = PROMPT_QA.format_messages(question=question, context=contexto)
    sistema, usuario = partir_mensajes(mensajes)

    yield ("fuentes", [str(h.doc.get("id")) for h in hits])
    partes: list[str] = []
    for trozo in llm.chat_stream(sistema, usuario):
        if not trozo:
            continue
        partes.append(trozo)
        yield ("token", trozo)
    yield ("fin", {"question": question, "respuesta": "".join(partes), "hits": hits})


def invocar(cadena: Runnable, entrada: dict) -> dict:
    """Invoca una cadena y devuelve su dict de estado."""
    return dict(cadena.invoke(entrada))


def a_json(estado: dict) -> str:
    """Serializa el estado de una cadena (util para depurar)."""
    return json.dumps(
        {k: v for k, v in estado.items() if k not in ("hits", "mensajes")},
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _unused(*_args: Any) -> None:  # pragma: no cover
    """Marcador para mantener el modulo sin imports opresivos."""
