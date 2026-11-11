"""Scraper de Caprabo (capraboacasa.com).

No hay API: recorre todas las categorias de supermercado (pagina a pagina, HTML) y publica
cada producto crudo en `scraper.caprabo.raw`, con `wh` = tienda online que sirve el catalogo
y `postal_code` = el primer codigo postal configurado de Cataluna. Deja un volcado txt en out/.

Sin iniciar sesion la web ensena siempre el catalogo de su tienda online por defecto: el
codigo postal no cambia el catalogo. Caprabo solo reparte en Cataluna; si ningun codigo
postal es de alli, no se hace nada.

Sale con codigo != 0 si no hay productos, si fallan demasiadas categorias o si no se
pueden publicar, para que el Job quede como fallido y se vea.

Variables:
  SCRAPER_POSTAL_CODES (08016)  codigos postales, separados por comas
  SCRAPER_DELAY (3)   segundos entre peticiones (~1.150 paginas)
  SCRAPER_EXCLUDE     slugs de categorias de primer nivel que no se recorren
  SCRAPER_MAX_CATEGORIES (0 = todas)  para pruebas
  NATS_URL, NATS_STREAM, NATS_DRY_RUN
"""
import os
import sys
import time
from pathlib import Path

from client import Site
from dump_txt import dump
from extractor import last_page, leaf_categories, products
from publish import DRY_RUN, publish

HOST = "www.capraboacasa.com"
PROVINCES = ("08", "17", "25", "43")  # zona de reparto: Cataluna (su pagina de envio)
# Categorias de primer nivel que no son de supermercado (electronica, hogar, libros...).
EXCLUDE_DEFAULT = "papeleria,hogar,electronica,electrohogar,descanso"

POSTAL_CODES = [c.strip() for c in os.getenv("SCRAPER_POSTAL_CODES", "08016").split(",") if c.strip()]
DELAY = float(os.getenv("SCRAPER_DELAY", "3"))
EXCLUDE = [x.strip() for x in os.getenv("SCRAPER_EXCLUDE", EXCLUDE_DEFAULT).split(",") if x.strip()]
MAX_CATEGORIES = int(os.getenv("SCRAPER_MAX_CATEGORIES", "0"))
MAX_FAILED = 0.05  # fraccion de categorias que pueden fallar


def scrape() -> tuple[list[dict], str, str, int, int]:
    site = Site(HOST, DELAY)
    categories = leaf_categories(site.get("/es/"), EXCLUDE)
    if MAX_CATEGORIES:
        categories = categories[:MAX_CATEGORIES]
    shop_id, shop_name = site.shop()
    print(f"   caprabo: tienda {shop_id} ({shop_name}), {len(categories)} categorias", flush=True)

    seen: dict[str, dict] = {}
    pages = failed = 0
    for n, path in enumerate(categories, 1):
        try:
            first = site.get(path)
            htmls = [first] + [site.get(f"{path}?pageNumber={p}") for p in range(1, last_page(first) + 1)]
        except RuntimeError as e:
            failed += 1
            print(f"   ERROR {e}", flush=True)
            continue
        pages += len(htmls)
        for h in htmls:
            for p in products(h):
                seen.setdefault(p["id"], p)   # un producto puede estar en varias categorias
        if n % 50 == 0:
            print(f"   caprabo: {n}/{len(categories)} categorias, {pages} paginas, {len(seen)} productos", flush=True)
    return list(seen.values()), shop_id, shop_name, len(categories), failed


if __name__ == "__main__":
    pc = next((c for c in POSTAL_CODES if c[:2] in PROVINCES), None)
    if pc is None:
        print(f"   caprabo: no reparte en {','.join(POSTAL_CODES)}; nada que hacer", flush=True)
        sys.exit(0)

    t0 = time.time()
    items, wh, shop_name, ncat, failed = scrape()
    path = dump(f"caprabo wh={wh} ({shop_name}) cp={pc} categorias={ncat} fallidas={failed}",
                200, items, Path(__file__).resolve().parents[1] / "out", wh)
    n, info = publish(items, wh, pc)
    print(f"200 {len(items)} items caprabo wh={wh} cp={pc} categorias={ncat} fallidas={failed} "
          f"en {time.time() - t0:.0f}s -> {path}")
    print(f"nats: {info}")
    if not items:
        sys.exit("ERROR: 0 productos")
    if ncat and failed / ncat > MAX_FAILED:
        sys.exit(f"ERROR: {failed} de {ncat} categorias fallidas")
    if not DRY_RUN and n != len(items):
        sys.exit(f"ERROR: publicados {n} de {len(items)}")
