from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    # Postgres. The migration role owns every object; app and agent are restricted roles.
    migration_database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ursache"
    app_database_url: str = "postgresql+psycopg://ursache_app:ursache_app@localhost:5432/ursache"
    agent_database_url: str = (
        "postgresql+psycopg://ursache_agent:ursache_agent@localhost:5432/ursache"
    )
    eval_database_url: str = "postgresql+psycopg://ursache_eval:ursache_eval@localhost:5432/ursache"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_cloud_inference: bool = False
    qdrant_doc_chunks_collection: str = "doc_chunks__gemb2_768__v1"
    qdrant_doc_chunks_alias: str = "doc_chunks"
    qdrant_defect_images_collection: str = "defect_images__gemb2_dinov2__v1"
    qdrant_defect_images_alias: str = "defect_images"
    bm25_local_model: str = "Qdrant/bm25"
    bm25_cloud_model: str = "qdrant/bm25"

    # Gemini
    gemini_api_key: SecretStr | None = None
    gemini_reasoning_model: str = "gemini-3.8-flash"
    gemini_light_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-2"
    embedding_dim: int = 768
    dino_dim: int = 768

    # Cohere
    cohere_api_key: SecretStr | None = None
    cohere_rerank_model: str = "rerank-v4.0-fast"

    # Blob storage (Backblaze B2 via the S3 API in prod)
    blob_backend: Literal["s3", "local"] = "local"
    blob_local_root: str = "../data/blobs"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_key_id: SecretStr | None = None
    s3_secret: SecretStr | None = None
    s3_public_base_url: str | None = None

    # Controlled documents written by the simulator and read by ingestion (relative to backend/)
    generated_docs_dir: str = "../data/generated/docs"

    # Langfuse (OTLP over HTTP); tracing is disabled when keys are unset
    langfuse_otlp_endpoint: str = "https://cloud.langfuse.com/api/public/otel/v1/traces"
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    otel_service_name: str = "ursache-api"

    # Quotas. Gemini resets daily quotas at midnight Pacific time.
    quota_timezone: str = "America/Los_Angeles"
    quota_reasoning_daily_requests: int = Field(default=20, ge=0)
    quota_light_daily_requests: int = Field(default=500, ge=0)
    quota_embedding_daily_requests: int = Field(default=1000, ge=0)
    quota_rerank_daily_requests: int = Field(default=30, ge=0)
    live_runs_per_ip_per_day: int = Field(default=3, ge=0)
    rate_limit_default: str = "60/minute"

    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def tracing_enabled(self) -> bool:
        return self.langfuse_public_key is not None and self.langfuse_secret_key is not None

    def daily_caps(self) -> dict[tuple[str, str], int]:
        """Daily request cap keyed by (provider, model)."""
        return {
            ("gemini", self.gemini_reasoning_model): self.quota_reasoning_daily_requests,
            ("gemini", self.gemini_light_model): self.quota_light_daily_requests,
            ("gemini", self.gemini_embedding_model): self.quota_embedding_daily_requests,
            ("cohere", self.cohere_rerank_model): self.quota_rerank_daily_requests,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
