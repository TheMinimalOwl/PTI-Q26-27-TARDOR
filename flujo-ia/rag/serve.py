"""Servicio HTTP del prototipo de RAG.

El equipo de API/BD y el de la app necesitan consumeR el RAG desde fuera. Este
modulo expone una API minima sobre Flask (la misma libreria que usa la funcion
de Fission del normalizador, para no anadir dependencias al equipo de ingesta).

Endpoints:

    GET  /health              estado del servicio (indice, modelo, LLM)
    POST /search              busqueda de catalogo
    POST /equiv               equivalencia entre cadenas
    POST /ask                 pregunta en lenguaje natural
    GET  /docs                documentacion interactiva (Swagger)

Se arranca con:

    python -m rag.serve --host 0.0.0.0 --port 8080

En un despliegue real, el indice se monta como volumen de solo lectura
(`.cache/index/<modelo>/`) y el servicio lo carga al arrancar: el indice no
cambia entre peticiones, asi que **no** se recalcula en caliente.
"""

from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal, InvalidOperation

from flask import Flask, Response, jsonify, request

from . import config
from .chain import flujo_qa
from .embeddings import Embedder
from .guardrails import aplicar_guardrails, construir_respuesta, validar
from .indexer import load_index
from .ingest import Product
from .llm import NoLLM, build_llm
from .pipelines import catalogo, equivalencia, qa
from .retriever import Filters, Retriever

app = Flask(__name__)

# Estado global del servicio: se carga una vez al arrancar.
_ESTADO: dict = {"retriever": None, "llm": None, "error": None}


def _dec(v):
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def inicializar(embed_model: str | None = None, llm_provider: str | None = None) -> None:
    """Carga el indice y el LLM. Se llama al arrancar el servicio."""
    embedder = Embedder(embed_model or config.DEFAULT_EMBEDDING)
    store = load_index(embedder)
    _ESTADO["retriever"] = Retriever(embedder, store)
    _ESTADO["embeddings"] = embedder.describe()
    try:
        _ESTADO["llm"] = build_llm(llm_provider or config.DEFAULT_LLM)
    except Exception as e:  # noqa: BLE001 - sin LLM el servicio sigue sirviendo retrieval
        _ESTADO["llm"] = None
        _ESTADO["llm_error"] = str(e)


def _retriever() -> Retriever:
    if _ESTADO["retriever"] is None:
        inicializar()
    return _ESTADO["retriever"]


def _llm():
    return _ESTADO.get("llm")


def _filtros(payload: dict) -> Filters:
    return Filters(
        chain=payload.get("chain"),
        chains=payload.get("chains"),
        category=payload.get("category"),
        min_total=_dec(payload.get("min_total")),
        max_total=_dec(payload.get("max_total")),
        min_unit_price=_dec(payload.get("min_unit_price")),
        max_unit_price=_dec(payload.get("max_unit_price")),
    )


def _hits_json(hits) -> list[dict]:
    return [
        {
            "rank": h.rank,
            "score": round(h.score, 4),
            "id": h.doc.get("id"),
            "name": h.doc.get("name"),
            "chain": h.doc.get("chain"),
            "category": h.doc.get("category"),
            "total": h.doc.get("total"),
            "unit_price": h.doc.get("unit_price"),
            "unit": h.doc.get("unit"),
            "size": h.doc.get("size"),
            "size_format": h.doc.get("size_format"),
            "url": h.doc.get("url"),
        }
        for h in hits
    ]


@app.get("/health")
def health():
    retriever = _ESTADO.get("retriever")
    llm = _ESTADO.get("llm")
    return jsonify(
        {
            "ok": retriever is not None,
            "error": _ESTADO.get("error"),
            "n_productos": len(retriever.store) if retriever else 0,
            "embeddings": _ESTADO.get("embeddings"),
            "llm": llm.describe() if llm else None,
            "llm_error": _ESTADO.get("llm_error"),
        }
    )


@app.post("/search")
def search():
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify({"error": "falta 'query'"}), 400
    k = int(payload.get("k") or config.TOP_K)
    filtros = _filtros(payload)
    res = catalogo(_retriever(), _llm(), query, k=k, filters=filtros)
    return jsonify(
        {
            "query": query,
            "filtros": filtros.describe(),
            "resultados": _hits_json(res.hits),
            "respuesta": res.respuesta,
            "proveedor": res.proveedor,
            "error": res.error,
        }
    )


