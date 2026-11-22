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

    # Servei d'embeddings de l'equip d'IA (flujo-ia, VM 2): URL base, p. ex.
    # http://10.4.41.108:8080 (s'hi afegeix /embed). Buit = sense embeddings: els productes
    # es queden a NULL i la cerca semàntica per text respon 503.
    rag_embed_url: str = ""
    # Clau de la capçalera X-API-Key. Només per entorn (.env fora del repo o Secret de k8s):
    # mai al codi, als logs ni en un commit.
    rag_embed_api_key: str = ""
    embed_batch_size: int = 256  # textos per petició (el servei n'accepta 256 com a màxim)
    embed_timeout: float = 60    # segons per petició (el model va en CPU)

    # Crea les extensions i les taules en arrencar si no existeixen.
    auto_create_schema: bool = True


settings = Settings()
