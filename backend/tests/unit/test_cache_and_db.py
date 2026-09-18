import os
from unittest.mock import AsyncMock, patch
import pytest

from app.core.cache import BaseCache, InMemoryTTLCache, get_cache
from app.core.config import Settings
from app.core.database import (
    Base,
    BatchQuery,
    get_db_url,
    init_db,
    record_batch_query,
)


class DummyCache(BaseCache):
    """Subclasse para testar a interface abstrata BaseCache."""
    pass


class TestBaseCacheInterface:
    def test_cannot_instantiate_abstract_cache(self):
        with pytest.raises(TypeError):
            DummyCache()  # type: ignore


class TestInMemoryTTLCache:
    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        cache = InMemoryTTLCache(default_ttl=60)
        result = await cache.get("non_existent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_returns_stored_value(self):
        cache = InMemoryTTLCache(default_ttl=60)
        await cache.set("user:1", {"id": 1, "name": "Ada Lovelace"})
        result = await cache.get("user:1")
        assert result == {"id": 1, "name": "Ada Lovelace"}

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration_lazy_eviction(self):
        cache = InMemoryTTLCache(default_ttl=5)

        with patch("time.time", return_value=1000.0):
            await cache.set("key1", "value1", ttl_seconds=5)
            assert await cache.get("key1") == "value1"

        # Simula o tempo avancando alem do TTL
        with patch("time.time", return_value=1006.0):
            # No get, deve ocorrer lazy eviction e retornar None
            assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_cache_delete_key(self):
        cache = InMemoryTTLCache(default_ttl=60)
        await cache.set("temp", 123)
        assert await cache.get("temp") == 123

        await cache.delete("temp")
        assert await cache.get("temp") is None

        # Deletar chave inexistente nao lanca excecao
        await cache.delete("non_existent")

    @pytest.mark.asyncio
    async def test_cache_clear(self):
        cache = InMemoryTTLCache(default_ttl=60)
        await cache.set("k1", 1)
        await cache.set("k2", 2)
        await cache.clear()

        assert await cache.get("k1") is None
        assert await cache.get("k2") is None

    @pytest.mark.asyncio
    async def test_purge_expired(self):
        cache = InMemoryTTLCache(default_ttl=10)

        with patch("time.time", return_value=1000.0):
            await cache.set("active", "live", ttl_seconds=20)
            await cache.set("expired1", "dead", ttl_seconds=5)
            await cache.set("expired2", "dead", ttl_seconds=8)

        # No tempo 1010, expired1 e expired2 estao expirados, active ainda e valido
        with patch("time.time", return_value=1010.0):
            purged_count = await cache.purge_expired()
            assert purged_count == 2
            assert await cache.get("active") == "live"
            assert await cache.get("expired1") is None

    def test_get_cache_singleton(self):
        cache1 = get_cache()
        cache2 = get_cache()
        assert cache1 is cache2
        assert isinstance(cache1, InMemoryTTLCache)


class TestDatabaseAndAudit:
    @pytest.mark.asyncio
    async def test_init_db_creates_tables(self):
        await init_db()
        assert "batch_queries" in Base.metadata.tables

    @pytest.mark.asyncio
    async def test_init_db_error_logged(self):
        """Testa o tratamento de falha na inicializacao do banco."""
        with patch.object(Base.metadata, "create_all", side_effect=Exception("DB init failed")):
            # Nao deve levantar excecao, apenas logar erro
            await init_db()

    def test_get_db_url_with_custom_postgresql(self):
        custom_settings = Settings(DATABASE_URL="postgresql://user:pass@localhost:5432/mydb")
        with patch("app.core.database.get_settings", return_value=custom_settings):
            url = get_db_url()
            assert url == "postgresql+asyncpg://user:pass@localhost:5432/mydb"

    def test_get_db_url_serverless_detection(self):
        custom_settings = Settings(DATABASE_URL=None)
        with patch("app.core.database.get_settings", return_value=custom_settings):
            with patch.dict(os.environ, {"VERCEL": "1"}):
                url = get_db_url()
                assert url == "sqlite+aiosqlite:////tmp/batch_history.db"

    def test_get_db_url_default_local(self):
        custom_settings = Settings(DATABASE_URL=None)
        with patch("app.core.database.get_settings", return_value=custom_settings):
            with patch.dict(os.environ, {}, clear=True):
                with patch("os.access", return_value=True):
                    url = get_db_url()
                    assert url == "sqlite+aiosqlite:///./batch_history.db"

    @pytest.mark.asyncio
    async def test_record_batch_query_successful(self):
        await init_db()
        await record_batch_query(
            query_id="query-test-uuid",
            requested_ids=[1, 2, 3],
            success_count=2,
            failed_count=1,
            cache_hits=1,
            execution_time_ms=35.5,
        )

    @pytest.mark.asyncio
    async def test_record_batch_query_silences_io_errors(self):
        """Garante que falhas de banco de dados nao quebrem o fluxo HTTP (resiliencia de auditoria)."""
        class FailingSessionContext:
            async def __aenter__(self):
                raise RuntimeError("Disk full / I/O failure")
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return False

        with patch("app.core.database.async_session_factory", return_value=FailingSessionContext()):
            # Nao deve levantar excecao
            await record_batch_query(
                query_id="failed-audit-id",
                requested_ids=[1],
                success_count=1,
                failed_count=0,
                cache_hits=0,
                execution_time_ms=10.0,
            )
