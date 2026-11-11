"""Prueba del adaptador de Consum (`from_consum`). `python test_consum.py`

1. Casos fijos sacados de productos reales de la API de Consum (11/11/2026): uno por cada
   `unitPriceUnitType` observado, con oferta, con pack "N x tamano" y sin tamano.
2. Si hay un volcado real (`scrappers/scrapper_consum/out/consum_*.txt`), lo normaliza
   entero y comprueba que no hay errores y que todo sale con precio unitario de la fuente.
"""

import ast
from decimal import Decimal
from pathlib import Path

from normalizer import from_consum, normalize_record, to_clean_json, to_clean_txt, to_common


def consum(code, name, desc, amount, unit_amount, unit_type, offer=None, cat="Cat", ptype=""):
    prices = [{"id": "PRICE", "value": {"centAmount": amount, "centUnitAmount": unit_amount}}]
    if offer:
        prices.append({"id": "OFFER_PRICE", "value": {"centAmount": offer[0], "centUnitAmount": offer[1]}})
    return {
        "id": 900000 + int(code), "code": str(code), "ean": "8400000000000",
        "productData": {"name": name, "description": desc,
                        "url": f"https://tienda.consum.es/es/p/x/{code}", "brand": {"name": "MARCA"}},
        "priceData": {"prices": prices, "priceUnitType": ptype, "unitPriceUnitType": unit_type},
        "categories": [{"id": 1, "name": cat, "type": 0}],
    }


CASES = [
    # (producto, total esperado, unitario esperado, unidad, tamano esperado)
    (consum(1669, "Rabanito Bolsa", "Rabanito Bolsa 250 Gr", 1.3, 5.2, "1 Kg"), "1.30", "5.20", "kg", Decimal("250")),
    (consum(2001, "Leche Entera", "Leche Entera Brik 1 L", 0.95, 0.95, "1 L"), "0.95", "0.95", "l", Decimal("1")),
    (consum(2002, "Gel de Ducha", "Gel de Ducha 750 ml", 2.4, 0.32, "100 ml"), "2.40", "3.20", "l", Decimal("750")),
    (consum(2003, "Orégano", "Orégano Bote 15 Gr", 1.1, 0.73, "100 Gr"), "1.10", "7.30", "kg", Decimal("15")),
    (consum(2004, "Lechuga", "Lechuga Iceberg 1 U", 0.89, 0.89, "1 U"), "0.89", "0.89", "ud", Decimal("1")),
    (consum(2005, "Detergente", "Detergente Líquido 40 Lv", 6.5, 0.16, "1 Lv"), "6.50", "0.16", "lavado", Decimal("40")),
    (consum(2006, "Huevos", "Huevos Camperos 1 Dc", 3.2, 3.2, "1 Dc"), "3.20", "0.2667", "ud", Decimal("1")),
    (consum(2007, "Aluminio", "Aluminio 30 M", 2.25, 0.08, "1 M"), "2.25", "0.08", "m", Decimal("30")),
    (consum(2008, "Pastillas Lavavajillas", "Pastillas Lavavajillas Clásicas 50 Do", 3.75, 0.08, "1 Do"), "3.75", "0.08", "ud", Decimal("50")),
    # oferta: manda OFFER_PRICE (lo que paga el cliente)
    (consum(2009, "Lentejas a La Riojana", "Lentejas a La Riojana Bote 425 Gr", 2.35, 5.53, "1 Kg", offer=(2.0, 4.71)),
     "2.00", "4.71", "kg", Decimal("425")),
    # pack: el tamano es N x unidad
    (consum(2010, "Yogur Sabor Limón", "Yogur Sabor Limón Pack de 4 Unidades 4 x 120 Gr", 1.2, 2.5, "1 Kg"),
     "1.20", "2.50", "kg", Decimal("480")),
    # sin tamano en la descripcion (fruta a granel): el precio de la fuente basta
    (consum(2011, "Manzana Fuji", "Manzana Fuji", 2.49, 2.49, "1 Kg", ptype="kg"), "2.49", "2.49", "kg", None),
]


def check_cases() -> None:
    for p, total, up, unit, size in CASES:
        r = normalize_record(p)
        name = p["productData"]["name"]
        assert r["id"] == p["code"], (name, r["id"])
        assert r["name"] == name, (name, r["name"])
        assert f"{r['total']:.2f}" == total, (name, r["total"], total)
        assert r["unit_price"] == Decimal(up), (name, r["unit_price"], up)
        assert r["unit"] == unit and r["unit_src"] == "fuente", (name, r["unit"], r["unit_src"])
        assert r["category"] == "Cat" and r["url"].endswith(p["code"]), (name, r)
        got_size = from_consum(p)["price_instructions"].get("unit_size")
        assert got_size == size, (name, got_size, size)
    print(f"OK: {len(CASES)} casos fijos de Consum")


def check_shape() -> None:
    # Mercadona pasa tal cual; Consum se traduce; el JSON estructurado tambien acepta Consum.
    merc = {"id": 1, "display_name": "x", "price_instructions": {"unit_price": "1"}}
    assert to_common(merc) is merc
    out = to_clean_json([c[0] for c in CASES])
    assert out["batch"] == len(CASES) and len(out["items"]) == len(CASES)
    assert all(i["unit_src"] == "fuente" for i in out["items"])
    txt = to_clean_txt([c[0] for c in CASES])
    assert "Incompletos: 0" in txt and "ERROR" not in txt, txt
    # linea limpia: mismo formato que Mercadona (la parsea el writer de API/BD por " | ")
    assert "2009 | Lentejas a La Riojana | 2.00EUR total | 4.71EUR/kg | 425Gr | Cat | " in txt, txt
    assert "2011 | Manzana Fuji | 2.49EUR total | 2.49EUR/kg | - | Cat | " in txt, txt
    print("OK: forma comun, JSON (CleanBatch) y texto")


def check_dump() -> None:
    base = Path(__file__).resolve().parents[2] / "scrappers" / "scrapper_consum" / "out"
    dumps = sorted(base.glob("consum_*.txt"))
    if not dumps:
        print("(sin volcado real de Consum: me salto la parte 2)")
        return
    items = [ast.literal_eval(l[5:]) for l in dumps[-1].read_text(encoding="utf-8").splitlines()
             if l.startswith("raw: ")]
    txt = to_clean_txt(items)
    head = txt.splitlines()[:2]
    errores = [l for l in txt.splitlines() if l.startswith("ERROR")]
    assert not errores, errores[:5]
    assert f"Items: {len(items)}" == head[0], head
    assert head[1].endswith("Incompletos: 0") and "calculado 0" in head[1], head
    print(f"OK: volcado real {dumps[-1].name}: {len(items)} productos, {head[1]}")


if __name__ == "__main__":
    check_cases()
    check_shape()
    check_dump()
