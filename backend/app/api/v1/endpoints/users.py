from fastapi import APIRouter, Depends, Request, status
import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.providers.external_user_provider import ExternalUserProvider
from app.schemas.user import UserBatchResponse, UserFetchRequest
from app.services.user_fetch_service import UserFetchService

logger = get_logger("users_endpoint")
router = APIRouter()


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Recupera a instância compartilhada de httpx.AsyncClient mantida no app.state."""
    client = getattr(request.app.state, "http_client", None)
    if client is None:
        # Fallback defensivo caso o lifespan não esteja ativo (ex: testes manuais)
        return httpx.AsyncClient()
    return client


def get_user_fetch_service(
    client: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> UserFetchService:
    """Dependency Provider para injeção de dependência desacoplada da camada de serviço."""
    provider = ExternalUserProvider(
        client=client,
        base_url=settings.EXTERNAL_USERS_API_URL,
        timeout=settings.REQUEST_TIMEOUT,
        max_attempts=settings.RETRY_MAX_ATTEMPTS,
    )
    return UserFetchService(
        provider=provider,
        max_concurrency=settings.MAX_CONCURRENCY,
    )


@router.post(
    "/fetch",
    response_model=UserBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta concorrente de usuários por lote de IDs",
    description=(
        "Recebe uma lista de IDs de usuários, consulta a API externa de forma assíncrona "
        "com controle de concorrência e tolerância a falhas parciais, retornando os "
        "usuários encontrados e os erros isolados."
    ),
    responses={
        200: {
            "description": "Lote processado com sucesso (pode conter falhas parciais isoladas)",
            "model": UserBatchResponse,
        },
        422: {
            "description": "Dados de requisição inválidos (lista vazia, mais de 100 itens ou tipos inválidos)",
        },
    },
)
async def fetch_users_batch(
    payload: UserFetchRequest,
    service: UserFetchService = Depends(get_user_fetch_service),
) -> UserBatchResponse:
    logger.info("api_user_fetch_batch_received", requested_count=len(payload.user_ids))
    result = await service.fetch_users_batch(payload.user_ids)
    return result
