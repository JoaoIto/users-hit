from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Hit Digital - Async User Batch Fetcher"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # External Provider Configuration
    EXTERNAL_USERS_API_URL: str = "https://jsonplaceholder.typicode.com"
    REQUEST_TIMEOUT: float = 10.0
    MAX_CONCURRENCY: int = 10
    MAX_BATCH_SIZE: int = 100

    # Cache Configuration
    CACHE_TTL_SECONDS: int = 60

    # Database Configuration (PostgreSQL / SQLite fallback)
    DATABASE_URL: Optional[str] = None

    # Retry Settings (Tenacity)
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_INITIAL_WAIT: float = 0.5
    RETRY_MAX_WAIT: float = 2.0

    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:80",
        "http://127.0.0.1:80",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
