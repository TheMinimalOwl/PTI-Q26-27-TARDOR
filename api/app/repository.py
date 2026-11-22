"""Consultes a la BD. Els routers no escriuen SQL: només criden aquestes funcions."""
from datetime import date
from decimal import Decimal

from sqlalchemy import Integer, Numeric, Select, and_, case, cast, func, literal, select
from sqlalchemy.orm import Session, aliased, joinedload

from .models import Chain, Price, Product, Store
from .schemas import ChainOut, PriceOut, ProductDetail, ProductSummary, VectorHit


# Format de la mida de l'etiqueta → (unitat base, factor). La mateixa taula que la ingesta
# (flujo-entrada/docs/03-contratos-datos.md): 500 g = 500 × 0,001 = 0,5 kg.
SIZE_FORMATS = {
    "kg": ("kg", Decimal("1")),
    "g": ("kg", Decimal("0.001")),
    "100 g": ("kg", Decimal("0.1")),
    "l": ("l", Decimal("1")),
    "ml": ("l", Decimal("0.001")),
    "cl": ("l", Decimal("0.01")),
    "100 ml": ("l", Decimal("0.1")),
    "ud": ("ud", Decimal("1")),
    "u": ("ud", Decimal("1")),
    "ud.": ("ud", Decimal("1")),
    "dc": ("ud", Decimal("12")),
    "dz": ("ud", Decimal("12")),
    "m": ("m", Decimal("1")),
    "lv": ("lavado", Decimal("1")),
}


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


def _pack_size(latest, unit: str):
    """Mida d'un paquet en `unit` (expressió SQL).

    Primer la de l'etiqueta (`size` × factor de `size_format`), si és un número i el format
    és d'aquesta unitat. Si no, total ÷ preu unitari: és menys fiable perquè el preu unitari
    de la font de vegades no quadra (oferta, pes escorregut, packs…)."""
    factors = {fmt: f for fmt, (base, f) in SIZE_FORMATS.items() if base == unit}
    from_label = None
    if factors:
        factor = case(factors, value=func.lower(func.trim(Product.size_format)))
        number = cast(func.replace(Product.size, ",", "."), Numeric)
        from_label = case((Product.size.regexp_match(r"^[0-9]+([.,][0-9]+)?$"), number * factor))
    from_prices = latest.total / func.nullif(latest.unit_price, 0)
    if from_label is None:
        return from_prices
    return func.coalesce(func.nullif(from_label, 0), from_prices)


def _name_conditions(q: str) -> list:
    """Cada paraula de `q` ha de sortir al nom (sense distingir majúscules ni accents)."""
    return [
        func.unaccent(Product.name).ilike(func.unaccent(f"%{_escape_like(word)}%"), escape="\\")
        for word in q.split()
    ]


def _main_unit(session: Session, conditions: list) -> str | None:
    """La unitat més freqüent entre els productes que compleixen `conditions`."""
    return session.scalar(
        select(Product.unit)
        .join(Product.chain)
        .where(and_(*conditions), Product.unit.is_not(None))
        .group_by(Product.unit)
        .order_by(func.count().desc(), Product.unit)
        .limit(1)
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

    conditions = _name_conditions(q)
    if chain:
        conditions.append(Chain.slug == chain)
    if unit:
        conditions.append(Product.unit == unit)

    base = select(Product).join(Product.chain).where(and_(*conditions))
    total = session.scalar(select(func.count()).select_from(base.subquery()))

    main_unit = unit or _main_unit(session, conditions)
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


def search_by_vector(
    session: Session,
    embedding: list[float],
    top_k: int,
    chains: list[str] | None,
    unit: str | None,
    max_price: Decimal | None,
    max_unit_price: Decimal | None,
) -> list[VectorHit]:
    """Els `top_k` productes més semblants a `embedding` (distància cosinus de pgvector)
    que compleixen els filtres. Els preus són els més recents, no els de quan es va calcular
    l'embedding. Els productes sense embedding (pendents de la IA) no hi surten.

    Sense índex vectorial a propòsit: amb desenes de milers de productes la cerca exacta
    triga mil·lisegons, i un índex HNSW amb filtres de preu pot tornar menys de `top_k`."""
    latest = aliased(Price, _latest_prices().subquery())
    distance = Product.embedding.cosine_distance(embedding).label("distance")

    conditions = [Product.embedding.is_not(None)]
    if chains:
        conditions.append(Chain.slug.in_(chains))
    if unit:
        conditions.append(Product.unit == unit)
    if max_price is not None:
        conditions.append(latest.total <= max_price)
    if max_unit_price is not None:
        conditions.append(latest.unit_price <= max_unit_price)

    rows = session.execute(
        select(Product, latest, Store.code, distance)
        .join(Product.chain)
        .outerjoin(latest, latest.product_id == Product.id)
        .outerjoin(Store, Store.id == latest.store_id)
        .where(and_(*conditions))
        .options(joinedload(Product.chain))
        .order_by(distance, Product.id)
        .limit(top_k)
    ).all()

    return [
        VectorHit(**_summary(p, price, code), similarity=round(1 - float(d), 4))
        for p, price, code, d in rows
    ]


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


def cheapest_per_chain(
    session: Session,
    q: str,
    unit: str | None,
    chains: list[str] | None,
    amount: Decimal | None,
    quantity: int,
) -> tuple[str | None, list[tuple[ProductSummary, int, Decimal]]]:
    """Per a un article de la llista, el producte amb què surt més barat a cada cadena.

    Només compara productes de la unitat principal (`unit` o la més freqüent).
    - Amb `amount` (p. ej. 3 l): paquets = amount ÷ mida del paquet (`_pack_size`), arrodonit
      cap amunt. Es tria el de menor cost = paquets × preu del paquet.
    - Sense `amount`: paquets = `quantity` i es tria el paquet més barat.
    A igualtat de cost, el de menor preu unitari. Els productes sense preu no compten.
    Retorna la unitat i, per cadena, (producte, paquets, cost)."""
    latest = aliased(Price, _latest_prices().subquery())

    conditions = _name_conditions(q)
    if chains:
        conditions.append(Chain.slug.in_(chains))
    main_unit = unit or _main_unit(session, conditions)
    if main_unit is None:
        return None, []
    conditions.append(Product.unit == main_unit)
    conditions.append(latest.total > 0)

    if amount is not None:
        # amount ÷ mida pot donar 3,003 en lloc de 3 (mides com 333 g, o la mida calculada
        # amb un preu unitari arrodonit): s'arrodoneix a 2 decimals abans del ceil.
        size = _pack_size(latest, main_unit)
        conditions.append(size > 0)
        packs = func.ceil(func.round(literal(amount, Numeric) / size, 2))
    else:
        packs = literal(quantity)
    packs = cast(packs, Integer).label("packs")
    cost = (latest.total * packs).label("cost")

    rows = session.execute(
        select(Product, latest, Store.code, packs, cost)
        .join(Product.chain)
        .join(latest, latest.product_id == Product.id)
        .join(Store, Store.id == latest.store_id)
        .where(and_(*conditions))
        .options(joinedload(Product.chain))
        .distinct(Product.chain_id)
        .order_by(Product.chain_id, cost, latest.unit_price.asc().nulls_last(), Product.id)
    ).all()

    return main_unit, [
        (ProductSummary(**_summary(p, price, code)), n, c) for p, price, code, n, c in rows
    ]
