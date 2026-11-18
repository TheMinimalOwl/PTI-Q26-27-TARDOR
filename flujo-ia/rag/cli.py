"""CLI del prototipo de RAG.

    python -m rag.cli index                       # indexa data/raw/*.txt
    python -m rag.cli search "aceite de oliva"    # catalogo
    python -m rag.cli equiv --id 10001 --chain carrefour
    python -m rag.cli ask "¿cual es el aceite mas barato por litro?"
    python -m rag.cli eval --llm ollama           # informe completo
    python -m rag.cli compare                     # bge-m3 vs e5-small

Opciones comunes:
    --embed bge-m3|e5-small|<id de HF>   modelo de embeddings
    --llm ollama|gemini|none              backend de LLM
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config
from .embeddings import Embedder
from .evaluate import ejecutar_evaluacion, formatear_informe
from .indexer import build_index, index_dir_for, load_index
from .ingest import Product
from .llm import build_llm
from .pipelines import catalogo, equivalencia, qa
from .retriever import Filters, Retriever


def _ficheros_raw() -> list[Path]:
    archivos = sorted(config.RAW_DIR.glob("*_clean.txt"))
    if not archivos:
        raise SystemExit(
            f"No hay datos en {config.RAW_DIR}. Genera el dataset con:\n"
            f"    python data/generate_dataset.py"
        )
    return archivos


def _retriever(args) -> Retriever:
    embedder = Embedder(args.embed)
    store = load_index(embedder)
    return Retriever(embedder, store)


def _llm(args):
    if getattr(args, "llm", "none") in (None, "none"):
        return None
    return build_llm(args.llm)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def cmd_index(args) -> int:
    embedder = Embedder(args.embed)
    print(f"Modelo: {embedder.spec.hf_id} ({embedder.spec.dim} dim)")
    store, report = build_index(embedder, _ficheros_raw())
    print(
        f"Indexados {report.n_productos} productos de {report.n_cadenas} cadenas "
        f"en {report.segundos:.1f}s -> {report.destino}"
    )
    print(f"  incompletos (sin precio unitario): {report.incompletos}")
    _ = store
    return 0


def cmd_search(args) -> int:
    retriever = _retriever(args)
    filtros = Filters(chain=args.chain, category=args.category)
    res = catalogo(retriever, _llm(args), args.query, k=args.k, filters=filtros)
    print(f"Consulta: {res.query}")
    if filtros.describe() != "sin filtros":
        print(f"Filtros: {filtros.describe()}")
    print(f"Recuperados {len(res.hits)}:")
    for h in res.hits:
        d = h.doc
        print(
            f"  [{h.rank}] {d.get('id')} {d.get('name')} | {d.get('chain')} | "
            f"{d.get('total')} EUR | unitario {d.get('unit_price')} EUR/{d.get('unit')} "
            f"| score {h.score:.3f}"
        )
    if res.respuesta:
        print("\nRespuesta del LLM:")
        print(res.respuesta)
    if res.error:
        print(f"\n(error del LLM: {res.error})", file=sys.stderr)
    return 0


def cmd_equiv(args) -> int:
    retriever = _retriever(args)
    doc = retriever.get(args.id)
    if doc is None:
        print(f"No encuentro el producto {args.id} en el indice", file=sys.stderr)
        return 1
    res = equivalencia(
        retriever, _llm(args), Product.from_dict(doc), chain_destino=args.chain, k=args.k
    )
    print(f"Origen: [{doc.get('id')}] {doc.get('name')} ({doc.get('chain')})")
    print(f"Candidatos recuperados ({len(res.candidatos)}):")
    for h in res.candidatos:
        d = h.doc
        print(
            f"  [{h.rank}] {d.get('id')} {d.get('name')} | {d.get('chain')} | "
            f"{d.get('size')} {d.get('size_format')} | {d.get('total')} EUR | score {h.score:.3f}"
        )
    if res.proveedor:
        print(f"\nDecision del LLM ({res.proveedor}):")
        print(f"  pid: {res.pid_elegido}  confianza: {res.confianza}")
        print(f"  motivo: {res.motivo}")
    else:
        print(f"\n(Solo retrieval: primer candidato = {res.top1_recuperado})")
    if res.error:
        print(f"(error del LLM: {res.error})", file=sys.stderr)
    return 0


def cmd_ask(args) -> int:
    retriever = _retriever(args)
    filtros = Filters(chain=args.chain, category=args.category)
    res = qa(retriever, _llm(args), args.question, k=args.k, filters=filtros)
    print(f"Pregunta: {res.question}")
    print("\nContexto recuperado:")
    for h in res.hits:
        d = h.doc
        print(
            f"  [{h.rank}] {d.get('id')} {d.get('name')} | {d.get('chain')} | "
            f"{d.get('total')} EUR | unitario {d.get('unit_price')} EUR/{d.get('unit')}"
        )
    if res.respuesta:
        print("\nRespuesta:")
        print(res.respuesta)
        print(f"Fuentes citadas: {res.fuentes}")
    if res.error:
        print(f"(error del LLM: {res.error})", file=sys.stderr)
    return 0


def cmd_eval(args) -> int:
    retriever = _retriever(args)
    llm = _llm(args)
    print(f"Embeddings: {retriever.embedder.spec.hf_id}")
    print(f"LLM: {llm.describe() if llm else 'ninguno (solo retrieval)'}")
    informe = ejecutar_evaluacion(retriever, llm, max_casos=args.max_casos)
    print()
    print(formatear_informe(informe))
    if args.json:
        destino = Path(args.json)
        destino.write_text(
            json.dumps(informe, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print(f"\nInforme completo: {destino}")
    return 0


def cmd_compare(args) -> int:
    """Compara modelos de embeddings con la misma evaluacion de retrieval."""
    modelos = args.models or ["bge-m3", "e5-small", "qwen3-embed-0.6b"]
    resultados = []
    for key in modelos:
        print(f"\n=== {key} ===")
        try:
            embedder = Embedder(key)
            store, report = build_index(embedder, _ficheros_raw(), destino=index_dir_for(key))
            retriever = Retriever(embedder, store)
            informe = ejecutar_evaluacion(retriever, None)
        except Exception as e:  # noqa: BLE001 - un modelo que falla no tumba la comparativa
            print(f"  ERROR con {key}: {e}")
            continue
        c = informe["catalogo"]["resumen"]
        e = informe["equivalencia"]["resumen"]
        fila = {
            "modelo": embedder.spec.hf_id,
            "dim": embedder.spec.dim,
            "segundos_indexado": round(report.segundos, 2),
            "catalogo_recall@1": round(c["recall@1"], 4),
            "catalogo_recall@3": round(c["recall@3"], 4),
            "catalogo_recall@5": round(c["recall@5"], 4),
            "catalogo_recall_full@3": round(c.get("recall_full@3", 0), 4),
            "catalogo_mrr": round(c["mrr"], 4),
            "equivalencia_recall@1": round(e.get("recall@1", 0), 4),
            "equivalencia_recall@3": round(e.get("recall@3", 0), 4),
            "equivalencia_recall@5": round(e.get("recall@5", 0), 4),
        }
        resultados.append(fila)
        print(fila)
    if not resultados:
        print("ningun modelo pudo evaluarse")
        return 1
    print("\nComparativa:")
    claves = list(resultados[0].keys())
    print(" | ".join(claves))
    for fila in resultados:
        print(" | ".join(str(fila[k]) for k in claves))
    if args.json:
        Path(args.json).write_text(
            json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


def _dsn_seguro(dsn: str) -> str:
    """Enmascara la clave de la conexion para imprimirla sin secretos."""
    import re

    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", dsn or "")


def cmd_pg_check(args) -> int:
    """Diagnostico de PostgreSQL + pgvector: conexion, esquema, embeddings
    y una busqueda de prueba de extremo a extremo."""
    from .pgstore import PgError, PgStore

    dsn = args.dsn or config.PG_DSN or None
    print(f"DSN: {_dsn_seguro(dsn) or '(sin RAG_PG_DSN)'}")
    try:
        store = PgStore(dsn=dsn)
        info = store.ping()
    except PgError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return 1
    print(f"  tabla: {info['tabla']} · columnas: {', '.join(info['columnas'])}")
    print(f"  productos: {info['n']}")
    if info["dim"] is None:
        print("  embeddings: NINGUNO en la tabla (o falta la columna vector)")
        print("  -> rellenalos con: python -m rag.cli pg-sync")
        return 1

    embedder = Embedder(args.embed)
    if info["dim"] != embedder.spec.dim:
        print(
            f"  ERROR: los vectores tienen dim {info['dim']} y el modelo "
            f"{embedder.spec.key} usa {embedder.spec.dim}: no son compatibles",
            file=sys.stderr,
        )
        return 1
    print(f"  embeddings: dim {info['dim']} (compatible con {embedder.spec.key})")

    filas = store.filtrar(Filters(), limite=2)
    for f in filas:
        print(f"  muestra: {f.get('id')} {f.get('name')} | {f.get('chain')} | {f.get('total')} EUR")

    qv = embedder.encode_one("aceite de oliva", is_query=True)
    try:
        hits = store.search(qv, k=3)
    except PgError as e:
        print(f"  ERROR en la busqueda de prueba: {e}", file=sys.stderr)
        return 1
    if not hits:
        print("  busqueda de prueba: sin resultados (¿sin embeddings?)", file=sys.stderr)
        return 1
    for h in hits:
        print(f"  busqueda: [{h.rank}] {h.doc.get('name')} | score {h.score:.3f}")
    print("PG OK: la base esta lista para RAG_STORE=pg")
    return 0


def cmd_pg_sync(args) -> int:
    """Rellena con el modelo de embeddings los que falten en la tabla."""
    from .pgstore import PgError, PgStore, vector_texto

    dsn = args.dsn or config.PG_DSN or None
    try:
        store = PgStore(dsn=dsn)
        store.ping()
        pendientes = store.pendientes(limite=args.limite)
    except PgError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return 1
    if not pendientes:
        print("Todo al dia: todos los productos de la tabla ya tienen embedding.")
        return 0
    embedder = Embedder(args.embed)
    print(f"Embebiendo {len(pendientes)} productos con {embedder.spec.key}...")
    textos = [Product.from_dict(d).embed_text for d in pendientes]
    vectores = embedder.encode(textos, is_query=False)
    pares = [(str(d["id"]), vector_texto(v)) for d, v in zip(pendientes, vectores)]
    n = store.guardar_embeddings(pares)
    print(f"Guardados {n} embeddings en '{store.tabla}'.")
    print("Comprueba todo con: python -m rag.cli pg-check")
    return 0


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rag.cli", description="Prototipo de RAG para TARDOR")
    p.add_argument("--embed", default=config.DEFAULT_EMBEDDING, help="modelo de embeddings")
    sub = p.add_subparsers(dest="comando", required=True)

    pi = sub.add_parser("index", help="indexa data/raw/*.txt")
    pi.set_defaults(func=cmd_index)

    ps = sub.add_parser("search", help="busqueda de catalogo")
    ps.add_argument("query")
    ps.add_argument("-k", type=int, default=config.TOP_K)
    ps.add_argument("--chain")
    ps.add_argument("--category")
    ps.add_argument("--llm", default="none", choices=config.LLM_PROVIDERS)
    ps.set_defaults(func=cmd_search)

    pe = sub.add_parser("equiv", help="equivalencia entre cadenas")
    pe.add_argument("--id", required=True, help="id del producto origen")
    pe.add_argument("--chain", help="cadena destino")
    pe.add_argument("-k", type=int, default=config.TOP_K_EQUIV)
    pe.add_argument("--llm", default="none", choices=config.LLM_PROVIDERS)
    pe.set_defaults(func=cmd_equiv)

    pq = sub.add_parser("ask", help="pregunta en lenguaje natural")
    pq.add_argument("question")
    pq.add_argument("-k", type=int, default=config.TOP_K)
    pq.add_argument("--chain")
    pq.add_argument("--category")
    pq.add_argument("--llm", default="none", choices=config.LLM_PROVIDERS)
    pq.set_defaults(func=cmd_ask)

    pv = sub.add_parser("eval", help="evaluacion completa")
    pv.add_argument("--llm", default="none", choices=config.LLM_PROVIDERS)
    pv.add_argument("--max-casos", type=int, help="recorta los casos evaluados")
    pv.add_argument("--json", help="guarda el informe completo en este fichero")
    pv.set_defaults(func=cmd_eval)

    pc = sub.add_parser("compare", help="compara modelos de embeddings")
    pc.add_argument("--models", nargs="*", help="claves de embeddings a comparar")
    pc.add_argument("--json", help="guarda la comparativa en este fichero")
    pc.set_defaults(func=cmd_compare)

    pchk = sub.add_parser(
        "pg-check", help="diagnostico de PostgreSQL + pgvector (conexion, esquema, busqueda)"
    )
    pchk.add_argument("--dsn", help="cadena de conexion (por defecto RAG_PG_DSN)")
    pchk.set_defaults(func=cmd_pg_check)

    psync = sub.add_parser(
        "pg-sync", help="rellena con el modelo los embeddings que falten en la tabla"
    )
    psync.add_argument("--dsn", help="cadena de conexion (por defecto RAG_PG_DSN)")
    psync.add_argument("--limite", type=int, default=10000, help="maximo de filas a embeber")
    psync.set_defaults(func=cmd_pg_sync)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
