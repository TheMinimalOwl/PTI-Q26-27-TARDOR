"""Normalizacion de productos crudos -> linea limpia con precio unitario canonico.

Contrato de la linea (ver docs/03-contratos-datos.md):

    pid | nombre | totalEUR total | unitEUR/unit | size+size_fmt | cat | url | ref=...EUR/... src=fuente|calculado

El precio unitario se lleva siempre a una **unidad base canonica** para que sea
comparable entre cadenas: kg, l, ud, m o lavado. Si la fuente ya trae
`reference_price`, se respeta (convertido a la base); si no, se calcula desde
`unit_price` y el tamano. Si la unidad es ambigua no se inventa nada: la linea
queda marcada como incompleta con el motivo.

Contrato Pydantic (ver docs/03-contratos-datos.md): `RawProduct` describe la entrada
tolerante, `NormalizedProduct` valida cada linea normalizada y `CleanBatch` es la
variante estructurada (JSON) del mensaje `clean`. Los modelos son un envoltorio
sobre `normalize_record()`: no rehacen la logica, solo la validan.

Los modelos viven en este mismo fichero a proposito: la funcion de Fission se
empaqueta como una unica fuente inline (`fission.yaml`), y el consumer reutiliza
el modulo (`from normalizer import to_clean_txt`).
"""

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# Formatos de medida -> (unidad base canonica, unidades base por 1 unidad del formato).
# Cubre los formatos reales observados en Mercadona (ver docs/03-contratos-datos.md):
# kg/g/100 g, l/ml/cl/100 ml, ud/dc/dz, m y lv (lavado).
UNITS: dict[str, tuple[str, Decimal]] = {
    # masa (base: kg)
    "kg": ("kg", Decimal("1")),
    "g": ("kg", Decimal("0.001")),
    "100 g": ("kg", Decimal("0.1")),
    # volumen (base: l)
    "l": ("l", Decimal("1")),
    "ml": ("l", Decimal("0.001")),
    "cl": ("l", Decimal("0.01")),
    "100 ml": ("l", Decimal("0.1")),
    # recuento (base: ud)
    "ud": ("ud", Decimal("1")),
    "u": ("ud", Decimal("1")),
    "dc": ("ud", Decimal("12")),  # docena
    "dz": ("ud", Decimal("12")),  # docena
    # otras magnitudes, comparables dentro de su clase
    "m": ("m", Decimal("1")),  # longitud (film, papel de aluminio)
    "lv": ("lavado", Decimal("1")),  # unidad funcional (detergente)
}

# Alias de otras cadenas -> clave de UNITS.
ALIASES: dict[str, str] = {
    "litro": "l", "litros": "l",
    "gramo": "g", "gramos": "g",
    "kilo": "kg", "kilos": "kg", "kilogramo": "kg", "kilogramos": "kg",
    "unidad": "ud", "unidades": "ud", "uds": "ud", "pieza": "ud", "piezas": "ud",
    "metro": "m", "metros": "m",
    "docena": "dc", "docenas": "dc",
    "lavado": "lv", "lavados": "lv",
    "100ml": "100 ml", "100g": "100 g",
    "100 gramos": "100 g", "100 gramo": "100 g",
    "100 mililitros": "100 ml", "100 mililitro": "100 ml",
    # Consum: Gr, 100 Gr y Do (dosis: pastillas de lavavajillas, bolsitas de infusion)
    "gr": "g", "100 gr": "100 g",
    "do": "ud", "dosis": "ud",
}


