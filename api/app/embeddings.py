"""Embeddings dels productes amb el servei d'IA (flujo-ia, VM 2): client de `POST /embed`
i sincronització de `products.embedding`.

Els productes nous, o els que han canviat de nom, categoria o mida, queden amb
`embedding = NULL` (ho fa l'upsert d'ingest.py). `sync_embeddings` els busca, envia el seu
text a `/embed` amb `kind: "passage"` i desa el vector. El writer la crida just després de
cada ingesta (quan la cua de NATS queda buida), i no dins de l'upsert: així una VM 2 caiguda
mai bloqueja la ingesta. Si falla, els productes continuen a NULL i s'omplen més tard.

Contracte de `/embed` (vegeu docs/CONTRATO.md):
    POST {RAG_EMBED_URL}/embed      capçalera X-API-Key: {RAG_EMBED_API_KEY}
    {"texts": ["...", ...], "kind": "passage" | "query"}
    → 200 {"embeddings": [[384 floats amb norma 1], ...]}   (mateix ordre que `texts`)
    400 cos invàlid · 401 clau incorrecta · 413 >256 textos o text >2000 caràcters
    503 el servei no té la clau configurada (no té sentit reintentar)
Els prefixos del model ("passage: " / "query: ") els posa el servei.

Executar (càrrega inicial o manual):
    python -m app.embeddings           # omple els que falten
    python -m app.embeddings --reset   # els torna a calcular tots (p. ej. si canvia el model)
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

MAX_BATCH = 256       # textos per petició que accepta /embed
MAX_TEXT_CHARS = 2000  # caràcters per text que accepta /embed


class EmbedError(RuntimeError):
    """El servei d'embeddings ha fallat (no respon, clau incorrecta, resposta estranya…)."""


class EmbedUnavailable(EmbedError):
    """503: el servei no té la clau configurada. Cal avisar l'equip d'IA; no té sentit reintentar."""


def enabled() -> bool:
    return bool(settings.rag_embed_url)


def _new_client() -> httpx.Client:
    return httpx.Client(timeout=settings.embed_timeout)


def _check(res: httpx.Response) -> None:
    """Converteix els errors de /embed en missatges clars (sense mostrar mai la clau)."""
    if res.status_code == 200:
        return
    detail = res.text[:200]
    if res.status_code == 401:
        raise EmbedError("/embed: 401, falta la clave o es incorrecta (revisad RAG_EMBED_API_KEY)")
    if res.status_code == 413:
        raise EmbedError(f"/embed: 413, lote de más de {MAX_BATCH} textos o texto de más de "
                         f"{MAX_TEXT_CHARS} caracteres ({detail})")
    if res.status_code == 503:
        raise EmbedUnavailable("/embed: 503, el servicio de IA no tiene la clave configurada: "
                               "avisad al equipo de IA")
    raise EmbedError(f"/embed: {res.status_code} ({detail})")


def embed_texts(texts: list[str], kind: str = "passage", client: httpx.Client | None = None) -> list[list[float]]:
    """Vectors de `texts` (mateix ordre), en lots de `embed_batch_size` (256 com a màxim).

    `kind`: "passage" per als productes i "query" per al que escriu l'usuari."""
    if not enabled():
        raise EmbedError("RAG_EMBED_URL no configurada")
    if not texts:
        return []
    url = settings.rag_embed_url.rstrip("/") + "/embed"
    headers = {"X-API-Key": settings.rag_embed_api_key} if settings.rag_embed_api_key else {}
    size = max(1, min(settings.embed_batch_size, MAX_BATCH))
    own_client = client is None
    client = client or _new_client()
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), size):
            chunk = [t[:MAX_TEXT_CHARS] for t in texts[i:i + size]]
            try:
                res = client.post(url, json={"texts": chunk, "kind": kind}, headers=headers)
            except httpx.HTTPError as exc:
                raise EmbedError(f"/embed no responde ({type(exc).__name__}: {exc})") from exc
            _check(res)
            got = res.json().get("embeddings")
            if not isinstance(got, list) or len(got) != len(chunk):
                raise EmbedError(f"/embed ha devuelto {len(got or [])} vectores para {len(chunk)} textos")
            for v in got:
                if len(v) != settings.embedding_dim:
                    raise EmbedError(
                        f"/embed ha devuelto vectores de {len(v)} dimensiones y la BD espera "
                        f"{settings.embedding_dim} (EMBEDDING_DIM)"
                    )
            vectors.extend(got)
    finally:
        if own_client:
            client.close()
    return vectors


def embed_query(text: str, client: httpx.Client | None = None) -> list[float]:
    """Vector d'una consulta de l'usuari (`kind: "query"`)."""
    return embed_texts([text], kind="query", client=client)[0]


# ---------------------------------------------------------------- text dels productes

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


# ---------------------------------------------------------------- sincronització

def sync_embeddings(client: httpx.Client | None = None) -> int:
    """Calcula l'embedding de tots els productes que no en tenen. Retorna quants n'ha omplert.

    Cada lot es desa en una transacció pròpia: si falla a mig camí, el que ja s'ha fet queda
    fet. Si un producte canvia mentre la VM 2 calcula el seu vector, el vector (que és del
    text antic) no es desa i el producte es queda pendent per a la propera vegada."""
    if not enabled():
        log.info("RAG_EMBED_URL no configurada: no se sincronizan embeddings")
        return 0
    own_client = client is None
    client = client or _new_client()
    size = max(1, min(settings.embed_batch_size, MAX_BATCH))
    done, last_id = 0, 0
    try:
        while True:
            with SessionLocal() as session:
                rows = session.execute(
                    select(Product.id, Product.name, Product.category, Product.size, Product.size_format)
                    .where(Product.embedding.is_(None), Product.id > last_id)
                    .order_by(Product.id)
                    .limit(size)
                ).all()
            if not rows:
                break
            last_id = rows[-1].id
            vectors = embed_texts([embed_text(*r[1:]) for r in rows], kind="passage", client=client)

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
    if not enabled():
        parser.error("falta RAG_EMBED_URL (p. ej. RAG_EMBED_URL=http://10.4.41.108:8080)")
    if args.reset:
        log.info("embeddings borrados: %d", reset_embeddings())
    try:
        log.info("listo: %d productos con embedding nuevo", sync_embeddings())
    except EmbedError as exc:
        raise SystemExit(f"error: {exc}")
