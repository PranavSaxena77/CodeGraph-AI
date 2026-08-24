from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or the local root .env file."""

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CodeGraph AI"
    app_version: str = "0.1.0"
    cors_origins: str = "http://localhost:5173"
    mongodb_host: str = "127.0.0.1"
    mongodb_port: int = Field(default=27017, ge=1, le=65535)
    neo4j_host: str = "127.0.0.1"
    neo4j_bolt_port: int = Field(default=7687, ge=1, le=65535)
    dependency_timeout_seconds: float = Field(default=1.0, gt=0, le=10)

    @property
    def cors_origin_list(self) -> list[str]:
        """Return normalized CORS origins from a comma-separated setting."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings object."""
    return Settings()
