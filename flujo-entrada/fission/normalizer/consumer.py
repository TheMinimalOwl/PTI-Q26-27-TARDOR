"""Puente NATS -> funcion `normalizer` de Fission -> NATS.

Lee los crudos de todas las cadenas (`scraper.<cadena>.raw`, via el consumidor durable
`normalizer`), los agrupa en lotes **por cadena y tienda** y publica cada lote limpio en
`scraper.<cadena>.clean`. La cadena sale del subject y la tienda va en `wh`: el writer de
API/BD los lee de ahi. Un lote nunca mezcla dos cadenas ni dos tiendas.
"""
import asyncio
import json
import os
from datetime import datetime, timezone

# Para mensajes cuyo subject no siga scraper.<cadena>.raw (no deberia pasar).
SUBJECT_OUT_DEFAULT = os.getenv("NATS_SUBJECT_OUT", "scraper.mercadona.clean")
NATS_URL = os.getenv("NATS_URL", "nats://nats.messaging.svc.cluster.local:4222")
NORMALIZE_URL = os.getenv("NORMALIZE_URL", "http://router.fission/normalize")
BATCH = int(os.getenv("CONSUMER_BATCH", "50"))
DELIVER = os.getenv("NATS_DELIVER", "deliver.normalizer")


def subject_out(subject_in: str) -> str:
    """scraper.<cadena>.raw -> scraper.<cadena>.clean"""
    parts = subject_in.split(".")
    if len(parts) == 3 and parts[0] == "scraper" and parts[2] == "raw":
        return f"scraper.{parts[1]}.clean"
    return SUBJECT_OUT_DEFAULT


def batch_key(subject_in: str, envelope) -> tuple[str, str, str]:
    """(subject de salida, tienda, codigo postal): lo que define un lote."""
    env = envelope if isinstance(envelope, dict) else {}
    return subject_out(subject_in), str(env.get("wh") or "default"), str(env.get("postal_code") or "")


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
    bufs: dict[tuple[str, str, str], list[tuple]] = {}
    lock = asyncio.Lock()  # flush() se llama desde el handler Y desde el bucle de 5 s: sin
                           # el lock, dos flushes solapan y publican el mismo lote dos veces

    async def flush(only: tuple[str, str, str] | None = None):
        async with lock:
            for key in [only] if only else list(bufs):
                await flush_one(key)

    async def flush_one(key: tuple[str, str, str]):
        buf = bufs.get(key)
        if not buf:
            return
        out_subject, wh, postal_code = key
        msgs, envelopes = zip(*buf)
        # Se drena antes de los await: lo que llegue mientras se publica forma otro lote.
        # Si el publish falla, esos mensajes se quedan sin ack -> los reentrega AckWait.
        buf.clear()
        raws = [e.get("product", e) if isinstance(e, dict) else e for e in envelopes]
        txt = await asyncio.to_thread(clean, list(raws))
        out = {
            "source": "normalizer",
            "wh": wh,
            "postal_code": postal_code,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "batch": len(raws),
            "clean": txt,
        }
        await js.publish(out_subject, json.dumps(out, ensure_ascii=False).encode("utf-8"))
        for m in msgs:
            await m.ack()
        print(f"batch {len(raws)} wh={wh} cp={postal_code} -> {out_subject}", flush=True)

    async def handler(msg):
        try:
            envelope = json.loads(msg.data.decode("utf-8"))
        except Exception as e:
            print(f"parse-error: {e}", flush=True)
            await msg.ack()
            return
        key = batch_key(msg.subject, envelope)
        bufs.setdefault(key, []).append((msg, envelope))
        if len(bufs[key]) >= BATCH:
            try:
                await flush(key)
            except Exception as e:
                print(f"flush-error: {e} (reintentara por AckWait)", flush=True)

    await nc.subscribe(DELIVER, cb=handler)
    print(f"listening {DELIVER} -> {NORMALIZE_URL or 'local'} -> scraper.<cadena>.clean", flush=True)
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
