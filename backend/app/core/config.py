from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field, SecretStr
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
    mongodb_database: str = "codegraph_ai"
    mongo_root_username: str | None = None
    mongo_root_password: SecretStr | None = None
    neo4j_host: str = "127.0.0.1"
    neo4j_bolt_port: int = Field(default=7687, ge=1, le=65535)
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr | None = None
    neo4j_database: str = "neo4j"
    dependency_timeout_seconds: float = Field(default=1.0, gt=0, le=10)
    github_api_base_url: str = "https://api.github.com"
    github_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    embedding_provider: str = "deterministic-local"
    embedding_fake_dimension: int = Field(default=128, ge=1)
    gemini_api_key: SecretStr | None = None
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimension: int = Field(default=768, ge=1)
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    embedding_batch_size: int = Field(default=32, ge=1, le=100)
    vector_index_root: Path = Path(".data/vector_indexes")
    max_chunk_chars: int = Field(default=8_000, ge=100)
    max_archive_bytes: int = Field(default=25_000_000, ge=1)
    max_archive_members: int = Field(default=10_000, ge=1)
    max_extracted_bytes: int = Field(default=100_000_000, ge=1)
    max_archive_member_bytes: int = Field(default=25_000_000, ge=1)

    @property
    def cors_origin_list(self) -> list[str]:
        """Return normalized CORS origins from a comma-separated setting."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def mongodb_uri(self) -> str:
        """Build a local MongoDB URI without logging or exposing credentials."""
        if self.mongo_root_username and self.mongo_root_password:
            username = quote_plus(self.mongo_root_username)
            password = quote_plus(self.mongo_root_password.get_secret_value())
            return (
                f"mongodb://{username}:{password}@{self.mongodb_host}:{self.mongodb_port}"
                "/?authSource=admin"
            )
        return f"mongodb://{self.mongodb_host}:{self.mongodb_port}"

    @property
    def neo4j_uri(self) -> str:
        """Build the configured Neo4j Bolt URI without embedding credentials."""
        return f"bolt://{self.neo4j_host}:{self.neo4j_bolt_port}"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings object."""
    return Settings()
