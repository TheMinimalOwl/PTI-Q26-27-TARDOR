"""Dades de DEMO per provar l'API i l'app sense dependre dels scrapers.

Reprodueix els exemples de la presentació (cistella de 4 productes = 30,79 €) i un historial
mensual de l'oli d'oliva verge extra 1 L des del 2023. Els ids porten el prefix
`demo-` per no xocar amb els reals. Es pot executar diverses vegades (upsert).

Executar:  python -m app.seed
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from .cache import cache
from .db import SessionLocal, init_db
from .ingest import Batch, NormalizedItem, upsert_batch

CHAINS = ["mercadona", "carrefour", "alcampo", "ahorramas"]

# id, nom, categoria, mida, unitat, preu total per cadena (mateix ordre que CHAINS)
CATALOG = [
    ("aceite-ove-1l", "Aceite de oliva virgen extra 1 L", "Aceite, especias y salsas", "1", "l",
     ["4.85", "4.99", "4.79", "4.95"]),
    ("aceite-oliva-5l", "Aceite de oliva 0,4º garrafa 5 L", "Aceite, especias y salsas", "5", "l",
     ["17.25", "19.90", "18.95", "19.50"]),
    ("leche-entera-6x1l", "Leche entera pack 6 x 1 L", "Huevos, leche y mantequilla", "6", "l",
     ["5.70", "5.58", "5.34", "5.64"]),
    ("pechuga-pollo-1kg", "Pechuga de pollo fileteada 1 kg", "Carne", "1", "kg",
     ["7.20", "6.95", "7.45", "7.10"]),
    ("arroz-redondo-1kg", "Arroz redondo 1 kg", "Arroz, legumbres y pasta", "1", "kg",
     ["1.35", "1.39", "1.29", "1.25"]),
    ("macarrones-500g", "Macarrones 500 g", "Arroz, legumbres y pasta", "0.5", "kg",
     ["0.80", "0.85", "0.78", "0.82"]),
    ("huevos-l-12", "Huevos frescos L 12 unidades", "Huevos, leche y mantequilla", "12", "ud",
     ["2.70", "2.85", "2.65", "2.79"]),
    # Surt cercant "aceite" però en €/ud: no ha de passar per davant dels olis en €/l.
    ("atun-aceite-3", "Atún claro en aceite de oliva pack 3 x 80 g", "Conservas", "3", "ud",
     ["3.10", "2.95", "3.05", "3.20"]),
]

Q = Decimal("0.0001")


def _item(pid, name, cat, size, unit, total: Decimal) -> NormalizedItem:
    return NormalizedItem(
        id=f"demo-{pid}", name=name, category=cat, size=size, size_format=unit, unit=unit,
        total=total.quantize(Decimal("0.01")), unit_price=(total / Decimal(size)).quantize(Q),
        unit_src="calculado", url="",
    )


def _oil_history(current: Decimal) -> list[tuple[date, Decimal]]:
    """Pujada de 3,99 € a 9,90 € (gen 2023 → set 2024, +148 %) i baixada fins a `current`."""
    points = []
    for i in range(46):  # gen 2023 → oct 2026
        day = date(2023 + i // 12, i % 12 + 1, 15)
        if i <= 20:
            value = 3.99 + (9.90 - 3.99) * (i / 20) ** 1.3
        elif i <= 30:
            value = 9.90 - (9.90 - float(current)) * ((i - 20) / 10)
        else:
            value = float(current)
        points.append((day, Decimal(str(round(value, 2)))))
    return points


def seed() -> None:
    init_db()
    today = datetime.now(timezone.utc).replace(hour=2, minute=0, second=0, microsecond=0)
    with SessionLocal() as session, session.begin():
        for c, chain in enumerate(CHAINS):
            # Preu d'avui de tot el catàleg
            items = [_item(pid, n, cat, s, u, Decimal(prices[c])) for pid, n, cat, s, u, prices in CATALOG]
            upsert_batch(session, Batch(chain=chain, ts=today, items=items))

            # Historial de l'oli 1 L (lleugerament diferent per cadena)
            pid, n, cat, s, u, prices = CATALOG[0]
            factor = Decimal(prices[c]) / Decimal(prices[0])
            for day, value in _oil_history(Decimal(prices[0]))[:-1]:
                ts = datetime(day.year, day.month, day.day, 2, tzinfo=timezone.utc)
                upsert_batch(session, Batch(chain=chain, ts=ts, items=[_item(pid, n, cat, s, u, value * factor)]))
    cache.invalidate()
    print(f"Demo cargada: {len(CHAINS)} cadenas, {len(CATALOG) * len(CHAINS)} productos.")


if __name__ == "__main__":
    seed()
