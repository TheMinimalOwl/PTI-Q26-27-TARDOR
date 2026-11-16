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
    amount: Decimal | None = Field(
        None, gt=0, le=1000,
        description="Cantidad deseada en la unidad (p. ej. 3 con unit 'l' = 3 litros). "
        "Si se indica, se elige el producto con el que cuesta menos llegar a esa cantidad "
        "y se ignora `quantity`.",
    )
    quantity: int = Field(1, ge=1, le=99, description="Paquetes, si no se indica `amount`")
    unit: str | None = Field(None, description="Opcional: kg, l, ud, m o lavado")


class ShoppingListIn(BaseModel):
    items: list[ListItemIn] = Field(min_length=1, max_length=50)
    chains: list[str] | None = Field(None, description="Opcional: solo estas cadenas (slugs)")


class ListLine(BaseModel):
    q: str
    amount: Money | None  # quantitat demanada (en product.unit), o null si es demanaven paquets
    packs: int            # paquets que cal comprar
    product: ProductSummary
    subtotal: Money       # preu del paquet × packs


class Basket(BaseModel):
    total: Money
    found: int
    missing: list[str]  # articles de la llista que no s'hi han trobat
    lines: list[ListLine]


class ChainBasket(Basket):
    chain: ChainOut


class OptimizedList(BaseModel):
    # Primer el resum (és el que es mira a Swagger i a l'app) i després el detall.
    best_chain: str | None = Field(description="Mejor súper para comprar toda la lista en uno solo")
    best_total: Money | None = Field(description="Precio final de la lista en `best_chain`")
    combined_total: Money = Field(description="Precio final comprando cada artículo donde es más barato")
    savings: Money | None = Field(
        description="Cuánto se ahorra combinando súpers (`best_total` − `combined_total`). "
        "Es null si no son comparables (faltan artículos distintos)"
    )
    combined: Basket = Field(description="Detalle de la compra combinada: cada artículo en el súper más barato")
    baskets: list[ChainBasket] = Field(
        description="Detalle de la lista entera en cada súper: primero los que tienen más artículos y, entre ellos, el más barato"
    )


class Health(BaseModel):
    status: str
    db: bool
    redis: bool
