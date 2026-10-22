"""Prueba del contrato Pydantic. Sin cluster: `python test_models.py`.

Cubre:
1. `RawProduct`: tolerante (ignora campos desconocidos) y coacciona tipos.
2. `NormalizedProduct`: coherencia entre linea incompleta y precio unitario.
3. `to_clean_txt`: sigue siendo tolerante -> `ERROR id=...` por item.
4. `to_clean_json`: `CleanBatch` estricto y serializable.
5. Volcado real: todos los productos del ultimo `mercadona_*.txt` validan.
"""

import ast
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from normalizer import (
    NormalizedProduct,
    RawProduct,
    normalize_model,
    normalize_record,
    to_clean_json,
    to_clean_txt,
)


def prod(id=12345, **pi):
    return {"id": id, "display_name": "  Aceite   de oliva ", "price_instructions": pi}


def check_raw() -> None:
    r = RawProduct.model_validate({
        "id": 12345,                                    # numero -> str
        "display_name": "Aceite",
        "share_url": "https://ejemplo/4241",
        "categories": [{"name": "Aceite", "id": 7}],    # id extra -> ignorado
        "price_instructions": {
            "unit_price": "1,80",                       # coma decimal
            "unit_size": "0.4",
            "size_format": "l",
            "reference_price": "0,450",
            "reference_format": "100 ml",
            "bulk_price": "99",                         # desconocido -> ignorado
        },
        "campo_que_no_existe": True,                    # desconocido -> ignorado
    })
    assert r.id == "12345", r.id
    assert r.price_instructions.unit_price == Decimal("1.80")
    assert r.price_instructions.reference_price == Decimal("0.450")
    assert r.categories[0].name == "Aceite"
    print("RawProduct: tolerante y coacciona tipos OK")


def check_normalized() -> None:
    d = normalize_record(prod(unit_price="1.80", unit_size=0.4, size_format="l",
                              reference_price="0.450", reference_format="100 ml"))
    m = NormalizedProduct.model_validate(d)
    assert m.name == "Aceite de oliva", repr(m.name)          # espacios colapsados
    assert (m.unit, m.unit_src) == ("l", "fuente")
    assert m.unit_price == Decimal("4.5000")
    assert Decimal(str(m.model_dump(mode="json")["unit_price"])) == Decimal("4.5")

    # Linea incompleta valida (sin precio unitario pero con motivo).
    incompleto = normalize_model(prod(unit_price="1.20", size_format="kg"))
    assert incompleto.unit_price is None and incompleto.unit_reason == "sin_tamano"

    # Combinaciones incoherentes que el modelo debe rechazar.
    malos = [
        {**d, "unit_price": None, "unit_reason": ""},            # sin motivo
        {**d, "unit_price": None},                               # incompleta con unidad/origen
        {**d, "unit": None},                                     # con precio y sin unidad
        {**d, "unit_src": "-"},                                  # con precio y origen "-"
        {**d, "unit_reason": "sin_tamano"},                      # motivo con precio
    ]
    for bad in malos:
        try:
            NormalizedProduct.model_validate(bad)
        except ValidationError:
            continue
        raise AssertionError(f"deberia haber fallado: {bad}")
    print("NormalizedProduct: coherencia OK")


def check_txt_tolerante() -> None:
    """Un item que no valida no tumba el lote: deja una linea ERROR con su id."""
    import normalizer

    orig = normalizer.normalize_record
    normalizer.normalize_record = lambda p: {"id": "9", "name": "x", "unit_src": "fuente"}
    try:
        txt = normalizer.to_clean_txt([{"id": "9"}, {"id": "10"}])
    finally:
        normalizer.normalize_record = orig

    lineas = txt.splitlines()
    assert lineas[0] == "Items: 2", txt
    assert len(lineas) == 5, lineas                       # 3 de cabecera + 1 por item
    assert lineas[3].startswith("ERROR id=9: validacion:"), lineas
    assert lineas[4].startswith("ERROR id=10: validacion:"), lineas
    print("to_clean_txt: ERROR por item sin romper el lote OK")


def check_json() -> None:
    items = [
        prod(unit_price="1.80", unit_size=0.4, size_format="l",
             reference_price="0.450", reference_format="100 ml"),
        prod(id=777, unit_price="1.20", size_format="kg"),      # incompleto, pero valido
    ]
    out = to_clean_json(items, wh="default", ts="2026-10-15T19:22:31+00:00")
    assert out["source"] == "normalizer" and out["batch"] == 2
    assert out["ts"] == "2026-10-15T19:22:31+00:00"
    assert len(out["items"]) == 2
    assert out["items"][0]["unit"] == "l" and out["items"][0]["unit_src"] == "fuente"
    assert out["items"][1]["unit_price"] is None
    assert out["items"][1]["unit_reason"] == "sin_tamano"
    # Serializa a JSON sin Decimal ni objetos raros.
    import json
    json.loads(json.dumps(out, ensure_ascii=False))

    # El camino estructurado es estricto: un crudo sin `id` no pasa.
    try:
        to_clean_json([{"unit_price": "1.00"}])
    except ValidationError:
        print("to_clean_json: estricto con la entrada OK")
        return
    raise AssertionError("un crudo sin id deberia fallar en el camino estructurado")


def check_dump() -> None:
    base = Path(__file__).resolve().parents[2]
    ins = sorted((base / "scrappers" / "scrapper_mercadona" / "out").glob("mercadona_*.txt"))
    if not ins:
        print("sin volcado real que validar")
        return
    src = ins[-1]
    n = 0
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.startswith("raw: "):
            continue
        try:
            p = ast.literal_eval(line[5:])
        except Exception:
            continue
        if not isinstance(p, dict) or "_errors" in p:
            continue
        NormalizedProduct.model_validate(normalize_record(p))
        n += 1
    print(f"volcado: {src.name} -> {n} productos validan")


def check_endpoint() -> None:
    """`POST /normalize` como lo llama el consumer: texto por defecto, JSON opt-in."""
    try:
        from flask import Flask
    except ImportError:
        print("flask no instalado: se omite la prueba del endpoint")
        return

    import json
    import normalizer

    app = Flask(__name__)
    item = prod(unit_price="1.80", unit_size=0.4, size_format="l",
                reference_price="0.450", reference_format="100 ml")

    def post(url, payload):
        with app.test_request_context(url, method="POST",
                                      data=json.dumps(payload),
                                      content_type="application/json"):
            return normalizer.main()

    r = post("/normalize", {"items": [item]})
    assert (r.status_code, r.mimetype) == (200, "text/plain"), (r.status_code, r.mimetype)
    assert "4.50EUR/l" in r.get_data(as_text=True)

    r = post("/normalize?format=json", {"items": [item], "wh": "valencia-1"})
    assert (r.status_code, r.mimetype) == (200, "application/json"), (r.status_code, r.mimetype)
    out = json.loads(r.get_data(as_text=True))
    assert out["wh"] == "valencia-1" and out["items"][0]["unit"] == "l"

    r = post("/normalize?format=json", {"items": [{"unit_price": "1.00"}]})  # crudo sin id
    assert r.status_code == 422, r.status_code

    with app.test_request_context("/normalize", method="POST", data="no-json",
                                  content_type="application/json"):
        assert normalizer.main().status_code == 400
    print("endpoint /normalize: texto por defecto + JSON opt-in OK")


if __name__ == "__main__":
    check_raw()
    check_normalized()
    check_txt_tolerante()
    check_json()
    check_endpoint()
    check_dump()
    print("TODO OK")
