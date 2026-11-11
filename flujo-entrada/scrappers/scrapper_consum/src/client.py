"""Cliente HTTP de la API de la tienda online de Consum.

Es la misma API JSON que usa la web (tienda.consum.es). No hace falta sesion ni cookies.

El codigo postal decide que tienda reparte y, con ello, el surtido (los precios, en las
pruebas, no cambian entre zonas). La web lo resuelve asi, y aqui se hace igual:

1. `GET shipping/area?zipCode=08016` -> tienda que reparte en ese codigo postal
   (zona 378, `shippingZoneId` 378D).
2. Las peticiones al catalogo llevan las cabeceras `X-TOL-ZONE` y `X-TOL-SHIPPING-ZONE`.

Uso academico y sin animo de lucro: una pasada nocturna, peticiones de una en una y con
pausa entre ellas (SCRAPER_DELAY), y reintentos con espera creciente si algo falla.
"""
import os
import time

import requests

BASE = "https://tienda.consum.es/api/rest/V1.0"
PRODUCTS_URL = f"{BASE}/catalog/product"
AREA_URL = f"{BASE}/shipping/area"
TIMEOUT = 30
RETRIES = 3
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; academic-price-research)")

_session = requests.Session()
_session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "es-ES,es;q=0.9",
})


def _get_json(url: str, *, params: dict, headers: dict | None = None, what: str):
    """GET con reintentos. Si no hay manera, lanza la excepcion: el scraper tiene que
    fallar de forma visible, no devolver 0 productos."""
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = _session.get(url, params=params, headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            print(f"   {what} intento {attempt}/{RETRIES}: {e}", flush=True)
            if attempt < RETRIES:
                time.sleep(10 * attempt)
    raise RuntimeError(f"no he podido leer {what}: {last}")


def resolve_zone(postal_code: str) -> dict | None:
    """Tienda de Consum que reparte a domicilio en `postal_code`, o None si no hay.

    Devuelve {"zone_id", "shipping_zone_id", "store_code", "store_name", "city"}.
    Prefiere el reparto a domicilio (`deliveryTypeId` D); si no lo hay, la primera zona
    activa (recogida en tienda, etc.).
    """
    groups = _get_json(
        AREA_URL,
        params={"shippingMethod": "D,X,T,L", "showDisableStore": "false", "zipCode": postal_code},
        what=f"shipping/area {postal_code}",
    )
    areas = [a for g in groups or [] for a in g.get("shippingAreas") or [] if a.get("enabled", True)]
    if not areas:
        return None
    area = next((a for a in areas if a.get("deliveryTypeId") == "D"), areas[0])
    zone = area.get("zone") or {}
    return {
        "zone_id": str(zone.get("id")),
        "shipping_zone_id": str(area.get("shippingZoneId")),
        "store_code": str(zone.get("storeCode") or zone.get("id")),
        "store_name": zone.get("name", ""),
        "city": (zone.get("address") or {}).get("city", ""),
    }


def fetch_page(offset: int, limit: int, zone: dict) -> dict:
    """Una pagina del catalogo tal como lo ve un cliente de esa zona."""
    data = _get_json(
        PRODUCTS_URL,
        params={"limit": limit, "offset": offset},
        headers={"X-TOL-ZONE": zone["zone_id"], "X-TOL-SHIPPING-ZONE": zone["shipping_zone_id"]},
        what=f"offset={offset}",
    )
    if not isinstance(data, dict) or "products" not in data:
        raise RuntimeError(f"respuesta inesperada en offset={offset}: {str(data)[:200]}")
    return data
