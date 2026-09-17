import datetime
import uuid
from typing import Any, List, Optional
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("database")


class Base(DeclarativeBase):
    pass


class BatchQuery(Base):
    """Tabela de auditoria e persistência para histórico de consultas em lote."""

    __tablename__ = "batch_queries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    requested_ids = Column(JSON, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    cache_hits = Column(Integer, default=0, nullable=False)
    execution_time_ms = Column(Float, nullable=False)


def get_db_url() -> str:
    settings = get_settings()
    if settings.DATABASE_URL:
        url = settings.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    import os
    is_serverless = (
        bool(os.getenv("VERCEL"))
        or bool(os.getenv("VERCEL_ENV"))
        or bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
        or bool(os.getenv("LAMBDA_TASK_ROOT"))
        or not os.access(".", os.W_OK)
    )
    if is_serverless:
        return "sqlite+aiosqlite:////tmp/batch_history.db"
    return "sqlite+aiosqlite:///./batch_history.db" 


db_url = get_db_url()
is_sqlite = db_url.startswith("sqlite")

engine = create_async_engine(
    db_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False, "timeout": 30.0} if is_sqlite else {},
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Inicializa as tabelas do banco de dados assincronamente no startup."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_initialized_successfully", url=get_db_url().split("@")[-1])
    except Exception as exc:
        logger.error("database_initialization_failed", error=str(exc))


async def record_batch_query(
    query_id: str,
    requested_ids: List[int],
    success_count: int,
    failed_count: int,
    cache_hits: int,
    execution_time_ms: float,
) -> None:
    """Grava o registro de auditoria assincronamente sem bloquear o fluxo HTTP."""
    try:
        async with async_session_factory() as session:
            async with session.begin():
                record = BatchQuery(
                    id=query_id,
                    requested_ids=requested_ids,
                    success_count=success_count,
                    failed_count=failed_count,
                    cache_hits=cache_hits,
                    execution_time_ms=execution_time_ms,
                )
                session.add(record)
        logger.debug("batch_query_audited_to_db", query_id=query_id)
    except Exception as exc:
        # Erro de gravação em auditoria não deve impactar o cliente final
        logger.warning("failed_to_record_batch_query", query_id=query_id, error=str(exc))
