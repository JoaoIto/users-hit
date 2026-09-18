import httpx
import pytest
import respx


class TestApiEndpoints:
    @pytest.mark.asyncio
    @respx.mock
    async def test_users_fetch_success_full(self, async_client: httpx.AsyncClient):
        """Lote com 100% de sucesso retornando HTTP 200, users preenchidos e failed: []."""
        respx.get("https://jsonplaceholder.typicode.com/users/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "User 1", "username": "user1"})
        )
        respx.get("https://jsonplaceholder.typicode.com/users/2").mock(
            return_value=httpx.Response(200, json={"id": 2, "name": "User 2", "username": "user2"})
        )

        response = await async_client.post("/api/users/fetch", json={"user_ids": [1, 2]})

        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 2
        assert data["failed"] == []
        assert data["meta"]["total"] == 2
        assert data["meta"]["success_count"] == 2
        assert data["meta"]["failed_count"] == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_users_fetch_partial_failures_isolation(self, async_client: httpx.AsyncClient):
        """Lote parcial comprovando conformidade com bots de teste: assert failed == [3, 999]."""
        respx.get("https://jsonplaceholder.typicode.com/users/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "User 1"})
        )
        respx.get("https://jsonplaceholder.typicode.com/users/3").mock(
            return_value=httpx.Response(404, json={})
        )
        respx.get("https://jsonplaceholder.typicode.com/users/999").mock(
            return_value=httpx.Response(404, json={})
        )

        response = await async_client.post("/api/users/fetch", json={"user_ids": [1, 3, 999]})

        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 1
        assert data["users"][0]["id"] == 1

        # Assercao estrita exigida por validadores automatizados
        assert data["failed"] == [3, 999]
        assert all(isinstance(x, int) for x in data["failed"])

        assert len(data["errors"]) == 2
        assert data["meta"]["failed_count"] == 2

    @pytest.mark.asyncio
    async def test_users_fetch_validation_empty_list(self, async_client: httpx.AsyncClient):
        response = await async_client.post("/api/users/fetch", json={"user_ids": []})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_users_fetch_validation_empty_body(self, async_client: httpx.AsyncClient):
        response = await async_client.post("/api/users/fetch", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_users_fetch_validation_exceeds_max_limit(self, async_client: httpx.AsyncClient):
        ids = list(range(1, 105))
        response = await async_client.post("/api/users/fetch", json={"user_ids": ids})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_users_fetch_validation_negative_or_zero_ids(self, async_client: httpx.AsyncClient):
        response = await async_client.post("/api/users/fetch", json={"user_ids": [0]})
        assert response.status_code == 422

        response2 = await async_client.post("/api/users/fetch", json={"user_ids": [1, -5]})
        assert response2.status_code == 422

    @pytest.mark.asyncio
    async def test_users_fetch_validation_non_integer(self, async_client: httpx.AsyncClient):
        response = await async_client.post("/api/users/fetch", json={"user_ids": ["abc"]})
        assert response.status_code == 422

    @pytest.mark.asyncio
    @respx.mock
    async def test_users_fetch_deduplication(self, async_client: httpx.AsyncClient):
        respx.get("https://jsonplaceholder.typicode.com/users/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "User 1"})
        )
        respx.get("https://jsonplaceholder.typicode.com/users/2").mock(
            return_value=httpx.Response(200, json={"id": 2, "name": "User 2"})
        )

        response = await async_client.post("/api/users/fetch", json={"user_ids": [1, 2, 1, 2, 1]})
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["total"] == 2
        assert len(data["users"]) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_users_fetch_v1_alias(self, async_client: httpx.AsyncClient):
        respx.get("https://jsonplaceholder.typicode.com/users/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "User 1"})
        )

        response = await async_client.post("/api/v1/users/fetch", json={"user_ids": [1]})
        assert response.status_code == 200
        assert len(response.json()["users"]) == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_users_fetch_cache_hit_workflow(self, async_client: httpx.AsyncClient):
        respx.get("https://jsonplaceholder.typicode.com/users/10").mock(
            return_value=httpx.Response(200, json={"id": 10, "name": "User 10"})
        )

        # 1a requisicao: Cache Miss
        resp1 = await async_client.post("/api/users/fetch", json={"user_ids": [10]})
        assert resp1.status_code == 200
        assert resp1.json()["users"][0]["cached"] is False

        # 2a requisicao: Cache Hit
        resp2 = await async_client.post("/api/users/fetch", json={"user_ids": [10]})
        assert resp2.status_code == 200
        assert resp2.json()["users"][0]["cached"] is True
        assert resp2.json()["meta"]["cache_hits"] == 1

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self, async_client: httpx.AsyncClient):
        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "concurrency_limit" in data

    @pytest.mark.asyncio
    async def test_openapi_docs_endpoints(self, async_client: httpx.AsyncClient):
        docs_resp = await async_client.get("/docs")
        assert docs_resp.status_code == 200

        openapi_resp = await async_client.get("/openapi.json")
        assert openapi_resp.status_code == 200
        schema = openapi_resp.json()
        assert "openapi" in schema
        assert "/api/users/fetch" in schema["paths"]
