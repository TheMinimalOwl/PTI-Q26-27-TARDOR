"""Prueba del adaptador de Condis (`from_condis`).
`python test_condis.py`

1. Casos fijos sacados de productos reales de compraonline.condis.es (11/11/2026): con el
   precio por unidad de la web (`pum`: "5,28€/Kilo", "0,23€/100 ml", "3,69€/Docena"...), en
   oferta, sin `pum` (se calcula con el tamano del nombre) y nombres truncados con "0 KG".
2. Si hay un volcado real (`scrappers/scrapper_condis/out/*.txt`), lo normaliza entero: sin
   errores, como mucho un 1 % incompleto, y donde la web y el nombre dan la misma clase de
   unidad, el calculado coincide con la web casi siempre.
"""

import ast
from decimal import Decimal
from pathlib import Path

from normalizer import from_condis, normalize_record, to_clean_txt, to_common


def cd(pid, name, current, pum=None, regular=None, family="Familia"):
    p = {
        "id": str(pid), "externalId": str(pid), "description": name, "brand": "MARCA",
        "price": {"current": current, "regular": regular or current},
        "section": "Alimentación", "family": family, "category": ["Alimentación", family, "Variedad"],
        "url": f"/producto/p/{pid}/es_ES", "variable_weight": 0,
    }
    if regular:
        p["price"]["discounted"] = current
    if pum is not None:
        p["pum"] = pum
    return p


CASES = [
    # (producto, unitario esperado, unidad, origen)
    (cd(116335, "TORTILLAS ZANUY TRIGO 8 UNIDADES 320 G", 1.69, "5,28€/Kilo", regular=1.95), "5.28", "kg", "fuente"),
    (cd(704048, "LECHE CONDIS SEMIDESNATADA 1 L", 0.87, "0,87€/Litro"), "0.87", "l", "fuente"),
    (cd(1, "GEL DUCHA SANEX 600 ML", 3.45, "0,58€/100 ml"), "5.80", "l", "fuente"),
    (cd(2, "HUEVOS CONDIS CAMPEROS 6 UNIDADES", 2.59, "5,18€/Docena"), "0.43", "ud", "fuente"),
    (cd(3, "ACEITUNAS SIN HUESO 150 G", 1.20, "12,10€/Kilo PNE"), "12.10", "kg", "fuente"),
    (cd(4, "NUECES BORGES SACO", 8.95, "8,95€/Kg"), "8.95", "kg", "fuente"),
    (cd(5, "PAPEL ALUMINIO CONDIS 30 M", 1.80, "0,06€/M"), "0.06", "m", "fuente"),
    # sin `pum`: se calcula con el nombre
    (cd(6, "TOMILLO CARMENCITA CRISTAL 22 G", 1.55), "70.45", "kg", "calculado"),
    (cd(7, "AZAFRAN CONDIS EN RAMA 1 UNIDAD", 1.49), "1.49", "ud", "calculado"),
    # nombre truncado con "0 KG" de relleno: cuenta el tamano de dentro
    (cd(8, "TAHIN INTEG RAL 225GRS VER 0 KG", 3.99), "17.73", "kg", "calculado"),
]


def check_cases() -> None:
    for p, up, unit, src in CASES:
        r = normalize_record(p)
        assert r["id"] == p["id"] and r["name"] == p["description"], r
        assert r["total"] == Decimal(str(p["price"]["current"])), (p["description"], r["total"])
        assert r["unit_price"] is not None and abs(r["unit_price"] - Decimal(up)) < Decimal("0.005"), \
            (p["description"], r["unit_price"], up)
        assert r["unit"] == unit and r["unit_src"] == src, (p["description"], r["unit"], r["unit_src"])
        assert r["category"] == "Familia", r
        assert r["url"] == f"https://compraonline.condis.es/producto/p/{p['id']}/es_ES", r
    # sin `pum` ni tamano: incompleto, no inventado
    r = normalize_record(cd(9, "CUÑA QUESO SEMI SA CANOVA 0 KG", 5.95))
    assert r["unit_price"] is None and r["unit_reason"].startswith("formato_no_comparable"), r
    print(f"OK: {len(CASES)} casos fijos + 1 incompleto")


def check_shape() -> None:
    items = [c[0] for c in CASES]
    assert to_common(items[0])["display_name"] == items[0]["description"]
    txt = to_clean_txt(items)
    assert "Incompletos: 0" in txt and "ERROR" not in txt, txt
    assert ("116335 | TORTILLAS ZANUY TRIGO 8 UNIDADES 320 G | 1.69EUR total | 5.28EUR/kg | 320g | "
            "Familia | https://compraonline.condis.es/producto/p/116335/es_ES | ref=5.28EUR/Kilo src=fuente") in txt, txt
    print("OK: forma comun y texto")


def check_dump() -> None:
    base = Path(__file__).resolve().parents[2] / "scrappers" / "scrapper_condis" / "out"
    dumps = sorted(base.glob("*.txt"))
    if not dumps:
        print("(sin volcado real de Condis: me salto la parte 2)")
        return
    items = [ast.literal_eval(l[5:]) for l in dumps[-1].read_text(encoding="utf-8").splitlines()
             if l.startswith("raw: ")]
    txt = to_clean_txt(items)
    lines = txt.splitlines()
    assert not [l for l in lines if l.startswith("ERROR")]
    incompletos = sum(1 for p in items if normalize_record(p)["unit_price"] is None)
    assert incompletos <= 0.01 * len(items), (incompletos, len(items))

    # Donde web y nombre dan la misma clase de unidad, el calculado debe coincidir con la web.
    # (Cuando no: "4 UNIDADES" con pum en €/Kilo; ahi manda la web.)
    ok = total = 0
    for p in items:
        c = from_condis(p)
        pi = c["price_instructions"]
        if "reference_price" not in pi or pi.get("unit_size") is None:
            continue
        fuente = normalize_record(c)
        calc = normalize_record({**c, "price_instructions": {k: v for k, v in pi.items()
                                                            if not k.startswith("reference")}})
        if fuente["unit_price"] is None or calc["unit_price"] is None or fuente["unit"] != calc["unit"]:
            continue
        total += 1
        ok += abs(fuente["unit_price"] - calc["unit_price"]) <= Decimal("0.02") * fuente["unit_price"] + Decimal("0.01")
    assert total == 0 or ok / total >= 0.9, (ok, total)
    print(f"OK: volcado real {dumps[-1].name}: {len(items)} productos, {lines[1]}; "
          f"calculado = web en {ok}/{total}")


if __name__ == "__main__":
    check_cases()
    check_shape()
    check_dump()
