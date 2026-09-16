import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from app.core.cache import BaseCache
from app.core.database import record_batch_query
from app.core.exceptions import (
    ProviderError,
    ProviderTimeoutError,
    UserNotFoundError,
)
from app.core.logging import get_logger
from app.providers.base import BaseUserProvider
from app.schemas.user import (
    BatchMetadata,
    FailedUserDetail,
    UserBatchResponse,
    UserResponse,
)

logger = get_logger("user_fetch_service")


class UserFetchService:
    """Camada de serviço responsável por orquestrar a consulta concorrente de usuários.
    
    Implementa:
    - Controle de concorrência com asyncio.Semaphore.
    - Isolamento absoluto de falhas via asyncio.gather(return_exceptions=True).
    - Cache em memória transparente com TTL de 60 segundos.
    - Auditoria assíncrona não-bloqueante no banco de dados.
    """

    def __init__(
        self,
        provider: BaseUserProvider,
        max_concurrency: int = 10,
        cache: Optional[BaseCache] = None,
        cache_ttl: int = 60,
    ):
        self.provider = provider
        self.max_concurrency = max(1, max_concurrency)
        self.cache = cache
        self.cache_ttl = cache_ttl
        self._semaphore = asyncio.Semaphore(self.max_concurrency)

    async def _fetch_single_user(self, user_id: int) -> Union[UserResponse, FailedUserDetail]:
        """Consulta um único usuário verificando cache prévio ou chamando o provedor com semáforo."""
        cache_key = f"user:{user_id}"

        # 1. Verificação de Cache (CACHE HIT)
        if self.cache:
            cached_data = await self.cache.get(cache_key)
            if cached_data is not None:
                logger.debug("user_fetch_cache_hit", user_id=user_id)
                return self._map_raw_to_response(cached_data, user_id, is_cached=True)

        # 2. CACHE MISS: Consulta assíncrona ao provedor estrangulada pelo semáforo
        async with self._semaphore:
            try:
                raw_data = await self.provider.fetch_user_by_id(user_id)
                response_obj = self._map_raw_to_response(raw_data, user_id, is_cached=False)

                # Grava no cache para consultas subsequentes rápidas
                if self.cache:
                    await self.cache.set(cache_key, raw_data, ttl_seconds=self.cache_ttl)

                return response_obj

            except UserNotFoundError as exc:
                logger.info("service_user_not_found", user_id=user_id)
                return FailedUserDetail(
                    user_id=user_id,
                    reason=exc.message,
                    status_code=404,
                )
            except ProviderTimeoutError as exc:
                logger.warning("service_provider_timeout", user_id=user_id, error=exc.message)
                return FailedUserDetail(
                    user_id=user_id,
                    reason=exc.message,
                    status_code=exc.status_code,
                )
            except ProviderError as exc:
                logger.warning("service_provider_error", user_id=user_id, error=exc.message, code=exc.status_code)
                return FailedUserDetail(
                    user_id=user_id,
                    reason=exc.message,
                    status_code=exc.status_code,
                )
            except Exception as exc:
                logger.error("service_unexpected_error", user_id=user_id, error=str(exc))
                return FailedUserDetail(
                    user_id=user_id,
                    reason=f"Erro inesperado ao consultar usuário: {str(exc)}",
                    status_code=500,
                )

    def _map_raw_to_response(
        self, raw: Dict[str, Any], fallback_id: int, is_cached: bool = False
    ) -> UserResponse:
        """Mapeia o payload bruto retornado pelo provedor em um UserResponse tipado."""
        user_id = raw.get("id", fallback_id)
        name = raw.get("name", f"Usuário {user_id}")
        username = raw.get("username")
        email = raw.get("email")
        phone = raw.get("phone")
        website = raw.get("website")

        company = raw.get("company")
        company_name = company.get("name") if isinstance(company, dict) else raw.get("company_name")

        return UserResponse(
            id=user_id,
            name=name,
            username=username,
            email=email,
            phone=phone,
            website=website,
            company_name=company_name,
            cached=is_cached,
        )

    async def fetch_users_batch(
        self, user_ids: List[int], request_id: Optional[str] = None
    ) -> UserBatchResponse:
        """Processa um lote de IDs de forma concorrente, com cache e auditoria assíncrona."""
        req_id = request_id or str(uuid.uuid4())
        start_time = time.perf_counter()
        total_requested = len(user_ids)

        logger.info(
            "service_batch_fetch_started",
            request_id=req_id,
            batch_size=total_requested,
            max_concurrency=self.max_concurrency,
        )

        tasks = [self._fetch_single_user(uid) for uid in user_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        users: List[UserResponse] = []
        failed_ids: List[int] = []
        errors: List[FailedUserDetail] = []
        cache_hits = 0

        for idx, res in enumerate(results):
            original_id = user_ids[idx]
            if isinstance(res, UserResponse):
                users.append(res)
                if res.cached:
                    cache_hits += 1
            elif isinstance(res, FailedUserDetail):
                failed_ids.append(res.user_id)
                errors.append(res)
            elif isinstance(res, Exception):
                logger.critical("service_unhandled_gather_exception", user_id=original_id, error=str(res))
                failed_ids.append(original_id)
                errors.append(
                    FailedUserDetail(
                        user_id=original_id,
                        reason=f"Exceção não tratada na thread de execução: {str(res)}",
                        status_code=500,
                    )
                )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Log estruturado operacional rastreável
        logger.info(
            "service_batch_fetch_completed",
            request_id=req_id,
            batch_size=total_requested,
            success_count=len(users),
            failed_count=len(failed_ids),
            cache_hit_count=cache_hits,
            duration_ms=duration_ms,
        )

        # Auditoria assíncrona não-bloqueante no banco de dados
        asyncio.create_task(
            record_batch_query(
                query_id=req_id,
                requested_ids=user_ids,
                success_count=len(users),
                failed_count=len(failed_ids),
                cache_hits=cache_hits,
                execution_time_ms=duration_ms,
            )
        )

        meta = BatchMetadata(
            total=total_requested,
            success_count=len(users),
            failed_count=len(failed_ids),
            cache_hits=cache_hits,
            execution_time_ms=duration_ms,
            request_id=req_id,
        )

        return UserBatchResponse(
            users=users,
            failed=failed_ids,
            errors=errors,
            meta=meta,
            total_requested=total_requested,
            total_success=len(users),
            total_failed=len(failed_ids),
            duration_ms=duration_ms,
        )
