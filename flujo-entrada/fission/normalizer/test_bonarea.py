"""Prueba del adaptador de bonÀrea (`from_bonarea`).
`python test_bonarea.py`

1. Casos fijos sacados de productos reales de bonarea-online.com (11/11/2026): precio por
   unidad de la web (`unitPrice`) con sus etiquetas mal puestas ("300,00 €/ml." son €/l),
   productos al peso ("aprox. 374 g"), dosis, metros, sin `unitPrice` (se calcula con
   `measurementUnit` o con el nombre) y sin nada (incompleto).
2. Si hay un volcado real (`scrappers/scrapper_bonarea/out/*.txt`), lo normaliza entero: sin
   errores, como mucho un 10 % incompleto (la web no da ni precio por unidad ni tamano en
   ~8 %: vinos, tintes, estuches) y el calculado coincide con la web casi siempre.
"""

import ast
from decimal import Decimal
from pathlib import Path

from normalizer import from_bonarea, normalize_record, to_clean_txt, to_common


def ba(ident, name, price, unit_price="", measure="", path=("Alimentació", "Carns i ous", "Gall dindi")):
    return {
        "identifier": ident, "description": name, "priceToPay": price, "unitPrice": unit_price,
        "measurementUnit": measure, "euroUnit": "€/u.", "discount": 0, "isAnApproximatePrice": False,
        "urlFriendly": f"https://www.bonarea-online.com/online/producte/x/{ident.replace('*', '_')}",
        "category_path": list(path),
    }


CASES = [
    # (producto, unitario esperado, unidad, origen)
    (ba("13*5179", "Pit filetejat de gall dindi 5 u.", 3.8, "10,15 €/kg", "aprox. 374 g"), "10.15", "kg", "fuente"),
    (ba("13*1", "Ous L ros en estoig", 2.8, "0,23 €/u.", "12 u."), "0.23", "ud", "fuente"),
    (ba("13*2", "Cardenal Mendoza brandy", 23.15, "33,07 €/l.", "70 cl."), "33.07", "l", "fuente"),
    (ba("13*3", "Ambientador cotxe canela", 2.1, "300,00 €/ml.", "7 ml."), "300.00", "l", "fuente"),
    (ba("13*4", "Vela Bulgarian", 13.26, "57,65 €/g.", "230 g."), "57.65", "kg", "fuente"),
    (ba("13*5", "Sorra absorbent zotalin", 2.82, "0,56 €/k.", "5 kg."), "0.56", "kg", "fuente"),
    (ba("13*6", "Ariel detergent líquid bàsic", 6.13, "0,20 €/d.", "30 d."), "0.20", "ud", "fuente"),
    (ba("13*7", "Paper alumini ús domèstic", 2.25, "0,08 €/m", "30 m"), "0.08", "m", "fuente"),
    # sin `unitPrice`: se calcula con `measurementUnit` o, si no, con el nombre
    (ba("13*8", "Brou en pastilles Maggi", 1.95, "", "32 u"), "0.06", "ud", "calculado"),
    (ba("13*9", "Norit no més planxa 500ml", 2.95), "5.90", "l", "calculado"),
    # "0,00 €/m." no cuenta: se calcula con "1/2 m."
    (ba("13*10", "Baikim apòsits tira", 0.88, "0,00 €/m.", "1/2 m."), "1.76", "m", "calculado"),
]


def check_cases() -> None:
    for p, up, unit, src in CASES:
        r = normalize_record(p)
        assert r["id"] == p["identifier"] and r["name"] == p["description"], r
        assert r["total"] == Decimal(str(p["priceToPay"])), (p["description"], r["total"])
        assert r["unit_price"] is not None and abs(r["unit_price"] - Decimal(up)) < Decimal("0.005"), \
            (p["description"], r["unit_price"], up)
        assert r["unit"] == unit and r["unit_src"] == src, (p["description"], r["unit"], r["unit_src"])
        assert r["category"] == "Gall dindi" and r["url"] == p["urlFriendly"], r
    # sin precio por unidad ni tamano: incompleto, no inventado
    r = normalize_record(ba("13*11", "Vermut lacuesta vermell", 6.5))
    assert r["unit_price"] is None and r["unit_reason"].startswith("formato_no_comparable"), r
    print(f"OK: {len(CASES)} casos fijos + 1 incompleto")


def check_shape() -> None:
    items = [c[0] for c in CASES]
    assert to_common(items[0])["display_name"] == items[0]["description"]
    txt = to_clean_txt(items)
    assert "Incompletos: 0" in txt and "ERROR" not in txt, txt
    assert ("13*5179 | Pit filetejat de gall dindi 5 u. | 3.80EUR total | 10.15EUR/kg | 374g | Gall dindi | "
            "https://www.bonarea-online.com/online/producte/x/13_5179 | ref=10.15EUR/kg src=fuente") in txt, txt
    print("OK: forma comun y texto")


def check_dump() -> None:
    base = Path(__file__).resolve().parents[2] / "scrappers" / "scrapper_bonarea" / "out"
    dumps = sorted(base.glob("*.txt"))
    if not dumps:
        print("(sin volcado real de bonÀrea: me salto la parte 2)")
        return
    items = [ast.literal_eval(l[5:]) for l in dumps[-1].read_text(encoding="utf-8").splitlines()
             if l.startswith("raw: ")]
    txt = to_clean_txt(items)
    lines = txt.splitlines()
    assert not [l for l in lines if l.startswith("ERROR")]
    incompletos = sum(1 for p in items if normalize_record(p)["unit_price"] is None)
    assert incompletos <= 0.10 * len(items), (incompletos, len(items))

    ok = total = 0
    for p in items:
        c = from_bonarea(p)
        pi = c["price_instructions"]
        if "reference_price" not in pi or pi.get("unit_size") is None:
            continue
        fuente = normalize_record(c)
        calc = normalize_record({**c, "price_instructions": {k: v for k, v in pi.items()
                                                            if not k.startswith("reference")}})
        if fuente["unit_price"] is None or calc["unit_price"] is None or fuente["unit"] != calc["unit"]:
            continue
        total += 1
        # al peso ("aprox. 1,2 kg") el redondeo del peso mueve unos centimos: margen del 5 %
        ok += abs(fuente["unit_price"] - calc["unit_price"]) <= Decimal("0.05") * fuente["unit_price"] + Decimal("0.01")
    assert total == 0 or ok / total >= 0.95, (ok, total)
    print(f"OK: volcado real {dumps[-1].name}: {len(items)} productos, {lines[1]}; "
          f"calculado = web en {ok}/{total}")


if __name__ == "__main__":
    check_cases()
    check_shape()
    check_dump()
