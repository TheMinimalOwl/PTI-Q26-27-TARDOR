"""Lectura de las lineas limpias que produce el normalizador.

El contrato de la linea (ver `flujo-entrada/docs/03-contratos-datos.md` en la
rama `scrapping`):

    pid | nombre | totalEUR total | upEUR/unidad | size+size_fmt | cat | url | ref=...EUR/... src=fuente|calculado

Este modulo es el **unico** punto que conoce ese formato. Si la linea cambia,
se toca aqui y no en el resto del pipeline.

El parser es deliberadamente tolerante, como el normalizador: una linea rota
debe perder informacion, no tumbar el lote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Separador de campos de la linea limpia.
SEP = " | "

# Motivos de incompletitud que emite el normalizador.
MOTIVOS = ("sin_precio", "sin_tamano")

_NUM_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_SIZE_RE = re.compile(r"^(?P<num>-?\d+(?:[.,]\d+)?)\s*(?P<fmt>.*)$")
_REF_RE = re.compile(r"^ref=(?P<ref>.*)EUR/(?P<ref_fmt>.*?)\s+src=(?P<src>\S+)\s*$")
_HEAD_RE = re.compile(r"^(Items:|Unitarios:|---$|ERROR id=)")


def _dec(valor: str | None) -> Decimal | None:
    """Convierte a `Decimal` admitiendo coma decimal. `None` si no es numero."""
    if valor is None:
        return None
    s = str(valor).strip().replace(" ", "").replace(",", ".")
    if not s or not _NUM_RE.match(s):
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


@dataclass
class Product:
    """Un producto ya normalizado, tal y como viaja en la linea limpia."""

    id: str
    name: str
    total: Decimal | None = None
    unit_price: Decimal | None = None
    unit: str | None = None
    size: str = "-"
    size_format: str = ""
    category: str = ""
    url: str = ""
    ref: str = "-"
    ref_format: str = ""
    unit_src: str = "-"
    unit_reason: str = ""
    # Campos que no vienen en la linea pero hacen falta para indexar:
    chain: str = ""
    wh: str = "default"
    ts: str = ""

    # -- serializacion ---------------------------------------------------
    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "total": str(self.total) if self.total is not None else None,
            "unit_price": str(self.unit_price) if self.unit_price is not None else None,
            "unit": self.unit,
            "size": self.size,
            "size_format": self.size_format,
            "category": self.category,
            "url": self.url,
            "ref": self.ref,
            "ref_format": self.ref_format,
            "unit_src": self.unit_src,
            "unit_reason": self.unit_reason,
            "chain": self.chain,
            "wh": self.wh,
            "ts": self.ts,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Product":
        def dec(v):
            return _dec(v) if v is not None else None

        return cls(
            id=str(d.get("id", "")),
            name=str(d.get("name", "")),
            total=dec(d.get("total")),
            unit_price=dec(d.get("unit_price")),
            unit=d.get("unit"),
            size=str(d.get("size", "-")),
            size_format=str(d.get("size_format", "")),
            category=str(d.get("category", "")),
            url=str(d.get("url", "")),
            ref=str(d.get("ref", "-")),
            ref_format=str(d.get("ref_format", "")),
            unit_src=str(d.get("unit_src", "-")),
            unit_reason=str(d.get("unit_reason", "")),
            chain=str(d.get("chain", "")),
            wh=str(d.get("wh", "default")),
            ts=str(d.get("ts", "")),
        )

    # -- texto para embeddings -------------------------------------------
    @property
    def embed_text(self) -> str:
        """Texto que se embebe.

        No se embebe la linea entera: precio y URL no ayudan a|matchear|
        productos y meten ruido en el vector. Interesa el nombre (que ya
        lleva marca, tamano y formato), la categoria y el tamano explicito.
        """
        bits = [self.name]
        if self.category:
            bits.append(f"categoria {self.category}")
        size = self.size_label
        if size:
            bits.append(f"tamano {size}")
        return " | ".join(bits)

    @property
    def size_label(self) -> str:
        """Tamano legible: `1 l`, `500 g`, `3 ud`."""
        if not self.size or self.size == "-":
            return ""
        num = _dec(self.size)
        base = self.size_format.strip()
        if num is None:
            return f"{self.size} {base}".strip()
        s = f"{num:f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return f"{s} {base}".strip()

    @property
    def unit_label(self) -> str:
        """Unidad base del precio unitario (`EUR/l`, `EUR/kg`...)."""
        if self.unit_price is None or not self.unit:
            return "-"
        s = f"{self.unit_price:f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return f"{s} EUR/{self.unit}"


def parse_clean_line(line: str, chain: str = "", wh: str = "default", ts: str = "") -> Product | None:
    """Parsea una linea limpia. `None` si la linea no es un producto."""
    raw = line.strip()
    if not raw or _HEAD_RE.match(raw):
        return None

    parts = raw.split(SEP)
    if len(parts) < 8:
        return None
    if len(parts) > 8:
        # Un nombre con " | " dentro: se re-agrupa todo lo que no sea cola.
        head = parts[0]
        name = SEP.join(parts[1:-6])
        parts = [head, name, *parts[-6:]]

    pid, name, total_s, up_s, size_s, cat, url, ref_s = [p.strip() for p in parts]

    total = _dec(total_s.replace("EUR total", ""))

    unit_price: Decimal | None = None
    unit: str | None = None
    unit_reason = ""
    if up_s.startswith("-"):
        # Linea incompleta: "- (sin_precio)" / "- (formato_no_comparable:xyz)"
        m = re.match(r"^-\s*\((?P<motivo>[^)]*)\)\s*$", up_s)
        unit_reason = m.group("motivo") if m else "desconocido"
    else:
        m = re.match(r"^(?P<val>[^EUR]+)EUR/(?P<unit>.+)$", up_s)
        if m:
            unit_price = _dec(m.group("val"))
            unit = m.group("unit").strip()

    size, size_format = size_s, ""
    m = _SIZE_RE.match(size_s)
    if m:
        size, size_format = m.group("num"), m.group("fmt").strip()

    ref, ref_format, unit_src = "-", "", "-"
    m = _REF_RE.match(ref_s)
    if m:
        ref = m.group("ref").strip()
        ref_format = m.group("ref_fmt").strip()
        unit_src = m.group("src").strip()

    return Product(
        id=pid,
        name=name,
        total=total,
        unit_price=unit_price,
        unit=unit,
        size=size,
        size_format=size_format,
        category=cat,
        url=url,
        ref=ref,
        ref_format=ref_format,
        unit_src=unit_src,
        unit_reason=unit_reason,
        chain=chain,
        wh=wh,
        ts=ts,
    )


@dataclass
class ParseStats:
    """Telling de una ingesta, para no ir a ciegas."""

    lines: int = 0
    productos: int = 0
    headers: int = 0
    errores: int = 0
    incompletos: int = 0
    con_precio_unitario: int = 0

    def as_dict(self) -> dict:
        return {
            "lines": self.lines,
            "productos": self.productos,
            "headers": self.headers,
            "errores": self.errores,
            "incompletos": self.incompletos,
            "con_precio_unitario": self.con_precio_unitario,
        }


def parse_clean_text(text: str, chain: str = "", wh: str = "default") -> tuple[list[Product], ParseStats]:
    """Parsea un lote completo (cabecera + lineas)."""
    stats = ParseStats()
    productos: list[Product] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        stats.lines += 1
        if _HEAD_RE.match(line.strip()):
            stats.headers += 1
            if line.strip().startswith("ERROR id="):
                stats.errores += 1
            continue
        p = parse_clean_line(line, chain=chain, wh=wh)
        if p is None:
            stats.errores += 1
            continue
        stats.productos += 1
        if p.unit_price is None:
            stats.incompletos += 1
        else:
            stats.con_precio_unitario += 1
        productos.append(p)
    return productos, stats


def parse_clean_file(path: str | Path, chain: str | None = None, wh: str = "default") -> tuple[list[Product], ParseStats]:
    """Parsea un fichero de lineas limpias.

    La cadena se deduce del nombre del fichero si no se pasa (`mercadona_clean.txt`
    -> `mercadona`) para no obligar a quien lo genera a duplicar el dato.
    """
    path = Path(path)
    chain = chain or path.stem.split("_")[0]
    return parse_clean_text(path.read_text(encoding="utf-8"), chain=chain, wh=wh)


def load_many(paths: list[str | Path], wh: str = "default") -> tuple[list[Product], dict[str, ParseStats]]:
    """Carga varios ficheros y devuelve los productos y el telling por fichero."""
    productos: list[Product] = []
    stats: dict[str, ParseStats] = {}
    for path in paths:
        ps, st = parse_clean_file(path, wh=wh)
        productos.extend(ps)
        stats[str(path)] = st
    return productos, stats
