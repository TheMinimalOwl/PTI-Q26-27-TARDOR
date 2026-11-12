import json
import os
from datetime import datetime, timezone

SUBJECT = os.getenv("NATS_SUBJECT", "scraper.consum.raw")
STREAM = os.getenv("NATS_STREAM", "SCRAPERS")
NATS_URL = os.getenv("NATS_URL", "nats://nats.messaging.svc.cluster.local:4222")
DRY_RUN = os.getenv("NATS_DRY_RUN", "0") == "1"


def build_envelope(product: dict, wh: str = "default", postal_code: str = "") -> dict:
    return {
        "source": "consum",
        "wh": wh,  # codigo de la tienda de Consum que reparte en postal_code
        "postal_code": postal_code,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # `code` es el id publico del producto (el de la URL de la tienda); `id` es interno.
        "product_id": str(product.get("code") or product.get("id", "-")),
        "product": product,
    }


async def _publish_async(envelopes: list[dict], url: str, stream: str, subject: str) -> int:
    import nats

    nc = await nats.connect(url, connect_timeout=5)
    try:
        js = nc.jetstream()
        # El stream lo declara Terraform (scraper.>, 7 dias); si no existe, publish falla y
        # el Job tambien. No se crea aqui: con un solo subject y sin retencion chocaria con el.
        for e in envelopes:
            await js.publish(subject, json.dumps(e, ensure_ascii=False).encode("utf-8"))
        return len(envelopes)
    finally:
        await nc.close()


def publish(items: list[dict], wh: str = "default", postal_code: str = "") -> tuple[int, str]:
    real = [p for p in items if "id" in p]
    envelopes = [build_envelope(p, wh, postal_code) for p in real]
    if DRY_RUN or not envelopes:
        return 0, f"dry-run ({len(envelopes)} pendientes)"
    import asyncio

    try:
        n = asyncio.run(_publish_async(envelopes, NATS_URL, STREAM, SUBJECT))
        return n, f"{n} -> {SUBJECT}@{NATS_URL}"
    except Exception as e:
        return 0, f"ERROR NATS ({e}), txt intacto"
