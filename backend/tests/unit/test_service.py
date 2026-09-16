import asyncio
from typing import Any, Dict
import pytest

from app.core.exceptions import UserNotFoundError
from app.providers.base import BaseUserProvider
from app.schemas.user import UserResponse
from app.services.user_fetch_service import UserFetchService


class DummyTrackingProvider(BaseUserProvider):
    """Provedor simulado para rastrear concorrência e retorno controlado."""

    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.active_calls = 0
        self.max_observed_concurrency = 0

    async def fetch_user_by_id(self, user_id: int) -> Dict[str, Any]:
        self.active_calls += 1
        if self.active_calls > self.max_observed_concurrency:
            self.max_observed_concurrency = self.active_calls

        await asyncio.sleep(self.delay)

        self.active_calls -= 1

        if user_id == 404:
            raise UserNotFoundError(user_id=404)
        if user_id == 500:
            raise RuntimeError("Database connection died")

        return {
            "id": user_id,
            "name": f"User {user_id}",
            "email": f"user{user_id}@example.com",
            "company": {"name": f"Company {user_id}"},
        }


@pytest.mark.asyncio
async def test_service_concurrency_semaphore_throttling():
    """Valida que o semáforo restringe estritamente o número de chamadas simultâneas."""
    max_concurrency = 3
    provider = DummyTrackingProvider(delay=0.05)
    service = UserFetchService(provider=provider, max_concurrency=max_concurrency)

    # 10 IDs para um semáforo de 3
    user_ids = list(range(1, 11))
    result = await service.fetch_users_batch(user_ids)

    assert result.meta.total == 10
    assert result.meta.success_count == 10
    assert result.meta.failed_count == 0
    assert result.failed == []
    # A concorrência máxima observada nunca pode ultrapassar o limite do semáforo
    assert provider.max_observed_concurrency <= max_concurrency


@pytest.mark.asyncio
async def test_service_failure_isolation_mixed_results():
    """Valida que erros e exceções não afetam outros usuários no lote e retornam failed como List[int]."""
    provider = DummyTrackingProvider(delay=0.01)
    service = UserFetchService(provider=provider, max_concurrency=5)

    user_ids = [1, 404, 2, 500, 3]
    result = await service.fetch_users_batch(user_ids)

    assert result.meta.total == 5
    assert result.meta.success_count == 3
    assert result.meta.failed_count == 2

    success_ids = [u.id for u in result.users]
    assert success_ids == [1, 2, 3]

    # Contrato conceitual estrito: failed é List[int]
    assert result.failed == [404, 500]

    # Detalhamento enriquecido em errors
    assert len(result.errors) == 2
    failed_404 = next(f for f in result.errors if f.user_id == 404)
    assert failed_404.status_code == 404

    failed_500 = next(f for f in result.errors if f.user_id == 500)
    assert failed_500.status_code == 500


@pytest.mark.asyncio
async def test_service_map_raw_to_response_nested_company():
    """Valida mapeamento correto de campos aninhados e alternativas de empresa."""
    provider = DummyTrackingProvider()
    service = UserFetchService(provider=provider)

    raw_dict = {
        "id": 42,
        "name": "Douglas Adams",
        "username": "dna",
        "email": "dna@galaxy.org",
        "company": {"name": "Megadodo Publications"},
    }
    mapped = service._map_raw_to_response(raw_dict, 42)
    assert isinstance(mapped, UserResponse)
    assert mapped.id == 42
    assert mapped.name == "Douglas Adams"
    assert mapped.company_name == "Megadodo Publications"
