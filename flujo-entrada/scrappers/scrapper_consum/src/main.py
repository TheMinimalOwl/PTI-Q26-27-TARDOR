"""Scraper de Consum: recorre el catalogo de la tienda que reparte en cada codigo postal y
publica cada producto crudo en NATS.

No normaliza nada (eso lo hace el normalizador de Fission): publica el objeto tal cual lo
da la API en `scraper.consum.raw` y deja un volcado txt de depuracion en out/.

Codigos postales: SCRAPER_POSTAL_CODES (lista separada por comas). Mas adelante los dara la
API (los de los usuarios de la app); mientras tanto, 08016 de ejemplo. Varios codigos que
caen en la misma tienda se recorren una sola vez.

Cada envelope lleva `wh` = codigo de la tienda de Consum (p. ej. "378") y `postal_code`.

Sale con codigo != 0 si una tienda no da productos o si no se pueden publicar, para que el
Job quede como fallido y se vea.

Variables:
  SCRAPER_POSTAL_CODES (08016)  codigos postales, separados por comas
  SCRAPER_DELAY (5)   segundos entre peticiones (el catalogo son ~90 paginas por tienda)
  SCRAPER_LIMIT (100) productos por pagina (el maximo que acepta la API)
  NATS_URL, NATS_SUBJECT, NATS_STREAM, NATS_DRY_RUN
"""
import os
import sys
import time
from pathlib import Path

from client import PRODUCTS_URL, fetch_page, resolve_zone
from dump_txt import dump
from publish import publish

POSTAL_CODES = [c.strip() for c in os.getenv("SCRAPER_POSTAL_CODES", "08016").split(",") if c.strip()]
DELAY = float(os.getenv("SCRAPER_DELAY", "5"))
LIMIT = int(os.getenv("SCRAPER_LIMIT", "100"))
DRY_RUN = os.getenv("NATS_DRY_RUN", "0") == "1"


def collect(zone: dict) -> tuple[list[dict], int]:
    """Todas las paginas del catalogo de una zona. Deduplica por `id`: si el catalogo cambia
    durante la pasada, un producto puede salir en dos paginas."""
    seen: dict[str, dict] = {}
    offset, total, pages = 0, None, 0
    while True:
        data = fetch_page(offset, LIMIT, zone)
        pages += 1
        total = data.get("totalCount", total)
        products = data.get("products") or []
        for p in products:
            if isinstance(p, dict) and "id" in p:
                seen.setdefault(str(p["id"]), p)
        if pages % 10 == 0:
            print(f"   {pages} paginas, {len(seen)}/{total} productos", flush=True)
        offset += LIMIT
        if not data.get("hasMore") or not products or (total is not None and offset >= total):
            break
        time.sleep(DELAY)
    return list(seen.values()), total or 0


def zones_for(postal_codes: list[str]) -> list[tuple[dict, str]]:
    """(zona, codigo postal) por tienda distinta. Un codigo sin reparto de Consum se avisa
    y se salta: no es un error del scraper."""
    by_store: dict[str, tuple[dict, str]] = {}
    for pc in postal_codes:
        zone = resolve_zone(pc)
        if zone is None:
            print(f"   {pc}: Consum no reparte en este codigo postal; se salta", flush=True)
            continue
        print(f"   {pc}: tienda {zone['store_code']} ({zone['store_name']}, {zone['city']}), "
              f"zona {zone['zone_id']}/{zone['shipping_zone_id']}", flush=True)
        by_store.setdefault(zone["store_code"], (zone, pc))
        time.sleep(DELAY)
    return list(by_store.values())


if __name__ == "__main__":
    base = Path(__file__).resolve().parents[1]
    failures = []
    for zone, pc in zones_for(POSTAL_CODES):
        wh = zone["store_code"]
        t0 = time.time()
        items, total = collect(zone)
        path = dump(f"{PRODUCTS_URL} wh={wh} cp={pc} total={total}", 200, items, base / "out", wh)
        n, info = publish(items, wh, pc)
        print(f"200 {len(items)} items wh={wh} cp={pc} total={total} en {time.time() - t0:.0f}s -> {path}")
        print(f"nats: {info}")
        if not items:
            failures.append(f"wh={wh}: 0 productos")
        elif not DRY_RUN and n != len(items):
            failures.append(f"wh={wh}: publicados {n} de {len(items)}")

    if failures:
        sys.exit("ERROR: " + "; ".join(failures))
