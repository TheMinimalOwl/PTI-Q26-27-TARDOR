"""Configuració per variables d'entorn: es reconfigura sense recompilar."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pti:pti@localhost:5432/precios"
    redis_url: str = "redis://localhost:6379/0"
    nats_url: str = "nats://localhost:4222"

    # Segons que viu una resposta a Redis. Els preus canvien com a molt un cop
    # al dia (CronJob nocturn), i el writer invalida la caché en carregar un lot.
    cache_ttl: int = 300

    # Dimensió dels embeddings. Depèn del model que triï l'equip d'IA:
    # 384 (multilingual-e5-small, MiniLM) o 1536 (OpenAI text-embedding-3-small).
    embedding_dim: int = 384

    # Crea les extensions i les taules en arrencar si no existeixen.
    auto_create_schema: bool = True


settings = Settings()