@app.post("/equiv")
def equiv():
    payload = request.get_json(silent=True) or {}
    k = int(payload.get("k") or config.TOP_K_EQUIV)
    retriever = _retriever()
    doc = None
    if payload.get("id"):
        doc = retriever.get(str(payload["id"]))
    elif payload.get("nombre"):
        # Busca por nombre y usa el mejor coincidente como origen.
        hits = retriever.search(payload["nombre"], k=1)
        doc = hits[0].doc if hits else None
    if doc is None:
        return jsonify({"error": "no se encuentra el producto origen"}), 404
    res = equivalencia(
        retriever, _llm(), Product.from_dict(doc), chain_destino=payload.get("chain"), k=k
    )
    elegido = retriever.get(res.pid_elegido) if res.pid_elegido else None
    return jsonify(
        {
            "origen": doc,
            "candidatos": _hits_json(res.candidatos),
            "elegido": elegido,
            "confianza": res.confianza,
            "motivo": res.motivo,
            "proveedor": res.proveedor,
            "error": res.error,
        }
    )


@app.post("/ask")
def ask():
    """Respuesta del asistente: JSON validado contra el esquema del repo.

    Antes de devolverla pasa por los guardrails (citas validas, cifras del
    contexto, abstension). En modo estricto la respuesta se corrige: se
    quitan las citas a productos que no estan en el contexto.
    """
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "falta 'question'"}), 400
    k = int(payload.get("k") or config.TOP_K)
    filtros = _filtros(payload)
    res = qa(_retriever(), _llm(), question, k=k, filters=filtros)

    g = aplicar_guardrails(
        res.respuesta or "",
        res.hits,
        estricto=bool(payload.get("estricto", True)),
    )
    respuesta = construir_respuesta(
        question=question,
        respuesta=g.respuesta_corregida or res.respuesta or "",
        hits=res.hits,
        fuentes=res.fuentes,
        confianza=0.8 if (not g.abstention and g.ok) else (0.3 if g.abstention else 0.0),
        abstained=g.abstention,
        guardrails=g,
        provider=res.proveedor or "none",
        model=getattr(_llm(), "model", None),
        latencia_s=res.latencia_s,
    )
    errores = validar(respuesta)
    if errores:
        respuesta["guardrails"]["warnings"].append(
            "La respuesta no cumple el JSON Schema: " + "; ".join(errores[:3])
        )
        respuesta["guardrails"]["ok"] = False
    return jsonify(respuesta)


@app.post("/ask/stream")
def ask_stream():
    """Respuesta en streaming por SSE (Server-Sent Events).

    Eventos: `fuentes` (los ids del contexto), `token` (trozo de texto) y
    `fin` (respuesta completa). Es lo que consume la app movil para pintar la
    respuesta a medida que se genera.
    """
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "falta 'question'"}), 400
    k = int(payload.get("k") or config.TOP_K)
    filtros = _filtros(payload)
    llm = _llm()
    if llm is None or isinstance(llm, NoLLM):
        return jsonify({"error": "streaming necesita un LLM configurado (RAG_LLM=ollama|gemini)"}), 400

    def generar():
        try:
            for tipo, dato in flujo_qa(_retriever(), llm, question, k=k, filters=filtros):
                yield "event: " + tipo + "\ndata: " + json.dumps(dato, ensure_ascii=False, default=str) + "\n\n"
        except Exception as e:  # noqa: BLE001 - el error viaja como evento
            yield "event: error\ndata: " + json.dumps({"error": str(e)}, ensure_ascii=False) + "\n\n"

    return Response(
        generar(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rag.serve", description="Servicio HTTP del RAG")
    p.add_argument("--host", default=os.environ.get("RAG_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("RAG_PORT", "8080")))
    p.add_argument("--embed", default=config.DEFAULT_EMBEDDING)
    p.add_argument("--llm", default=config.DEFAULT_LLM, choices=config.LLM_PROVIDERS)
    args = p.parse_args(argv)

    inicializar(args.embed, args.llm)
    print(f"embeddings: {_ESTADO.get('embeddings')}")
    print(f"llm: {_ESTADO['llm'].describe() if _ESTADO.get('llm') else 'ninguno'}")
    print(f"productos indexados: {len(_ESTADO['retriever'].store)}")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
