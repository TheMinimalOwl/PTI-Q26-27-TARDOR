"""Generador del dataset de prueba del prototipo de RAG.

Por que datos sinteticos y no los reales de Mercadona:
- El repo del scrapeador no versiona los `.txt` (estan en `out/` con
  `.gitignore`), asi que el dataset real no esta disponible en el repo.
- Los datos sinteticos se generan **en el mismo formato de linea limpia** que
  produce el normalizador (mismo separador, mismos campos, mismos motivos de
  incompletitud), de modo que cuando el equipo de ingesta comparta el `.txt`
  real este pipeline lo consume sin tocar una linea.
- Ademas permiten tener *ground truth* exacto: sabemos que dos productos son
  el mismo y cuales no, cosa que con datos reales habria que etiquetar a mano.

El generador es determinista (semilla fija): el dataset no cambia entre
ejecuciones, asi que las metricas son comparables.

Uso:
    python -m data.generate_dataset          # escribe data/raw y data/gold
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RAW_DIR = RAIZ / "data" / "raw"
GOLD_DIR = RAIZ / "data" / "gold"

SEMILLA = 20261021
SEPARADOR = " | "

# Formatos -> (unidad base canonica, factor). Copia de `UNITS` del normalizador
# (rama `scrapping`): el generador tiene que aplicar la MISMA conversion para
# que el dato sintetico sea indistinguible del real.
UNITS: dict[str, tuple[str, Decimal]] = {
    "kg": ("kg", Decimal("1")),
    "g": ("kg", Decimal("0.001")),
    "100 g": ("kg", Decimal("0.1")),
    "l": ("l", Decimal("1")),
    "ml": ("l", Decimal("0.001")),
    "cl": ("l", Decimal("0.01")),
    "100 ml": ("l", Decimal("0.1")),
    "ud": ("ud", Decimal("1")),
    "u": ("ud", Decimal("1")),
    "dc": ("ud", Decimal("12")),
    "dz": ("ud", Decimal("12")),
    "m": ("m", Decimal("1")),
    "lv": ("lavado", Decimal("1")),
}

CADENAS = ("mercadona", "carrefour", "alcampo")

# Marca propia de cada cadena. Los productos de marca compartida (Bimbo,
# Valor...) se llaman igual en todas: son el caso dificil, porque el vector
# no puede apoyarse en la marca para decidir la equivalencia.
MARCAS_PROPIAS = {
    "mercadona": "Hacendado",
    "carrefour": "Carrefour",
    "alcampo": "Alcampo",
}

# Productos de marca compartida (mismo nombre en todas las cadenas).
MARCAS_COMPARTIDAS = {
    "pan-molde-blanco": "Bimbo",
    "chocolate-leche": "Valor",
    "cerveza-rubia": "Mahou",
    "agua-mineral": "Lanjaron",
    "papel-higienico": "Scott",
}


@dataclass(frozen=True)
class Canonico:
    """Producto canonico: el mismo producto vendido en varias cadenas."""

    key: str
    nombre: str
    categoria: str
    size: str          # texto del tamaño tal y como lo da la fuente
    size_fmt: str      # formato de la fuente (clave de UNITS)
    total: str         # precio del envase
    ref_fmt: str       # formato de referencia de la fuente ("" = no hay ref)
    ref: str           # precio de referencia de la fuente ("-" si no hay)
    ref_unit: str      # unidad canonica esperada (para sanity check)


def _lookup_unit(fmt: str) -> tuple[str, Decimal]:
    """Normaliza el formato de la fuente igual que `_unit()` del normalizador.

    La fuente manda el formato en mayusculas ("L", "KG", "UD", "LV"); el
    normalizador lo pasa a minusculas antes de buscarlo en `UNITS`.
    """
    key = " ".join(str(fmt or "").split()).lower()
    return UNITS[key]


def _up(ref: str, ref_fmt: str) -> tuple[Decimal, str]:
    """Precio unitario canonico a partir del precio de referencia de la fuente."""
    base, factor = _lookup_unit(ref_fmt)
    return (Decimal(ref) / factor), base


# Catalogo canonico. `ref`/`ref_fmt` reproducen lo que manda la fuente:
# precio por la unidad de referencia ("12.500" por "L", "0.460" por "100 g"...)
CATALOGO: tuple[Canonico, ...] = (
    # -- Aceites, especias y salsas
    Canonico("aceite-oliva-ve-1l", "Aceite de oliva virgen extra", "Aceites, especias y salsas", "1", "l", "12.50", "L", "12.500", "l"),
    Canonico("aceite-oliva-ve-05l", "Aceite de oliva virgen extra", "Aceites, especias y salsas", "0.5", "l", "6.80", "L", "13.600", "l"),
    Canonico("aceite-oliva-suave-1l", "Aceite de oliva suave", "Aceites, especias y salsas", "1", "l", "7.20", "L", "7.200", "l"),
    Canonico("aceite-girasol-1l", "Aceite de girasol", "Aceites, especias y salsas", "1", "l", "2.40", "L", "2.400", "l"),
    Canonico("vinagre-vino-1l", "Vinagre de vino blanco", "Aceites, especias y salsas", "1", "l", "1.60", "L", "1.600", "l"),
    Canonico("salsa-soja-025l", "Salsa de soja", "Aceites, especias y salsas", "0.25", "l", "2.10", "L", "8.400", "l"),
    Canonico("mayonesa-04l", "Mayonesa", "Aceites, especias y salsas", "0.4", "l", "4.30", "L", "10.750", "l"),
    Canonico("mostaza-025l", "Mostaza", "Aceites, especias y salsas", "0.25", "l", "1.90", "L", "7.600", "l"),
    Canonico("sal-marina-1kg", "Sal marina fina", "Aceites, especias y salsas", "1", "kg", "0.85", "KG", "0.850", "kg"),
    Canonico("azucar-blanco-1kg", "Azúcar blanco", "Aceites, especias y salsas", "1", "kg", "1.10", "KG", "1.100", "kg"),
    Canonico("harina-trigo-1kg", "Harina de trigo", "Aceites, especias y salsas", "1", "kg", "1.05", "KG", "1.050", "kg"),
    Canonico("cafe-molido-250g", "Café molido natural", "Aceites, especias y salsas", "250", "g", "3.50", "100 g", "1.400", "kg"),
    # -- Leche y yogures
    Canonico("leche-entera-1l", "Leche entera", "Leche y yogures", "1", "l", "1.15", "L", "1.150", "l"),
    Canonico("leche-semidesnatada-1l", "Leche semidesnatada", "Leche y yogures", "1", "l", "1.10", "L", "1.100", "l"),
    Canonico("leche-desnatada-1l", "Leche desnatada", "Leche y yogures", "1", "l", "1.10", "L", "1.100", "l"),
    Canonico("yogur-natural-500g", "Yogur natural", "Leche y yogures", "500", "g", "2.20", "KG", "4.400", "kg"),
    Canonico("yogur-fresa-125g", "Yogur de fresa", "Leche y yogures", "125", "g", "0.65", "100 g", "0.520", "kg"),
    Canonico("queso-curado-250g", "Queso curado semicurado", "Leche y yogures", "250", "g", "4.50", "KG", "18.000", "kg"),
    Canonico("mozzarella-125g", "Queso mozzarella", "Leche y yogures", "125", "g", "1.60", "100 g", "1.280", "kg"),
    Canonico("mantequilla-250g", "Mantequilla", "Leche y yogures", "250", "g", "2.30", "KG", "9.200", "kg"),
    Canonico("nata-cocinar-500ml", "Nata para cocinar", "Leche y yogures", "500", "ml", "1.70", "L", "3.400", "l"),
    Canonico("batido-chocolate-1l", "Batido de chocolate", "Leche y yogures", "1", "l", "1.90", "L", "1.900", "l"),
    Canonico("flan-vainilla-4ud", "Flan de vainilla", "Leche y yogures", "4", "ud", "1.80", "UD", "0.450", "ud"),
    # -- Panaderia
    Canonico("pan-molde-integral-600g", "Pan de molde integral", "Panadería", "600", "g", "2.40", "KG", "4.000", "kg"),
    Canonico("barra-pan-rustica-250g", "Barra de pan rústica", "Panadería", "250", "g", "1.20", "KG", "4.800", "kg"),
    Canonico("pan-molde-blanco-600g", "Pan de molde blanco", "Panadería", "600", "g", "1.80", "KG", "3.000", "kg"),
    Canonico("magdalenas-12ud", "Magdalenas", "Panadería", "12", "ud", "1.50", "UD", "0.125", "ud"),
    Canonico("croissant-mantequilla-55g", "Croissant de mantequilla", "Panadería", "55", "g", "0.35", "100 g", "0.636", "kg"),
    Canonico("donut-chocolate-1ud", "Donut de chocolate", "Panadería", "1", "ud", "0.45", "UD", "0.450", "ud"),
    # -- Cereales y desayuno
    Canonico("copos-avena-500g", "Copos de avena", "Cereales y desayuno", "500", "g", "1.60", "KG", "3.200", "kg"),
    Canonico("cereales-chocolate-500g", "Cereales con chocolate", "Cereales y desayuno", "500", "g", "2.30", "100 g", "0.460", "kg"),
    Canonico("corn-flakes-500g", "Corn flakes", "Cereales y desayuno", "500", "g", "2.10", "KG", "4.200", "kg"),
    Canonico("mermelada-fresa-300g", "Mermelada de fresa", "Cereales y desayuno", "300", "g", "2.40", "KG", "8.000", "kg"),
    Canonico("miel-1kg", "Miel", "Cereales y desayuno", "1", "kg", "6.50", "KG", "6.500", "kg"),
    # -- Conservas
    Canonico("atun-aceite-3ud", "Atún claro en aceite de oliva", "Conservas", "3", "ud", "2.30", "UD", "0.767", "ud"),
    Canonico("gulas-caseras-400g", "Gulas caseras", "Conservas", "400", "g", "3.50", "KG", "8.750", "kg"),
    Canonico("tomate-triturado-400g", "Tomate triturado", "Conservas", "400", "g", "1.40", "KG", "3.500", "kg"),
    Canonico("alubias-cocidas-570g", "Alubias cocidas", "Conservas", "570", "g", "1.35", "KG", "2.368", "kg"),
    Canonico("atun-salmuera-3ud", "Atún en salmuera", "Conservas", "3", "ud", "2.60", "UD", "0.867", "ud"),
    Canonico("sardinas-aceite-120g", "Sardinas en aceite de oliva", "Conservas", "120", "g", "1.80", "KG", "15.000", "kg"),
    Canonico("maiz-duce-300g", "Maíz dulce", "Conservas", "300", "g", "1.20", "KG", "4.000", "kg"),
    Canonico("aceitunas-verdes-250g", "Aceitunas verdes rellenas", "Conservas", "250", "g", "2.90", "KG", "11.600", "kg"),
    # -- Bebidas
    Canonico("agua-mineral-15l", "Agua mineral", "Bebidas", "1.5", "l", "0.45", "L", "0.300", "l"),
    Canonico("agua-gas-15l", "Agua con gas", "Bebidas", "1.5", "l", "0.75", "L", "0.500", "l"),
    Canonico("zumo-naranja-1l", "Zumo de naranja 100%", "Bebidas", "1", "l", "1.90", "L", "1.900", "l"),
    Canonico("zumo-manzana-1l", "Zumo de manzana", "Bebidas", "1", "l", "1.40", "L", "1.400", "l"),
    Canonico("refresco-cola-2l", "Refresco de cola", "Bebidas", "2", "l", "2.10", "L", "1.050", "l"),
    Canonico("cerveza-rubia-33cl", "Cerveza rubia", "Bebidas", "0.33", "l", "0.90", "L", "2.727", "l"),
    Canonico("vino-tinto-1l", "Vino tinto D.O.", "Bebidas", "1", "l", "6.50", "L", "6.500", "l"),
    Canonico("tonica-1l", "Tónica", "Bebidas", "1", "l", "1.30", "L", "1.300", "l"),
    # -- Dulces y snacks
    Canonico("patatas-fritas-150g", "Patatas fritas", "Dulces y snacks", "150", "g", "1.70", "KG", "11.333", "kg"),
    Canonico("cacahuetes-200g", "Cacahuetes salados", "Dulces y snacks", "200", "g", "1.50", "KG", "7.500", "kg"),
    Canonico("chocolate-leche-125g", "Chocolate con leche", "Dulces y snacks", "125", "g", "1.60", "100 g", "1.280", "kg"),
    Canonico("galletas-chocolate-300g", "Galletas de chocolate", "Dulces y snacks", "300", "g", "1.20", "KG", "4.000", "kg"),
    Canonico("chucherias-150g", "Chucherías surtidas", "Dulces y snacks", "150", "g", "1.80", "KG", "12.000", "kg"),
    Canonico("kikos-70g", "Kikos", "Dulces y snacks", "70", "g", "1.10", "KG", "15.714", "kg"),
    Canonico("chicle-menta-1ud", "Chicle de menta", "Dulces y snacks", "1", "ud", "0.15", "UD", "0.150", "ud"),
    # -- Limpieza
    Canonico("detergente-liquido-40lav", "Detergente líquido", "Limpieza", "40", "lv", "9.50", "LV", "0.238", "lavado"),
    Canonico("lejia-2l", "Lejía perfumada", "Limpieza", "2", "l", "2.10", "L", "1.050", "l"),
    Canonico("limpiacristales-750ml", "Limpiacristales", "Limpieza", "750", "ml", "1.60", "L", "2.133", "l"),
    Canonico("suavizante-1l", "Suavizante concentrado", "Limpieza", "1", "l", "3.20", "L", "3.200", "l"),
    Canonico("jabon-manos-500ml", "Jabón de manos", "Limpieza", "500", "ml", "2.40", "L", "4.800", "l"),
    Canonico("lavavajillas-750ml", "Lavavajillas concentrado", "Limpieza", "750", "ml", "2.80", "L", "3.733", "l"),
    Canonico("papel-higienico-12ud", "Papel higiénico", "Limpieza", "12", "ud", "3.20", "UD", "0.267", "ud"),
    Canonico("rollo-cocina-2ud", "Rollo de cocina", "Limpieza", "2", "ud", "1.90", "UD", "0.950", "ud"),
    Canonico("bayeta-microfibra-5ud", "Bayeta de microfibra", "Limpieza", "5", "ud", "2.50", "UD", "0.500", "ud"),
    Canonico("bolsas-basura-20ud", "Bolsas de basura", "Limpieza", "20", "ud", "1.40", "UD", "0.070", "ud"),
    Canonico("limpiador-multiusos-1l", "Limpiador multiusos", "Limpieza", "1", "l", "1.80", "L", "1.800", "l"),
    # -- Frutas y verduras
    Canonico("platano-canarias-1kg", "Plátano de Canarias", "Frutas y verduras", "1", "kg", "2.10", "KG", "2.100", "kg"),
    Canonico("manzana-golden-1kg", "Manzana golden", "Frutas y verduras", "1", "kg", "2.40", "KG", "2.400", "kg"),
    Canonico("tomate-pera-1kg", "Tomate pera", "Frutas y verduras", "1", "kg", "2.20", "KG", "2.200", "kg"),
    Canonico("lechuga-iceberg-1ud", "Lechuga iceberg", "Frutas y verduras", "1", "ud", "1.20", "UD", "1.200", "ud"),
    Canonico("patatas-25kg", "Patatas", "Frutas y verduras", "2.5", "kg", "2.00", "KG", "0.800", "kg"),
    Canonico("zanahoria-1kg", "Zanahoria", "Frutas y verduras", "1", "kg", "1.70", "KG", "1.700", "kg"),
    Canonico("limones-1kg", "Limones", "Frutas y verduras", "1", "kg", "1.90", "KG", "1.900", "kg"),
    Canonico("aguacates-4ud", "Aguacates", "Frutas y verduras", "4", "ud", "3.50", "UD", "0.875", "ud"),
    Canonico("cebollas-1kg", "Cebollas", "Frutas y verduras", "1", "kg", "1.50", "KG", "1.500", "kg"),
    # -- Congelados
    Canonico("guisantes-1kg", "Guisantes congelados", "Congelados", "1", "kg", "2.60", "KG", "2.600", "kg"),
    Canonico("merluza-filetes-400g", "Merluza en filetes", "Congelados", "400", "g", "5.50", "KG", "13.750", "kg"),
    Canonico("pizza-cuatro-quesos-350g", "Pizza cuatro quesos", "Congelados", "350", "g", "2.90", "KG", "8.286", "kg"),
    Canonico("patatas-prefritas-1kg", "Patatas prefritas congeladas", "Congelados", "1", "kg", "3.20", "KG", "3.200", "kg"),
    # -- Mascotas
    Canonico("comida-perros-3kg", "Comida para perros", "Mascotas", "3", "kg", "6.50", "KG", "2.167", "kg"),
    Canonico("comida-gatos-15kg", "Comida para gatos", "Mascotas", "1.5", "kg", "4.20", "KG", "2.800", "kg"),
)

# Variantes con otro formato: el mismo producto en otra presentacion. **No son
# equivalentes** y son el caso dificil del retrieval (el nombre es casi igual).
VARIANTES: tuple[tuple[str, str, str, str], ...] = (
    # (key canonico, cadena, size, size_fmt)
    ("flan-vainilla-4ud", "carrefour", "8", "ud"),
    ("atun-aceite-3ud", "carrefour", "6", "ud"),
    ("papel-higienico-12ud", "alcampo", "24", "ud"),
    ("bolsas-basura-20ud", "carrefour", "30", "ud"),
    ("aguacates-4ud", "alcampo", "6", "ud"),
    ("aceite-oliva-ve-1l", "carrefour", "0.75", "l"),
    ("leche-entera-1l", "alcampo", "0.5", "l"),
    ("detergente-liquido-40lav", "alcampo", "60", "lv"),
)

# Productos a los que se les quita el precio de referencia de la fuente: el
# normalizador cae al respaldo (`src=calculado`) y el precio unitario se
# calcula desde precio y tamano. Ejercita ese camino del contrato.
SIN_REFERENCIA = {"detergente-liquido-40lav", "bolsas-basura-20ud", "kikos-70g"}

# Un par sin precio: el normalizador lo marca como incompleto
# (`- (sin_precio)`). El pipeline debe tolerarlo.
SIN_PRECIO = {"chicle-menta-1ud"}


# ---------------------------------------------------------------------------
# Utilidades de formato (espejo de `normalizer.py`)
# ---------------------------------------------------------------------------


def fmt_dec(v: Decimal | None) -> str:
    """Formatea un importe como hace `_fmt` del normalizador."""
    if v is None:
        return "-"
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    ent, _, dec = s.partition(".")
    if len(dec) < 2:
        dec = (dec + "00")[:2]
    return f"{ent}.{dec}"


def fmt_precio_unitario(up: Decimal, unit: str) -> str:
    return f"{fmt_dec(up)}EUR/{unit}"


# ---------------------------------------------------------------------------
# Construccion del dataset
# ---------------------------------------------------------------------------


def nombre_para(canonico: Canonico, chain: str, index: int) -> str:
    """Nombre de|display del producto en una cadena.

    Simula lo que hace cada cadena con el mismo producto: cambia la marca
    propia, abrevia ("Aceite de oliva" -> "Aceite oliva") y a veces mete
    coletillas. El nombre **no** lleva el precio ni el formato: eso va aparte.
    """
    marca = MARCAS_COMPARTIDAS.get(canonico.key) or MARCAS_PROPIAS[chain]
    base = f"{canonico.nombre} {marca}"
    if chain == "carrefour" and index % 7 == 0:
        base = base.replace(" de ", " ")
    if chain == "alcampo" and index % 11 == 0:
        base = base.replace("virgen extra", "virgen extra.")
    return base


def precio_para(canonico: Canonico, chain: str, rng: random.Random) -> str:
    """Precio total del envase, con la politica de precios de cada cadena."""
    base = Decimal(canonico.total)
    factor = {"mercadona": Decimal("1.00"), "carrefour": Decimal("0.94"), "alcampo": Decimal("0.97")}[chain]
    jitter = Decimal(str(rng.uniform(-0.02, 0.02)))
    return str((base * factor * (Decimal("1") + jitter)).quantize(Decimal("0.01")))


def construir() -> tuple[dict[str, list[str]], list[dict]]:
    """Devuelve (lineas por cadena, productos con su metadato canonico)."""
    rng = random.Random(SEMILLA)
    lineas: dict[str, list[str]] = {c: [] for c in CADENAS}
    productos: list[dict] = []
    pid = 10000

    for index, canonico in enumerate(CATALOGO):
        for chain in CADENAS:
            pid += 1
            nombre = nombre_para(canonico, chain, index)
            total = precio_para(canonico, chain, rng)

            if canonico.key in SIN_PRECIO:
                # Linea incompleta: sin precio y con motivo.
                lineas[chain].append(
                    SEPARADOR.join(
                        [
                            str(pid),
                            nombre,
                            "-EUR total",
                            "- (sin_precio)",
                            f"{canonico.size}{canonico.size_fmt}",
                            canonico.categoria,
                            f"https://tienda.{chain}.es/product/{pid}",
                            "ref=-EUR/- src=-",
                        ]
                    )
                )
                productos.append(
                    {
                        "pid": str(pid),
                        "chain": chain,
                        "key": canonico.key,
                        "nombre": nombre,
                        "categoria": canonico.categoria,
                        "size": canonico.size,
                        "size_fmt": canonico.size_fmt,
                        "total": None,
                        "unit_price": None,
                        "unit": None,
                        "incompleto": True,
                    }
                )
                continue

            if canonico.key in SIN_REFERENCIA:
                # Sin precio de referencia: el normalizador calcula el unitario.
                base, factor = _lookup_unit(canonico.size_fmt)
                up = (Decimal(total) / (Decimal(canonico.size) * factor)).quantize(Decimal("0.0001"))
                unit, unit_src, ref, ref_fmt = base, "calculado", "-", ""
            else:
                up, unit = _up(canonico.ref, canonico.ref_fmt)
                unit_src, ref, ref_fmt = "fuente", canonico.ref, canonico.ref_fmt

            up_str = fmt_precio_unitario(up, unit)
            lineas[chain].append(
                SEPARADOR.join(
                    [
                        str(pid),
                        nombre,
                        f"{fmt_dec(Decimal(total))}EUR total",
                        up_str,
                        f"{canonico.size}{canonico.size_fmt}",
                        canonico.categoria,
                        f"https://tienda.{chain}.es/product/{pid}",
                        f"ref={ref}EUR/{ref_fmt} src={unit_src}",
                    ]
                )
            )
            productos.append(
                {
                    "pid": str(pid),
                    "chain": chain,
                    "key": canonico.key,
                    "nombre": nombre,
                    "categoria": canonico.categoria,
                    "size": canonico.size,
                    "size_fmt": canonico.size_fmt,
                    "total": str(Decimal(total)),
                    "unit_price": str(up),
                    "unit": unit,
                    "incompleto": False,
                }
            )

    # Variantes con otro formato (caso duro: NO son equivalentes).
    for key, chain, size, size_fmt in VARIANTES:
        canonico = next(c for c in CATALOGO if c.key == key)
        pid += 1
        nombre = f"{canonico.nombre} {MARCAS_PROPIAS[chain]}"
        total = str((Decimal(canonico.total) * Decimal("1.35")).quantize(Decimal("0.01")))
        base, factor = _lookup_unit(size_fmt)
        up = (Decimal(total) / (Decimal(size) * factor)).quantize(Decimal("0.0001"))
        lineas[chain].append(
            SEPARADOR.join(
                [
                    str(pid),
                    nombre,
                    f"{fmt_dec(Decimal(total))}EUR total",
                    fmt_precio_unitario(up, base),
                    f"{size}{size_fmt}",
                    canonico.categoria,
                    f"https://tienda.{chain}.es/product/{pid}",
                    f"ref=-EUR/- src=calculado",
                ]
            )
        )
        productos.append(
            {
                "pid": str(pid),
                "chain": chain,
                "key": key,
                "nombre": nombre,
                "categoria": canonico.categoria,
                "size": size,
                "size_fmt": size_fmt,
                "total": total,
                "unit_price": str(up),
                "unit": base,
                "incompleto": False,
                "variante": True,
            }
        )

    return lineas, productos


def escribir_raw(lineas: dict[str, list[str]]) -> None:
    """Escribe los ficheros de lineas limpias (una por cadena)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for chain, rows in lineas.items():
        cuerpo = "\n".join(rows)
        pids = [r.split(SEPARADOR)[0] for r in rows]
        # Reparto de "fuente" / "calculado" para que la cabecera cuadre.
        fuente = sum(1 for r in rows if "src=fuente" in r)
        calculado = sum(1 for r in rows if "src=calculado" in r)
        incompletos = sum(1 for r in rows if "- (" in r)
        cabecera = [
            f"Items: {len(rows)}",
            f"Unitarios: {fuente + calculado} (fuente {fuente}, calculado {calculado}) | Incompletos: {incompletos}",
            "---",
        ]
        (RAW_DIR / f"{chain}_clean.txt").write_text(
            "\n".join(cabecera + rows) + "\n", encoding="utf-8"
        )
        _ = pids


