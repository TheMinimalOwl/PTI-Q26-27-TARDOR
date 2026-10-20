"""Carga de lotes limpios del normalizador en la BD.

Entrada: mensajes de `scraper.<cadena>.clean` (ver flujo-entrada/docs/03-contratos-datos.md).
Acepta los dos formatos del contrato:
  - JSON estructurado `CleanBatch` (`items: NormalizedProduct[]`), el preferido;
  - texto plano (`clean: "..."`), el que publica hoy el consumer, parseado por ` | `.

La carga es idempotente (upsert): reprocesar un mensaje no duplica nada.
"""
import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import Chain, Price, Product, Store

log = logging.getLogger(__name__)


class NormalizedItem(BaseModel):
    """Espejo tolerante de `NormalizedProduct` del normalizador."""
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    total: Decimal | None = None
    unit_price: Decimal | None = None
    unit: str | None = None
    unit_src: str = "-"
    unit_reason: str = ""
    size: Any = None
    size_format: str = ""
    category: str = ""
    url: str = ""

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, v: Any) -> str:
        return v if isinstance(v, str) else str(v)


class Batch(BaseModel):
    chain: str
    wh: str = "default"
    ts: datetime
    items: list[NormalizedItem]


# ---------------------------------------------------------------- formato texto

_NUM = r"-?\d+(?:[.,]\d+)?"
_TOTAL = re.compile(rf"^({_NUM})\s*EUR total$")
_UNIT = re.compile(rf"^({_NUM})\s*EUR/(\S+)$")
_REASON = re.compile(r"^-\s*\((.+)\)$")
_SIZE = re.compile(rf"^({_NUM})\s*(.*)$")
_SRC = re.compile(r"src=(\S+)")


def _dec(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def parse_clean_line(line: str) -> NormalizedItem | None:
    """`{pid} | {nombre} | {total}EUR total | {up}EUR/{unidad} | {size}{fmt} | {cat} | {url} | ref=... src=...`

    Los 6 últimos campos son fijos, así que se cortan desde la derecha: un ` | ` dentro
    del nombre no rompe el parseo. Devuelve None para cabeceras y líneas `ERROR`."""
    parts = [p.strip() for p in line.split(" | ")]
    if len(parts) < 8 or line.startswith("ERROR"):
        return None
    pid, name = parts[0], " | ".join(parts[1:-6])
    total_s, unit_s, size_s, cat, url, refsrc = parts[-6:]

    total = _TOTAL.match(total_s)
    item = dict(id=pid, name=name, category=cat, url=url,
                total=_dec(total.group(1)) if total else None)

    if m := _UNIT.match(unit_s):
        src = _SRC.search(refsrc)
        item.update(unit_price=_dec(m.group(1)), unit=m.group(2),
                    unit_src=src.group(1) if src else "fuente")
    elif m := _REASON.match(unit_s):
        item.update(unit_reason=m.group(1))
    else:
        item.update(unit_reason=f"no_parseable:{unit_s}")

    if m := _SIZE.match(size_s):
        item.update(size=m.group(1), size_format=m.group(2))
    else:
        item.update(size=size_s)
    return NormalizedItem(**item)


def parse_message(subject: str, data: bytes) -> Batch:
    """Convierte un mensaje NATS en un lote. La cadena sale del subject."""
    chain = subject.split(".")[1]
    payload = json.loads(data)
    ts = payload.get("ts") or datetime.now(timezone.utc).isoformat()
    wh = payload.get("wh") or "default"

    if "items" in payload:
        items = payload["items"]
    elif "clean" in payload:
        items = [i for line in payload["clean"].splitlines() if (i := parse_clean_line(line))]
    else:
        raise ValueError("mensaje sin 'items' ni 'clean'")
    return Batch(chain=chain, wh=wh, ts=ts, items=items)


# ---------------------------------------------------------------- escritura

CHAIN_NAMES = {"ahorramas": "Ahorramás"}


def _get_or_create_chain(session: Session, slug: str) -> int:
    chain_id = session.scalar(select(Chain.id).where(Chain.slug == slug))
    if chain_id is None:
        chain = Chain(slug=slug, name=CHAIN_NAMES.get(slug, slug.capitalize()))
        session.add(chain)
        session.flush()
        chain_id = chain.id
    return chain_id


def _get_or_create_store(session: Session, chain_id: int, code: str) -> int:
    store_id = session.scalar(select(Store.id).where(Store.chain_id == chain_id, Store.code == code))
    if store_id is None:
        store = Store(chain_id=chain_id, code=code)
        session.add(store)
        session.flush()
        store_id = store.id
    return store_id


def upsert_batch(session: Session, batch: Batch) -> dict[str, int]:
    """Inserta o actualiza productos y el precio del día. No hace commit."""
    chain_id = _get_or_create_chain(session, batch.chain)
    store_id = _get_or_create_store(session, chain_id, batch.wh)
    stats = {"products": 0, "prices": 0, "without_price": 0}

    for item in batch.items:
        product_values = dict(
            name=item.name, category=item.category, url=item.url,
            size="" if item.size is None else str(item.size),
            size_format=item.size_format, unit=item.unit,
        )
        product_id = session.scalar(
            insert(Product)
            .values(chain_id=chain_id, source_id=item.id, **product_values)
            .on_conflict_do_update(
                index_elements=[Product.chain_id, Product.source_id],
                set_={**product_values, "updated_at": datetime.now(timezone.utc)},
            )
            .returning(Product.id)
        )
        stats["products"] += 1

        if item.total is None and item.unit_price is None:
            stats["without_price"] += 1
            continue
        price_values = dict(
            observed_at=batch.ts, total=item.total, unit_price=item.unit_price,
            unit_src=item.unit_src, unit_reason=item.unit_reason,
        )
        session.execute(
            insert(Price)
            .values(product_id=product_id, store_id=store_id,
                    observed_on=batch.ts.date(), **price_values)
            .on_conflict_do_update(
                index_elements=[Price.product_id, Price.store_id, Price.observed_on],
                set_=price_values,
            )
        )
        stats["prices"] += 1
    return stats
