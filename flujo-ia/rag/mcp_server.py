"""Server MCP (Model Context Protocol) del prototipo de RAG.

Transporte **stdio**: el cliente (Claude Code, Claude Desktop, otro agente)
lanza el proceso y habla por stdin/stdout:

    /ruta/al/venv/bin/python -m rag.mcp_server

Tools:

    estado, buscar, preguntar, equivalencia   -> API HTTP del RAG (:8080)
    consulta_productos, productos_similares   -> PostgreSQL + pgvector

El server **no carga modelos**: las tools del RAG consumen la API que ya
esta en marcha (cero RAM duplicada) y las de la BD van a psycopg directo.
Si la API o la BD no estan, la tool devuelve un error amable en vez de
tirar el proceso. La base de datos es opcional: sin RAG_PG_DSN las tools
de productos explican que falta configurarla.

Conexion desde un cliente (ejemplo para Claude Code, en el portatil):

    ssh alumne@10.4.41.108 "cd TARDOR-test/flujo-ia && .venv/bin/python -m rag.mcp_server"
"""

from __future__ import annotations

import requests

from . import config
from .retriever import Filters

try:
    from mcp.server.mcpserver import MCPServer
except ImportError as e:  # pragma: no cover - depende del entorno
    raise SystemExit(
        "Falta el paquete 'mcp': instala dependencias con "
        "'pip install -r requirements.txt'"
    )

mcp = MCPServer(
    name="rag-supermercados",
    instructions=(
        "Herramientas del RAG de supermercados (PTI): buscar productos por "
        "texto, responder preguntas con citas a productos [id], encontrar "
        "equivalencias entre cadenas y consultar la base de productos con "
        "pgvector. Las respuestas del asistente llevan guardrails: si no hay "
        "informacion suficiente, abstienen en vez de inventar."
    ),
)

# /ask con LLM local puede tardar bastante (qwen3:8b en CPU); el resto es
# retrieval, que es rapido.
_TIMEOUT_LARGO = 180
_TIMEOUT_CORTO = 60


def _llamar(metodo: str, ruta: str, body: dict | None = None, timeout: int = _TIMEOUT_CORTO) -> dict:
    """Llama a la API del RAG y devuelve su JSON (o un error amable)."""
    url = config.API_URL + ruta
    try:
        resp = requests.request(metodo, url, json=body, timeout=timeout)
    except requests.RequestException as e:
        return {
            "error": (
                f"no responde la API del RAG en {config.API_URL} ({e.__class__.__name__}). "
                "¿Esta en marcha? Arrancala con: python -m rag.serve"
            )
        }
    try:
        datos = resp.json()
    except ValueError:
        return {"error": f"respuesta no JSON de {ruta}: HTTP {resp.status_code}"}
    if resp.status_code >= 400:
        return {"error": datos.get("error") or f"HTTP {resp.status_code}"}
    return datos


def _store_pg():
    """PgStore listo para usar, o (None, mensaje de error amable)."""
    from .pgstore import PgError, PgStore

    if not config.PG_DSN:
        return None, {
            "error": (
                "base de datos no configurada: define RAG_PG_DSN "
                "(postgresql://usuario:clave@127.0.0.1:5432/base) y reinicia"
            )
        }
    try:
        store = PgStore()
        store._columnas_reales()  # valida tabla/columnas sin tocar el vector
        return store, None
    except PgError as e:
        return None, {"error": f"base de datos no disponible: {e}"}


# ---------------------------------------------------------------------------
# Tools sobre la API del RAG
# ---------------------------------------------------------------------------


@mcp.tool()
def estado() -> dict:
    """Estado del servicio RAG: si responde, de donde lee los datos (indice
    local o PostgreSQL), cuantos productos hay y que LLM esta configurado."""
    return _llamar("GET", "/health")


