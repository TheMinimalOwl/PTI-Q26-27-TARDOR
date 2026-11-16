"""Llista de la compra optimitzada.

Per a cada article es busca el producte més barat de cada cadena (repository.cheapest_per_chain).
Amb això es calculen dues coses:
- la cistella sencera a cada cadena (anar a un sol supermercat);
- la cistella combinada: cada article a la cadena on surt més barat.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from . import repository
from .schemas import Basket, ChainBasket, ChainOut, ListLine, OptimizedList, ShoppingListIn


def _line(q: str, quantity: int, product) -> ListLine:
    return ListLine(q=q, quantity=quantity, product=product, subtotal=product.price.total * quantity)


def _basket(lines: list[ListLine], missing: list[str]) -> dict:
    return dict(total=sum((l.subtotal for l in lines), Decimal(0)), found=len(lines), missing=missing, lines=lines)


def optimize(session: Session, body: ShoppingListIn) -> OptimizedList:
    chains = {c.slug: c for c in repository.list_chains(session)}
    if body.chains:
        chains = {slug: c for slug, c in chains.items() if slug in body.chains}

    per_chain: dict[str, list[ListLine]] = {slug: [] for slug in chains}
    combined: list[ListLine] = []
    combined_missing: list[str] = []

    for item in body.items:
        q = " ".join(item.q.lower().split())
        _, products = repository.cheapest_per_chain(session, q, item.unit, list(chains))
        for product in products:
            per_chain[product.chain.slug].append(_line(q, item.quantity, product))
        if products:
            best = min(products, key=lambda p: (p.price.total, p.chain.slug))
            combined.append(_line(q, item.quantity, best))
        else:
            combined_missing.append(q)

    queries = [" ".join(i.q.lower().split()) for i in body.items]
    baskets = []
    for slug, lines in per_chain.items():
        found = {l.q for l in lines}
        missing = [q for q in queries if q not in found]
        baskets.append(ChainBasket(chain=ChainOut.model_validate(chains[slug]), **_basket(lines, missing)))
    baskets.sort(key=lambda b: (-b.found, b.total, b.chain.slug))

    combined_basket = Basket(**_basket(combined, combined_missing))
    best = baskets[0] if baskets and baskets[0].found else None
    savings = None
    if best is not None and best.found == combined_basket.found:
        savings = best.total - combined_basket.total

    return OptimizedList(
        baskets=baskets,
        best_chain=best.chain.slug if best else None,
        combined=combined_basket,
        savings=savings,
    )
