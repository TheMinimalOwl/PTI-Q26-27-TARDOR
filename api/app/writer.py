"""Writer: NATS `scraper.*.clean` → PostgreSQL.

Consumidor durable `api-writer` en modo pull sobre el stream SCRAPERS. Cada mensaje se
confirma (ack) solo después del commit; si falla la BD se pide reentrega (nak). Como la
carga es idempotente, una reentrega no duplica datos.

Ejecutar:  python -m app.writer
"""
import asyncio
import logging

import nats
from nats.errors import TimeoutError as NatsTimeout

from .cache import cache
from .config import settings
from .db import SessionLocal, init_db
from .ingest import parse_message, upsert_batch

log = logging.getLogger("writer")

STREAM = "SCRAPERS"
SUBJECT = "scraper.*.clean"
DURABLE = "api-writer"


def _store(subject: str, data: bytes) -> dict[str, int]:
    batch = parse_message(subject, data)
    with SessionLocal() as session, session.begin():
        return upsert_batch(session, batch)


async def run() -> None:
    if settings.auto_create_schema:
        init_db()
    nc = await nats.connect(settings.nats_url)
    js = nc.jetstream()
    sub = await js.pull_subscribe(SUBJECT, durable=DURABLE, stream=STREAM)
    log.info("escuchando %s en %s", SUBJECT, settings.nats_url)

    while True:
        try:
            msgs = await sub.fetch(10, timeout=5)
        except NatsTimeout:
            continue
        for msg in msgs:
            try:
                stats = await asyncio.to_thread(_store, msg.subject, msg.data)
            except ValueError as exc:
                # Mensaje mal formado: reintentar no lo arreglará.
                log.error("descartado %s: %s", msg.subject, exc)
                await msg.term()
                continue
            except Exception:
                log.exception("error guardando %s, se reintentará", msg.subject)
                await msg.nak(delay=10)
                continue
            await msg.ack()
            cache.invalidate()
            log.info("%s: %s", msg.subject, stats)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())