def _dec(v) -> Decimal | None:
    """Convierte a Decimal de forma defensiva (admite coma decimal). None si no se puede."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, Decimal):
        return v if v.is_finite() else None
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, float):
        v = repr(v)
    s = str(v).strip().replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _unit(fmt) -> tuple[str, Decimal] | None:
    """Normaliza un `size_format`/`reference_format` a su unidad base y factor."""
    key = " ".join(str(fmt or "").split()).lower()
    key = ALIASES.get(key, key)
    return UNITS.get(key)


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _fmt(v: Decimal | None) -> str:
    """Formatea un importe: sin ceros de relleno, minimo 2 decimales."""
    if v is None:
        return "-"
    s = f"{_q(v):f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    ent, _, dec = s.partition(".")
    if len(dec) < 2:
        dec = (dec + "00")[:2]
    return f"{ent}.{dec}"


# ---------------------------------------------------------------------------
# Contrato Pydantic (ver docs/03-contratos-datos.md)
# ---------------------------------------------------------------------------

# Reutiliza _dec(): admite coma decimal y rechaza NaN/Inf/cadena vacia.
Dec = Annotated[Decimal, BeforeValidator(_dec)]
# La fuente manda `id` como numero: se coacciona a str (mismo criterio que str(...)).
Id = Annotated[str, BeforeValidator(lambda v: v if isinstance(v, str) else str(v))]

# Unidades base y origenes; deben seguir a UNITS y a unit_price().
UnitBase = Literal["kg", "l", "ud", "m", "lavado"]
UnitSrc = Literal["fuente", "calculado", "-"]


class Category(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""


class PriceInstructions(BaseModel):
    """Solo los campos que usa unit_price(); el resto (bulk_price, pack_size,
    approx_size, total_units...) se ignora a proposito."""

    model_config = ConfigDict(extra="ignore")

    unit_price: Dec | None = None        # precio del envase (total)
    reference_price: Dec | None = None   # base de la fuente, si la trae
    reference_format: str = ""
    unit_size: Dec | None = None
    size_format: str = ""
    drained_weight: Dec | None = None    # peso escurrido (pesables)


class RawProduct(BaseModel):
    """Producto crudo de la cadena. Tolerante: ignora campos desconocidos, para
    que un cambio en la fuente no rompa la ingesta."""

    model_config = ConfigDict(extra="ignore")

    id: Id
    display_name: str = ""
    price_instructions: PriceInstructions = Field(default_factory=PriceInstructions)
    share_url: str = ""
    categories: list[Category] = Field(default_factory=list)


class NormalizedProduct(BaseModel):
    """Salida de normalize_record(): mismos campos, con tipos y validacion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Id
    name: str
    total: Dec | None = None
    unit_price: Dec | None = None
    unit: UnitBase | None = None
    unit_src: UnitSrc
    unit_reason: str = ""            # "", sin_precio, sin_tamano, formato_no_comparable:<fmt>
    ref: Any = None                  # crudo de la fuente ("-", numero o texto) -> trazabilidad
    ref_format: str = ""
    size: Any = None                 # crudo de la fuente
    size_format: str = ""
    category: str = ""
    url: str = ""

    @field_validator("name", mode="before")
    @classmethod
    def _collapse(cls, v: Any) -> str:
        return " ".join(str(v or "").split())

    @model_validator(mode="after")
    def _coherente(self) -> "NormalizedProduct":
        """La linea incompleta y el precio unitario no pueden coexistir mal."""
        if self.unit_price is None:
            if not self.unit_reason:
                raise ValueError("sin unit_price hace falta unit_reason")
            if self.unit is not None or self.unit_src != "-":
                raise ValueError("linea incompleta no puede traer unidad ni origen")
        else:
            if self.unit is None or self.unit_src == "-":
                raise ValueError("con unit_price la unidad y el origen son obligatorios")
            if self.unit_reason:
                raise ValueError("unit_reason debe estar vacio cuando hay unit_price")
        return self


class CleanBatch(BaseModel):
    """Variante estructurada del mensaje `clean` (un lote)."""

    source: Literal["normalizer"] = "normalizer"
    wh: str = "default"
    ts: str                          # ISO-8601 UTC, igual que el envelope
    batch: int                       # nº de productos crudos del lote
    items: list[NormalizedProduct]


# ---------------------------------------------------------------------------
# Adaptadores de cadena -> forma comun
# ---------------------------------------------------------------------------
#
# El normalizador trabaja sobre la forma de Mercadona (`id`, `display_name`,
# `price_instructions`, `share_url`, `categories`). Cada cadena nueva solo necesita una
# funcion que traduzca su crudo a esa forma; el resto (precio unitario canonico, linea
# limpia, contrato Pydantic) es comun. La cadena se detecta por la forma del objeto, asi
# que el scraper sigue publicando el crudo tal cual.

# "Lentejas Bote 425 Gr", "Yogur Pack de 4 4 x 120 Gr", "Cerveza 12 x 0,25 L"
_CONSUM_SIZE = re.compile(r"(?:(\d+)\s*x\s*)?(\d+(?:[.,]\d+)?)\s*(Gr|Kg|ml|cl|L|U|Lv|Dc|M|Do)\s*$", re.I)


