from pathlib import Path
from client import fetch
from extractor import extract_raw
from dump_txt import dump

URLS = [
    "https://www.carrefour.es/supermercado/ofertas",
]

if __name__ == "__main__":
    base = Path(__file__).resolve().parents[1]
    out_dir = base / "out"
    for url in URLS:
        status, html, _ = fetch(url)
        items = extract_raw(html, url) if status == 200 else []
        path = dump(url, status, items, out_dir)
        print(f"{status} {len(items)} items -> {path}")
