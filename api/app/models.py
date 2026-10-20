"""Esquema de la base de datos (fuente única de verdad).

    chains 1──* stores
    chains 1──* products 1──* prices *──1 stores

Un producto es el artículo de UNA cadena (el aceite Hacendado de Mercadona). La
equivalencia entre cadenas llegará después; de momento se compara por precio unitario.
"""
from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import settings

# Importes con 4 decimales, igual que la cuantización del normalizador (_q).
Money = Numeric(12, 4)


class Base(DeclarativeBase):
    pass


class Chain(Base):
    """Cadena de supermercados. `slug` es el <cadena> del subject scraper.<cadena>.clean."""
    __tablename__ = "chains"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))

    stores: Mapped[list["Store"]] = relationship(back_populates="chain")


class Store(Base):
    """Tienda o almacén de una cadena. `code` es el `wh` del mensaje (hoy siempre 'default')."""
    __tablename__ = "stores"
    __table_args__ = (UniqueConstraint("chain_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"))
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120), default="")
    address: Mapped[str] = mapped_column(String(200), default="")
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    chain: Mapped[Chain] = relationship(back_populates="stores")


class Product(Base):
    """Catálogo. Clave natural: (cadena, id del producto en la web de la cadena)."""
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("chain_id", "source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"))
    source_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(120), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    size: Mapped[str] = mapped_column(String(40), default="")         # crudo de la fuente
    size_format: Mapped[str] = mapped_column(String(20), default="")
    unit: Mapped[str | None] = mapped_column(String(10))               # kg, l, ud, m, lavado
    # La rellena el equipo de IA; NULL = pendiente de calcular.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chain: Mapped[Chain] = relationship()
    prices: Mapped[list["Price"]] = relationship(back_populates="product", passive_deletes=True)


class Price(Base):
    """Un precio observado por producto, tienda y día. Es a la vez el precio actual
    (el más reciente) y el historial. La clave única hace idempotente la carga."""
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("product_id", "store_id", "observed_on"),
        Index("ix_prices_product_date", "product_id", "observed_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    observed_on: Mapped[date] = mapped_column(Date)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total: Mapped[Decimal | None] = mapped_column(Money)              # precio del envase
    unit_price: Mapped[Decimal | None] = mapped_column(Money)         # EUR por product.unit
    unit_src: Mapped[str] = mapped_column(String(10), default="-")    # fuente, calculado, -
    unit_reason: Mapped[str] = mapped_column(String(80), default="")  # motivo si no hay unit_price

    product: Mapped[Product] = relationship(back_populates="prices")
    store: Mapped[Store] = relationship()
