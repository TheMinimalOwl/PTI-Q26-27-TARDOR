"""Client de /embed (servei d'IA, VM 2) i sincronització d'embeddings. El servei se simula
amb httpx.MockTransport. Els tests que toquen la BD es salten si PostgreSQL no està en marxa."""
import json
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select, text

from app import embeddings
from app.config import settings
from app.embeddings import EmbedError, EmbedUnavailable, embed_query, embed_text, embed_texts

KEY = "clau-de-prova"


class FakeEmbed:
    """Servei /embed fals amb el contracte de flujo-ia. Registra les peticions.

    El vector és una bossa de paraules (cada paraula, una posició) amb norma 1, perquè la
    cerca semàntica doni resultats amb sentit als tests."""

    def __init__(self, status: int = 200):
        self.status = status
        self.calls: list[dict] = []

    @staticmethod
    def vector(t: str) -> list[float]:
        import unicodedata
        import zlib

        t = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
        v = [0.0] * settings.embedding_dim
        for w in t.replace("|", " ").split():
            v[zlib.crc32(w.encode()) % settings.embedding_dim] += 1
        norm = sum(x * x for x in v) ** 0.5 or 1
        return [x / norm for x in v]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append({"url": str(request.url), "body": body, "key": request.headers.get("X-API-Key")})
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "simulado"})
        if request.headers.get("X-API-Key") != KEY:
            return httpx.Response(401, json={"error": "falta X-API-Key"})
        if len(body["texts"]) > 256 or any(len(t) > 2000 for t in body["texts"]):
            return httpx.Response(413, json={"error": "demasiado grande"})
        return httpx.Response(200, json={"embeddings": [self.vector(t) for t in body["texts"]]})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


@pytest.fixture
def service(monkeypatch):
    """Configura la URL i la clau i fa que el codi faci servir el servei fals."""
    fake = FakeEmbed()
    monkeypatch.setattr(settings, "rag_embed_url", "http://vm2:8080/")
    monkeypatch.setattr(settings, "rag_embed_api_key", KEY)
    monkeypatch.setattr(embeddings, "_new_client", fake.client)
    return fake


# --- Client de /embed (no necessita BD) -------------------------------------------------

def test_200_vectores_en_orden(service):
    out = embed_texts(["leche entera 1 l", "agua mineral 1,5 l"])
    assert out == [FakeEmbed.vector("leche entera 1 l"), FakeEmbed.vector("agua mineral 1,5 l")]
    (call,) = service.calls
    assert call["url"] == "http://vm2:8080/embed"  # URL base + /embed, sense doble barra
    assert call["key"] == KEY
    assert call["body"] == {"texts": ["leche entera 1 l", "agua mineral 1,5 l"], "kind": "passage"}


def test_query_usa_kind_query(service):
    assert len(embed_query("algo para desayunar")) == settings.embedding_dim
    assert service.calls[0]["body"]["kind"] == "query"
    assert service.calls[0]["body"]["texts"] == ["algo para desayunar"]  # sense prefix


def test_mas_de_256_textos_van_en_lotes(service):
    texts = [f"producto {i}" for i in range(600)]
    out = embed_texts(texts)
    assert [len(c["body"]["texts"]) for c in service.calls] == [256, 256, 88]
    assert out[300] == FakeEmbed.vector("producto 300")  # l'ordre es manté entre lots


def test_lote_configurado_nunca_pasa_de_256(service, monkeypatch):
    monkeypatch.setattr(settings, "embed_batch_size", 1000)
    embed_texts(["x"] * 300)
    assert max(len(c["body"]["texts"]) for c in service.calls) == 256


def test_texto_largo_se_recorta(service):
    embed_texts(["a" * 5000])
    assert len(service.calls[0]["body"]["texts"][0]) == 2000


def test_lista_vacia_no_llama(service):
    assert embed_texts([]) == []
    assert service.calls == []


def test_401_clave_incorrecta(service, monkeypatch):
    monkeypatch.setattr(settings, "rag_embed_api_key", "otra")
    with pytest.raises(EmbedError, match="401.*RAG_EMBED_API_KEY") as exc:
        embed_texts(["x"])
    assert "otra" not in str(exc.value)  # la clau no surt mai als missatges


def test_413(service):
    service.status = 413
    with pytest.raises(EmbedError, match="413"):
        embed_texts(["x"])


def test_503_no_tiene_sentido_reintentar(service):
    service.status = 503
    with pytest.raises(EmbedUnavailable, match="equipo de IA"):
        embed_texts(["x"])


def test_servicio_caido(monkeypatch):
    def down(request):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(settings, "rag_embed_url", "http://vm2:8080")
    monkeypatch.setattr(embeddings, "_new_client", lambda: httpx.Client(transport=httpx.MockTransport(down)))
    with pytest.raises(EmbedError, match="no responde"):
        embed_texts(["x"])


def test_dimension_incorrecta(monkeypatch):
    monkeypatch.setattr(settings, "rag_embed_url", "http://vm2:8080")
    monkeypatch.setattr(embeddings, "_new_client", lambda: httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"embeddings": [[0.1, 0.2] for _ in json.loads(r.content)["texts"]]})
    )))
    with pytest.raises(EmbedError, match="dimensiones"):
        embed_texts(["x"])


