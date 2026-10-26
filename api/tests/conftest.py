"""Els tests fan servir una BD (`<bd>_test`) i una base de Redis (la 15) pròpies, perquè
les dades que es carreguen a mà a la BD de desenvolupament no els facin fallar.

S'ha d'executar abans d'importar res d'`app` que creï connexions (db, cache): pytest
carrega aquest fitxer abans que els mòduls de test."""
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings

dev_url = make_url(settings.database_url)
test_db = f"{dev_url.database}_test"

try:
    admin = create_engine(dev_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": test_db})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{test_db}"'))
    admin.dispose()
except Exception:
    pass  # sense PostgreSQL, test_api.py se salta sol

settings.database_url = dev_url.set(database=test_db).render_as_string(hide_password=False)
settings.redis_url = urlsplit(settings.redis_url)._replace(path="/15").geturl()
