"""Servicio HTTP del prototipo de RAG.

El equipo de API/BD y el de la app necesitan consumeR el RAG desde fuera. Este
modulo expone una API minima sobre Flask (la misma libreria que usa la funcion
de Fission del normalizador, para no anadir dependencias al equipo de ingesta).

Endpoints:

    GET  /health              estado del servicio (indice, modelo, LLM)
    POST /search              busqueda de catalogo
    POST /equiv               equivalencia entre cadenas
    POST /ask                 pregunta en lenguaje natural (JSON validado)
    POST /ask/stream          respuesta token a token (SSE)
    POST /embed               embeddings e5-small (384) para la BD; pide X-API-Key
    GET  /docs                documentacion de los endpoints (HTML)
    GET  /probar              cliente de prueba en vivo: demo + streaming (HTML)

El servicio envia cabeceras CORS (`Access-Control-Allow-Origin: *`) para que
la app pueda llamarlo desde otro origen en el navegador. El contrato completo
(documentacion de los payloads y plan de pruebas) esta en
`docs/06-integracion-api.md`.

Se arranca con:

    python -m rag.serve --host 0.0.0.0 --port 8080

En un despliegue real, el indice se monta como volumen de solo lectura
(`.cache/index/<modelo>/`) y el servicio lo carga al arrancar: el indice no
cambia entre peticiones, asi que **no** se recalcula en caliente.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
from decimal import Decimal, InvalidOperation

from flask import Flask, Response, jsonify, request

from . import config
from .chain import flujo_qa
from .embeddings import Embedder
from .guardrails import aplicar_guardrails, construir_respuesta, validar
from .ingest import Product
from .llm import NoLLM, build_llm
from .pgstore import cargar_store
from .pipelines import catalogo, equivalencia, qa
from .retriever import Filters, Retriever

app = Flask(__name__)


@app.after_request
def _cors(resp: Response) -> Response:
    """CORS abierto: la app (otro origen) puede llamar desde el navegador."""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

# Estado global del servicio: se carga una vez al arrancar.
_ESTADO: dict = {"retriever": None, "llm": None, "error": None, "embed": None}

# --- /embed -----------------------------------------------------------------
# El modelo de /embed es fijo: la columna `products.embedding` de la BD es
# vector(384), asi que aunque RAG_EMBED_MODEL apunte a otro modelo, aqui se usa
# siempre e5-small.
EMBED_MODEL = "e5-small"
EMBED_MAX_TEXTS = 256
EMBED_MAX_CHARS = 2000
EMBED_KINDS = ("passage", "query")


def _embed_api_key() -> str | None:
    """Clave compartida con el equipo de API/BD (`RAG_EMBED_API_KEY`)."""
    return (os.environ.get("RAG_EMBED_API_KEY") or "").strip() or None


def _embedder_embed() -> Embedder:
    """Embedder de /embed: reutiliza el del indice si ya es e5-small."""
    if _ESTADO.get("embed") is None:
        retriever = _ESTADO.get("retriever")
        emb = getattr(retriever, "embedder", None) if retriever else None
        if emb is not None and getattr(emb, "spec", None) is not None and emb.spec.key == EMBED_MODEL:
            _ESTADO["embed"] = emb
        else:
            _ESTADO["embed"] = Embedder(EMBED_MODEL)
    return _ESTADO["embed"]


def _quitar_prefijo(texto: str, spec) -> str:
    """Si el cliente ya trae "passage: "/"query: ", no se duplica."""
    for pref in (spec.passage_prefix, spec.query_prefix):
        if pref and texto.startswith(pref):
            return texto[len(pref):]
    return texto


def _dec(v):
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def inicializar(embed_model: str | None = None, llm_provider: str | None = None) -> None:
    """Carga el almacen y el LLM. Se llama al arrancar el servicio.

    El almacen lo elige `cargar_store` segun `RAG_STORE`: indice local o
    PostgreSQL+pgvector, con fallback al local si la base no responde.
    """
    embedder = Embedder(embed_model or config.DEFAULT_EMBEDDING)
    store, origen, error = cargar_store(embedder)
    _ESTADO["retriever"] = Retriever(embedder, store)
    _ESTADO["store"] = origen
    _ESTADO["store_error"] = error
    _ESTADO["embeddings"] = embedder.describe()
    _ESTADO["embed"] = None  # /embed lo resuelve (y reutiliza) en la primera llamada
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


def _fin_json(fin: dict) -> dict:
    """Evento final del streaming con el mismo contrato que `/ask`.

    Los `hits` salen como JSON (antes se serializaban los objetos Python tal
    cual, inservibles para la app) y el texto pasa por los guardrails, para
    que la app pinte el aviso de abstencion igual que con `/ask`. El
    `respuesta` de aqui manda sobre lo pintado en vivo: corrige citas si
    hace falta.
    """
    hits = fin.get("hits") or []
    g = aplicar_guardrails(fin.get("respuesta") or "", hits, estricto=True)
    return {
        "question": fin.get("question"),
        "respuesta": g.respuesta_corregida or fin.get("respuesta") or "",
        "fuentes": fin.get("fuentes") or [],
        "hits": _hits_json(hits),
        "abstained": bool(g.abstention),
        "guardrails": g.as_dict(),
    }


@app.get("/health")
def health():
    retriever = _ESTADO.get("retriever")
    llm = _ESTADO.get("llm")
    return jsonify(
        {
            "ok": retriever is not None,
            "error": _ESTADO.get("error"),
            "n_productos": len(retriever.store) if retriever else 0,
            "store": _ESTADO.get("store", "local"),
            "store_error": _ESTADO.get("store_error"),
            "embeddings": _ESTADO.get("embeddings"),
            "llm": llm.describe() if llm else None,
            "llm_error": _ESTADO.get("llm_error"),
            "embed": {
                "model": EMBED_MODEL,
                "dim": config.embedding_spec(EMBED_MODEL).dim,
                "key_configured": _embed_api_key() is not None,
            },
        }
    )


@app.post("/embed")
def embed():
    """Embeddings para la BD (`products.embedding`, vector(384)).

    Pide la cabecera `X-API-Key` igual a `RAG_EMBED_API_KEY`. Si el servicio
    no tiene clave configurada devuelve 503: el endpoint nunca queda abierto
    por descuido. Cuerpo: `{"texts": [...], "kind": "passage"|"query"}`.
    Devuelve `{"embeddings": [[384 floats], ...]}` en el mismo orden, con
    norma 1 (coseno == producto escalar en pgvector).
    """
    clave = _embed_api_key()
    if clave is None:
        return jsonify({"error": "RAG_EMBED_API_KEY no configurada en el servicio"}), 503
    recibida = request.headers.get("X-API-Key") or ""
    if not hmac.compare_digest(recibida.encode(), clave.encode()):
        return jsonify({"error": "X-API-Key ausente o incorrecta"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "el cuerpo tiene que ser un objeto JSON"}), 400
    texts = payload.get("texts")
    if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
        return jsonify({"error": "'texts' tiene que ser una lista de strings"}), 400
    kind = payload.get("kind", "passage")
    if kind not in EMBED_KINDS:
        return jsonify({"error": "'kind' tiene que ser 'passage' o 'query'"}), 400
    if len(texts) > EMBED_MAX_TEXTS:
        return jsonify({"error": f"maximo {EMBED_MAX_TEXTS} textos por peticion"}), 413
    if any(len(t) > EMBED_MAX_CHARS for t in texts):
        return jsonify({"error": f"maximo {EMBED_MAX_CHARS} caracteres por texto"}), 413
    if not texts:
        return jsonify({"embeddings": []})

    emb = _embedder_embed()
    limpios = [_quitar_prefijo(t, emb.spec) for t in texts]
    vecs = emb.encode(limpios, is_query=(kind == "query"), normalize=True)
    return jsonify({"embeddings": [[float(x) for x in v] for v in vecs]})


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
                if tipo == "fin":
                    dato = _fin_json(dato)
                yield "event: " + tipo + "\ndata: " + json.dumps(dato, ensure_ascii=False, default=str) + "\n\n"
        except Exception as e:  # noqa: BLE001 - el error viaja como evento
            yield "event: error\ndata: " + json.dumps({"error": str(e)}, ensure_ascii=False) + "\n\n"

    return Response(
        generar(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_DOCS_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>RAG · API</title>
<style>
 body{font-family:Arial,sans-serif;background:#0F172A;color:#F8FAFC;margin:0;padding:40px}
 h1{font-size:28px} h1 span{color:#38BDF8} h2{font-size:18px;color:#34D399;margin-top:32px}
 table{border-collapse:collapse;width:100%;max-width:900px}
 td,th{border:1px solid #334155;padding:8px 12px;text-align:left;font-size:14px}
 th{background:#1E293B;color:#94A3B8} code{color:#818CF8}
 pre{background:#1E293B;border-radius:8px;padding:14px;max-width:900px;overflow:auto;font-size:13px}
 p,a{color:#94A3B8;font-size:14px}
</style></head><body>
<h1>API del <span>RAG</span> · contrato para la app</h1>
<p>Contrato completo, payloads de ejemplo y plan de pruebas: <code>docs/06-integracion-api.md</code><br>
Prueba en vivo con las preguntas de demo y streaming: <a href="/probar" style="color:#38BDF8">/probar</a></p>
<h2>Endpoints</h2>
<table>
<tr><th>Método</th><th>Ruta</th><th>Cuerpo</th><th>Devuelve</th></tr>
<tr><td>GET</td><td><code>/health</code></td><td>—</td><td>estado: índice, embeddings, LLM</td></tr>
<tr><td>POST</td><td><code>/search</code></td><td><code>{"query", "k", filtros...}</code></td><td>resultados + respuesta</td></tr>
<tr><td>POST</td><td><code>/equiv</code></td><td><code>{"id"|"nombre", "chain"}</code></td><td>candidatos + elegido</td></tr>
<tr><td>POST</td><td><code>/ask</code></td><td><code>{"question", "k", "estricto"}</code></td><td>JSON validado (answer, sources, guardrails...)</td></tr>
<tr><td>POST</td><td><code>/ask/stream</code></td><td><code>{"question"}</code></td><td>SSE: <code>fuentes</code>, <code>token</code>, <code>fin</code></td></tr>
<tr><td>POST</td><td><code>/embed</code></td><td><code>{"texts", "kind"}</code> + cabecera <code>X-API-Key</code></td><td><code>{"embeddings": [[384 floats]...]}</code> (e5-small, norma 1)</td></tr>
</table>
<h2>Ejemplo</h2>
<pre>curl -s -X POST http://localhost:8080/ask \\
  -H 'Content-Type: application/json' \\
  -d '{"question": "¿Cuánto cuesta el agua mineral de 1.5 l en Mercadona?"}'</pre>
<h2>Errores</h2>
<table>
<tr><td>400</td><td>falta <code>query</code>/<code>question</code>; o <code>/ask/stream</code> sin LLM</td></tr>
<tr><td>404</td><td><code>/equiv</code>: producto origen no encontrado</td></tr>
</table>
</body></html>"""