def _consum_price(price_data: dict) -> dict:
    """Precio vigente: el de oferta si lo hay (es lo que paga el cliente), si no el normal."""
    prices = {x.get("id"): (x.get("value") or {}) for x in price_data.get("prices") or []}
    return prices.get("OFFER_PRICE") or prices.get("PRICE") or {}


def from_consum(p: dict) -> dict:
    """Producto crudo de la API de Consum -> forma comun.

    - `id`: `code`, el id publico (el de la URL); `id` de Consum es interno.
    - precio: `centAmount` (en euros, pese al nombre) y `centUnitAmount` por
      `unitPriceUnitType` ("1 Kg", "1 L", "100 ml", "1 U"...), que se trata como el
      `reference_price`/`reference_format` de Mercadona: la fuente manda.
    - tamano: no viene estructurado; se saca del final de `description`
      ("... 425 Gr", "... 4 x 120 Gr"). Solo se usa si faltara el precio de la fuente.
    """
    pd = p.get("productData") or {}
    price_data = p.get("priceData") or {}
    value = _consum_price(price_data)
    ref_fmt = re.sub(r"^1\s+", "", str(price_data.get("unitPriceUnitType") or "").strip())

    size, size_fmt = None, ""
    m = _CONSUM_SIZE.search(str(pd.get("description") or ""))
    if m:
        n, amount, size_fmt = m.groups()
        size = _dec(amount)
        if size is not None and n:
            size = size * int(n)

    pi = {
        "unit_price": value.get("centAmount"),
        "reference_price": value.get("centUnitAmount"),
        "reference_format": ref_fmt,
    }
    if size is not None:  # sin tamano, la linea muestra "-" como en Mercadona
        pi.update(unit_size=size, size_format=size_fmt)
    return {
        "id": str(p.get("code") or p.get("id", "-")),
        "display_name": pd.get("name", ""),
        "price_instructions": pi,
        "share_url": pd.get("url", ""),
        "categories": [{"name": c.get("name", "")} for c in p.get("categories") or [] if isinstance(c, dict)],
    }


def to_common(p):
    """Traduce el crudo de cualquier cadena a la forma comun (Mercadona pasa tal cual)."""
    if isinstance(p, dict) and "priceData" in p and "productData" in p:
        return from_consum(p)
    return p


# ---------------------------------------------------------------------------
# Calculo y normalizacion
# ---------------------------------------------------------------------------


def unit_price(p: dict) -> tuple[Decimal | None, str | None, str, str]:
    """Precio unitario canonico de un producto crudo.

    Devuelve `(valor, unidad, origen, motivo)`:
    - `origen` = `"fuente"` (reference_price convertido), `"calculado"` (desde
      unit_price/tamano) o `"-"` (incompleto).
    - `motivo` describe por que falta el valor cuando `valor is None`.
    """
    p = to_common(p)
    pi = p.get("price_instructions") or {}

    ref = _dec(pi.get("reference_price"))
    if ref is not None and ref > 0:
        u = _unit(pi.get("reference_format"))
        if u:
            base, factor = u
            return _q(ref / factor), base, "fuente", ""

    total = _dec(pi.get("unit_price"))
    if total is None or total <= 0:
        return None, None, "-", "sin_precio"
    u = _unit(pi.get("size_format"))
    if not u:
        return None, None, "-", f"formato_no_comparable:{pi.get('size_format') or '?'}"
    base, factor = u

    # Para productos pesables (aceitunas, conservas...) la referencia de la
    # fuente usa el peso ESCURRIDO, no unit_size. Reproducirlo para que el
    # respaldo coincida con lo que daria la fuente.
    drained = _dec(pi.get("drained_weight"))
    if base == "kg" and drained is not None and drained > 0:
        amount = drained
    else:
        size = _dec(pi.get("unit_size"))
        if size is None or size <= 0:
            return None, None, "-", "sin_tamano"
        amount = size * factor

    return _q(total / amount), base, "calculado", ""


def normalize_record(p: dict) -> dict:
    """Campos normalizados de un producto (base de la linea y del JSON)."""
    p = to_common(p)
    pi = p.get("price_instructions") or {}
    cats = p.get("categories") or []
    up, base, src, motivo = unit_price(p)
    return {
        "id": str(p.get("id", "-")),
        "name": " ".join(str(p.get("display_name", "")).split()),
        "total": _dec(pi.get("unit_price")),
        "unit_price": up,
        "unit": base,
        "unit_src": src,
        "unit_reason": motivo,
        "ref": pi.get("reference_price", "-"),
        "ref_format": pi.get("reference_format", ""),
        "size": pi.get("unit_size", "-"),
        "size_format": pi.get("size_format", ""),
        "category": cats[0].get("name", "") if cats else "",
        "url": p.get("share_url", ""),
    }


