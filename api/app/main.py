"""API del comparador de preus.

Flux de consulta: app → API → Redis (L1) → PostgreSQL (L2).
Documentació interactiva a /docs; contracte a /openapi.json.
"""
from contextlib import asynccontextmanager
import hashlib
import json
from datetime import date

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import repository, shopping
from .cache import Cache, get_cache
from .config import settings
from .db import get_session, init_db
from .schemas import (
    ChainOut, Health, OptimizedList, PriceHistory, ProductDetail, SearchPage, ShoppingListIn,
    VectorSearchIn, VectorSearchResult,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_schema:
        init_db()
    yield


app = FastAPI(
    title="Comparador de precios de supermercados",
    version="0.1.0",
    lifespan=lifespan,
)
# L'app mòbil en desenvolupament (Expo web) crida des d'un altre origen.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/health", response_model=Health, tags=["sistema"])  # Comprova si la BD i Redis responen. Kubernetes el fa servir per saber si el contenidor està bé.
def health(session: Session = Depends(get_session), cache: Cache = Depends(get_cache)):
    try:
        db_ok = session.execute(text("SELECT 1")).scalar() == 1
    except Exception:
        db_ok = False
    redis_ok = cache.ping()
    return Health(status="ok" if db_ok else "degraded", db=db_ok, redis=redis_ok)


@app.get("/chains", response_model=list[ChainOut], tags=["catálogo"])
def chains(session: Session = Depends(get_session)):
    return repository.list_chains(session)


@app.get("/products/search", response_model=SearchPage, tags=["catálogo"])
def search_products(
    response: Response,
    q: str = Query(min_length=2, max_length=100, description="Texto a buscar, p. ej. 'aceite oliva'"),
    chain: str | None = Query(None, description="Filtra por cadena (slug), p. ej. 'mercadona'"),
    unit: str | None = Query(None, description="Solo productos con esta unidad: kg, l, ud, m o lavado"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    cache: Cache = Depends(get_cache),
):
    """Productes de totes les cadenes el nom dels quals conté totes les paraules de `q`,
    ordenats per preu unitari (€/kg, €/l…) de menor a major. Primer els de la unitat
    principal (`unit` a la resposta) i després la resta, perquè €/l i €/ud no es comparen."""
    q = " ".join(q.lower().split())
    key = f"search:{q}:{chain or ''}:{unit or ''}:{limit}:{offset}"
    if (cached := cache.get(key)) is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    total, main_unit, items = repository.search_products(session, q, chain, unit, limit, offset)
    page = SearchPage(query=q, unit=main_unit, total=total, limit=limit, offset=offset, items=items)
    cache.set(key, page.model_dump(mode="json"))
    response.headers["X-Cache"] = "MISS"
    return page


@app.post(
    "/products/search-vector",
    response_model=VectorSearchResult,
    tags=["catálogo"],
    summary="Búsqueda semántica (para el asistente de IA)",
)
def search_products_by_vector(body: VectorSearchIn, session: Session = Depends(get_session)):
    """Los productos más parecidos a un embedding, del más al menos parecido, con su último precio.

    La llama el servidor MCP del asistente (VM 2): convierte la pregunta en un vector con su
    modelo de embeddings y lo envía aquí junto con los filtros. Sin caché: cada vector es distinto."""
    items = repository.search_by_vector(
        session, body.embedding, body.top_k, body.chains, body.unit,
        body.max_price, body.max_unit_price,
    )
    return VectorSearchResult(items=items)


@app.get(
    "/products/{product_id}",
    response_model=ProductDetail,
    responses={404: {"description": "Producto no encontrado"}},
    tags=["catálogo"],
)
def get_product(
    product_id: int,
    response: Response,
    session: Session = Depends(get_session),
    cache: Cache = Depends(get_cache),
):
    key = f"product:{product_id}"
    if (cached := cache.get(key)) is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    product = repository.get_product(session, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    cache.set(key, product.model_dump(mode="json"))
    response.headers["X-Cache"] = "MISS"
    return product


@app.get(
    "/products/{product_id}/prices",
    response_model=PriceHistory,
    responses={404: {"description": "Producto no encontrado"}},
    tags=["precios"],
)
def get_price_history(
    product_id: int,
    since: date | None = Query(None, alias="from", description="Desde (YYYY-MM-DD)"),
    until: date | None = Query(None, alias="to", description="Hasta (YYYY-MM-DD)"),
    session: Session = Depends(get_session),
):
    """Evolució del preu d'un producte, del més antic al més recent."""
    product = repository.get_product(session, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    points = repository.price_history(session, product_id, since, until)
    return PriceHistory(product_id=product_id, unit=product.unit, points=points)


# Exemples que surten al desplegable de Swagger (/docs). Fan servir les dades de demo.
LIST_EXAMPLES = {
    "con_cantidades": {
        "summary": "Con cantidades (recomendado)",
        "description": "Cada artículo dice cuánto quieres; la API elige el tamaño de envase más barato.",
        "value": {"items": [
            {"q": "aceite oliva", "amount": 3, "unit": "l"},
            {"q": "macarrones", "amount": 2, "unit": "kg"},
            {"q": "arroz redondo", "amount": 2, "unit": "kg"},
            {"q": "pechuga pollo", "amount": 1, "unit": "kg"},
            {"q": "huevos", "amount": 12, "unit": "ud"},
        ]},
    },
    "sin_cantidades": {
        "summary": "Sin cantidades (envases)",
        "description": "Sin `amount`: el envase más barato × `quantity`.",
        "value": {"items": [
            {"q": "aceite oliva virgen extra"},
            {"q": "leche entera"},
            {"q": "arroz redondo", "quantity": 2},
            {"q": "huevos"},
        ]},
    },
    "algunas_cadenas": {
        "summary": "Solo algunos súpers",
        "description": "`chains` limita la comparación a estas cadenas.",
        "value": {
            "items": [{"q": "arroz redondo", "amount": 2, "unit": "kg"}, {"q": "huevos"}],
            "chains": ["mercadona", "alcampo"],
        },
    },
}


@app.post(
    "/shopping-list/optimize",
    response_model=OptimizedList,
    tags=["lista"],
    summary="Lista de la compra optimizada",
)
def optimize_shopping_list(
    response: Response,
    body: ShoppingListIn = Body(openapi_examples=LIST_EXAMPLES),
    session: Session = Depends(get_session),
    cache: Cache = Depends(get_cache),
):
    """Cuánto cuesta la lista entera en cada súper y cuánto comprando cada artículo donde es más barato.

    **Cómo probarlo:** *Try it out* → elige un ejemplo en el desplegable → *Execute*.
    El precio final está **al principio de la respuesta**: `best_chain` y `best_total`
    (mejor súper si vas a uno solo), `combined_total` (combinando súpers) y `savings` (ahorro).

    Con `amount` (p. ej. 3 litros) se calcula cuántos envases hacen falta y se elige el que
    sale más barato, así todos los súpers se comparan por la misma cantidad."""
    raw = json.dumps(body.model_dump(mode="json"), sort_keys=True)
    key = "list:" + hashlib.sha1(raw.encode()).hexdigest()
    if (cached := cache.get(key)) is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    result = shopping.optimize(session, body)
    cache.set(key, result.model_dump(mode="json"))
    response.headers["X-Cache"] = "MISS"
    return result