@app.get("/docs")
def docs():
    """Documentacion de los endpoints: pagina HTML sin dependencias."""
    return Response(_DOCS_HTML, mimetype="text/html")


_PROBAR_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RAG · Probar</title>
<style>
 body{font-family:Arial,sans-serif;background:#0F172A;color:#F8FAFC;margin:0;padding:32px;max-width:960px}
 h1{font-size:26px} h1 span{color:#38BDF8}
 p{color:#94A3B8;font-size:14px}
 code{color:#818CF8}
 label{font-size:13px;color:#94A3B8;display:block;margin-top:16px}
 input,textarea{font-family:inherit;font-size:14px;border-radius:8px;border:1px solid #334155;background:#1E293B;color:#F8FAFC;padding:10px 12px;width:100%;box-sizing:border-box}
 textarea{min-height:64px;resize:vertical}
 button{font-family:inherit;font-size:14px;border-radius:8px;border:0;padding:10px 16px;margin:10px 6px 0 0;cursor:pointer;background:#38BDF8;color:#0F172A;font-weight:bold}
 button.sec{background:#334155;color:#F8FAFC;font-weight:normal}
 button.demo{background:#1E293B;color:#94A3B8;border:1px solid #334155;font-weight:normal;font-size:13px;padding:6px 10px;margin:6px 6px 0 0}
 button.demo:hover{border-color:#38BDF8;color:#F8FAFC}
 button:disabled{opacity:.5;cursor:wait}
 #out{background:#1E293B;border-radius:8px;padding:16px;min-height:80px;margin-top:16px;font-size:15px;line-height:1.5;white-space:pre-wrap}
 #meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
 .chip{font-size:12px;padding:4px 10px;border-radius:999px;background:#1E293B;border:1px solid #334155;color:#94A3B8}
 .ok{border-color:#34D399;color:#34D399} .bad{border-color:#F87171;color:#F87171} .warn{border-color:#FBBF24;color:#FBBF24}
 .fuentes{font-size:12px;color:#94A3B8;margin-top:10px}
 .fuentes b{color:#F8FAFC;font-weight:normal}
 .err{color:#F87171;font-size:13px;margin-top:8px}
 #st{color:#94A3B8}
 a{color:#38BDF8}
</style></head><body>
<h1>Probar el <span>RAG</span> en vivo</h1>
<p>Cliente de referencia: usa el mismo contrato que la app (<code>/ask/stream</code> y <code>/ask</code>).
Documentación: <a href="/docs">/docs</a> · Estado: <span id="st">comprobando…</span></p>

<label for="base">Base URL (cámbiala para apuntar a otro servicio y comprobar CORS)</label>
<input id="base" onchange="health()">

<label>Preguntas de demo (verificadas con qwen3:8b)</label>
<div id="demob"></div>

<label for="q">Pregunta</label>
<textarea id="q" placeholder="¿Cuánto cuesta el agua mineral de 1.5 l en Mercadona?"></textarea>
<button id="bstream" onclick="stream()">Preguntar · stream</button>
<button class="sec" id="bask" onclick="simple()">Preguntar · JSON</button>
<button class="sec" onclick="limpiar()">Limpiar</button>

<div id="out"></div>
<div id="meta"></div>
<div class="fuentes" id="fuentes"></div>
<div class="err" id="err"></div>

<script>
const DEMO = [
  "¿Cuál es el aceite de oliva virgen extra de 1 l más barato en total?",
  "¿Cuál es el aceite de oliva virgen extra de 1 l más barato por unidad en cada una de las tres cadenas?",
  "¿Cuánto cuesta el agua mineral de 1.5 l en Mercadona?",
  "¿Cuánto cuesta el arroz bomba de 1 kg en Lidl?"
];
const $ = id => document.getElementById(id);
$("base").value = /^https?:/.test(location.protocol) ? location.origin : "http://10.4.41.108:8080";

DEMO.forEach(q => {
  const b = document.createElement("button");
  b.className = "demo";
  b.textContent = q.length > 62 ? q.slice(0, 60) + "\\u2026" : q;
  b.title = q;
  b.onclick = () => { $("q").value = q; stream(); };
  $("demob").appendChild(b);
});

async function health() {
  try {
    const r = await fetch($("base").value + "/health");
    const d = await r.json();
    $("st").textContent = (d.ok ? "\\u2705 " : "\\u26a0\\ufe0f ") + d.n_productos + " productos \\u00b7 " + (d.llm ? d.llm.model : "sin LLM");
    $("st").style.color = d.ok ? "#34D399" : "#FBBF24";
  } catch (e) {
    $("st").textContent = "\\u274c el servicio no responde";
    $("st").style.color = "#F87171";
  }
}
health();

function chip(texto, clase) {
  const s = document.createElement("span");
  s.className = "chip" + (clase ? " " + clase : "");
  s.textContent = texto;
  $("meta").appendChild(s);
}

function pintarResultado(d, ms) {
  $("meta").innerHTML = "";
  chip("\\u23f1 " + (ms / 1000).toFixed(1) + " s");
  chip(d.abstained ? "abstained: s\\u00ed" : "abstained: no", d.abstained ? "warn" : "ok");
  const gok = d.guardrails && d.guardrails.ok;
  chip("guardrails: " + (gok ? "ok" : "REVISAR"), gok ? "ok" : "bad");
  if (d.guardrails && d.guardrails.warnings && d.guardrails.warnings.length) {
    chip("\\u26a0 " + d.guardrails.warnings.join(" \\u00b7 "), "warn");
  }
  const fuentes = d.sources || [];
  $("fuentes").innerHTML = fuentes.length
    ? "Fuentes: " + fuentes.map(f =>
        "<b>[" + f.id + "]</b> " + f.name + " \\u00b7 " + f.chain +
        (f.price_total != null ? " \\u00b7 " + f.price_total + " \\u20ac" : "")
      ).join(" &nbsp;|&nbsp; ")
    : "";
}

async function stream() {
  const q = $("q").value.trim();
  if (!q) return;
  activar(false);
  $("err").textContent = ""; $("meta").innerHTML = ""; $("fuentes").innerHTML = "";
  $("out").textContent = "\\u2026";
  const t0 = Date.now();
  try {
    const r = await fetch($("base").value + "/ask/stream", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: q}),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.error || "HTTP " + r.status);
    }
    const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
    let buf = "", texto = "", fin = null;
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += value;
      let i;
      while ((i = buf.indexOf("\\n\\n")) >= 0) {
        const bloque = buf.slice(0, i);
        buf = buf.slice(i + 2);
        let ev = "", data = "";
        for (const linea of bloque.split("\\n")) {
          if (linea.startsWith("event: ")) ev = linea.slice(7);
          else if (linea.startsWith("data: ")) data = linea.slice(6);
        }
        if (!ev) continue;
        let dato;
        try { dato = JSON.parse(data); } catch { dato = data; }
        if (ev === "token") { texto += dato; $("out").textContent = texto; }
        else if (ev === "fin") fin = dato;
        else if (ev === "error") throw new Error(dato.error || "error del stream");
      }
    }
    const ms = Date.now() - t0;
    if (fin) {
      $("out").textContent = fin.respuesta;
      pintarResultado({
        abstained: fin.abstained,
        guardrails: fin.guardrails,
        sources: (fin.hits || []).map(h => ({id: h.id, name: h.name, chain: h.chain, price_total: h.total})),
      }, ms);
    } else {
      $("out").textContent = texto;
      chip("\\u23f1 " + (ms / 1000).toFixed(1) + " s");
    }
  } catch (e) {
    $("out").textContent = "";
    $("err").textContent = "Error: " + e.message;
  }
  activar(true);
}

async function simple() {
  const q = $("q").value.trim();
  if (!q) return;
  activar(false);
  $("err").textContent = ""; $("meta").innerHTML = ""; $("fuentes").innerHTML = "";
  $("out").textContent = "\\u2026";
  const t0 = Date.now();
  try {
    const r = await fetch($("base").value + "/ask", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: q}),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "HTTP " + r.status);
    $("out").textContent = d.answer;
    pintarResultado(d, Date.now() - t0);
  } catch (e) {
    $("out").textContent = "";
    $("err").textContent = "Error: " + e.message;
  }
  activar(true);
}

function activar(on) {
  $("bstream").disabled = !on;
  $("bask").disabled = !on;
}

function limpiar() {
  $("q").value = ""; $("out").textContent = ""; $("meta").innerHTML = "";
  $("fuentes").innerHTML = ""; $("err").textContent = "";
}
</script>
</body></html>"""


@app.get("/probar")
def probar():
    """Cliente de prueba en vivo: las 4 preguntas de demo y el streaming."""
    return Response(_PROBAR_HTML, mimetype="text/html")



def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rag.serve", description="Servicio HTTP del RAG")
    p.add_argument("--host", default=os.environ.get("RAG_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("RAG_PORT", "8080")))
    p.add_argument("--embed", default=config.DEFAULT_EMBEDDING)
    p.add_argument("--llm", default=config.DEFAULT_LLM, choices=config.LLM_PROVIDERS)
    args = p.parse_args(argv)

    inicializar(args.embed, args.llm)
    print(f"embeddings: {_ESTADO.get('embeddings')}")
    print(f"store: {_ESTADO.get('store')}" + (f" (aviso: {_ESTADO.get('store_error')})" if _ESTADO.get("store_error") else ""))
    print(f"llm: {_ESTADO['llm'].describe() if _ESTADO.get('llm') else 'ninguno'}")
    print(f"productos indexados: {len(_ESTADO['retriever'].store)}")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