def test_sin_url_no_configurado(monkeypatch):
    monkeypatch.setattr(settings, "rag_embed_url", "")
    with pytest.raises(EmbedError, match="RAG_EMBED_URL"):
        embed_texts(["x"])


def test_texto_igual_que_flujo_ia():
    assert embed_text("Aceite de oliva 0,4º Hacendado", "Aceite, especias y salsas", "5.0", "l") == (
        "Aceite de oliva 0,4º Hacendado | categoria Aceite, especias y salsas | tamano 5 l"
    )
    assert embed_text("Macarrones", "", "0.500", "kg") == "Macarrones | tamano 0.5 kg"
    assert embed_text("Bolsa regalo", "Varios", "", "") == "Bolsa regalo | categoria Varios"
    assert embed_text("Pack", "", "3x80", "g") == "Pack | tamano 3x80 g"


# --- Contra la BD ----------------------------------------------------------------------

@pytest.fixture
def db():
    from app.db import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL no disponible")
    from app.cache import cache
    from app.db import init_db
    from app.seed import seed

    init_db()
    seed()
    with engine.begin() as conn:
        conn.execute(text("UPDATE products SET embedding = NULL"))
    cache.invalidate()
    yield engine
    seed()  # desfà els canvis de nom/preu dels tests
    with engine.begin() as conn:
        conn.execute(text("UPDATE products SET embedding = NULL"))


def _pending(engine) -> int:
    with engine.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM products WHERE embedding IS NULL"))


def test_sync_omple_tots_els_pendents(db, service, monkeypatch):
    from app.embeddings import sync_embeddings

    monkeypatch.setattr(settings, "embed_batch_size", 5)
    total = _pending(db)
    assert total > 5

    assert sync_embeddings() == total
    assert _pending(db) == 0
    assert all(len(c["body"]["texts"]) <= 5 for c in service.calls)  # en lots
    assert {c["body"]["kind"] for c in service.calls} == {"passage"}
    assert any(" | categoria " in t for c in service.calls for t in c["body"]["texts"])

    service.calls.clear()
    assert sync_embeddings() == 0  # ja no queda res
    assert service.calls == []


def test_sync_sin_url_no_hace_nada(db, monkeypatch):
    from app.embeddings import sync_embeddings

    monkeypatch.setattr(settings, "rag_embed_url", "")
    assert sync_embeddings() == 0


def test_sync_vm2_con_error_no_pierde_nada(db, service):
    from app.embeddings import sync_embeddings

    before = _pending(db)
    service.status = 503
    with pytest.raises(EmbedUnavailable):
        sync_embeddings()
    assert _pending(db) == before  # continuen pendents per a la propera vegada


def test_upsert_borra_el_embedding_si_cambia_el_nombre(db, service):
    from app.db import SessionLocal
    from app.embeddings import sync_embeddings
    from app.ingest import Batch, NormalizedItem, upsert_batch
    from app.models import Chain, Product

    sync_embeddings()

    def item(name, total):
        return NormalizedItem(
            id="demo-arroz-redondo-1kg", name=name, category="Arroz, legumbres y pasta",
            size="1", size_format="kg", unit="kg", total=Decimal(total), unit_price=Decimal(total),
        )

    def embedding_is_null() -> bool:
        with SessionLocal() as s:
            return s.scalar(
                select(Product.embedding.is_(None))
                .join(Product.chain)
                .where(Product.source_id == "demo-arroz-redondo-1kg", Chain.slug == "mercadona")
            )

    def load(name, total):
        with SessionLocal() as s, s.begin():
            upsert_batch(s, Batch(chain="mercadona", ts=datetime.now(timezone.utc), items=[item(name, total)]))

    # Canvia només el preu: l'embedding es manté.
    load("Arroz redondo 1 kg", "1.40")
    assert embedding_is_null() is False
    # Canvia el nom: l'embedding ja no val.
    load("Arroz redondo extra 1 kg", "1.40")
    assert embedding_is_null() is True


# --- GET /products/semantic-search ------------------------------------------------------

@pytest.fixture
def api(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_semantic_search(api, service):
    from app.embeddings import sync_embeddings

    sync_embeddings()
    service.calls.clear()
    res = api.get("/products/semantic-search", params={"q": "arroz", "top_k": 3})
    assert res.status_code == 200
    items = res.json()["items"]
    assert [i["name"] for i in items] == ["Arroz redondo 1 kg"] * 3
    assert items[0]["price"]["total"] > 0
    assert service.calls[0]["body"] == {"texts": ["arroz"], "kind": "query"}

    res = api.get("/products/semantic-search", params={"q": "aceite oliva", "max_price": 10, "chain": "alcampo"})
    items = res.json()["items"]
    assert items and all(i["chain"]["slug"] == "alcampo" and i["price"]["total"] <= 10 for i in items)


def test_semantic_search_errores(api, service, monkeypatch):
    service.status = 503
    res = api.get("/products/semantic-search", params={"q": "arroz"})
    assert res.status_code == 502 and "equipo de IA" in res.json()["detail"]

    monkeypatch.setattr(settings, "rag_embed_url", "")
    assert api.get("/products/semantic-search", params={"q": "arroz"}).status_code == 503
