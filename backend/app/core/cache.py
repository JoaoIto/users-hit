import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple


class BaseCache(ABC):
    """Interface abstrata para camada de cache desacoplada (Clean Architecture).
    
    Permite alternar transparentemente entre implementações em memória,
    Redis, Memcached ou cache distribuído sem alterar o código de domínio.
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Recupera um valor do cache se ainda não tiver expirado."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Armazena um valor no cache associado a um tempo de vida (TTL)."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove uma chave específica do cache."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Limpa todas as entradas do cache."""
        pass


class InMemoryTTLCache(BaseCache):
    """Implementação em memória thread-safe e assíncrona com expiração por TTL."""

    def __init__(self, default_ttl: int = 60):
        self.default_ttl = default_ttl
        self._store: Dict[str, Tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            value, expire_at = entry
            # Verifica se o TTL expirou
            if time.time() > expire_at:
                del self._store[key]
                return None

            return value

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expire_at = time.time() + max(0, ttl)

        async with self._lock:
            self._store[key] = (value, expire_at)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    async def purge_expired(self) -> int:
        """Remove todas as chaves expiradas para liberar memória."""
        now = time.time()
        purged = 0
        async with self._lock:
            expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired_keys:
                del self._store[k]
                purged += 1
        return purged


# Singleton global de cache em memória
_cache_instance: Optional[BaseCache] = None


def get_cache() -> BaseCache:
    """Dependency provider para injeção de dependência do cache."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = InMemoryTTLCache(default_ttl=60)
    return _cache_instance
