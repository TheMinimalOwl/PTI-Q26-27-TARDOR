"""Tests del almacen sobre la API de la BD (`RAG_STORE=api`).

Sin red: `requests` se sustituye por un servidor simulado que responde como
la API del equipo de API/BD (`/health`, `/chains`, `/products/search`,
`/products/search-vector`, `/products/{id}`).
"""

from __future__ import annotations

import numpy as np
import pytest

from rag import apistore, serve
from rag.apistore import ApiError, ApiStore, palabras_clave
from rag.retriever import Filters, Retriever


class EmbedderFalso:
    """Vector por palabra clave: 'aceite' -> eje 0, el resto -> eje 1."""

    class spec:
        key = "e5-small"
        dim = 2

    def _v(self, texto):
        return np.array([1.0, 0.0] if "aceite" in texto.lower() else [0.0, 1.0], dtype=np.float32)

    def encode_one(self, texto, is_query=True):
        return self._v(texto)

    def encode(self, textos, is_query=False):
        return np.vstack([self._v(t) for t in textos])


def _item(id_, nombre, cadena, total, up, unit="l", similarity=None):
    it = {
        "id": id_,
        "name": nombre,
        "chain": {"slug": cadena, "name": cadena.title()},
        "category": "Aceite",
        "unit": unit,
        "url": f"https://x/{id_}",
        "price": {"observed_on": "2026-11-22", "store": "1", "total": total, "unit_price": up, "unit_src": "fuente"},
    }
    if similarity is not None:
        it["similarity"] = similarity
    return it


class Resp:
    def __init__(self, status, datos):
        self.status_code = status
        self._datos = datos

    def json(self):
        return self._datos


class ApiFalsa:
    """Registra las llamadas y responde como la API real."""

    def __init__(self, search_vector=True, vector_status=200):
        self.search_vector = search_vector
        self.vector_status = vector_status
        self.llamadas: list[tuple] = []

    def get(self, url, params=None, timeout=None):
        ruta = url.split("://", 1)[1].split("/", 1)[1]
        self.llamadas.append(("GET", "/" + ruta, params))
        if ruta == "health":
            return Resp(200, {"status": "ok", "db": True, "redis": True})
        if ruta == "chains":
            return Resp(200, [{"slug": "mercadona"}, {"slug": "caprabo"}])
        if ruta == "products/search":
            if "aceite" not in params["q"] or params.get("unit") != "l":
                return Resp(200, {"items": []})
            items = [
                _item(1, "Aceite de oliva 0,4º Hacendado", "mercadona", 16.75, 3.35),
                _item(2, "Grissini al aceite de oliva", "caprabo", 2.69, 13.45),
            ]
            if params.get("chain"):
                items = [i for i in items if i["chain"]["slug"] == params["chain"]]
            return Resp(200, {"items": items})
        if ruta.startswith("products/"):
            pid = ruta.split("/")[1]
            if pid == "1":
                return Resp(200, {**_item(1, "Aceite de oliva 0,4º Hacendado", "mercadona", 16.75, 3.35), "size": "5", "size_format": "l"})
            return Resp(404, {"detail": "Not Found"})
        raise AssertionError(f"ruta inesperada {ruta}")

    def post(self, url, json=None, timeout=None):
        self.llamadas.append(("POST", url, json))
        if not self.search_vector:
            return Resp(405, {"detail": "Method Not Allowed"})
        if self.vector_status != 200:
            return Resp(self.vector_status, {})
        return Resp(200, {"items": [
            _item(3, "Aceite de oliva virgen", "caprabo", 3.6, 3.6, similarity=0.91),
            _item(4, "Aceite de girasol", "mercadona", 1.9, 1.9, similarity=0.80),
        ]})


