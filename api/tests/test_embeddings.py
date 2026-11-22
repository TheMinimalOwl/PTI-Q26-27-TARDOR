"""Sincronització d'embeddings amb la IA. El servei /embed de la VM 2 se simula amb
httpx.MockTransport. Els tests que toquen la BD es salten si PostgreSQL no està en marxa."""
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select, text

from app.config import settings
from app.embeddings import embed_text


# --- Text que s'embeddeja (no necessita BD) --------------------------------------------

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
    from app.db import init_db
    from app.seed import seed

    init_db()
    seed()
    with engine.begin() as conn:
        conn.execute(text("UPDATE products SET embedding = NULL"))
    yield engine
    seed()  # desfà els canvis de nom/preu dels tests
    with engine.begin() as conn:
        conn.execute(text("UPDATE products SET embedding = NULL"))


@pytest.fixture
def fake_embed(monkeypatch):
    """Servei /embed fals: vector constant (0.5 a la primera posició) i registre de les peticions."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        calls.append({"body": body, "key": request.headers.get("X-API-Key")})
        vec = [0.0] * settings.embedding_dim
        vec[0] = 0.5
        return httpx.Response(200, json={"embeddings": [vec for _ in body["texts"]]})

    monkeypatch.setattr(settings, "embed_url", "http://vm2/embed")
    monkeypatch.setattr(settings, "embed_api_key", "secreto")
    monkeypatch.setattr(settings, "embed_batch_size", 5)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    yield client, calls
    client.close()


def _pending(engine) -> int:
    with engine.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM products WHERE embedding IS NULL"))


def test_sync_omple_tots_els_pendents(db, fake_embed):
    from app.embeddings import sync_embeddings

    client, calls = fake_embed
    total = _pending(db)
    assert total > 5

    assert sync_embeddings(client) == total
    assert _pending(db) == 0
    assert all(len(c["body"]["texts"]) <= 5 for c in calls)  # en lots
    assert {c["body"]["kind"] for c in calls} == {"passage"}
    assert {c["key"] for c in calls} == {"secreto"}
    assert any(" | categoria " in t for c in calls for t in c["body"]["texts"])

    calls.clear()
    assert sync_embeddings(client) == 0  # ja no queda res
    assert calls == []


def test_sync_sin_url_no_hace_nada(db, monkeypatch):
    from app.embeddings import sync_embeddings

    monkeypatch.setattr(settings, "embed_url", "")
    assert sync_embeddings() == 0


def test_sync_rechaza_dimension_incorrecta(db, monkeypatch):
    from app.embeddings import sync_embeddings

    monkeypatch.setattr(settings, "embed_url", "http://vm2/embed")
    import json

    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"embeddings": [[0.1, 0.2] for _ in json.loads(r.content)["texts"]]}
    )))
    with pytest.raises(ValueError, match="dimensions"):
        sync_embeddings(client)


def test_sync_vm2_caida_no_pierde_nada(db, monkeypatch):
    from app.embeddings import sync_embeddings

    monkeypatch.setattr(settings, "embed_url", "http://vm2/embed")
    before = _pending(db)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError):
        sync_embeddings(client)
    assert _pending(db) == before  # continuen pendents per a la propera vegada


def test_upsert_borra_el_embedding_si_cambia_el_nombre(db, fake_embed):
    from app.db import SessionLocal
    from app.embeddings import sync_embeddings
    from app.ingest import Batch, NormalizedItem, upsert_batch
    from app.models import Chain, Product

    sync_embeddings(fake_embed[0])

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
