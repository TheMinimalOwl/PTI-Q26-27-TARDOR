"""Consultes a la BD. Els routers no escriuen SQL: només criden aquestes funcions."""
from datetime import date

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session, aliased, joinedload

from .models import Chain, Price, Product, Store
from .schemas import ChainOut, PriceOut, ProductDetail, ProductSummary


def _latest_prices() -> Select:
    """Preu més recent de cada producte (DISTINCT ON de PostgreSQL)."""
    return (
        select(Price)
        .distinct(Price.product_id)
        .order_by(Price.product_id, Price.observed_on.desc())
    )


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _price_out(price: Price | None, store_code: str | None) -> PriceOut | None:
    if price is None:
        return None
    return PriceOut(
        observed_on=price.observed_on,
        store=store_code or "",
        total=price.total,
        unit_price=price.unit_price,
        unit_src=price.unit_src,
    )


def _summary(product: Product, price: Price | None, store_code: str | None) -> dict:
    return dict(
        id=product.id,
        name=product.name,
        chain=ChainOut.model_validate(product.chain),
        category=product.category,
        unit=product.unit,
        url=product.url,
        price=_price_out(price, store_code),
    )


def search_products(
    session: Session, q: str, chain: str | None, unit: str | None, limit: int, offset: int
) -> tuple[int, str | None, list[ProductSummary]]:
    """Cerca per nom (sense distingir majúscules ni accents). Cada paraula de `q`
    hi ha d'aparèixer. Ordena per preu unitari: el més barat primer.

    Els preus unitaris només es poden comparar dins d'una mateixa unitat (una llauna
    a 0,52 €/ud no és més barata que un oli a 3,45 €/l). Per això primer van els
    productes de la unitat principal (`unit` o, si no se'n demana cap, la més
    freqüent entre els resultats) i després la resta. Retorna també aquesta unitat."""
    latest = aliased(Price, _latest_prices().subquery())

    conditions = [
        func.unaccent(Product.name).ilike(func.unaccent(f"%{_escape_like(word)}%"), escape="\\")
        for word in q.split()
    ]
    if chain:
        conditions.append(Chain.slug == chain)
    if unit:
        conditions.append(Product.unit == unit)

    base = select(Product).join(Product.chain).where(and_(*conditions))
    total = session.scalar(select(func.count()).select_from(base.subquery()))

    main_unit = unit or session.scalar(
        select(Product.unit)
        .join(Product.chain)
        .where(and_(*conditions), Product.unit.is_not(None))
        .group_by(Product.unit)
        .order_by(func.count().desc(), Product.unit)
        .limit(1)
    )
    order = [latest.unit_price.asc().nulls_last(), Product.name]
    if main_unit:
        order.insert(0, case((Product.unit == main_unit, 0), else_=1))

    rows = session.execute(
        base.add_columns(latest, Store.code)
        .outerjoin(latest, latest.product_id == Product.id)
        .outerjoin(Store, Store.id == latest.store_id)
        .options(joinedload(Product.chain))
        .order_by(*order)
        .limit(limit)
        .offset(offset)
    ).all()

    return total, main_unit, [ProductSummary(**_summary(p, price, code)) for p, price, code in rows]


def get_product(session: Session, product_id: int) -> ProductDetail | None:
    product = session.get(Product, product_id, options=[joinedload(Product.chain)])
    if product is None:
        return None
    row = session.execute(
        select(Price, Store.code)
        .join(Store, Store.id == Price.store_id)
        .where(Price.product_id == product_id)
        .order_by(Price.observed_on.desc())
        .limit(1)
    ).first()
    price, code = row if row else (None, None)
    return ProductDetail(
        **_summary(product, price, code),
        source_id=product.source_id,
        size=product.size,
        size_format=product.size_format,
        updated_at=product.updated_at,
    )


def price_history(
    session: Session, product_id: int, since: date | None, until: date | None
) -> list[PriceOut]:
    stmt = (
        select(Price, Store.code)
        .join(Store, Store.id == Price.store_id)
        .where(Price.product_id == product_id)
        .order_by(Price.observed_on)
    )
    if since:
        stmt = stmt.where(Price.observed_on >= since)
    if until:
        stmt = stmt.where(Price.observed_on <= until)
    return [_price_out(price, code) for price, code in session.execute(stmt).all()]


def list_chains(session: Session) -> list[ChainOut]:
    return [ChainOut.model_validate(c) for c in session.scalars(select(Chain).order_by(Chain.name))]
