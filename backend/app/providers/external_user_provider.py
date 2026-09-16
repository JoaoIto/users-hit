import re
from typing import Any, Dict, Optional
import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)
from tenacity.wait import wait_base

from app.core.exceptions import (
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    UserNotFoundError,
)
from app.core.logging import get_logger
from app.providers.base import BaseUserProvider

logger = get_logger("external_user_provider")


class wait_retry_after_or_exponential(wait_base):
    """Estratégia de espera customizada do Tenacity que respeita o cabeçalho Retry-After (HTTP 429).
    
    Se o servidor remoto retornar HTTP 429 com o cabeçalho Retry-After, a espera respeita
    o tempo estipulado pelo servidor remoto antes de voltar ao backoff exponencial aleatório padrão.
    """

    def __init__(self, fallback_wait: wait_base, max_wait: float = 10.0):
        self.fallback_wait = fallback_wait
        self.max_wait = max_wait

    def __call__(self, retry_state: RetryCallState) -> float:
        if retry_state.outcome and retry_state.outcome.failed:
            exc = retry_state.outcome.exception()
            if isinstance(exc, ProviderRateLimitError) and exc.retry_after is not None:
                # Respeita o cabeçalho Retry-After, com teto de segurança
                wait_time = min(float(exc.retry_after), self.max_wait)
                logger.info(
                    "tenacity_respecting_retry_after_header",
                    user_id=exc.user_id,
                    wait_seconds=wait_time,
                )
                return wait_time
        return self.fallback_wait(retry_state)


class ExternalUserProvider(BaseUserProvider):
    """Implementação concreta de BaseUserProvider integrada com API HTTP externa.
    
    Aplica resiliência com Tenacity (retries com wait adaptativo respeitando Retry-After e jitter),
    utiliza pool de conexões via httpx.AsyncClient e traduz respostas e códigos HTTP
    em exceções semânticas de domínio.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = "https://jsonplaceholder.typicode.com",
        timeout: float = 10.0,
        max_attempts: int = 3,
    ):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_attempts = max_attempts

    async def fetch_user_by_id(self, user_id: int) -> Dict[str, Any]:
        """Consulta o usuário no provedor com retries automáticos para falhas transitórias."""
        try:
            return await self._fetch_with_retry(user_id)
        except httpx.TimeoutException:
            logger.warning("provider_request_timeout_exhausted", user_id=user_id, timeout=self.timeout)
            raise ProviderTimeoutError(user_id=user_id, timeout_seconds=self.timeout)
        except httpx.RequestError as exc:
            logger.warning("provider_request_network_error", user_id=user_id, error=str(exc))
            raise ProviderError(
                user_id=user_id,
                message=f"Network communication failure with external provider: {str(exc)}",
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_retry_after_or_exponential(
            fallback_wait=wait_random_exponential(min=0.5, max=2.0),
            max_wait=10.0,
        ),
        retry=retry_if_exception_type((httpx.RequestError, ProviderRateLimitError, ProviderServerError)),
        reraise=True,
    )
    async def _fetch_with_retry(self, user_id: int) -> Dict[str, Any]:
        url = f"{self.base_url}/users/{user_id}"
        logger.debug("fetching_user_from_provider", user_id=user_id, url=url)

        response = await self.client.get(url, timeout=self.timeout)

        # 404: Usuário não existe - Falha de domínio (não deve retentar)
        if response.status_code == 404:
            logger.info("provider_user_not_found", user_id=user_id)
            raise UserNotFoundError(user_id=user_id)

        # 429: Limitação de taxa no provedor externo (extrai Retry-After se disponível)
        if response.status_code == 429:
            retry_after_val = self._parse_retry_after(response.headers.get("Retry-After"))
            logger.warning(
                "provider_rate_limited",
                user_id=user_id,
                retry_after=retry_after_val,
            )
            raise ProviderRateLimitError(user_id=user_id, retry_after=retry_after_val)

        # 5xx: Erro interno no provedor externo (retenta com backoff)
        if response.status_code >= 500:
            logger.warning("provider_server_error", user_id=user_id, status_code=response.status_code)
            raise ProviderServerError(user_id=user_id, status_code=response.status_code)

        # 4xx genérico: Erro de requisição do cliente
        if response.status_code >= 400:
            logger.error("provider_client_error", user_id=user_id, status_code=response.status_code)
            raise ProviderError(
                user_id=user_id,
                message=f"External provider returned HTTP {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        logger.debug("provider_user_fetched_success", user_id=user_id)
        return data

    @staticmethod
    def _parse_retry_after(header_val: Optional[str]) -> Optional[float]:
        """Converte cabeçalho Retry-After (em segundos) para float seguro."""
        if not header_val:
            return None
        try:
            val = float(header_val.strip())
            return max(0.0, val)
        except (ValueError, TypeError):
            # Formatos de data HTTP (IMF-fixdate) raros em APIs modernas de rate limit
            return None