def normalize_model(p: dict) -> NormalizedProduct:
    """`normalize_record()` validado con Pydantic (lanza `ValidationError` si no cuadra)."""
    return NormalizedProduct.model_validate(normalize_record(p))


def to_clean_json(
    items: list[dict],
    *,
    wh: str = "default",
    ts: str | None = None,
    source: str = "normalizer",
) -> dict:
    """Variante estructurada de `clean`: un `CleanBatch` serializable a JSON.

    Es estricta: valida tambien la entrada (`RawProduct`) y, si un item no cuadra,
    lanza `ValidationError` en vez de degradarlo. La linea de texto sigue siendo
    la via tolerante, con `ERROR id=...` por item.
    """
    productos = []
    for p in items:
        if not isinstance(p, dict) or "_errors" in p:
            continue
        p = to_common(p)
        RawProduct.model_validate(p)  # entrada: el camino estructurado no tolera crudos rotos
        productos.append(normalize_model(p))
    batch = CleanBatch(
        source=source,
        wh=wh,
        ts=ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        batch=len(items),
        items=productos,
    )
    return batch.model_dump(mode="json")


def _validacion_msg(e: ValidationError) -> str:
    """Resumen de un `ValidationError` en **una sola linea** (el formato es 1 linea/item)."""
    partes = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err.get("loc", ())) or "modelo"
        msg = " ".join(str(err.get("msg", "")).split())
        partes.append(f"{loc}: {msg}")
    return " | ".join(partes)


def format_record(r: dict) -> str:
    if r["unit_price"] is None:
        up = f"- ({r['unit_reason']})"
    else:
        up = f"{_fmt(r['unit_price'])}EUR/{r['unit']}"
    return (
        f"{r['id']} | {r['name']} | {_fmt(r['total'])}EUR total | {up} | "
        f"{r['size']}{r['size_format']} | {r['category']} | {r['url']} | "
        f"ref={r['ref']}EUR/{r['ref_format']} src={r['unit_src']}"
    )


def to_clean_txt(items: list[dict]) -> str:
    rows = []
    fuentes = calculados = incompletos = 0
    for p in items:
        if "_errors" in p:
            continue
        p = to_common(p)
        try:
            r = normalize_record(p)
            NormalizedProduct.model_validate(r)  # contrato Pydantic: deja rastro si no cuadra
            if r["unit_price"] is None:
                incompletos += 1
            elif r["unit_src"] == "fuente":
                fuentes += 1
            else:
                calculados += 1
            rows.append(format_record(r))
        except ValidationError as e:
            pid = p.get("id", "?") if isinstance(p, dict) else "?"
            rows.append(f"ERROR id={pid}: validacion: {_validacion_msg(e)}")
        except Exception as e:
            rows.append(f"ERROR id={p.get('id', '?')}: {e}")
    head = [
        f"Items: {len(items)}",
        f"Unitarios: {fuentes + calculados} (fuente {fuentes}, calculado {calculados}) | Incompletos: {incompletos}",
        "---",
    ]
    return "\n".join(head + rows) + "\n"


def _unwrap(data) -> list[dict]:
    items = data if isinstance(data, list) else data.get("items", [data])
    out = []
    for it in items:
        out.append(it.get("product", it) if isinstance(it, dict) else it)
    return out


def main():
    from flask import request, Response
    import json

    raw = request.get_data(cache=False)
    try:
        data = json.loads(raw or b"null")
    except Exception:
        return Response("Body debe ser JSON: dict producto, envelope {product:...} o {\"items\": [...]}", status=400, mimetype="text/plain")

    items = _unwrap(data)

    # Variante estructurada (opt-in): POST /normalize?format=json -> CleanBatch.
    if str(request.args.get("format", "")).lower() == "json":
        wh = (data.get("wh") if isinstance(data, dict) else None) or "default"
        ts = data.get("ts") if isinstance(data, dict) else None
        try:
            out = to_clean_json(items, wh=wh, ts=ts)
        except ValidationError as e:
            return Response(f"ERROR de validacion: {_validacion_msg(e)}", status=422, mimetype="text/plain")
        return Response(json.dumps(out, ensure_ascii=False), mimetype="application/json")

    return Response(to_clean_txt(items), mimetype="text/plain")
