"""Esquemes de resposta de l'API (el que veu l'app). Generen el contracte OpenAPI."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from .config import settings

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


class VectorSearchIn(BaseModel):
    """Cerca semàntica: el vector el calcula l'equip d'IA (VM 2) amb el mateix model que els
    embeddings dels productes. Amb e5 la pregunta porta el prefix "query: " i els productes
    "passage: "; l'API no en sap res, només compara vectors."""
    embedding: list[float] = Field(
        description=f"Embedding de la pregunta ({settings.embedding_dim} dimensiones)"
    )
    top_k: int = Field(10, ge=1, le=50, description="Cuántos productos devolver")
    chains: list[str] | None = Field(None, description="Opcional: solo estas cadenas (slugs)")
    unit: str | None = Field(None, description="Opcional: kg, l, ud, m o lavado")
    max_price: Decimal | None = Field(None, gt=0, description="Opcional: precio máximo del envase (€)")
    max_unit_price: Decimal | None = Field(
        None, gt=0, description="Opcional: precio unitario máximo (€/kg, €/l…)"
    )

    @field_validator("embedding")
    @classmethod
    def _dimension(cls, v: list[float]) -> list[float]:
        if len(v) != settings.embedding_dim:
            raise ValueError(f"se esperaban {settings.embedding_dim} dimensiones y llegan {len(v)}")
        return v


class VectorHit(ProductSummary):
    similarity: float  # similitud cosinus (1 = idèntic)


class VectorSearchResult(BaseModel):
    items: list[VectorHit]


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
