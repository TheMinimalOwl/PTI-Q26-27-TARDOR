"""Writer: NATS `scraper.*.clean` → PostgreSQL.

Consumidor durable `api-writer` en mode pull sobre el stream SCRAPERS. Cada missatge es
confirma (ack) només després del commit; si falla la BD, se'n demana el reenviament (nak).
Com que la càrrega és idempotent, un reenviament no duplica dades.

Quan no queden missatges per processar, demana a la IA (VM 2) els embeddings dels productes
nous o canviats (embeddings.sync_embeddings). Es fa fora del bucle de missatges perquè una VM 2
lenta o caiguda no bloquegi mai la ingesta; si falla, es torna a provar més tard.

Executar:  python -m app.writer
"""
import asyncio
import logging
import time

import nats
from nats.errors import TimeoutError as NatsTimeout

from .cache import cache
from .config import settings
from .db import SessionLocal, init_db
from .embeddings import sync_embeddings
from .ingest import parse_message, upsert_batch

log = logging.getLogger("writer")

STREAM = "SCRAPERS"
SUBJECT = "scraper.*.clean"
DURABLE = "api-writer"
SYNC_RETRY = 600  # segons fins a tornar a provar si la VM 2 no respon


def _store(subject: str, data: bytes) -> dict[str, int]:
    batch = parse_message(subject, data)
    with SessionLocal() as session, session.begin():
        return upsert_batch(session, batch)


async def _sync() -> float | None:
    """Sincronitza els embeddings. Retorna quan s'ha de tornar a provar (None = no cal)."""
    try:
        n = await asyncio.to_thread(sync_embeddings)
    except Exception as exc:
        log.warning("embeddings: la IA no responde (%s), se reintentará en %d s", exc, SYNC_RETRY)
        return time.monotonic() + SYNC_RETRY
    if n:
        log.info("embeddings: %d productos con embedding nuevo", n)
    return None


async def run() -> None:
    if settings.auto_create_schema:
        init_db()
    nc = await nats.connect(settings.nats_url)
    js = nc.jetstream()
    sub = await js.pull_subscribe(SUBJECT, durable=DURABLE, stream=STREAM)
    log.info("escuchando %s en %s", SUBJECT, settings.nats_url)

    sync_at: float | None = 0.0  # quan toca sincronitzar embeddings (None = res pendent)
    while True:
        try:
            msgs = await sub.fetch(10, timeout=5)
        except NatsTimeout:
            # Cua buida: és el moment de calcular embeddings (també en arrencar).
            if sync_at is not None and time.monotonic() >= sync_at:
                sync_at = await _sync()
            continue
        for msg in msgs:
            try:
                stats = await asyncio.to_thread(_store, msg.subject, msg.data)
            except ValueError as exc:
                # Missatge mal format: reintentar-ho no ho arreglarà.
                log.error("descartado %s: %s", msg.subject, exc)
                await msg.term()
                continue
            except Exception:
                log.exception("error guardando %s, se reintentará", msg.subject)
                await msg.nak(delay=10)
                continue
            await msg.ack()
            cache.invalidate()
            if sync_at is None:
                sync_at = 0.0
            log.info("%s: %s", msg.subject, stats)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())
