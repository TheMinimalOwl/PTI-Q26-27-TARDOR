"""Puente NATS -> funcion `normalizer` de Fission -> NATS.

Lee los crudos de todas las cadenas (`scraper.<cadena>.raw`, via el consumidor durable
`normalizer`), los agrupa en lotes **por cadena y tienda** y publica cada lote limpio en
`scraper.<cadena>.clean`. La cadena sale del subject y la tienda va en `wh`: el writer de
API/BD los lee de ahi. Un lote nunca mezcla dos cadenas ni dos tiendas.
"""
import asyncio
import json
import os
import time
from datetime import datetime, timezone

# Para mensajes cuyo subject no siga scraper.<cadena>.raw (no deberia pasar).
SUBJECT_OUT_DEFAULT = os.getenv("NATS_SUBJECT_OUT", "scraper.mercadona.clean")
NATS_URL = os.getenv("NATS_URL", "nats://nats.messaging.svc.cluster.local:4222")
NORMALIZE_URL = os.getenv("NORMALIZE_URL", "http://router.fission/normalize")
BATCH = int(os.getenv("CONSUMER_BATCH", "50"))
DELIVER = os.getenv("NATS_DELIVER", "deliver.normalizer")
# Marca de vida para la livenessProbe: se toca cada 5 s mientras haya conexion con NATS.
# Si NATS cae, nats-py reintenta sin fin; si no vuelve en HEALTH_MAX s (consumer.yaml), la
# marca envejece y Kubernetes reinicia el pod. Si la conexion se cierra del todo, se sale.
HEALTH_FILE = os.getenv("HEALTH_FILE", "/tmp/healthy")
# Metricas para Prometheus en :METRICS_PORT/metrics (el pod lleva las anotaciones
# prometheus.io/scrape). METRICS_PORT=0 las desactiva.
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))


class Metrics:
    """Contadores por cadena. Sin prometheus_client (pruebas en local) no hacen nada."""

    def __init__(self, port: int):
        self.on = False
        if not port:
            return
        try:
            from prometheus_client import Counter, Gauge, Histogram, start_http_server
        except ImportError:
            return
        self.raw = Counter("normalizer_raw_messages", "Crudos recibidos de NATS", ["chain"])
        self.batches = Counter("normalizer_batches", "Lotes limpios publicados", ["chain"])
        self.products = Counter("normalizer_products", "Productos en los lotes publicados", ["chain"])
        self.clean_errors = Counter("normalizer_clean_errors", "Lineas ERROR en los lotes (no validan)", ["chain"])
        self.incomplete = Counter("normalizer_clean_incomplete", "Lineas sin precio por unidad", ["chain"])
        self.flush_errors = Counter("normalizer_flush_errors", "Lotes que no se han podido publicar")
        self.parse_errors = Counter("normalizer_parse_errors", "Crudos que no son JSON (se descartan)")
        self.connected = Gauge("normalizer_nats_connected", "1 si hay conexion con NATS")
        self.last_batch = Gauge("normalizer_last_batch_timestamp_seconds", "Ultimo lote publicado", ["chain"])
        self.seconds = Histogram("normalizer_clean_seconds", "Duracion de la llamada a la funcion de Fission",
                                 buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60))
        start_http_server(port)
        self.on = True

    def batch(self, chain: str, n: int, txt: str, seconds: float) -> None:
        if not self.on:
            return
        lines = txt.splitlines()
        self.batches.labels(chain).inc()
        self.products.labels(chain).inc(n)
        self.clean_errors.labels(chain).inc(sum(1 for l in lines if l.startswith("ERROR")))
        self.incomplete.labels(chain).inc(sum(1 for l in lines if " | - (" in l))
        self.last_batch.labels(chain).set_to_current_time()
        self.seconds.observe(seconds)


def chain_of(subject: str) -> str:
    """scraper.<cadena>.raw|clean -> <cadena>"""
    parts = subject.split(".")
    return parts[1] if len(parts) == 3 and parts[0] == "scraper" else "otra"


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
    metrics = Metrics(METRICS_PORT)
    closed = asyncio.Event()

    async def on_closed():
        closed.set()

    async def on_disconnected():
        print("nats-disconnected: reintentando", flush=True)

    async def on_reconnected():
        print("nats-reconnected", flush=True)

    # Reintentos sin fin: si NATS se reinicia, el consumer vuelve solo. Si aun asi la
    # conexion se cierra, el bucle de abajo sale con error y Kubernetes reinicia el pod.
    nc = await nats.connect(NATS_URL, max_reconnect_attempts=-1, reconnect_time_wait=2,
                            closed_cb=on_closed, disconnected_cb=on_disconnected,
                            reconnected_cb=on_reconnected)
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
        t0 = time.monotonic()
        txt = await asyncio.to_thread(clean, list(raws))
        took = time.monotonic() - t0
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
        metrics.batch(chain_of(out_subject), len(raws), txt, took)
        print(f"batch {len(raws)} wh={wh} cp={postal_code} -> {out_subject}", flush=True)

    async def handler(msg):
        try:
            envelope = json.loads(msg.data.decode("utf-8"))
        except Exception as e:
            print(f"parse-error: {e}", flush=True)
            if metrics.on:
                metrics.parse_errors.inc()
            await msg.ack()
            return
        if metrics.on:
            metrics.raw.labels(chain_of(msg.subject)).inc()
        key = batch_key(msg.subject, envelope)
        bufs.setdefault(key, []).append((msg, envelope))
        if len(bufs[key]) >= BATCH:
            try:
                await flush(key)
            except Exception as e:
                print(f"flush-error: {e} (reintentara por AckWait)", flush=True)
                if metrics.on:
                    metrics.flush_errors.inc()

    await nc.subscribe(DELIVER, cb=handler)
    print(f"listening {DELIVER} -> {NORMALIZE_URL or 'local'} -> scraper.<cadena>.clean", flush=True)
    try:
        while True:
            await asyncio.sleep(5)
            if closed.is_set() or nc.is_closed:
                raise SystemExit("ERROR: conexion con NATS cerrada; salgo para que Kubernetes me reinicie")
            if metrics.on:
                metrics.connected.set(1 if nc.is_connected else 0)
            if nc.is_connected:
                with open(HEALTH_FILE, "w") as f:
                    f.write(datetime.now(timezone.utc).isoformat())
            try:
                await flush()
            except Exception as e:
                print(f"flush-error: {e} (reintentara por AckWait)", flush=True)
                if metrics.on:
                    metrics.flush_errors.inc()
    finally:
        if not nc.is_closed:
            await nc.close()


if __name__ == "__main__":
    asyncio.run(run())
