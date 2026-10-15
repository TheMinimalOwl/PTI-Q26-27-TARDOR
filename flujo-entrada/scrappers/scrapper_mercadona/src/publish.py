import json
import os
from datetime import datetime, timezone

SUBJECT = os.getenv("NATS_SUBJECT", "mercadona.raw")
STREAM = os.getenv("NATS_STREAM", "SCRAPER")
NATS_URL = os.getenv("NATS_URL", "nats://nats.messaging.svc.cluster.local:4222")
DRY_RUN = os.getenv("NATS_DRY_RUN", "0") == "1"


def build_envelope(product: dict, wh: str = "default") -> dict:
    return {
        "source": "mercadona",
        "wh": wh,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "product_id": str(product.get("id", "-")),
        "product": product,
    }


async def _publish_async(envelopes: list[dict], url: str, stream: str, subject: str) -> int:
    import nats

    nc = await nats.connect(url, connect_timeout=5)
    try:
        js = nc.jetstream()
        try:
            await js.add_stream(name=stream, subjects=[subject])
        except Exception:
            pass
        for e in envelopes:
            await js.publish(subject, json.dumps(e, ensure_ascii=False).encode("utf-8"))
        return len(envelopes)
    finally:
        await nc.close()


def publish(items: list[dict], wh: str = "default") -> tuple[int, str]:
    real = [p for p in items if "id" in p]
    envelopes = [build_envelope(p, wh) for p in real]
    if DRY_RUN or not envelopes:
        return 0, f"dry-run ({len(envelopes)} pendientes)"
    import asyncio

    try:
        n = asyncio.run(_publish_async(envelopes, NATS_URL, STREAM, SUBJECT))
        return n, f"{n} -> {SUBJECT}@{NATS_URL}"
    except Exception as e:
        return 0, f"ERROR NATS ({e}), txt intacto"
