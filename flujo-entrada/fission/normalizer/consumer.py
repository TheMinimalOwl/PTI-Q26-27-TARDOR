import asyncio
import json
import os
from datetime import datetime, timezone

SUBJECT_IN = os.getenv("NATS_SUBJECT_IN", "scraper.mercadona.raw")
SUBJECT_OUT = os.getenv("NATS_SUBJECT_OUT", "scraper.mercadona.clean")
NATS_URL = os.getenv("NATS_URL", "nats://nats.messaging.svc.cluster.local:4222")
NORMALIZE_URL = os.getenv("NORMALIZE_URL", "http://router.fission/normalize")
BATCH = int(os.getenv("CONSUMER_BATCH", "50"))
DELIVER = os.getenv("NATS_DELIVER", "deliver.normalizer")


def clean_local(products: list[dict]) -> str:
    from normalizer import to_clean_txt

    return to_clean_txt(products)


def clean_remote(products: list[dict]) -> str:
    import urllib.request

    body = json.dumps({"items": products}).encode("utf-8")
    req = urllib.request.Request(NORMALIZE_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


async def run() -> None:
    import nats

    clean = clean_remote if NORMALIZE_URL else clean_local
    nc = await nats.connect(NATS_URL)
    js = nc.jetstream()
    buf: list[tuple] = []

    async def flush():
        if not buf:
            return
        msgs, products = zip(*buf)
        wh = (products[0].get("wh") if isinstance(products[0], dict) else "default") or "default"
        raws = [p.get("product", p) for p in products]
        txt = await asyncio.to_thread(clean, list(raws))
        out = {
            "source": "normalizer",
            "wh": wh,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "batch": len(raws),
            "clean": txt,
        }
        await js.publish(SUBJECT_OUT, json.dumps(out, ensure_ascii=False).encode("utf-8"))
        for m in msgs:
            await m.ack()
        buf.clear()
        print(f"batch {len(raws)} -> {SUBJECT_OUT}", flush=True)

    async def handler(msg):
        try:
            buf.append((msg, json.loads(msg.data.decode("utf-8"))))
        except Exception as e:
            print(f"parse-error: {e}", flush=True)
            await msg.ack()
            return
        if len(buf) >= BATCH:
            try:
                await flush()
            except Exception as e:
                print(f"flush-error: {e} (reintentara por AckWait)", flush=True)

    await nc.subscribe(DELIVER, cb=handler)
    print(f"listening {DELIVER} -> {NORMALIZE_URL or 'local'} -> {SUBJECT_OUT}", flush=True)
    try:
        while True:
            await asyncio.sleep(5)
            try:
                await flush()
            except Exception as e:
                print(f"flush-error: {e} (reintentara por AckWait)", flush=True)
    finally:
        await nc.close()


if __name__ == "__main__":
    asyncio.run(run())
