"""Prueba del precio unitario canonico. Sin dependencias: `python test_unit_price.py`.

Dos partes:
1. Casos fijos, uno por formato real observado (fuente, calculado e incompleto).
2. Validacion sobre el ultimo volcado real: para cada producto en el que la
   unidad del `reference_format` y la del `size_format` son de la misma familia,
   el valor de la fuente y el calculado deben coincidir.
"""

import ast
from decimal import Decimal
from pathlib import Path

from normalizer import format_record, normalize_record, to_clean_txt, unit_price


def prod(**pi):
    return {"id": "1", "display_name": "Producto", "price_instructions": pi}


CASES = [
    # (descripcion, producto, valor esperado, unidad, origen)
    ("aceite 5 l, ref EUR/L", prod(unit_price="17.25", unit_size=5.0, size_format="l",
                                   reference_price="3.450", reference_format="L"),
     "3.45", "l", "fuente"),
    ("gel 0.4 l, ref por 100 ml", prod(unit_price="1.80", unit_size=0.4, size_format="l",
                                       reference_price="0.450", reference_format="100 ml"),
     "4.50", "l", "fuente"),
    ("oregano 0.025 kg, ref por 100 g", prod(unit_price="1.00", unit_size=0.025, size_format="kg",
                                             reference_price="4.000", reference_format="100 g"),
     "40.00", "kg", "fuente"),
    ("huevos 12 ud, ref por docena (dc)", prod(unit_price="4.30", unit_size=12.0, size_format="ud",
                                               reference_price="4.300", reference_format="dc"),
     "0.3583", "ud", "fuente"),
    ("huevos 24 ud, ref por docena (dz)", prod(unit_price="5.25", unit_size=24.0, size_format="ud",
                                               reference_price="2.625", reference_format="dz"),
     "0.2188", "ud", "fuente"),
    ("detergente 3 l, ref por lavado", prod(unit_price="3.50", unit_size=3.0, size_format="l",
                                            reference_price="0.070", reference_format="lv"),
     "0.07", "lavado", "fuente"),
    ("aluminio 30 m, ref EUR/m", prod(unit_price="2.25", unit_size=30.0, size_format="m",
                                      reference_price="0.075", reference_format="m"),
     "0.075", "m", "fuente"),
    ("sin reference_price -> calculado", prod(unit_price="2.00", unit_size=0.5, size_format="kg"),
     "4.00", "kg", "calculado"),
    ("sin reference_price, 500 g -> calculado", prod(unit_price="1.20", unit_size=500.0, size_format="g"),
     "2.40", "kg", "calculado"),
    ("sin reference_price, respaldo usa peso escurrido",
     prod(unit_price="3.00", unit_size=1.05, size_format="kg", drained_weight=0.45),
     "6.6667", "kg", "calculado"),
    ("sin tamano -> incompleto", prod(unit_price="1.20", size_format="kg"), None, None, "-"),
    ("formato desconocido -> incompleto", prod(unit_price="1.20", unit_size=1.0, size_format="pack"), None, None, "-"),
]


def check_cases() -> None:
    for desc, p, val, unit, src in CASES:
        got, got_unit, got_src, motivo = unit_price(p)
        assert src == got_src, f"{desc}: origen {got_src} != {src} ({motivo})"
        assert unit == got_unit, f"{desc}: unidad {got_unit} != {unit}"
        if val is None:
            assert got is None, f"{desc}: se esperaba None, salio {got}"
        else:
            assert got is not None and abs(got - Decimal(val)) < Decimal("0.0001"), f"{desc}: {got} != {val}"
    print(f"casos fijos: {len(CASES)} OK")


def family(fmt) -> tuple | None:
    from normalizer import _unit
    return _unit(fmt)


