"""Esquemes de resposta de l'API (el que veu l'app). Generen el contracte OpenAPI."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

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
