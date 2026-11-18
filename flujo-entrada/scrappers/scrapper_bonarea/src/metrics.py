"""Metricas de cada pasada para Prometheus, a traves del Pushgateway.

Un Job dura unos minutos y Prometheus (que consulta cada 1 min) puede no verlo nunca, asi que
al publicar cada tienda se envian sus numeros al Pushgateway y Prometheus los lee de ahi. Es
un PUT por (cadena, tienda): sustituye los de la pasada anterior de esa tienda.

Si el Pushgateway no responde se avisa y se sigue: la monitorizacion nunca hace fallar al
scraper. PUSHGATEWAY_URL="" lo desactiva (pruebas en local).

Este fichero es igual en todos los scrapers (cada uno tiene su imagen).
"""
import base64
import os
import time
import urllib.request

PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "http://pushgateway.monitoring.svc.cluster.local:9091")
_START = time.time()  # arranque del Job


def _b64(v: str) -> str:
    # Valores de la clave de agrupacion en base64 (admite '/' y vacio).
    return base64.urlsafe_b64encode(v.encode()).decode() or "="


def push(chain: str, store: str, postal_code: str, scraped: int, published: int) -> None:
    if not PUSHGATEWAY_URL:
        return
    now = time.time()
    lbl = f'{{postal_code="{postal_code}"}}'
    body = "".join(f"# TYPE {name} gauge\n{name}{lbl} {value}\n" for name, value in [
        ("scraper_products_scraped", scraped),      # productos con id en la pasada
        ("scraper_products_published", published),  # los que han llegado a NATS
        ("scraper_publish_ok", int(published == scraped and scraped > 0)),
        ("scraper_job_elapsed_seconds", round(now - _START)),
        ("scraper_last_run_timestamp_seconds", round(now)),
    ])
    url = f"{PUSHGATEWAY_URL}/metrics/job/scraper/chain@base64/{_b64(chain)}/store@base64/{_b64(store)}"
    req = urllib.request.Request(url, data=body.encode(), method="PUT",
                                 headers={"Content-Type": "text/plain; version=0.0.4"})
    try:
        urllib.request.urlopen(req, timeout=5).close()
    except Exception as e:  # noqa: BLE001 - nunca rompe la pasada
        print(f"metrics: no he podido enviar al Pushgateway ({e})", flush=True)
