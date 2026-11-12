import json
import os
from datetime import datetime, timezone

STREAM = os.getenv("NATS_STREAM", "SCRAPERS")
NATS_URL = os.getenv("NATS_URL", "nats://nats.messaging.svc.cluster.local:4222")
DRY_RUN = os.getenv("NATS_DRY_RUN", "0") == "1"
SUBJECT = "scraper.bonarea.raw"


def build_envelope(product: dict, wh: str, postal_code: str) -> dict:
    return {
        "source": "bonarea",
        "wh": wh,  # tienda online de bonArea (un solo catalogo)
        "postal_code": postal_code,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "product_id": str(product.get("identifier", "-")),
        "product": product,
    }


async def _publish_async(envelopes: list[dict]) -> int:
    import nats

    nc = await nats.connect(NATS_URL, connect_timeout=5)
    try:
        js = nc.jetstream()
        for e in envelopes:
            await js.publish(SUBJECT, json.dumps(e, ensure_ascii=False).encode("utf-8"))
        return len(envelopes)
    finally:
        await nc.close()


def publish(items: list[dict], wh: str, postal_code: str) -> tuple[int, str]:
    envelopes = [build_envelope(p, wh, postal_code) for p in items if "identifier" in p]
    if DRY_RUN or not envelopes:
        return 0, f"dry-run ({len(envelopes)} pendientes)"
    import asyncio

    try:
        n = asyncio.run(_publish_async(envelopes))
        return n, f"{n} -> {SUBJECT}@{NATS_URL}"
    except Exception as e:
        return 0, f"ERROR NATS ({e}), txt intacto"
