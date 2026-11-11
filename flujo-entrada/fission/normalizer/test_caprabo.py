"""Prueba del adaptador de Caprabo (`from_caprabo`).
`python test_caprabo.py`

1. Casos fijos sacados de productos reales de capraboacasa.com (11/11/2026): con precio por
   unidad de la web ("1 KILO A 2,00 €"), sin el (se calcula con el tamano del nombre), packs,
   productos al peso, docenas y productos sin cantidad.
2. Si hay un volcado real (`scrappers/scrapper_caprabo/out/*.txt`), lo normaliza entero:
   sin errores, como mucho un 2 % incompleto, y el calculado coincide con la web en la
   inmensa mayoria de productos que traen los dos.
"""

import ast
from decimal import Decimal
from pathlib import Path

from normalizer import from_caprabo, normalize_record, to_clean_json, to_clean_txt, to_common


def ge(pid, name, price, unit_text="", cat="Cat", before=""):
    return {
        "platform": "caprabo", "id": str(pid), "name": name,
        "brand": "MARCA", "price": price, "price_now": f"{price:.2f}".replace(".", ","),
        "price_before": before, "unit_price_text": unit_text, "by_weight": "al peso" in name,
        "category": cat, "category_ids": ["1", "2", "3"],
        "url": f"https://www.capraboacasa.com/es/productdetail/{pid}-x/",
    }


CASES = [
    # (producto, unitario esperado, unidad, origen)
    (ge(13899893, "Naranja de zumo PREMIER, malla 2 kg", 3.99, "1 KILO A 2,00 €", before="5,99"), "2.00", "kg", "fuente"),
    (ge(1, "Leche desnatada calcio PASCUAL, brik 1 litro", 1.39, "1 LITRO A 1,39 €"), "1.39", "l", "fuente"),
    (ge(2, "Huevos camperos EROSKI, cartón 12 uds.", 3.60, "1 DOCENA A 3,60 €"), "0.30", "ud", "fuente"),
    # sin precio por unidad en la web: se calcula con el nombre
    (ge(18457754, "Mandarina TORRES, bolsa 1 kg", 3.50), "3.50", "kg", "calculado"),
    (ge(3, "Yogur natural DANONE, pack 4x125 g", 2.00), "4.00", "kg", "calculado"),
    (ge(4, "Cerveza ESTRELLA DAMM, pack 6x33 cl", 4.95), "2.50", "l", "calculado"),
    (ge(5, "Limón, al peso, compra mínima 500 g", 1.30), "2.60", "kg", "calculado"),
    (ge(6, "Huevo fresco clase L, 1/2 docena", 1.50), "0.25", "ud", "calculado"),
    (ge(7, "Papel de aluminio EROSKI, rollo 30 m", 2.40), "0.08", "m", "calculado"),
    (ge(8, "Detergente líquido EROSKI, 40 lavados", 6.00), "0.15", "lavado", "calculado"),
    (ge(9, "Coco, unidad", 1.99), "1.99", "ud", "calculado"),
    (ge(10, "Cebolleta extra EROSKI, manojo", 1.25), "1.25", "ud", "calculado"),
]


def check_cases() -> None:
    for p, up, unit, src in CASES:
        r = normalize_record(p)
        assert r["id"] == p["id"] and r["name"] == p["name"], r
        assert r["total"] == Decimal(str(p["price"])), (p["name"], r["total"])
        assert r["unit_price"] is not None and abs(r["unit_price"] - Decimal(up)) < Decimal("0.005"), \
            (p["name"], r["unit_price"], up)
        assert r["unit"] == unit and r["unit_src"] == src, (p["name"], r["unit"], r["unit_src"])
        assert r["category"] == "Cat" and r["url"] == p["url"], r
    # sin cantidad ni precio por unidad: incompleto, no inventado
    r = normalize_record(ge(11, "Tomacó CONCA, malla", 2.10))
    assert r["unit_price"] is None and r["unit_reason"].startswith("formato_no_comparable"), r
    print(f"OK: {len(CASES)} casos fijos + 1 incompleto")


def check_shape() -> None:
    items = [c[0] for c in CASES]
    assert to_common(items[0])["display_name"] == items[0]["name"]
    out = to_clean_json(items)
    assert len(out["items"]) == len(CASES)
    txt = to_clean_txt(items)
    assert "Incompletos: 0" in txt and "ERROR" not in txt, txt
    # linea limpia: mismo formato que las demas cadenas (la parsea el writer de API/BD)
    assert ("13899893 | Naranja de zumo PREMIER, malla 2 kg | 3.99EUR total | 2.00EUR/kg | 2kg | "
            "Cat | https://www.capraboacasa.com/es/productdetail/13899893-x/ | ref=2.00EUR/KILO src=fuente") in txt, txt
    print("OK: forma comun, JSON (CleanBatch) y texto")


def check_dump() -> None:
    base = Path(__file__).resolve().parents[2] / "scrappers" / "scrapper_caprabo" / "out"
    dumps = sorted(base.glob("*.txt"))
    if not dumps:
        print("(sin volcado real de Caprabo: me salto la parte 2)")
        return
    items = [ast.literal_eval(l[5:]) for l in dumps[-1].read_text(encoding="utf-8").splitlines()
             if l.startswith("raw: ")]
    txt = to_clean_txt(items)
    lines = txt.splitlines()
    assert not [l for l in lines if l.startswith("ERROR")]
    incompletos = sum(1 for p in items if normalize_record(p)["unit_price"] is None)
    assert incompletos <= 0.02 * len(items), (incompletos, len(items))

    # Donde la web da precio por unidad y el nombre tamano, el calculado debe coincidir casi siempre.
    ok = total = 0
    for p in items:
        c = from_caprabo(p)
        pi = c["price_instructions"]
        if "reference_price" not in pi or pi.get("unit_size") is None:
            continue
        fuente = normalize_record(c)
        calc = normalize_record({**c, "price_instructions": {k: v for k, v in pi.items()
                                                            if not k.startswith("reference")}})
        if fuente["unit_price"] is None or calc["unit_price"] is None:
            continue
        total += 1
        ok += fuente["unit"] == calc["unit"] and \
            abs(fuente["unit_price"] - calc["unit_price"]) <= Decimal("0.02") * fuente["unit_price"] + Decimal("0.01")
    assert total == 0 or ok / total >= 0.9, (ok, total)
    print(f"OK: volcado real {dumps[-1].name}: {len(items)} productos, {lines[1]}; "
          f"calculado = web en {ok}/{total}")


if __name__ == "__main__":
    check_cases()
    check_shape()
    check_dump()
