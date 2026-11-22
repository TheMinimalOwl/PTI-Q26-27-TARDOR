"""Scraper de Mercadona: catalogo completo del almacen que sirve cada codigo postal.

Codigos postales: SCRAPER_POSTAL_CODES (lista separada por comas). Mas adelante los dara la
API (los de los usuarios de la app); mientras tanto, 08016 de ejemplo. Cada codigo se
traduce a su almacen (08016 -> bcn1) y cada almacen se recorre una sola vez.

Cada envelope lleva `wh` = almacen de Mercadona y `postal_code`.

Si Mercadona no resuelve un codigo postal (ni tras los reintentos de client.py), se usa el
ultimo almacen conocido para ese codigo, guardado en out/mercadona_wh.json (el volumen
persistente) en cada resolucion correcta. Los almacenes casi nunca cambian.

Sale con codigo != 0 si no consigue productos, si falla mas de un MAX_FAILED de las
subcategorias (pasada a medias) o si no los puede publicar (antes acababa con 0 y el Job
parecia correcto aunque no hubiera datos).
"""
from pathlib import Path
import json
import os
import sys
import time
from client import fetch_json, resolve_wh
from extractor import collect_raw
from dump_txt import dump
from publish import DRY_RUN, publish

CATEGORIES_URL = "https://tienda.mercadona.es/api/categories/"
SUB_URL = "https://tienda.mercadona.es/api/categories/{}/"
POSTAL_CODES = [c.strip() for c in os.getenv("SCRAPER_POSTAL_CODES", "08016").split(",") if c.strip()]
MAX_FAILED = float(os.getenv("SCRAPER_MAX_FAILED", "0.05"))  # fraccion de subcategorias


def _load_cache(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def warehouses(postal_codes: list[str], cache_path: Path) -> list[tuple[str, str]]:
    """(almacen, codigo postal) por almacen distinto. Si un codigo no se puede resolver, se
    usa el ultimo almacen conocido; si tampoco lo hay, se avisa y se salta."""
    cache = _load_cache(cache_path)
    by_wh: dict[str, str] = {}
    for pc in postal_codes:
        wh = resolve_wh(pc)
        if wh:
            print(f"   {pc}: almacen {wh}", flush=True)
            cache[pc] = wh
        elif pc in cache:
            wh = cache[pc]
            print(f"   {pc}: Mercadona no responde; uso el ultimo almacen conocido ({wh})", flush=True)
        else:
            print(f"   {pc}: Mercadona no devuelve almacen para este codigo postal; se salta", flush=True)
            continue
        by_wh.setdefault(wh, pc)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    except OSError as e:
        print(f"   no he podido guardar {cache_path} ({e})", flush=True)
    return [(wh, pc) for wh, pc in by_wh.items()]


def scrape(wh: str) -> tuple[int | None, list[dict], int, int]:
    params = {"lang": "es", "wh": wh}
    status_top, top = fetch_json(CATEGORIES_URL, params)
    results = (top.get("results") or []) if status_top == 200 else []
    sub_ids = [
        (c["id"], c.get("name", ""))
        for fam in results if isinstance(fam, dict)
        for c in (fam.get("categories") or []) if isinstance(c, dict) and "id" in c
    ]
    items: list[dict] = []
    errors: list[str] = []
    for sid, sname in sub_ids:
        s, data = fetch_json(SUB_URL.format(sid), params)
        if s == 200:
            items.extend(collect_raw(data))
        else:
            errors.append(f"{sid} status={s}")
        time.sleep(0.3)
    status = 200 if not errors and status_top == 200 else status_top
    if errors:
        items.append({"_errors": errors})
    return status, items, len(results), len(sub_ids)


if __name__ == "__main__":
    base = Path(__file__).resolve().parents[1]
    whs = warehouses(POSTAL_CODES, base / "out" / "mercadona_wh.json")
    failures = [] if whs else ["ningun codigo postal se ha podido resolver a un almacen"]
    for wh, pc in whs:
        status, items, tops, subs = scrape(wh)
        path = dump(f"full wh={wh} cp={pc} tops={tops} subs={subs}", status, items, base / "out", wh)
        n, info = publish(items, wh, pc)
        real = sum(1 for p in items if "id" in p)
        failed = sum(len(p["_errors"]) for p in items if "_errors" in p)
        print(f"{status} {len(items)} items wh={wh} cp={pc} subs={subs} fallidas={failed} -> {path}")
        print(f"nats: {info}")
        if real == 0:
            failures.append(f"wh={wh}: 0 productos (status {status})")
        elif subs and failed / subs > MAX_FAILED:
            failures.append(f"wh={wh}: {failed} de {subs} subcategorias fallidas")
        elif not DRY_RUN and n != real:
            failures.append(f"wh={wh}: publicados {n} de {real}")

    if failures:
        sys.exit("ERROR: " + "; ".join(failures))
