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
    assert page["total"] >= 8
    unit_prices = [i["price"]["unit_price"] for i in page["items"]]
    assert unit_prices == sorted(unit_prices)
    assert page["items"][0]["name"] == "Aceite de oliva 0,4º garrafa 5 L"  # 3,45 €/l


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
