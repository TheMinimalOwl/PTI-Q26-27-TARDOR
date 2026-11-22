"""Sincronització dels embeddings dels productes amb el servei d'IA (VM 1 → VM 2).

Els productes nous, o els que han canviat de nom, categoria o mida, queden amb
`embedding = NULL` (ho fa l'upsert d'ingest.py). Aquí es busquen, s'envia el seu text al
servei `/embed` de la VM 2 en lots i es guarda el vector que torna.

Si la VM 2 no respon, no es perd res: els productes continuen a NULL i s'omplen a la propera
sincronització. Per això la ingesta no depèn mai de la IA.

Contracte de `/embed` (POST, JSON):
    petició:  {"texts": ["...", ...], "kind": "passage"}
    resposta: {"embeddings": [[<embedding_dim floats>], ...]}   (mateix ordre que `texts`)
El prefix del model (amb e5, "passage: " / "query: ") el posa la VM 2 segons `kind`.

Executar (càrrega inicial o manual):
    python -m app.embeddings           # omple els que falten
    python -m app.embeddings --reset   # els torna a calcular tots (p. ex. si canvia el model)
"""
import argparse
import logging
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select, update

from .config import settings
from .db import SessionLocal
from .models import Product

log = logging.getLogger("embeddings")


def _size_label(size: str, size_format: str) -> str:
    """Mida llegible: `1 l`, `500 g`, `3 ud`. Igual que `Product.size_label` de flujo-ia."""
    if not size or size == "-":
        return ""
    base = size_format.strip()
    try:
        num = Decimal(size.replace(",", "."))
    except InvalidOperation:
        return f"{size} {base}".strip()
    s = f"{num:f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s} {base}".strip()


def embed_text(name: str, category: str, size: str, size_format: str) -> str:
    """Text que s'embeddeja d'un producte. És el mateix format que `Product.embed_text` de
    flujo-ia (amb què es va avaluar el model): nom, categoria i mida. El preu i la URL no hi
    van perquè no ajuden a trobar el producte i fan soroll al vector."""
    bits = [name]
    if category:
        bits.append(f"categoria {category}")
    if label := _size_label(size, size_format):
        bits.append(f"tamano {label}")
    return " | ".join(bits)


def _embed(client: httpx.Client, texts: list[str]) -> list[list[float]]:
    headers = {"X-API-Key": settings.embed_api_key} if settings.embed_api_key else {}
    res = client.post(settings.embed_url, json={"texts": texts, "kind": "passage"}, headers=headers)
    res.raise_for_status()
    vectors = res.json()["embeddings"]
    if len(vectors) != len(texts):
        raise ValueError(f"/embed ha tornat {len(vectors)} vectors per a {len(texts)} textos")
    for v in vectors:
        if len(v) != settings.embedding_dim:
            raise ValueError(
                f"/embed ha tornat vectors de {len(v)} dimensions i la BD n'espera "
                f"{settings.embedding_dim} (EMBEDDING_DIM)"
            )
    return vectors


def sync_embeddings(client: httpx.Client | None = None) -> int:
    """Calcula l'embedding de tots els productes que no en tenen. Retorna quants n'ha omplert.

    Cada lot es desa en una transacció pròpia: si falla a mig camí, el que ja s'ha fet queda
    fet. Si un producte canvia mentre la VM 2 calcula el seu vector, el vector (que és del
    text antic) no es desa i el producte es queda pendent per a la propera vegada."""
    if not settings.embed_url:
        log.info("EMBED_URL no configurada: no se sincronizan embeddings")
        return 0
    own_client = client is None
    client = client or httpx.Client(timeout=settings.embed_timeout)
    done, last_id = 0, 0
    try:
        while True:
            with SessionLocal() as session:
                rows = session.execute(
                    select(Product.id, Product.name, Product.category, Product.size, Product.size_format)
                    .where(Product.embedding.is_(None), Product.id > last_id)
                    .order_by(Product.id)
                    .limit(settings.embed_batch_size)
                ).all()
            if not rows:
                break
            last_id = rows[-1].id
            vectors = _embed(client, [embed_text(*r[1:]) for r in rows])

            with SessionLocal() as session, session.begin():
                for r, vector in zip(rows, vectors):
                    result = session.execute(
                        update(Product)
                        .where(
                            Product.id == r.id,
                            Product.embedding.is_(None),
                            Product.name == r.name,
                            Product.category == r.category,
                            Product.size == r.size,
                            Product.size_format == r.size_format,
                        )
                        .values(embedding=vector)
                    )
                    done += result.rowcount
            log.info("embeddings: %d productos actualizados", done)
    finally:
        if own_client:
            client.close()
    return done


def reset_embeddings() -> int:
    """Esborra tots els embeddings perquè es tornin a calcular."""
    with SessionLocal() as session, session.begin():
        return session.execute(update(Product).values(embedding=None)).rowcount


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Calcula los embeddings de los productos que no tienen")
    parser.add_argument("--reset", action="store_true", help="recalcularlos todos (p. ej. si cambia el modelo)")
    args = parser.parse_args()
    if not settings.embed_url:
        parser.error("falta EMBED_URL (p. ej. EMBED_URL=http://ip-vm2:8001/embed)")
    if args.reset:
        log.info("embeddings borrados: %d", reset_embeddings())
    log.info("listo: %d productos con embedding nuevo", sync_embeddings())
