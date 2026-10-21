import ast
from datetime import datetime
from pathlib import Path
from normalizer import to_clean_txt

if __name__ == "__main__":
    base = Path(__file__).resolve().parents[2]
    ins = sorted((base / "scrappers" / "scrapper_mercadona" / "out").glob("mercadona_*.txt"))
    src = ins[-1]
    items = []
    for line in src.read_text(encoding="utf-8").splitlines():
        if line.startswith("raw: "):
            try:
                items.append(ast.literal_eval(line[5:]))
            except Exception:
                pass
    txt = to_clean_txt(items)
    out_dir = Path(__file__).resolve().parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"clean_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    dst.write_text(txt, encoding="utf-8")
    print(f"{len(items)} raws -> {len(txt.splitlines()) - 2} limpias -> {dst}")
    print("\n".join(txt.splitlines()[:8]))
