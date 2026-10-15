from pathlib import Path
import os
import time
from client import fetch_json
from extractor import collect_raw
from dump_txt import dump
from publish import publish

CATEGORIES_URL = "https://tienda.mercadona.es/api/categories/"
SUB_URL = "https://tienda.mercadona.es/api/categories/{}/"
WH = os.getenv("SCRAPER_WH", "default")

if __name__ == "__main__":
    base = Path(__file__).resolve().parents[1]
    status_top, top = fetch_json(CATEGORIES_URL)
    results = top.get("results", []) if status_top == 200 else []
    sub_ids = [
        (c["id"], c["name"])
        for fam in results
        for c in fam.get("categories", [])
    ]
    items: list[dict] = []
    errors: list[str] = []
    for sid, sname in sub_ids:
        s, data = fetch_json(SUB_URL.format(sid))
        if s == 200:
            items.extend(collect_raw(data))
        else:
            errors.append(f"{sid} status={s}")
        time.sleep(0.3)
    label = f"full tops={len(results)} subs={len(sub_ids)}"
    status = 200 if not errors and status_top == 200 else status_top
    if errors:
        items.append({"_errors": errors})
    path = dump(label, status, items, base / "out")
    n, info = publish(items, WH)
    print(f"{status} {len(items)} items subs={len(sub_ids)} -> {path}")
    print(f"nats: {info}")
