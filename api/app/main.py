"""API del comparador de preus.

Flux de consulta: app → API → Redis (L1) → PostgreSQL (L2).
Documentació interactiva a /docs; contracte a /openapi.json.
"""
from contextlib import asynccontextmanager
import hashlib
import json
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import repository, shopping
from .cache import Cache, get_cache
from .config import settings
from .db import get_session, init_db
from .schemas import (
    ChainOut, Health, OptimizedList, PriceHistory, ProductDetail, SearchPage, ShoppingListIn,
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


@app.post("/shopping-list/optimize", response_model=OptimizedList, tags=["lista"])
def optimize_shopping_list(
    body: ShoppingListIn,
    response: Response,
    session: Session = Depends(get_session),
    cache: Cache = Depends(get_cache),
):
    """Quant costa la llista a cada cadena i quant costa comprant cada article on és més barat.

    Per a cada article es tria, a cada cadena, el producte de menor preu unitari (el que surt
    més a compte) dins de la unitat principal, com a la cerca. El cost és preu total × quantitat."""
    raw = json.dumps(body.model_dump(mode="json"), sort_keys=True)
    key = "list:" + hashlib.sha1(raw.encode()).hexdigest()
    if (cached := cache.get(key)) is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    result = shopping.optimize(session, body)
    cache.set(key, result.model_dump(mode="json"))
    response.headers["X-Cache"] = "MISS"
    return result
