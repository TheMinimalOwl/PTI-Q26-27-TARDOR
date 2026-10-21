from datetime import datetime
from pathlib import Path

def dump(url: str, status: int | None, items: list[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"mercadona_{ts}.txt"
    lines = [
        f"URL origen: {url}",
        f"Fecha: {datetime.now().isoformat(timespec='seconds')}",
        f"Status: {status}",
        f"Items: {len(items)}",
        "---",
    ]
    if status != 200:
        lines.append(f"ERROR status={status}")
    for p in items:
        # Volcado crudo, sin normalizar (normaliza Fission)
        lines.append(f"raw: {p}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
