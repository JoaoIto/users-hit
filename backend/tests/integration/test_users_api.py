import httpx
import pytest
import respx


@pytest.mark.asyncio
@respx.mock
async def test_users_fetch_success_full(async_client: httpx.AsyncClient, mock_user_payload: dict):
    """Teste 1: Consulta de lote com 100% de sucesso retornando todos os usuários no formato esperado."""
    user1 = {**mock_user_payload, "id": 1, "name": "Alice Johnson"}
    user2 = {**mock_user_payload, "id": 2, "name": "Bob Smith"}

    respx.get("https://jsonplaceholder.typicode.com/users/1").mock(
        return_value=httpx.Response(200, json=user1)
    )
    respx.get("https://jsonplaceholder.typicode.com/users/2").mock(
        return_value=httpx.Response(200, json=user2)
    )

    response = await async_client.post("/api/users/fetch", json={"user_ids": [1, 2]})

    assert response.status_code == 200
    data = response.json()

    # Contrato estrito: failed deve ser List[int] vazia em sucesso total
    assert data["failed"] == []
    assert len(data["users"]) == 2
    assert len(data["errors"]) == 0

    # Metadados operacionais
    assert data["meta"]["total"] == 2
    assert data["meta"]["success_count"] == 2
    assert data["meta"]["failed_count"] == 0
    assert data["meta"]["execution_time_ms"] >= 0

    assert data["users"][0]["id"] == 1
    assert data["users"][0]["name"] == "Alice Johnson"
    assert data["users"][0]["company_name"] == "Romaguera-Crona"
    assert data["users"][1]["id"] == 2
    assert data["users"][1]["name"] == "Bob Smith"


@pytest.mark.asyncio
@respx.mock
async def test_users_fetch_partial_failures_isolation(async_client: httpx.AsyncClient, mock_user_payload: dict):
    """Teste 2: Lote contendo IDs com status 200, 404, 500 e Timeout simulado,
    comprovando isolamento total de falhas e conformidade com failed: [2, 3, 4] e errors enriquecidos.
    """
    user1 = {**mock_user_payload, "id": 1, "name": "Carol White"}

    # ID 1: Sucesso 200
    respx.get("https://jsonplaceholder.typicode.com/users/1").mock(
        return_value=httpx.Response(200, json=user1)
    )
    # ID 2: 404 Not Found (usuário inexistente)
    respx.get("https://jsonplaceholder.typicode.com/users/2").mock(
        return_value=httpx.Response(404, json={})
    )
    # ID 3: 500 Internal Server Error (falha temporária no provedor)
    respx.get("https://jsonplaceholder.typicode.com/users/3").mock(
        return_value=httpx.Response(500, json={"error": "Internal Server Error"})
    )
    # ID 4: Simulação de Timeout de rede
    respx.get("https://jsonplaceholder.typicode.com/users/4").mock(
        side_effect=httpx.ConnectTimeout("Connection timed out")
    )

    response = await async_client.post("/api/users/fetch", json={"user_ids": [1, 2, 3, 4]})

    assert response.status_code == 200
    data = response.json()

    # Conformidade estrita: failed é exatamente List[int]
    assert data["failed"] == [2, 3, 4]
    assert len(data["users"]) == 1
    assert data["users"][0]["id"] == 1

    # Metadados operacionais
    assert data["meta"]["total"] == 4
    assert data["meta"]["success_count"] == 1
    assert data["meta"]["failed_count"] == 3

    # Mapeamento enriquecido das falhas
    errors_map = {item["user_id"]: item for item in data["errors"]}

    assert errors_map[2]["status_code"] == 404
    assert "not found" in errors_map[2]["reason"].lower()

    assert errors_map[3]["status_code"] == 500
    assert "500" in errors_map[3]["reason"]

    assert errors_map[4]["status_code"] == 504
    assert "timed out" in errors_map[4]["reason"].lower()


