import asyncio
from typing import AsyncGenerator, Dict
import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from app.core.cache import get_cache
from app.core.config import Settings, get_settings
from app.core.database import init_db
from app.main import app


def get_test_settings() -> Settings:
    return Settings(
        ENVIRONMENT="testing",
        LOG_LEVEL="DEBUG",
        EXTERNAL_USERS_API_URL="https://jsonplaceholder.typicode.com",
        MAX_CONCURRENCY=5,
        REQUEST_TIMEOUT=2.0,
        MAX_BATCH_SIZE=100,
        CACHE_TTL_SECONDS=60,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        RETRY_MAX_ATTEMPTS=2,
        RETRY_INITIAL_WAIT=0.01,
        RETRY_MAX_WAIT=0.05,
    )


@pytest_asyncio.fixture(autouse=True)
async def setup_test_environment():
    test_settings = get_test_settings()
    app.dependency_overrides[get_settings] = lambda: test_settings
    await get_cache().clear()
    await init_db()
    yield
    await asyncio.sleep(0.05)
    await get_cache().clear()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Cliente HTTP assíncrono para testes na API FastAPI com cliente HTTP mockado limpo a cada teste."""
    # Cria um novo client externo para o app a cada teste, garantindo estado isolado
    external_client = httpx.AsyncClient()
    app.state.http_client = external_client

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await external_client.aclose()
    app.state.http_client = None


@pytest.fixture
def mock_user_payload() -> Dict[str, object]:
    return {
        "id": 1,
        "name": "Leanne Graham",
        "username": "Bret",
        "email": "Sincere@april.biz",
        "phone": "1-770-736-8031 x56442",
        "website": "hildegard.org",
        "company": {
            "name": "Romaguera-Crona",
            "catchPhrase": "Multi-layered client-server neural-net",
            "bs": "harness real-time e-markets",
        },
    }
