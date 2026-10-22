"""Tests del parser de lineas limpias.

El parser es la frontera con el equipo de ingesta: si el formato cambia, esto
falla. Por eso se prueba contra lineas reales del dataset generado y contra
casos limite inventados.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from rag.ingest import parse_clean_file, parse_clean_line, parse_clean_text

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

LINEA_REAL = (
    "10001 | Aceite de oliva virgen extra Hacendado | 12.52EUR total | 12.50EUR/l | "
    "1l | Aceites, especias y salsas | https://tienda.mercadona.es/product/10001 | "
    "ref=12.500EUR/L src=fuente"
)


def test_linea_completa():
    p = parse_clean_line(LINEA_REAL, chain="mercadona")
    assert p is not None
    assert p.id == "10001"
    assert p.name == "Aceite de oliva virgen extra Hacendado"
    assert p.total == Decimal("12.52")
    assert p.unit_price == Decimal("12.50")
    assert p.unit == "l"
    assert p.size == "1"
    assert p.size_format == "l"
    assert p.category == "Aceites, especias y salsas"
    assert p.url.endswith("/10001")
    assert p.ref == "12.500"
    assert p.ref_format == "L"
    assert p.unit_src == "fuente"
    assert p.chain == "mercadona"


def test_linea_calculada():
    linea = (
        "10166 | Kikos Hacendado | 1.10EUR total | 15.7143EUR/kg | 70g | Dulces y snacks | "
        "https://tienda.mercadona.es/product/10166 | ref=-EUR/ src=calculado"
    )
    p = parse_clean_line(linea)
    assert p.unit_src == "calculado"
    assert p.unit_price == Decimal("15.7143")
    assert p.unit == "kg"
    assert p.ref == "-"
    assert p.ref_format == ""


def test_linea_incompleta():
    linea = (
        "10169 | Chicle de menta Hacendado | -EUR total | - (sin_precio) | 1ud | Dulces y snacks | "
        "https://tienda.mercadona.es/product/10169 | ref=-EUR/- src=-"
    )
    p = parse_clean_line(linea)
    assert p.total is None
    assert p.unit_price is None
    assert p.unit is None
    assert p.unit_reason == "sin_precio"
    assert p.unit_src == "-"


def test_motivo_con_formato_no_comparable():
    linea = (
        "9 | Producto raro | 1.00EUR total | - (formato_no_comparable:banana) | 1ud | Cat | "
        "https://x.es/p/9 | ref=-EUR/- src=-"
    )
    p = parse_clean_line(linea)
    assert p.unit_reason == "formato_no_comparable:banana"


def test_cabecera_no_se_parsea_como_producto():
    for linea in (
        "Items: 50",
        "Unitarios: 50 (fuente 48, calculado 2) | Incompletos: 0",
        "---",
        "ERROR id=123: validacion: total: Field required",
    ):
        assert parse_clean_line(linea) is None


def test_nombre_con_separador():
    linea = (
        "1 | Aceite | de | oliva | 1.00EUR total | 1.00EUR/ud | 1ud | Cat | url | ref=-EUR/- src=-"
    )
    # 8 campos + el nombre partido: el parser reagrupa por la cola.
    p = parse_clean_line(linea)
    assert p is not None
    assert p.name == "Aceite | de | oliva"
    assert p.total == Decimal("1.00")


def test_linea_corta_se_ignora():
    assert parse_clean_line("1 | 2 | 3") is None


@pytest.mark.parametrize("fichero", ["mercadona_clean.txt", "carrefour_clean.txt", "alcampo_clean.txt"])
def test_dataset_generado_se_parsea_completo(fichero):
    path = RAW_DIR / fichero
    if not path.exists():
        pytest.skip("falta el dataset: python data/generate_dataset.py")
    prods, stats = parse_clean_file(path)
    assert stats.errores == 0
    assert stats.productos == len(prods)
    assert stats.productos > 50
    # Ningun producto debe quedarse sin nombre ni id.
    for p in prods:
        assert p.id
        assert p.name


def test_cabecera_cuadra_con_el_contenido():
    path = RAW_DIR / "mercadona_clean.txt"
    if not path.exists():
        pytest.skip("falta el dataset")
    texto = path.read_text(encoding="utf-8")
    prods, _ = parse_clean_text(texto)
    items = int(texto.splitlines()[0].split(":")[1])
    assert items == len(prods)
