from datetime import datetime
from pathlib import Path


def dump(label: str, status: int | None, items: list[dict], out_dir: Path, wh: str) -> Path:
    """Volcado crudo de depuracion: out/bonarea_<tienda>_<fecha>.txt, un `raw: {...}` por producto."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"bonarea_{wh}_{ts}.txt"
    lines = [
        f"Origen: {label}",
        f"Fecha: {datetime.now().isoformat(timespec='seconds')}",
        f"Status: {status}",
        f"Items: {len(items)}",
        "---",
    ]
    for p in items:
        lines.append(f"raw: {p}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
