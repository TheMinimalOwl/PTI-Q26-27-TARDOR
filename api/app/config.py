"""Configuración por variables de entorno: se reconfigura sin recompilar."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pti:pti@localhost:5432/precios"
    redis_url: str = "redis://localhost:6379/0"
    nats_url: str = "nats://localhost:4222"

    # Segundos que vive una respuesta en Redis. Los precios cambian como mucho una vez
    # al día (CronJob nocturno), y el writer invalida la caché al cargar un lote.
    cache_ttl: int = 300

    # Dimensión de los embeddings. Depende del modelo que elija el equipo de IA:
    # 384 (multilingual-e5-small, MiniLM) o 1536 (OpenAI text-embedding-3-small).
    embedding_dim: int = 384

    # Crea extensiones y tablas al arrancar si no existen.
    auto_create_schema: bool = True


settings = Settings()
