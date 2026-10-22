"""API del comparador de preus.

Flux de consulta: app → API → Redis (L1) → PostgreSQL (L2).
Documentació interactiva a /docs; contracte a /openapi.json.
"""
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import repository
from .cache import Cache, get_cache
from .config import settings
from .db import get_session, init_db
from .schemas import ChainOut, Health, PriceHistory, ProductDetail, SearchPage


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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


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
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    cache: Cache = Depends(get_cache),
):
    """Productes de totes les cadenes el nom dels quals conté totes les paraules de `q`,
    ordenats per preu unitari (€/kg, €/l…) de menor a major."""
    q = " ".join(q.lower().split())
    key = f"search:{q}:{chain or ''}:{limit}:{offset}"
    if (cached := cache.get(key)) is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    total, items = repository.search_products(session, q, chain, limit, offset)
    page = SearchPage(query=q, total=total, limit=limit, offset=offset, items=items)
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
