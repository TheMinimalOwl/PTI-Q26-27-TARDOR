"""Scraper de bonÀrea: todas las categorias de supermercado de la tienda online, una
llamada por categoria hoja al JSON interno de la web (`ShoppingBody`). Publica cada producto
crudo en `scraper.bonarea.raw` y deja un volcado txt de depuracion en out/.

Codigo postal: la tienda online tiene un unico catalogo sin iniciar sesion; se publica
`wh` = "online" y `postal_code` = el primer codigo postal configurado de Cataluna. Con
codigos de fuera no se hace nada.

Sale con codigo != 0 si no hay productos, si fallan mas del 5 % de las categorias o si no
se pueden publicar, para que el Job quede como fallido y se vea.

Variables:
  SCRAPER_POSTAL_CODES (08016)  codigos postales, separados por comas
  SCRAPER_DELAY (3)    segundos entre peticiones (~400 categorias)
  SCRAPER_EXCLUDE      categorias de primer nivel que no se recorren (no son de supermercado)
  SCRAPER_MAX_CATEGORIES (0 = todas)  para pruebas
  NATS_URL, NATS_STREAM, NATS_DRY_RUN
"""
import os
import sys
import time
from pathlib import Path

from client import FIRST, Client, leaves
from dump_txt import dump
from publish import DRY_RUN, publish

WH = "online"
PROVINCES = ("08", "17", "25", "43")  # Cataluna
EXCLUDE_DEFAULT = ("Llar i jardí|Electrodomèstics|Roba, calçat i tèxtil llar|Informàtica i papereria|"
                   "Joguines i món nadó|Bricolatge|Automoció|Material ramader")
POSTAL_CODES = [c.strip() for c in os.getenv("SCRAPER_POSTAL_CODES", "08016").split(",") if c.strip()]
DELAY = float(os.getenv("SCRAPER_DELAY", "3"))
# Separadas por "|" (algun nombre lleva comas).
EXCLUDE = [x.strip().lower() for x in os.getenv("SCRAPER_EXCLUDE", EXCLUDE_DEFAULT).split("|") if x.strip()]
MAX_CATEGORIES = int(os.getenv("SCRAPER_MAX_CATEGORIES", "0"))
MAX_FAILED = 0.05


if __name__ == "__main__":
    pc = next((c for c in POSTAL_CODES if c[:2] in PROVINCES), None)
    if pc is None:
        print(f"   bonarea: no reparte en {','.join(POSTAL_CODES)}; nada que hacer", flush=True)
        sys.exit(0)

    t0 = time.time()
    client = Client(DELAY)
    client.start()
    first = client.body(FIRST)
    cats = leaves(first["nivells"], EXCLUDE)
    if MAX_CATEGORIES:
        cats = cats[:MAX_CATEGORIES]
    print(f"   bonarea: {len(cats)} categorias", flush=True)

    seen: dict[str, dict] = {}
    failed = 0
    for n, (ref, path) in enumerate(cats, 1):
        try:
            data = first if ref == FIRST else client.body(ref)
        except RuntimeError as e:
            failed += 1
            print(f"   ERROR {e}", flush=True)
            continue
        for p in data["articles"]:
            if isinstance(p, dict) and p.get("identifier"):
                p["category_path"] = path   # la respuesta no dice en que categoria esta
                seen.setdefault(str(p["identifier"]), p)
        if n % 50 == 0:
            print(f"   bonarea: {n}/{len(cats)} categorias, {len(seen)} productos", flush=True)
    items = list(seen.values())

    path = dump(f"bonarea ShoppingBody wh={WH} cp={pc} categorias={len(cats)} fallidas={failed}",
                200, items, Path(__file__).resolve().parents[1] / "out", WH)
    n, info = publish(items, WH, pc)
    print(f"200 {len(items)} items bonarea wh={WH} cp={pc} categorias={len(cats)} fallidas={failed} "
          f"en {time.time() - t0:.0f}s -> {path}")
    print(f"nats: {info}")
    if not items:
        sys.exit("ERROR: 0 productos")
    if cats and failed / len(cats) > MAX_FAILED:
        sys.exit(f"ERROR: {failed} de {len(cats)} categorias fallidas")
    if not DRY_RUN and n != len(items):
        sys.exit(f"ERROR: publicados {n} de {len(items)}")
