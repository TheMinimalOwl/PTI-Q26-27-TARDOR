"""Proves de l'API contra PostgreSQL i Redis reals (docker compose up -d db redis).
Es salten si la BD no està en marxa."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine

try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
except Exception:
    pytest.skip("PostgreSQL no disponible", allow_module_level=True)

from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="module")
def client():
    seed()
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json()["db"] is True


def test_busqueda_ordena_por_precio_unitario(client):
    page = client.get("/products/search", params={"q": "aceite"}).json()
    assert page["total"] >= 12
    assert page["unit"] == "l"
    oils = [i for i in page["items"] if i["unit"] == "l"]
    unit_prices = [i["price"]["unit_price"] for i in oils]
    assert unit_prices == sorted(unit_prices)
    assert page["items"][0]["name"] == "Aceite de oliva 0,4º garrafa 5 L"  # 3,45 €/l


def test_busqueda_no_mezcla_unidades(client):
    # La tonyina (≈1 €/ud) és "més barata" que l'oli (3,45 €/l), però no són comparables:
    # primer van tots els €/l i després els €/ud.
    items = client.get("/products/search", params={"q": "aceite oliva"}).json()["items"]
    units = [i["unit"] for i in items]
    assert units == sorted(units, key=lambda u: u != "l")
    assert units[-1] == "ud"


def test_busqueda_filtra_por_unidad(client):
    page = client.get("/products/search", params={"q": "aceite", "unit": "ud"}).json()
    assert page["unit"] == "ud"
    assert page["total"] == 4
    assert all("Atún" in i["name"] for i in page["items"])


def test_busqueda_sin_acentos_y_varias_palabras(client):
    page = client.get("/products/search", params={"q": "ACEITE oliva garrafa", "chain": "mercadona"}).json()
    assert page["total"] == 1
    assert page["items"][0]["chain"]["slug"] == "mercadona"


def test_segunda_busqueda_sale_de_cache(client):
    client.get("/products/search", params={"q": "arroz"})
    response = client.get("/products/search", params={"q": "arroz"})
    if client.get("/health").json()["redis"]:
        assert response.headers["X-Cache"] == "HIT"


def test_detalle_e_historial(client):
    first = client.get("/products/search", params={"q": "virgen extra", "chain": "mercadona"}).json()["items"][0]
    detail = client.get(f"/products/{first['id']}").json()
    assert detail["unit"] == "l"
    history = client.get(f"/products/{first['id']}/prices", params={"from": "2023-01-01"}).json()
    # 45 mesos d'historial + el preu d'avui; si la demo s'ha carregat altres dies, n'hi ha un més per dia.
    assert len(history["points"]) >= 46
    assert history["points"][0]["total"] == 3.99


def test_producto_inexistente(client):
    assert client.get("/products/999999").status_code == 404


def _optimize(client, items, **extra):
    return client.post("/shopping-list/optimize", json={"items": items, **extra}).json()


def test_lista_optimizada(client):
    # Dades de demo: Alcampo és la més barata sencera (15,36 €); combinant, l'arròs
    # s'agafa a Ahorramàs (1,25 € en lloc d'1,29 €) i surt a 15,28 €.
    res = _optimize(client, [
        {"q": "aceite oliva virgen extra"},
        {"q": "leche entera"},
        {"q": "arroz redondo", "quantity": 2},
        {"q": "huevos"},
    ])
    assert res["best_chain"] == "alcampo"
    assert [b["chain"]["slug"] for b in res["baskets"]][:2] == ["alcampo", "ahorramas"]
    assert res["baskets"][0]["total"] == 15.36
    assert res["combined"]["total"] == 15.28
    assert res["savings"] == 0.08
    rice = next(l for l in res["combined"]["lines"] if l["q"] == "arroz redondo")
    assert rice["product"]["chain"]["slug"] == "ahorramas"
    assert rice["subtotal"] == 2.5


def test_lista_tria_el_millor_preu_unitari(client):
    # "aceite": la garrafa de 5 L (3,45 €/l) surt més a compte que l'ampolla d'1 L.
    res = _optimize(client, [{"q": "aceite"}], chains=["mercadona"])
    line = res["baskets"][0]["lines"][0]
    assert line["product"]["name"] == "Aceite de oliva 0,4º garrafa 5 L"


def test_lista_con_articulo_que_no_existe(client):
    res = _optimize(client, [{"q": "huevos"}, {"q": "caviar beluga"}])
    assert res["combined"]["missing"] == ["caviar beluga"]
    assert all(b["missing"] == ["caviar beluga"] for b in res["baskets"])
    assert res["best_chain"] == "alcampo"
    assert res["savings"] == 0


def test_lista_solo_algunas_cadenas(client):
    res = _optimize(client, [{"q": "arroz redondo"}], chains=["mercadona", "carrefour"])
    assert {b["chain"]["slug"] for b in res["baskets"]} == {"mercadona", "carrefour"}
    assert res["best_chain"] == "mercadona"


def test_lista_vacia_es_error(client):
    assert client.post("/shopping-list/optimize", json={"items": []}).status_code == 422
