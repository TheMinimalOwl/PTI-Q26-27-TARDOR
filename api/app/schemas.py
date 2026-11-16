"""Esquemes de resposta de l'API (el que veu l'app). Generen el contracte OpenAPI."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# A la BD els imports són Decimal; en JSON viatgen com a número (Pydantic els passaria a string).
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class ChainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str


class PriceOut(BaseModel):
    observed_on: date
    store: str
    total: Money | None
    unit_price: Money | None
    unit_src: str


class ProductSummary(BaseModel):
    id: int
    name: str
    chain: ChainOut
    category: str
    unit: str | None
    url: str
    price: PriceOut | None


class ProductDetail(ProductSummary):
    source_id: str
    size: str
    size_format: str
    updated_at: datetime


class SearchPage(BaseModel):
    query: str
    unit: str | None  # unitat que va primer a `items`: els preus unitaris només es comparen dins d'ella
    total: int
    limit: int
    offset: int
    items: list[ProductSummary]


class PriceHistory(BaseModel):
    product_id: int
    unit: str | None
    points: list[PriceOut]


class ListItemIn(BaseModel):
    q: str = Field(min_length=2, max_length=100, description="Qué comprar, p. ej. 'leche entera'")
    quantity: int = Field(1, ge=1, le=99)
    unit: str | None = Field(None, description="Opcional: kg, l, ud, m o lavado")


class ShoppingListIn(BaseModel):
    items: list[ListItemIn] = Field(min_length=1, max_length=50)
    chains: list[str] | None = Field(None, description="Opcional: solo estas cadenas (slugs)")


class ListLine(BaseModel):
    q: str
    quantity: int
    product: ProductSummary
    subtotal: Money  # preu total del producte × quantitat


class Basket(BaseModel):
    total: Money
    found: int
    missing: list[str]  # articles de la llista que no s'hi han trobat
    lines: list[ListLine]


class ChainBasket(Basket):
    chain: ChainOut


class OptimizedList(BaseModel):
    baskets: list[ChainBasket]  # tota la llista a cada cadena: primer les més completes i, dins, la més barata
    best_chain: str | None      # la primera de `baskets`
    combined: Basket            # cada article a la cadena on és més barat
    savings: Money | None       # best_chain − combined; null si no es poden comparar (falten articles diferents)


class Health(BaseModel):
    status: str
    db: bool
    redis: bool
