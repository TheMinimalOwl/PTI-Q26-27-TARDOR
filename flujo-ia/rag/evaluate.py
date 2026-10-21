"""Evaluacion del prototipo: tres tareas, tres metricas.

- **Catalogo**: dada una peticion en lenguaje natural, ¿estan los productos
  esperados entre los k recuperados? -> recall@k, MRR.
- **Equivalencia**: dado un producto de una cadena, ¿el equivalente de la
  otra cadena esta entre los candidatos? -> recall@k; y con LLM, ¿el LLM elige
  el correcto? -> precision@1.
- **QA**: la respuesta contiene el dato esperado y no cita productos
  inventados -> acierto de contenido + acierto de citas.

La evaluacion no necesita LLM para el retrieval (se mide con `--llm none`),
lo que permite comparar modelos de embeddings sin gastar API ni depender de
la red.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .llm import BaseLLM, LLMError
from .pipelines import equivalencia, qa
from .retriever import Filters, Retriever

GOLD_DIR = Path(__file__).resolve().parent.parent / "data" / "gold"


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------


def eval_catalogo(retriever: Retriever, gold: list[dict], ks=(1, 3, 5, 10)) -> dict:
    """recall@k y MRR de la busqueda de catalogo."""
    resultados = []
    if not gold:
        return {"resumen": {"n": 0}, "casos": []}
    # Una sola pasada de embedding para todas las consultas (en CPU, codificar
    # de una en una cuesta ~1 s por consulta con bge-m3).
    vectores = retriever.embedder.encode([c["query"] for c in gold], is_query=True)
    kmax = max(ks)
    for caso, vector in zip(gold, vectores):
        ids = caso["expected_ids"]
        hits = retriever.store.search(vector, k=kmax)
        recovered = [h.doc.get("id") for h in hits]
        fila = {"query": caso["query"], "expected": ids, "recovered": recovered}
        for k in ks:
            topk = recovered[:k]
            fila[f"recall@{k}"] = 1.0 if any(i in topk for i in ids) else 0.0
            # recall "real": fraction de esperados que aparecen en el top-k.
            fila[f"recall_full@{k}"] = (
                sum(1 for i in ids if i in topk) / len(ids) if ids else 0.0
            )
        mrr = 0.0
        for rank, pid in enumerate(recovered, start=1):
            if pid in ids:
                mrr = 1.0 / rank
                break
        fila["mrr"] = mrr
        resultados.append(fila)

    resumen = {"n": len(resultados)}
    for k in ks:
        clave = f"recall@{k}"
        resumen[clave] = sum(r[clave] for r in resultados) / len(resultados) if resultados else 0.0
        clave_full = f"recall_full@{k}"
        resumen[clave_full] = (
            sum(r[clave_full] for r in resultados) / len(resultados) if resultados else 0.0
        )
    resumen["mrr"] = sum(r["mrr"] for r in resultados) / len(resultados) if resultados else 0.0
    return {"resumen": resumen, "casos": resultados}


# ---------------------------------------------------------------------------
# Equivalencia
# ---------------------------------------------------------------------------


def eval_equivalencia(
    retriever: Retriever,
    gold: list[dict],
    no_equivalentes: list[dict],
    llm: BaseLLM | None = None,
    ks=(1, 3, 5, 8),
) -> dict:
    """Equivalencia entre cadenas.

    `gold` son los pares conocidos (mismo producto en otra cadena).
    `no_equivalentes` son los casos trampa: mismo nombre, formato distinto.
    Con LLM se mide tambien si el LLM distingue los unos de los otros.
    """
    resultados = []
    # Los productos origen se codifican en una sola pasada: son 498 pares pero
    # solo ~257 productos distintos, y en CPU cada forward suelto cuesta ~1 s.
    # Se codifican tambien los origenes de las trampas, que son los mismos.
    pids = []
    for caso in list(gold) + list(no_equivalentes):
        pid = str(caso["pid_origen"])
        if pid not in pids:
            pids.append(pid)
    docs = [retriever.get(pid) for pid in pids]
    pares = [(pid, doc) for pid, doc in zip(pids, docs) if doc is not None]
    if not pares:
        return {"resumen": {"n": 0}, "casos": [], "trampas": []}
    vectores = retriever.embedder.encode(
        [_as_product(doc).embed_text for _pid, doc in pares], is_query=True
    )
    vector_por_pid = {pid: v for (pid, _doc), v in zip(pares, vectores)}

    for caso in gold:
        origen = retriever.get(caso["pid_origen"])
        vector = vector_por_pid.get(str(caso["pid_origen"]))
        destino = caso["pid_destino"]
        if origen is None or vector is None:
            continue
        filtros = Filters(chain=caso["chain_destino"])
        hits = retriever.store.search(vector, k=max(ks), where=filtros.matches)
        recovered = [h.doc.get("id") for h in hits]
        fila = {"pid_origen": caso["pid_origen"], "pid_destino": destino, "recovered": recovered}
        for k in ks:
            fila[f"recall@{k}"] = 1.0 if destino in recovered[:k] else 0.0
        if llm is not None:
            res = equivalencia(
                retriever, llm, origen, chain_destino=caso["chain_destino"], vector=vector
            )
            fila["llm_pid"] = res.pid_elegido
            fila["llm_ok"] = 1.0 if res.pid_elegido == destino else 0.0
            fila["llm_confianza"] = res.confianza
            fila["llm_error"] = res.error
        resultados.append(fila)

    resumen = {"n": len(resultados)}
    for k in ks:
        clave = f"recall@{k}"
        resumen[clave] = sum(r.get(clave, 0.0) for r in resultados) / len(resultados) if resultados else 0.0
    if llm is not None:
        resumen["precision@1_llm"] = (
            sum(r.get("llm_ok", 0.0) for r in resultados) / len(resultados) if resultados else 0.0
        )
        resumen["precision@1_top1"] = (
            sum(1.0 for r in resultados if r["recovered"] and r["recovered"][0] == r["pid_destino"])
            / len(resultados)
            if resultados
            else 0.0
        )

    # Casos trampa: el LLM no debe decir que son equivalentes.
    trampas = []
    for caso in no_equivalentes:
        origen = retriever.get(caso["pid_origen"])
        vector = vector_por_pid.get(str(caso["pid_origen"]))
        if origen is None or llm is None or vector is None:
            continue
        res = equivalencia(
            retriever, llm, origen, chain_destino=caso.get("chain_destino"), vector=vector
        )
        bien = 1.0 if res.pid_elegido != caso["pid_destino"] else 0.0
        trampas.append(
            {
                "pid_origen": caso["pid_origen"],
                "pid_trampa": caso["pid_destino"],
                "llm_pid": res.pid_elegido,
                "ok": bien,
            }
        )
    if trampas:
        resumen["trampas_ok"] = sum(t["ok"] for t in trampas) / len(trampas)
        resumen["n_trampas"] = len(trampas)

    return {"resumen": resumen, "casos": resultados, "trampas": trampas}


# ---------------------------------------------------------------------------
# QA
# ---------------------------------------------------------------------------


def eval_qa(retriever: Retriever, gold: list[dict], llm: BaseLLM | None = None, k: int = 6) -> dict:
    """QA: la respuesta debe contener el dato esperado y citar solo lo recuperado."""
    if llm is None:
        return {"resumen": {"n": 0, "nota": "QA necesita LLM"}, "casos": []}

    resultados = []
    if not gold:
        return {"resumen": {"n": 0}, "casos": []}
    # Las preguntas se codifican en una sola pasada (en CPU, una a una son
    # ~1 s cada una con bge-m3).
    vectores = retriever.embedder.encode([c["question"] for c in gold], is_query=True)
    for caso, vector in zip(gold, vectores):
        t0 = time.perf_counter()
        res = qa(retriever, llm, caso["question"], k=k, vector=vector)
        latencia = time.perf_counter() - t0
        respuesta = (res.respuesta or "").lower()
        contenido = all(
            any(alt.lower() in respuesta for alt in grupo) for grupo in caso.get("expected_contains", [])
        )
        esperado_pids = set(caso.get("expected_pids", []))
        citados = set(res.fuentes)
        recuperados = {h.doc.get("id") for h in res.hits}
        # Cita inventada: el LLM menciona un id que no estaba en el contexto.
        citas_inventadas = sorted(citadas - recuperados)
        resultados.append(
            {
                "question": caso["question"],
                "respuesta": res.respuesta,
                "contenido_ok": 1.0 if contenido else 0.0,
                "citas_inventadas": citas_inventadas,
                "citas_ok": 1.0 if not citas_inventadas else 0.0,
                "cubre_esperados": 1.0 if not esperado_pids or (citados & esperado_pids) else 0.0,
                "latencia_s": latencia,
                "error": res.error,
            }
        )

    n = len(resultados)
    resumen = {
        "n": n,
        "contenido_ok": sum(r["contenido_ok"] for r in resultados) / n if n else 0.0,
        "citas_ok": sum(r["citas_ok"] for r in resultados) / n if n else 0.0,
        "cubre_esperados": sum(r["cubre_esperados"] for r in resultados) / n if n else 0.0,
        "latencia_media_s": sum(r["latencia_s"] for r in resultados) / n if n else 0.0,
    }
    return {"resumen": resumen, "casos": resultados}


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------


def _as_product(doc: dict):
    from .ingest import Product

    return Product.from_dict(doc)


def cargar_gold() -> dict:
    """Carga los ficheros de ground truth."""
    gold = {"catalogo": [], "qa": [], "equivalencias": [], "no_equivalentes": []}
    catalogo = GOLD_DIR / "catalogo.json"
    if catalogo.exists():
        gold["catalogo"] = json.loads(catalogo.read_text(encoding="utf-8"))
    qa_file = GOLD_DIR / "qa.json"
    if qa_file.exists():
        gold["qa"] = json.loads(qa_file.read_text(encoding="utf-8"))
    eq = GOLD_DIR / "equivalencias.csv"
    if eq.exists():
        import csv

        filas = list(csv.DictReader(eq.open(encoding="utf-8")))
        # Cada producto canonico genera un par por cada combinacion de cadenas.
        por_key: dict[str, list[dict]] = {}
        for f in filas:
            por_key.setdefault(f["key"], []).append(f)
        for key, prods in por_key.items():
            for a in prods:
                for b in prods:
                    if a["cadena"] == b["cadena"]:
                        continue
                    gold["equivalencias"].append(
                        {
                            "key": key,
                            "pid_origen": a["pid"],
                            "pid_destino": b["pid"],
                            "chain_destino": b["cadena"],
                        }
                    )
    ne = GOLD_DIR / "no_equivalentes.csv"
    if ne.exists():
        import csv

        for f in csv.DictReader(ne.open(encoding="utf-8")):
            gold["no_equivalentes"].append(
                {
                    "pid_origen": f["pid_origen"],
                    "pid_destino": f["pid_destino"],
                    "chain_destino": f.get("cadena_destino") or None,
                    "motivo": f.get("motivo", ""),
                }
            )
    return gold


def ejecutar_evaluacion(
    retriever: Retriever, llm: BaseLLM | None = None, max_casos: int | None = None
) -> dict:
    """Pasa las tres evaluaciones y devuelve el informe completo.

    `max_casos` recorta los casos evaluados. Hace falta porque con el LLM
    local (4B en CPU) cada llamada cuesta varios segundos: la evaluacion
    completa son ~500 llamadas, mientras que una muestra de 25 da la misma
    informacion para decidir.
    """
    gold = cargar_gold()
    catalogo_gold = gold["catalogo"][:max_casos] if max_casos else gold["catalogo"]
    eq_gold = gold["equivalencias"][:max_casos] if max_casos else gold["equivalencias"]
    qa_gold = gold["qa"][:max_casos] if max_casos else gold["qa"]
    informe = {
        "catalogo": eval_catalogo(retriever, catalogo_gold),
        "equivalencia": eval_equivalencia(
            retriever, eq_gold, gold["no_equivalentes"], llm=llm
        ),
    }
    if llm is not None:
        informe["qa"] = eval_qa(retriever, qa_gold, llm=llm)
    informe["meta"] = {
        "n_catalogo": len(catalogo_gold),
        "n_equivalencia": len(eq_gold),
        "n_qa": len(qa_gold),
        "max_casos": max_casos,
        "llm": llm.describe() if llm else None,
        "embeddings": retriever.embedder.describe(),
    }
    return informe


def formatear_informe(informe: dict) -> str:
    """Informe legible para consola."""
    lineas = []
    c = informe["catalogo"]["resumen"]
    lineas.append("CATALOGO (busqueda)")
    lineas.append(
        f"  recall@1={c['recall@1']:.3f}  recall@3={c['recall@3']:.3f}  "
        f"recall@5={c['recall@5']:.3f}  recall@10={c['recall@10']:.3f}  MRR={c['mrr']:.3f}"
    )
    if "recall_full@3" in c:
        lineas.append(
            f"  recall_full@1={c['recall_full@1']:.3f}  recall_full@3={c['recall_full@3']:.3f}  "
            f"recall_full@5={c['recall_full@5']:.3f}  (fraccion de esperados en el top-k)"
        )
    e = informe["equivalencia"]["resumen"]
    lineas.append("EQUIVALENCIA")
    lineas.append(
        f"  recall@1={e.get('recall@1', 0):.3f}  recall@3={e.get('recall@3', 0):.3f}  "
        f"recall@5={e.get('recall@5', 0):.3f}  recall@8={e.get('recall@8', 0):.3f}"
    )
    if "precision@1_llm" in e:
        lineas.append(
            f"  precision@1 LLM={e['precision@1_llm']:.3f}  "
            f"(solo retrieval: {e.get('precision@1_top1', 0):.3f})"
        )
    if "trampas_ok" in e:
        lineas.append(
            f"  casos trampa bien descartados: {e['trampas_ok']:.3f} (n={e['n_trampas']})"
        )
    if "qa" in informe:
        q = informe["qa"]["resumen"]
        lineas.append("QA")
        lineas.append(
            f"  contenido={q['contenido_ok']:.3f}  citas sin inventar={q['citas_ok']:.3f}  "
            f"cubre esperados={q['cubre_esperados']:.3f}  latencia media={q['latencia_media_s']:.1f}s"
        )
    return "\n".join(lineas)