def escribir_gold(productos: list[dict]) -> None:
    """Escribe el ground truth: equivalencias, no-equivalencias, catalogo y QA."""
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    por_key: dict[str, list[dict]] = {}
    for p in productos:
        por_key.setdefault(p["key"], []).append(p)

    # -- equivalencias: el mismo producto en cada cadena -----------------
    with (GOLD_DIR / "equivalencias.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "cadena", "pid", "nombre", "total", "unit_price", "unit"])
        for key, prods in sorted(por_key.items()):
            for p in sorted(prods, key=lambda x: x["chain"]):
                if p.get("variante"):
                    continue
                w.writerow(
                    [
                        key,
                        p["chain"],
                        p["pid"],
                        p["nombre"],
                        p["total"],
                        p["unit_price"],
                        p["unit"],
                    ]
                )

    # -- no equivalencias: variantes de formato ---------------------------
    with (GOLD_DIR / "no_equivalentes.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pid_origen", "pid_destino", "key", "cadena_destino", "motivo"])
        for p in productos:
            if not p.get("variante"):
                continue
            origen = next(
                (q for q in por_key[p["key"]] if not q.get("variante") and q["chain"] != p["chain"]),
                None,
            )
            if origen:
                w.writerow(
                    [
                        origen["pid"],
                        p["pid"],
                        p["key"],
                        p["chain"],
                        f"formato distinto: {origen['size']}{origen['size_fmt']} vs {p['size']}{p['size_fmt']}",
                    ]
                )

    # -- catalogo: consultas en lenguaje natural con su pid esperado ------
    consultas = []
    for key, prods in sorted(por_key.items()):
        base = next(p for p in prods if not p.get("variante"))
        canonico = next(c for c in CATALOGO if c.key == key)
        etiqueta = f"{canonico.nombre.lower()} {canonico.size} {canonico.size_fmt}"
        esperados = [p["pid"] for p in sorted(prods, key=lambda x: x["chain"]) if not p.get("variante")]
        consultas.append(
            {
                "query": etiqueta,
                "expected_ids": esperados,
                "category": canonico.categoria,
                "note": "el mismo producto en las tres cadenas",
            }
        )
    # Consultas que discriminan por cadena.
    for key, prods in sorted(por_key.items()):
        canonico = next(c for c in CATALOGO if c.key == key)
        p = next((q for q in prods if q["chain"] == "mercadona" and not q.get("variante")), None)
        if p:
            consultas.append(
                {
                    "query": f"{canonico.nombre.lower()} de mercadona",
                    "expected_ids": [p["pid"]],
                    "category": canonico.categoria,
                    "note": "filtra por cadena",
                }
            )
    (GOLD_DIR / "catalogo.json").write_text(
        json.dumps(consultas, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # -- QA: preguntas con respuesta verificable --------------------------
    preguntas = []
    for key, prods in sorted(por_key.items()):
        canonico = next(c for c in CATALOGO if c.key == key)
        completos = [p for p in prods if not p.get("variante") and not p.get("incompleto")]
        if len(completos) < 2:
            continue

        def _pregunta(titulo: str, campo: str, nota: str) -> dict:
            """Genera la pregunta de minimo con su ground truth.

            Ojo con los empates: el **precio unitario** viene del precio de
            referencia de la fuente, que es el mismo en las tres cadenas, asi
            que "el mas barato por unidad" suele ser un empate de tres. El
            ground truth tiene que aceptar **todas** las cadenas empatadas:
            si no, se marca como fallo una respuesta que es correcta.
            """
            minimo = min(Decimal(p[campo]) for p in completos)
            empatados = [p for p in completos if Decimal(p[campo]) == minimo]
            valor = f"{minimo:.2f}"
            return {
                "question": f"¿Cuál es el {canonico.nombre.lower()} {titulo}?",
                "expected_pids": [p["pid"] for p in empatados],
                "expected_contains": [
                    [valor, valor.replace(".", ",")],
                    sorted({p["chain"] for p in empatados}),
                ],
                "note": nota,
            }

        preguntas.append(
            _pregunta("más barato por unidad", "unit_price", "precio unitario minimo entre cadenas")
        )
        preguntas.append(
            _pregunta("más barato en total", "total", "precio total minimo entre cadenas")
        )

    # Preguntas agregadas por categoria con umbral de precio.
    por_categoria: dict[str, list[dict]] = {}
    for p in productos:
        if p.get("variante") or p.get("incompleto"):
            continue
        por_categoria.setdefault(p["categoria"], []).append(p)
    for categoria, prods in sorted(por_categoria.items()):
        baratos = [p for p in prods if Decimal(p["total"]) < Decimal("2.00")]
        if len(baratos) >= 3:
            preguntas.append(
                {
                    "question": f"¿Qué productos de {categoria.lower()} cuestan menos de 2 EUR?",
                    "expected_pids": [p["pid"] for p in baratos],
                    "expected_contains": [],
                    "note": "pregunta agregada con filtro de precio",
                }
            )
    (GOLD_DIR / "qa.json").write_text(
        json.dumps(preguntas, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    lineas, productos = construir()
    escribir_raw(lineas)
    escribir_gold(productos)
    total = sum(len(v) for v in lineas.values())
    print(f"dataset generado: {total} productos en {len(lineas)} cadenas")
    for chain, rows in lineas.items():
        print(f"  {chain}: {len(rows)} lineas -> data/raw/{chain}_clean.txt")
    print(f"  gold: {len(list(GOLD_DIR.glob('*')))} ficheros en data/gold/")


if __name__ == "__main__":
    main()
