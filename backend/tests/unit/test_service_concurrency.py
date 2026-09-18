import asyncio
from typing import Any, Dict
import pytest

from app.core.cache import InMemoryTTLCache
from app.core.exceptions import (
    ProviderError,
    ProviderServerError,
    ProviderTimeoutError,
    UserNotFoundError,
)
from app.providers.base import BaseUserProvider
from app.schemas.user import FailedUserDetail, UserResponse
from app.services.user_fetch_service import UserFetchService


class ThrottledMockProvider(BaseUserProvider):
    """Provedor mock que rastreia concorrência máxima simultânea para validar o semáforo."""

    def __init__(self, delay: float = 0.03):
        self.delay = delay
        self.current_concurrency = 0
        self.max_concurrency_seen = 0
        self.lock = asyncio.Lock()

    async def fetch_user_by_id(self, user_id: int) -> Dict[str, Any]:
        async with self.lock:
            self.current_concurrency += 1
            if self.current_concurrency > self.max_concurrency_seen:
                self.max_concurrency_seen = self.current_concurrency

        await asyncio.sleep(self.delay)

        async with self.lock:
            self.current_concurrency -= 1

        return {
            "id": user_id,
            "name": f"User {user_id}",
            "username": f"user{user_id}",
            "email": f"user{user_id}@example.com",
            "company": {"name": f"Company {user_id}"},
        }


class HeterogeneousMockProvider(BaseUserProvider):
    """Provedor que retorna respostas variadas para testar o padrão Bulkhead."""

    async def fetch_user_by_id(self, user_id: int) -> Dict[str, Any]:
        if user_id == 1:
            return {"id": 1, "name": "Valid User", "username": "valid1"}
        elif user_id == 2:
            raise UserNotFoundError(user_id=2)
        elif user_id == 3:
            raise ProviderTimeoutError(user_id=3, timeout_seconds=2.0)
        elif user_id == 4:
            raise ProviderServerError(user_id=4, status_code=500)
        elif user_id == 5:
            raise ProviderError(user_id=5, message="Custom provider failure", status_code=502)
        elif user_id == 6:
            raise RuntimeError("Unexpected low-level memory failure")
        return {"id": user_id, "name": f"User {user_id}"}


class TestUserFetchServiceConcurrency:
    @pytest.mark.asyncio
    async def test_semaphore_throttles_concurrency_strictly(self):
        """Garante que a concorrencia simultanea respeita estritamente o semaforo (max_concurrency=4)."""
        provider = ThrottledMockProvider(delay=0.04)
        service = UserFetchService(provider=provider, max_concurrency=4)

        # Dispara 16 IDs simultaneos
        user_ids = list(range(1, 17))
        response = await service.fetch_users_batch(user_ids)

        assert len(response.users) == 16
        assert len(response.failed) == 0
        assert provider.max_concurrency_seen <= 4
        assert provider.max_concurrency_seen > 1

    @pytest.mark.asyncio
    async def test_cache_short_circuit_skips_provider(self):
        """Garante que IDs com Cache Hit nao acionam o provedor externo."""
        cache = InMemoryTTLCache(default_ttl=60)
        # Pre-popula cache para user:1
        await cache.set("user:1", {"id": 1, "name": "Cached Alice", "username": "alice"})

        provider = ThrottledMockProvider(delay=0.01)
        service = UserFetchService(provider=provider, max_concurrency=5, cache=cache)

        response = await service.fetch_users_batch([1, 2])

        assert len(response.users) == 2
        user_1 = next(u for u in response.users if u.id == 1)
        user_2 = next(u for u in response.users if u.id == 2)

        assert user_1.cached is True
        assert user_1.name == "Cached Alice"
        assert user_2.cached is False

        # Verifica que o provedor foi acionado apenas para o user 2
        assert response.meta.cache_hits == 1

    @pytest.mark.asyncio
    async def test_bulkhead_fault_isolation_comprehensive(self):
        """Valida que falhas diversas nao derrubam o lote e isolam falhas em failed e errors."""
        provider = HeterogeneousMockProvider()
        service = UserFetchService(provider=provider, max_concurrency=10)

        response = await service.fetch_users_batch([1, 2, 3, 4, 5, 6])

        # Apenas ID 1 teve sucesso
        assert len(response.users) == 1
        assert response.users[0].id == 1

        # IDs 2, 3, 4, 5, 6 devem estar em failed
        assert response.failed == [2, 3, 4, 5, 6]
        assert len(response.errors) == 5

        error_map = {e.user_id: e for e in response.errors}
        assert error_map[2].status_code == 404
        assert error_map[3].status_code == 504
        assert error_map[4].status_code == 500
        assert error_map[5].status_code == 502
        assert error_map[6].status_code == 500
        assert "Unexpected low-level memory failure" in error_map[6].reason

    @pytest.mark.asyncio
    async def test_gather_unhandled_exception_branch(self):
        """Testa o ramo onde gather retorna uma exceção direta como resultado."""
        provider = ThrottledMockProvider()
        service = UserFetchService(provider=provider, max_concurrency=5)

        # Mocka _fetch_single_user para levantar diretamente
        async def failing_fetch(uid):
            raise ValueError("Direct gather exception")

        service._fetch_single_user = failing_fetch
        response = await service.fetch_users_batch([10])

        assert response.failed == [10]
        assert len(response.errors) == 1
        assert "Direct gather exception" in response.errors[0].reason

    def test_map_raw_to_response_variations(self):
        service = UserFetchService(provider=ThrottledMockProvider())

        # 1. Com objeto de company aninhado
        raw1 = {"id": 10, "name": "Bob", "company": {"name": "Tech Corp"}}
        res1 = service._map_raw_to_response(raw1, fallback_id=10)
        assert res1.company_name == "Tech Corp"

        # 2. Com campo plano company_name
        raw2 = {"id": 20, "name": "Carol", "company_name": "Flat Corp"}
        res2 = service._map_raw_to_response(raw2, fallback_id=20)
        assert res2.company_name == "Flat Corp"

        # 3. Sem nome (fallback para 'Usuário {user_id}')
        raw3 = {"id": 30}
        res3 = service._map_raw_to_response(raw3, fallback_id=30)
        assert "Usuário 30" in res3.name

        # 4. Sem id no payload (fallback para fallback_id)
        raw4 = {"name": "No ID"}
        res4 = service._map_raw_to_response(raw4, fallback_id=40)
        assert res4.id == 40