@pytest.fixture
def api(monkeypatch):
    def montar(**kw):
        falsa = ApiFalsa(**kw)
        monkeypatch.setattr(apistore.requests, "get", falsa.get)
        monkeypatch.setattr(apistore.requests, "post", falsa.post)
        return falsa, ApiStore(EmbedderFalso(), base_url="https://bd.test")

    return montar


def test_palabras_clave_quita_lo_que_no_es_producto():
    assert palabras_clave("¿Cuál es el precio del aceite de oliva?") == ["aceite", "oliva"]


def test_sin_url_no_hay_store(monkeypatch):
    monkeypatch.setattr(apistore.config, "BD_API_URL", "")
    with pytest.raises(ApiError):
        ApiStore(EmbedderFalso(), base_url="")


def test_usa_search_vector_y_su_similarity(api):
    falsa, store = api()
    hits = Retriever(EmbedderFalso(), store).search("aceite de oliva", k=2)
    assert [h.id for h in hits] == ["3", "4"]
    # coseno de pgvector + el bonus por empezar por la palabra principal
    assert hits[0].score == pytest.approx(0.91 + apistore._BONUS_CABEZA)
    assert hits[0].doc["total"] == "3.6" and hits[0].doc["chain"] == "caprabo"
    assert not any(c[0] == "GET" and c[1] == "/products/search" for c in falsa.llamadas)


def test_sin_search_vector_busca_por_texto_y_no_reintenta(api):
    falsa, store = api(search_vector=False)
    r = Retriever(EmbedderFalso(), store)
    hits = r.search("¿Cuál es el precio del aceite de oliva?", k=2)
    # el producto que ES aceite va por delante del que lo lleva de ingrediente
    assert hits[0].doc["name"] == "Aceite de oliva 0,4º Hacendado"
    assert store._search_vector is False
    r.search("aceite de oliva", k=2)
    assert sum(1 for c in falsa.llamadas if c[0] == "POST") == 1


def test_un_5xx_de_search_vector_cae_a_texto_esta_vez(api):
    falsa, store = api(vector_status=530)
    hits = Retriever(EmbedderFalso(), store).search("aceite de oliva", k=2)
    assert hits and store._search_vector is None  # se volvera a probar


def test_la_cadena_de_la_pregunta_es_un_filtro(api):
    falsa, store = api(search_vector=False)
    hits = Retriever(EmbedderFalso(), store).search("aceite oliva mercadona", k=5)
    assert {h.doc["chain"] for h in hits} == {"mercadona"}
    busquedas = [c[2] for c in falsa.llamadas if c[1] == "/products/search"]
    assert all(p["chain"] == "mercadona" and "mercadona" not in p["q"] for p in busquedas)


def test_filtros_se_aplican(api):
    falsa, store = api()
    hits = Retriever(EmbedderFalso(), store).search("aceite", k=5, filters=Filters(chain="mercadona"))
    assert [h.id for h in hits] == ["4"]
    post = [c for c in falsa.llamadas if c[0] == "POST"][0]
    assert post[2]["chains"] == ["mercadona"]


def test_get_y_docs(api):
    falsa, store = api()
    assert store.get("1")["size"] == "5"
    assert store.get("999") is None
    assert {d["chain"] for d in store.docs} == {"mercadona", "caprabo"}


def test_api_caida_da_503_y_no_datos_de_prueba(monkeypatch):
    class StoreCaido:
        docs: list = []

        def search_query(self, *a, **k):
            raise ApiError("no responde la API de la BD (ConnectTimeout)")

        def __len__(self):
            return 0

    serve.inicializar("e5-small", "none")
    serve._ESTADO["retriever"] = Retriever(serve._ESTADO["retriever"].embedder, StoreCaido())
    serve.app.config["TESTING"] = True
    try:
        with serve.app.test_client() as c:
            r = c.post("/ask", json={"question": "¿precio del aceite?"})
        assert r.status_code == 503
        assert "base de datos" in r.get_json()["error"]
    finally:
        serve._ESTADO["retriever"] = None