@mcp.tool()
def buscar(
    query: str,
    k: int = 5,
    chain: str | None = None,
    category: str | None = None,
    min_total: float | None = None,
    max_total: float | None = None,
) -> dict:
    """Busca productos del catalogo por texto con su score de similitud.

    Devuelve los `k` mejores (id, name, chain, total, unit_price...) y,
    si hay LLM, una respuesta redactada. Filtros opcionales:
    `chain` (p.ej. 'mercadona', 'carrefour', 'lidl'), `category`
    (subcadena, p.ej. 'aceite'), `min_total`/`max_total` (precio total en EUR).
    """
    body = {
        "query": query,
        "k": k,
        "chain": chain,
        "category": category,
        "min_total": min_total,
        "max_total": max_total,
    }
    return _llamar("POST", "/search", body)


@mcp.tool()
def preguntar(question: str, k: int = 8, estricto: bool = True) -> dict:
    """Responde una pregunta en lenguaje natural citando productos [id].

    Devuelve el JSON validado del asistente: `answer`, `sources` (fuentes
    con id, nombre, cadena y precio), `confidence`, `abstained` y
    `guardrails`. Si el contexto no alcanza para responder, `abstained`
    es true en vez de inventar. Sirve para dudas de precio, marca,
    tamano o disponibilidad por cadena.
    """
    body = {"question": question, "k": k, "estricto": estricto}
    return _llamar("POST", "/ask", body, timeout=_TIMEOUT_LARGO)


@mcp.tool()
def equivalencia(
    id: str | None = None,
    nombre: str | None = None,
    chain: str | None = None,
    k: int = 8,
) -> dict:
    """Encuentra el equivalente de un producto en otra cadena.

    Pasa el `id` (o el `nombre`) del producto origen y la `chain` destino
    (p.ej. 'carrefour'). Devuelve el origen, los candidatos recuperados,
    el elegido y la confianza. 404 como `error` si el origen no existe.
    """
    body = {"id": id, "nombre": nombre, "chain": chain, "k": k}
    return _llamar("POST", "/equiv", body)


# ---------------------------------------------------------------------------
# Tools sobre PostgreSQL + pgvector
# ---------------------------------------------------------------------------


@mcp.tool()
def consulta_productos(
    chain: str | None = None,
    category: str | None = None,
    min_total: float | None = None,
    max_total: float | None = None,
    limite: int = 20,
) -> dict:
    """Lista productos de la base (PostgreSQL + pgvector) con filtros.

    Es un SELECT con filtros de metadatos (sin similitud): misma
    `chain`, `category`, `min_total`/`max_total` que `buscar`, y hasta
    `limite` filas (maximo 500). Requiere RAG_PG_DSN configurado.
    """
    store, err = _store_pg()
    if err:
        return err
    filtros = Filters(
        chain=chain,
        category=category,
        min_total=min_total,
        max_total=max_total,
    )
    try:
        filas = store.filtrar(filtros, limite=limite)
    except Exception as e:  # noqa: BLE001 - error de BD -> mensaje para el agente
        return {"error": f"base de datos no disponible: {e}"}
    return {"n": len(filas), "productos": filas}


@mcp.tool()
def productos_similares(id_producto: str, k: int = 5) -> dict:
    """Top-k de productos parecidos a uno dado (distancia de coseno).

    Usa el vector ya guardado en la columna de pgvector: no hace falta
    modelo de embeddings, es una consulta SQL pura. `id_producto` es el
    id del producto origen; si no existe o no tiene vector, devuelve
    `n: 0`. Requiere RAG_PG_DSN configurado.
    """
    store, err = _store_pg()
    if err:
        return err
    try:
        filas = store.similares(id_producto, k=k)
    except Exception as e:  # noqa: BLE001 - error de BD -> mensaje para el agente
        return {"error": f"base de datos no disponible: {e}"}
    return {"n": len(filas), "origen": id_producto, "productos": filas}


def main() -> int:
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