def check_dump() -> None:
    base = Path(__file__).resolve().parents[2]
    ins = sorted((base / "scrappers" / "scrapper_mercadona" / "out").glob("mercadona_*.txt"))
    if not ins:
        print("sin volcado real que validar")
        return
    src_file = ins[-1]
    items = []
    for line in src_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("raw: "):
            try:
                items.append(ast.literal_eval(line[5:]))
            except Exception:
                pass

    por_unidad: dict[str, int] = {}
    por_origen: dict[str, int] = {}
    incompletos = []
    simples = 0
    coinciden = 0
    excepciones = []
    compuestos = 0
    compuestos_sin_fuente = 0
    for p in items:
        pi = p.get("price_instructions") or {}
        up, unit, src, motivo = unit_price(p)
        por_origen[src] = por_origen.get(src, 0) + 1
        if up is None:
            incompletos.append((p.get("id"), motivo))
            continue
        por_unidad[unit] = por_unidad.get(unit, 0) + 1

        # Producto "compuesto": la fuente puede basar su reference_price en algo
        # que no es unit_size (peso escurrido, pack, unidad funcional, tamano
        # estimado). El respaldo calculado es solo aproximado ahi, asi que no
        # se exige que coincida con la fuente.
        compuesto = bool(
            pi.get("unit_name")
            or pi.get("drained_weight") is not None
            or pi.get("is_pack")
            or pi.get("pack_size") is not None
            or pi.get("total_units") is not None
            or pi.get("approx_size")
        )
        if compuesto:
            compuestos += 1
            if not pi.get("reference_price"):
                compuestos_sin_fuente += 1
            continue

        # En productos simples, el calculo desde unit_price/unit_size debe
        # reproducir el reference_price de la fuente salvo redondeo.
        total = pi.get("unit_price")
        size = pi.get("unit_size")
        ref = pi.get("reference_price")
        rf, sf = family(pi.get("reference_format")), family(pi.get("size_format"))
        if ref and total and size and rf and sf and rf[0] == sf[0]:
            simples += 1
            calculado = Decimal(str(total)) / (Decimal(str(size)) * sf[1])
            rel = abs(up - calculado) / calculado
            if rel <= Decimal("0.01"):
                coinciden += 1
            else:
                excepciones.append((p.get("id"), str(up), str(calculado), p.get("display_name")))

    print(f"volcado: {src_file.name} ({len(items)} productos)")
    print(f"por unidad: {por_unidad}")
    print(f"por origen: {por_origen}")
    print(f"simples: {simples} | compuestos (escurrido/pack/ud funcional/estimado): {compuestos}"
          f" (de ellos sin reference_price: {compuestos_sin_fuente})")
    if incompletos:
        print(f"incompletos: {len(incompletos)} -> {incompletos[:5]}")
    assert not incompletos, f"{len(incompletos)} productos sin precio unitario en datos comparables"

    tasa = coinciden / simples if simples else 1
    print(f"simples donde calculo == fuente (<=1%): {coinciden}/{simples} ({tasa:.2%})")
    if excepciones:
        print(f"excepciones (fuente incoherente consigo misma): {len(excepciones)} -> {excepciones[:3]}")
    assert tasa >= Decimal("0.98"), f"solo {tasa:.2%} de productos simples reproducen la fuente"


def check_line() -> None:
    p = prod(unit_price="1.80", unit_size=0.4, size_format="l",
             reference_price="0.450", reference_format="100 ml")
    p["share_url"] = "https://ejemplo/1"
    p["categories"] = [{"name": "Bebe"}]
    linea = format_record(normalize_record(p))
    assert "4.50EUR/l" in linea, linea
    assert "src=fuente" in linea, linea
    txt = to_clean_txt([p, {"unit_price": "1.00"}])
    assert txt.splitlines()[0] == "Items: 2", txt
    assert "Incompletos: 1" in txt.splitlines()[1], txt
    print("linea limpia OK")


if __name__ == "__main__":
    check_cases()
    check_line()
    check_dump()
    print("TODO OK")
