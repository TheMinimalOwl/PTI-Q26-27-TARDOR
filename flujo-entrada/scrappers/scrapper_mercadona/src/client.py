"""Peticiones a la API de la tienda de Mercadona, con reintentos.

Cada peticion se reintenta (RETRIES veces, con espera creciente) si no hay respuesta (DNS,
conexion, timeout) o si la respuesta es 429 o 5xx: son fallos pasajeros. Un 4xx distinto de
429 no se reintenta. Cada fallo se escribe en el log del pod con su motivo.

Antes no habia reintentos y `resolve_wh` devolvia None en silencio: un fallo pasajero del
PUT de cambio de codigo postal a las 02:00 bastaba para que el Job acabara en ~2 s sin datos
y sin decir por que (noches del 15, 16, 19, 21 y 22/11/2026).
"""
import os
import time

import requests

TIMEOUT = 15
RETRIES = int(os.getenv("SCRAPER_RETRIES", "4"))
BACKOFF = float(os.getenv("SCRAPER_BACKOFF", "5"))  # s; espera BACKOFF * 2^(intento-1)
# USER_AGENT viene del Secret scraper-secrets (lo monta cronjob.yaml).
HEADERS = {"User-Agent": os.getenv("USER_AGENT", "Mozilla/5.0")}
CHANGE_PC_URL = "https://tienda.mercadona.es/api/postal-codes/actions/change-pc/"


def _transient(status: int | None) -> bool:
    return status is None or status == 429 or status >= 500


def _request(what: str, method: str, url: str, **kw) -> tuple[int | None, requests.Response | None]:
    """(status, respuesta) del ultimo intento; status None si no hubo respuesta."""
    status: int | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.request(method, url, headers=HEADERS, timeout=TIMEOUT, **kw)
            status, reason = r.status_code, f"status {r.status_code}"
            if not _transient(status):
                return status, r
        except requests.RequestException as e:
            r, status, reason = None, None, f"{type(e).__name__}: {e}"
        print(f"   {what}: intento {attempt}/{RETRIES} fallido ({reason})", flush=True)
        if attempt < RETRIES:
            time.sleep(BACKOFF * 2 ** (attempt - 1))
    return status, r


def fetch_json(url: str, params: dict | None = None) -> tuple[int | None, dict]:
    status, r = _request(url.removeprefix("https://tienda.mercadona.es"), "GET", url, params=params)
    if status != 200 or r is None:
        return status, {}
    try:
        data = r.json()
    except ValueError:
        print(f"   {url}: respuesta 200 que no es JSON", flush=True)
        return None, {}
    return status, data if isinstance(data, dict) else {}


def resolve_wh(postal_code: str) -> str | None:
    """Almacen de Mercadona que sirve `postal_code` (p. ej. 08016 -> bcn1), o None.

    Es lo que hace la web al escribir el codigo postal: la respuesta trae el almacen en la
    cabecera `x-customer-wh`. Despues el catalogo se pide con `?wh=<almacen>`.
    """
    status, r = _request(f"change-pc {postal_code}", "PUT", CHANGE_PC_URL,
                         json={"new_postal_code": postal_code})
    if status != 200 or r is None:
        print(f"   {postal_code}: change-pc sin exito (status {status})", flush=True)
        return None
    wh = r.headers.get("x-customer-wh")
    if not wh:
        print(f"   {postal_code}: change-pc 200 sin cabecera x-customer-wh", flush=True)
    return wh or None
