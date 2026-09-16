from typing import Optional


class UserDomainException(Exception):
    """Exceção base para o domínio de usuários."""
    pass


class UserNotFoundError(UserDomainException):
    """Lançada quando o usuário solicitado não existe no provedor (HTTP 404)."""
    def __init__(self, user_id: int, message: Optional[str] = None):
        self.user_id = user_id
        self.status_code = 404
        self.message = message or f"User with ID {user_id} not found."
        super().__init__(self.message)


class ProviderError(UserDomainException):
    """Exceção genérica para falhas na comunicação com o provedor externo."""
    def __init__(self, user_id: int, message: str, status_code: Optional[int] = None):
        self.user_id = user_id
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ProviderTimeoutError(ProviderError):
    """Lançada quando a requisição ao provedor excede o tempo limite configurado."""
    def __init__(self, user_id: int, timeout_seconds: float):
        super().__init__(
            user_id=user_id,
            message=f"Request to provider timed out after {timeout_seconds}s.",
            status_code=504,
        )


class ProviderRateLimitError(ProviderError):
    """Lançada quando o provedor externo retorna limitação de taxa (HTTP 429)."""
    def __init__(self, user_id: int, retry_after: Optional[float] = None):
        self.retry_after = retry_after
        msg = f"Rate limit reached at external provider for user ID {user_id}."
        if retry_after:
            msg += f" Retry-After: {retry_after}s."
        super().__init__(
            user_id=user_id,
            message=msg,
            status_code=429,
        )


class ProviderServerError(ProviderError):
    """Lançada quando o provedor externo retorna erro interno (HTTP 5xx)."""
    def __init__(self, user_id: int, status_code: int = 500, detail: Optional[str] = None):
        msg = f"External provider server error (HTTP {status_code}) for user ID {user_id}."
        if detail:
            msg += f" Detail: {detail}"
        super().__init__(
            user_id=user_id,
            message=msg,
            status_code=status_code,
        )
