from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Crea les extensions i les taules que faltin (idempotent)."""
    with engine.begin() as conn:
        # Diverses rèpliques arrenquen alhora: només una crea l'esquema, la resta s'espera.
        conn.execute(text("SELECT pg_advisory_xact_lock(424242)"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        Base.metadata.create_all(conn)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
