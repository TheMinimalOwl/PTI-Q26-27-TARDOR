"""Scraper de Condis: todo el catalogo de la tienda online, por secciones, desde la API JSON
del buscador (Empathy.co). Publica cada producto crudo en `scraper.condis.raw` y deja un
volcado txt de depuracion en out/.

Codigo postal: sin iniciar sesion la web ensena el catalogo de la tienda 718, y la eleccion
de tienda por codigo postal la hace el servidor de la web al pedir (no hay API publica para
ello). De momento se usa SCRAPER_STORE (718) y se publica `postal_code` = el primero de
SCRAPER_POSTAL_CODES. Condis reparte en Cataluna (y alrededores): con un codigo postal de
fuera no se hace nada.

Sale con codigo != 0 si no hay productos, si falta mas de un 2 % respecto al total que da la
API o si no se pueden publicar, para que el Job quede como fallido y se vea.

Variables:
  SCRAPER_POSTAL_CODES (08016)  codigos postales, separados por comas
  SCRAPER_STORE (718)  tienda de Condis
  SCRAPER_DELAY (3)    segundos entre peticiones (~20 en total)
  NATS_URL, NATS_STREAM, NATS_DRY_RUN
"""
import os
import sys
import time
from pathlib import Path

from client import Client
from dump_txt import dump
from publish import DRY_RUN, publish

PROVINCES = ("08", "17", "25", "43")  # Cataluna
POSTAL_CODES = [c.strip() for c in os.getenv("SCRAPER_POSTAL_CODES", "08016").split(",") if c.strip()]
STORE = os.getenv("SCRAPER_STORE", "718")
DELAY = float(os.getenv("SCRAPER_DELAY", "3"))
MAX_MISSING = 0.02


if __name__ == "__main__":
    pc = next((c for c in POSTAL_CODES if c[:2] in PROVINCES), None)
    if pc is None:
        print(f"   condis: no reparte en {','.join(POSTAL_CODES)}; nada que hacer", flush=True)
        sys.exit(0)

    t0 = time.time()
    client = Client(STORE, DELAY)
    total, sections = client.sections()
    print(f"   condis: tienda {STORE}, {total} productos en {len(sections)} secciones", flush=True)
    seen: dict[str, dict] = {}
    for name, count in sections.items():
        got = client.section(name)
        for p in got:
            if isinstance(p, dict) and p.get("id"):
                p.pop("tagging", None)  # URLs de analitica de la web, no son datos del producto
                seen.setdefault(str(p["id"]), p)
        print(f"   {name}: {len(got)}/{count}", flush=True)
    items = list(seen.values())

    path = dump(f"empathy condis store={STORE} cp={pc} total={total}", 200, items,
                Path(__file__).resolve().parents[1] / "out", STORE)
    n, info = publish(items, STORE, pc)
    print(f"200 {len(items)} items condis wh={STORE} cp={pc} total={total} en {time.time() - t0:.0f}s -> {path}")
    print(f"nats: {info}")
    if not items:
        sys.exit("ERROR: 0 productos")
    if total and len(items) < (1 - MAX_MISSING) * total:
        sys.exit(f"ERROR: {len(items)} de {total} productos")
    if not DRY_RUN and n != len(items):
        sys.exit(f"ERROR: publicados {n} de {len(items)}")
