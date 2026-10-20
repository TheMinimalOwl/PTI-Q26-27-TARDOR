"""Esquemas de respuesta de la API (lo que ve la app). Generan el contrato OpenAPI."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# En BD los importes son Decimal; en JSON viajan como número (Pydantic los pasaría a string).
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
    total: int
    limit: int
    offset: int
    items: list[ProductSummary]


class PriceHistory(BaseModel):
    product_id: int
    unit: str | None
    points: list[PriceOut]


class Health(BaseModel):
    status: str
    db: bool
    redis: bool
