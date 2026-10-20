"""Parseo de los mensajes del normalizador (no necesita BD)."""
import json
from decimal import Decimal

from app.ingest import parse_clean_line, parse_message

# Ejemplo real de flujo-entrada/docs/03-contratos-datos.md
LINE = ("4241 | Aceite de oliva 0,4º Hacendado | 17.25EUR total | 3.45EUR/l | 5.0l | "
        "Aceite, especias y salsas | https://tienda.mercadona.es/product/4241/x | ref=3.450EUR/L src=fuente")


def test_linea_completa():
    item = parse_clean_line(LINE)
    assert item.id == "4241"
    assert item.name == "Aceite de oliva 0,4º Hacendado"
    assert item.total == Decimal("17.25")
    assert item.unit_price == Decimal("3.45")
    assert item.unit == "l"
    assert item.unit_src == "fuente"
    assert (item.size, item.size_format) == ("5.0", "l")
    assert item.category == "Aceite, especias y salsas"


def test_linea_incompleta_guarda_el_motivo():
    line = "99 | Bolsa regalo | 1.00EUR total | - (sin_tamano) | - | Varios | https://x | ref=- src=-"
    item = parse_clean_line(line)
    assert item.unit_price is None and item.unit is None
    assert item.unit_reason == "sin_tamano"
    assert item.total == Decimal("1.00")


def test_barra_en_el_nombre_no_rompe_el_parseo():
    line = LINE.replace("Hacendado", "Hacendado | oferta")
    assert parse_clean_line(line).name == "Aceite de oliva 0,4º Hacendado | oferta"


def test_cabeceras_y_errores_se_ignoran():
    for line in ["Items: 50", "Unitarios: 50 (fuente 48, calculado 2) | Incompletos: 0", "---",
                 "ERROR id=7: validacion: falta precio"]:
        assert parse_clean_line(line) is None


def test_mensaje_texto():
    msg = {"source": "normalizer", "wh": "default", "ts": "2026-10-15T19:22:31+00:00", "batch": 1,
           "clean": f"Items: 1\nUnitarios: 1 (fuente 1, calculado 0) | Incompletos: 0\n---\n{LINE}"}
    batch = parse_message("scraper.mercadona.clean", json.dumps(msg).encode())
    assert batch.chain == "mercadona"
    assert [i.id for i in batch.items] == ["4241"]


def test_mensaje_json():
    msg = {"source": "normalizer", "wh": "default", "ts": "2026-10-15T19:22:31+00:00", "batch": 1,
           "items": [{"id": 4241, "name": "Aceite", "total": "17.25", "unit_price": "3.45", "unit": "l",
                      "unit_src": "fuente", "unit_reason": "", "ref": "3.450", "ref_format": "L",
                      "size": 5.0, "size_format": "l", "category": "Aceite", "url": ""}]}
    batch = parse_message("scraper.carrefour.clean", json.dumps(msg).encode())
    assert batch.chain == "carrefour"
    assert batch.items[0].id == "4241"
    assert batch.items[0].unit_price == Decimal("3.45")
