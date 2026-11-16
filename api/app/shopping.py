"""Llista de la compra optimitzada.

Per a cada article es busca, a cada cadena, el producte amb què surt més barat
(repository.cheapest_per_chain). Si l'article diu quina quantitat es vol (`amount`), totes
les cadenes es comparen per aquesta mateixa quantitat. Amb això es calculen dues coses:
- la cistella sencera a cada cadena (anar a un sol supermercat);
- la cistella combinada: cada article a la cadena on surt més barat.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from . import repository
from .schemas import Basket, ChainBasket, ChainOut, ListLine, OptimizedList, ShoppingListIn


def _line(q: str, amount: Decimal | None, product, packs: int, cost: Decimal) -> ListLine:
    return ListLine(q=q, amount=amount, packs=packs, product=product, subtotal=cost)


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
        _, options = repository.cheapest_per_chain(
            session, q, item.unit, list(chains), item.amount, item.quantity
        )
        lines = [_line(q, item.amount, product, packs, cost) for product, packs, cost in options]
        for line in lines:
            per_chain[line.product.chain.slug].append(line)
        if lines:
            combined.append(min(lines, key=lambda l: (l.subtotal, l.product.chain.slug)))
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
        best_chain=best.chain.slug if best else None,
        best_total=best.total if best else None,
        combined_total=combined_basket.total,
        savings=savings,
        combined=combined_basket,
        baskets=baskets,
    )
