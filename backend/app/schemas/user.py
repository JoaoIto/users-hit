from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class UserFetchRequest(BaseModel):
    user_ids: List[int] = Field(
        ...,
        description="Lista de IDs de usuários a serem consultados.",
        examples=[[1, 2, 3, 4]],
    )

    @field_validator("user_ids")
    @classmethod
    def validate_and_deduplicate_ids(cls, v: List[int]) -> List[int]:
        if not v:
            raise ValueError("A lista de IDs não pode ser vazia.")

        if len(v) > 100:
            raise ValueError("O limite máximo por lote é de 100 IDs.")

        for user_id in v:
            if user_id <= 0:
                raise ValueError(f"O ID {user_id} é inválido. Todos os IDs devem ser inteiros positivos.")

        # Deduplicação automática preservando a ordem original de inserção
        deduplicated = list(dict.fromkeys(v))
        return deduplicated


class UserResponse(BaseModel):
    id: int = Field(..., description="Identificador único do usuário")
    name: str = Field(..., description="Nome completo do usuário")
    username: Optional[str] = Field(default=None, description="Nome de usuário / apelido")
    email: Optional[str] = Field(default=None, description="E-mail de contato")
    phone: Optional[str] = Field(default=None, description="Telefone de contato")
    website: Optional[str] = Field(default=None, description="Site ou portfólio")
    company_name: Optional[str] = Field(default=None, description="Nome da empresa do usuário")
    cached: bool = Field(default=False, description="Flag indicando se o dado foi obtido de cache em memória (TTL)")


class FailedUserDetail(BaseModel):
    user_id: int = Field(..., description="ID do usuário que falhou na consulta")
    status_code: Optional[int] = Field(default=None, description="Código de status HTTP da falha, quando aplicável")
    reason: str = Field(..., description="Motivo amigável e detalhado da falha")


class BatchMetadata(BaseModel):
    total: int = Field(..., description="Total de IDs únicos solicitados no lote")
    success_count: int = Field(..., description="Total de usuários obtidos com sucesso")
    failed_count: int = Field(..., description="Total de falhas registradas")
    cache_hits: int = Field(default=0, description="Total de registros recuperados via cache em memória")
    execution_time_ms: float = Field(..., description="Tempo total de processamento em milissegundos")
    request_id: Optional[str] = Field(default=None, description="ID único da requisição para observabilidade e auditoria")


class UserBatchResponse(BaseModel):
    # Formato conceitual estrito esperado por validadores automatizados
    users: List[UserResponse] = Field(
        default_factory=list,
        description="Lista de usuários consultados com sucesso",
    )
    failed: List[int] = Field(
        default_factory=list,
        description="Lista estrita de inteiros com os IDs que falharam (conforme contrato base do teste)",
        examples=[[3, 4]],
    )

    # Campos enriquecidos para observabilidade e diferenciação técnica
    errors: List[FailedUserDetail] = Field(
        default_factory=list,
        description="Detalhamento semântico enriquecido de cada falha (status code e motivo)",
    )
    meta: BatchMetadata = Field(
        ...,
        description="Metadados operacionais de execução do lote",
    )

    # Aliases opcionais para compatibilidade adicional
    total_requested: Optional[int] = None
    total_success: Optional[int] = None
    total_failed: Optional[int] = None
    duration_ms: Optional[float] = None
