from datetime import datetime
from pathlib import Path

def dump(url: str, status: int | None, items: list[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"carrefour_{ts}.txt"
    lines = [
        f"URL origen: {url}",
        f"Fecha: {datetime.now().isoformat(timespec='seconds')}",
        f"Status: {status}",
        f"Items: {len(items)}",
        "---",
    ]
    if status != 200:
        lines.append(f"ERROR status={status} (posible bloqueo anti-bot)")
    if not items and status == 200:
        lines.append("SIN TARJETAS DETECTADAS (revisar selectores)")
    for it in items:
        lines.append(f"nombre_raw: {it.get('texto_raw','')}")
        lines.append(f"url_raw: {it.get('url_raw','')}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