@pytest.mark.asyncio
async def test_users_fetch_validation_empty_list(async_client: httpx.AsyncClient):
    """Teste 3a: Envio de payload inválido (lista vazia), garantindo retorno HTTP 422."""
    response = await async_client.post("/api/users/fetch", json={"user_ids": []})
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_users_fetch_validation_exceeds_max_limit(async_client: httpx.AsyncClient):
    """Teste 3b: Envio de mais de 100 itens no lote, garantindo retorno HTTP 422."""
    excessive_ids = list(range(1, 102))  # 101 IDs
    response = await async_client.post("/api/users/fetch", json={"user_ids": excessive_ids})
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_users_fetch_validation_negative_or_zero_ids(async_client: httpx.AsyncClient):
    """Teste 3c: Envio de IDs inválidos (<= 0), garantindo retorno HTTP 422."""
    response = await async_client.post("/api/users/fetch", json={"user_ids": [1, -5, 0]})
    assert response.status_code == 422


@pytest.mark.asyncio
@respx.mock
async def test_users_fetch_deduplication(async_client: httpx.AsyncClient, mock_user_payload: dict):
    """Teste: Deduplicação automática preservando a ordem original."""
    user1 = {**mock_user_payload, "id": 1, "name": "User 1"}
    user2 = {**mock_user_payload, "id": 2, "name": "User 2"}
    user3 = {**mock_user_payload, "id": 3, "name": "User 3"}

    respx.get("https://jsonplaceholder.typicode.com/users/1").mock(return_value=httpx.Response(200, json=user1))
    respx.get("https://jsonplaceholder.typicode.com/users/2").mock(return_value=httpx.Response(200, json=user2))
    respx.get("https://jsonplaceholder.typicode.com/users/3").mock(return_value=httpx.Response(200, json=user3))

    # Enviando IDs repetidos [1, 2, 1, 3, 2]
    response = await async_client.post("/api/users/fetch", json={"user_ids": [1, 2, 1, 3, 2]})
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["total"] == 3
    assert [u["id"] for u in data["users"]] == [1, 2, 3]


@pytest.mark.asyncio
@respx.mock
async def test_users_fetch_v1_alias(async_client: httpx.AsyncClient, mock_user_payload: dict):
    """Teste: O endpoint /api/v1/users/fetch deve funcionar identicamente ao /api/users/fetch."""
    respx.get("https://jsonplaceholder.typicode.com/users/1").mock(
        return_value=httpx.Response(200, json=mock_user_payload)
    )
    response = await async_client.post("/api/v1/users/fetch", json={"user_ids": [1]})
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["success_count"] == 1


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: httpx.AsyncClient):
    """Teste: Health check do sistema."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
@respx.mock
async def test_users_fetch_cache_hit_workflow(async_client: httpx.AsyncClient, mock_user_payload: dict):
    """Teste Diferencial: Validação do TTL Cache (primeira chamada MISS, segunda chamada HIT instantâneo)."""
    user1 = {**mock_user_payload, "id": 1, "name": "Cache Test User"}

    # Rota mockada: monitoramos a quantidade de chamadas
    route = respx.get("https://jsonplaceholder.typicode.com/users/1").mock(
        return_value=httpx.Response(200, json=user1)
    )

    # 1ª chamada: Cache MISS (consulta a rede)
    res1 = await async_client.post("/api/users/fetch", json={"user_ids": [1]})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["meta"]["cache_hits"] == 0
    assert data1["users"][0]["cached"] is False
    assert route.call_count == 1

    # 2ª chamada idêntica: Cache HIT (retorna da memória sem bater na rede)
    res2 = await async_client.post("/api/users/fetch", json={"user_ids": [1]})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["meta"]["cache_hits"] == 1
    assert data2["users"][0]["cached"] is True
    # O mock externo continua com apenas 1 chamada efetuada!
    assert route.call_count == 1
