import httpx
import pytest
import respx

from app.core.exceptions import (
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    UserNotFoundError,
)
from app.providers.external_user_provider import ExternalUserProvider


@pytest.mark.asyncio
@respx.mock
async def test_provider_fetch_user_success(mock_user_payload: dict):
    """Valida retorno correto dos dados do provedor para status 200."""
    respx.get("https://jsonplaceholder.typicode.com/users/10").mock(
        return_value=httpx.Response(200, json=mock_user_payload)
    )

    async with httpx.AsyncClient() as client:
        provider = ExternalUserProvider(client=client, timeout=2.0)
        result = await provider.fetch_user_by_id(10)

    assert result["id"] == 1
    assert result["name"] == "Leanne Graham"


@pytest.mark.asyncio
@respx.mock
async def test_provider_fetch_user_not_found():
    """Valida que status 404 levanta UserNotFoundError imediatamente sem retries."""
    route = respx.get("https://jsonplaceholder.typicode.com/users/999").mock(
        return_value=httpx.Response(404, json={})
    )

    async with httpx.AsyncClient() as client:
        provider = ExternalUserProvider(client=client, timeout=2.0)
        with pytest.raises(UserNotFoundError) as exc_info:
            await provider.fetch_user_by_id(999)

    assert exc_info.value.user_id == 999
    assert exc_info.value.status_code == 404
    assert route.call_count == 1  # 404 não deve gerar retries


@pytest.mark.asyncio
@respx.mock
async def test_provider_fetch_user_server_error_retries():
    """Valida que status 500 dispara retries com backoff e levanta ProviderServerError."""
    route = respx.get("https://jsonplaceholder.typicode.com/users/50").mock(
        return_value=httpx.Response(500, json={"message": "Internal Server Error"})
    )

    async with httpx.AsyncClient() as client:
        provider = ExternalUserProvider(client=client, timeout=2.0)
        with pytest.raises(ProviderServerError) as exc_info:
            await provider.fetch_user_by_id(50)

    assert exc_info.value.user_id == 50
    assert exc_info.value.status_code == 500
    assert route.call_count == 3  # stop_after_attempt(3)


@pytest.mark.asyncio
@respx.mock
async def test_provider_fetch_user_timeout():
    """Valida que timeout na conexão é capturado e encapsulado em ProviderTimeoutError."""
    respx.get("https://jsonplaceholder.typicode.com/users/77").mock(
        side_effect=httpx.ConnectTimeout("Connect timeout")
    )

    async with httpx.AsyncClient() as client:
        provider = ExternalUserProvider(client=client, timeout=1.0)
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await provider.fetch_user_by_id(77)

    assert exc_info.value.user_id == 77
    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
@respx.mock
async def test_provider_fetch_user_rate_limit_retry_after():
    """Valida que status 429 captura e parseia o cabeçalho Retry-After."""
    respx.get("https://jsonplaceholder.typicode.com/users/88").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0.1"}, json={"error": "Too Many Requests"})
    )

    async with httpx.AsyncClient() as client:
        provider = ExternalUserProvider(client=client, timeout=2.0)
        with pytest.raises(ProviderRateLimitError) as exc_info:
            await provider.fetch_user_by_id(88)

    assert exc_info.value.user_id == 88
    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after == 0.1
