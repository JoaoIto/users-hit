from contextlib import asynccontextmanager
from typing import AsyncGenerator
import httpx
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger("main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Ciclo de vida do FastAPI: gerencia pool de conexões HTTP reutilizável com limites estritos anti-leak."""
    logger.info("application_startup", project=settings.PROJECT_NAME, version=settings.VERSION)

    # Gestão avançada de conexões HTTPX:
    # - Limites estritos de Keep-Alive e conexões máximas para evitar RemoteProtocolError por desconexão unilateral
    # - Timeouts granulares em cada fase do ciclo HTTP (connect, read, write, pool)
    limits = httpx.Limits(
        max_keepalive_connections=10,
        max_connections=20,
        keepalive_expiry=5.0,
    )
    timeout = httpx.Timeout(
        connect=3.0,
        read=7.0,
        write=5.0,
        pool=5.0,
    )

    client = httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
        follow_redirects=True,
    )
    app.state.http_client = client

    # Inicialização assíncrona do banco de dados (SQLite/PostgreSQL)
    await init_db()

    yield

    logger.info("application_shutdown_closing_http_pool")
    await client.aclose()
    logger.info("application_shutdown_completed")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API assíncrona de alta performance para consulta concorrente de usuários com tolerância a falhas.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Configuração de CORS para permitir acesso seguro do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Roteamento duplo:
# 1. /api/users/fetch (conforme especificação original do desafio)
# 2. /api/v1/users/fetch (versionamento de API recomendado em produção)
app.include_router(api_v1_router, prefix="/api")
app.include_router(api_v1_router, prefix="/api/v1")


@app.get(
    "/health",
    tags=["System"],
    summary="Health check do sistema",
    status_code=status.HTTP_200_OK,
)
@app.get(
    "/api/health",
    tags=["System"],
    summary="Health check da API",
    status_code=status.HTTP_200_OK,
)
async def health_check() -> JSONResponse:
    return JSONResponse(
        content={
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "concurrency_limit": settings.MAX_CONCURRENCY,
        }
    )
