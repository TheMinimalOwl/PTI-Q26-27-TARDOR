"""Caché L1 en Redis.

Invalidación por versión: cada clave lleva delante la versión del catálogo
(`catalog:version`). Cuando el writer carga un lote incrementa la versión y todas las
claves antiguas dejan de usarse (y caducan solas por TTL). Así no hay que buscar ni
borrar claves.

Si Redis no está disponible la API sigue funcionando contra PostgreSQL.
"""
import json
import logging
from typing import Any

import redis

from .config import settings

log = logging.getLogger(__name__)

VERSION_KEY = "catalog:version"


class Cache:
    def __init__(self, url: str, ttl: int):
        self.ttl = ttl
        self.client = redis.Redis.from_url(url, socket_timeout=0.2, socket_connect_timeout=0.2)

    def _version(self) -> str:
        return (self.client.get(VERSION_KEY) or b"0").decode()

    def get(self, key: str) -> Any | None:
        try:
            raw = self.client.get(f"v{self._version()}:{key}")
        except redis.RedisError as exc:
            log.warning("redis no disponible (get): %s", exc)
            return None
        return json.loads(raw) if raw else None

    def set(self, key: str, value: Any) -> None:
        try:
            self.client.set(f"v{self._version()}:{key}", json.dumps(value), ex=self.ttl)
        except redis.RedisError as exc:
            log.warning("redis no disponible (set): %s", exc)

    def invalidate(self) -> None:
        try:
            self.client.incr(VERSION_KEY)
        except redis.RedisError as exc:
            log.warning("redis no disponible (invalidate): %s", exc)

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except redis.RedisError:
            return False


cache = Cache(settings.redis_url, settings.cache_ttl)


def get_cache() -> Cache:
    return cache
