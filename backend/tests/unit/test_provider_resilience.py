from unittest.mock import MagicMock
import httpx
import pytest
import respx
from tenacity import RetryCallState

from app.core.exceptions import (
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    UserNotFoundError,
)
from app.providers.external_user_provider import (
    ExternalUserProvider,
    wait_retry_after_or_exponential,
)


class TestWaitRetryAfterOrExponential:
    def test_wait_with_retry_after_header(self):
        fallback = MagicMock(return_value=1.0)
        wait_strategy = wait_retry_after_or_exponential(fallback_wait=fallback, max_wait=10.0)

        retry_state = MagicMock(spec=RetryCallState)
        retry_state.outcome = MagicMock()
        retry_state.outcome.failed = True
        retry_state.outcome.exception.return_value = ProviderRateLimitError(user_id=1, retry_after=3.5)

        wait_time = wait_strategy(retry_state)
        assert wait_time == 3.5
        fallback.assert_not_called()

    def test_wait_with_retry_after_exceeding_max_wait(self):
        fallback = MagicMock(return_value=1.0)
        wait_strategy = wait_retry_after_or_exponential(fallback_wait=fallback, max_wait=8.0)

        retry_state = MagicMock(spec=RetryCallState)
        retry_state.outcome = MagicMock()
        retry_state.outcome.failed = True
        retry_state.outcome.exception.return_value = ProviderRateLimitError(user_id=1, retry_after=30.0)

        wait_time = wait_strategy(retry_state)
        assert wait_time == 8.0  # Teto max_wait respeitado

    def test_wait_fallback_when_no_retry_after(self):
        fallback = MagicMock(return_value=2.2)
        wait_strategy = wait_retry_after_or_exponential(fallback_wait=fallback, max_wait=10.0)

        retry_state = MagicMock(spec=RetryCallState)
        retry_state.outcome = MagicMock()
        retry_state.outcome.failed = True
        retry_state.outcome.exception.return_value = ProviderServerError(user_id=1, status_code=500)

        wait_time = wait_strategy(retry_state)
        assert wait_time == 2.2
        fallback.assert_called_once_with(retry_state)


class TestParseRetryAfter:
    def test_parse_valid_seconds(self):
        assert ExternalUserProvider._parse_retry_after("5") == 5.0
        assert ExternalUserProvider._parse_retry_after(" 2.5 ") == 2.5

    def test_parse_negative_seconds(self):
        assert ExternalUserProvider._parse_retry_after("-3") == 0.0

    def test_parse_none_or_invalid(self):
        assert ExternalUserProvider._parse_retry_after(None) is None
        assert ExternalUserProvider._parse_retry_after("") is None
        assert ExternalUserProvider._parse_retry_after("invalid-date-string") is None


class TestExternalUserProviderResilience:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_user_success(self, mock_user_payload):
        respx.get("https://jsonplaceholder.typicode.com/users/1").mock(
            return_value=httpx.Response(200, json=mock_user_payload)
        )

        async with httpx.AsyncClient() as client:
            provider = ExternalUserProvider(client=client, base_url="https://jsonplaceholder.typicode.com")
            data = await provider.fetch_user_by_id(1)

        assert data["id"] == 1
        assert data["name"] == "Leanne Graham"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_user_404_not_found_zero_retries(self):
        """Valida que HTTP 404 lanca UserNotFoundError de imediato com ZERO retentativas."""
        route = respx.get("https://jsonplaceholder.typicode.com/users/999").mock(
            return_value=httpx.Response(404, json={})
        )

        async with httpx.AsyncClient() as client:
            provider = ExternalUserProvider(client=client, base_url="https://jsonplaceholder.typicode.com")
            with pytest.raises(UserNotFoundError) as exc_info:
                await provider.fetch_user_by_id(999)

        assert exc_info.value.user_id == 999
        assert exc_info.value.status_code == 404
        assert route.call_count == 1  # Exatamente 1 chamada, sem retentativas!

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_user_server_error_500_retries_exhausted(self):
        """Valida que falhas 5xx retentam ate esgotar as 3 tentativas do Tenacity."""
        route = respx.get("https://jsonplaceholder.typicode.com/users/2").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        async with httpx.AsyncClient() as client:
            provider = ExternalUserProvider(client=client, base_url="https://jsonplaceholder.typicode.com")
            with pytest.raises(ProviderServerError) as exc_info:
                await provider.fetch_user_by_id(2)

        assert exc_info.value.user_id == 2
        assert exc_info.value.status_code == 500
        assert route.call_count == 3  # 3 tentativas antes de propagar

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_user_rate_limit_429_retries_exhausted(self):
        """Valida que HTTP 429 com cabeçalho Retry-After retenta e mapeia para ProviderRateLimitError."""
        route = respx.get("https://jsonplaceholder.typicode.com/users/429").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "0.01"}, text="Too Many Requests")
        )

        async with httpx.AsyncClient() as client:
            provider = ExternalUserProvider(client=client, base_url="https://jsonplaceholder.typicode.com")
            with pytest.raises(ProviderRateLimitError) as exc_info:
                await provider.fetch_user_by_id(429)

        assert exc_info.value.user_id == 429
        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 0.01
        assert route.call_count == 3

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_user_socket_timeout_exhausted(self):
        """Valida que timeouts de socket sao capturados e mapeados para ProviderTimeoutError."""
        route = respx.get("https://jsonplaceholder.typicode.com/users/3").mock(
            side_effect=httpx.TimeoutException("Connection timed out")
        )

        async with httpx.AsyncClient() as client:
            provider = ExternalUserProvider(client=client, base_url="https://jsonplaceholder.typicode.com", timeout=2.0)
            with pytest.raises(ProviderTimeoutError) as exc_info:
                await provider.fetch_user_by_id(3)

        assert exc_info.value.user_id == 3
        assert exc_info.value.status_code == 504
        assert route.call_count == 3

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_user_network_connect_error(self):
        """Valida erro de conexao de rede mapeado para ProviderError."""
        route = respx.get("https://jsonplaceholder.typicode.com/users/4").mock(
            side_effect=httpx.ConnectError("Failed to resolve host")
        )

        async with httpx.AsyncClient() as client:
            provider = ExternalUserProvider(client=client, base_url="https://jsonplaceholder.typicode.com")
            with pytest.raises(ProviderError) as exc_info:
                await provider.fetch_user_by_id(4)

        assert exc_info.value.user_id == 4
        assert route.call_count == 3

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_user_client_error_403(self):
        """Valida erro 4xx generico (nao 404/429) mapeado para ProviderError sem retentativas."""
        route = respx.get("https://jsonplaceholder.typicode.com/users/5").mock(
            return_value=httpx.Response(403, text="Forbidden")
        )

        async with httpx.AsyncClient() as client:
            provider = ExternalUserProvider(client=client, base_url="https://jsonplaceholder.typicode.com")
            with pytest.raises(ProviderError) as exc_info:
                await provider.fetch_user_by_id(5)

        assert exc_info.value.user_id == 5
        assert exc_info.value.status_code == 403
        assert route.call_count == 1
