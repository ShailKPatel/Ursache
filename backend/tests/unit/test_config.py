import pytest
from qdrant_client import models

from ursache.config import Settings
from ursache.embeddings.bm25 import CloudBM25Encoder, LocalBM25Encoder, make_sparse_encoder


def make_settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


def test_reads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql+psycopg://ursache_app:pw@db:5432/x")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    monkeypatch.setenv("QUOTA_REASONING_DAILY_REQUESTS", "7")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://a.example, https://b.example")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_database_url.endswith("@db:5432/x")
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "secret-key"
    assert "secret-key" not in repr(settings)
    assert settings.cors_allowed_origins == ["https://a.example", "https://b.example"]
    assert settings.daily_caps()[("gemini", settings.gemini_reasoning_model)] == 7


def test_defaults_target_local_dev() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.embedding_dim == 768
    assert settings.blob_backend == "local"
    assert settings.qdrant_cloud_inference is False
    assert settings.tracing_enabled is False


def test_dev_uses_local_fastembed_bm25(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDRANT_CLOUD_INFERENCE", "false")
    encoder = make_sparse_encoder(Settings(_env_file=None))  # type: ignore[call-arg]
    assert isinstance(encoder, LocalBM25Encoder)
    assert encoder.model_version == "Qdrant/bm25"


def test_prod_uses_qdrant_cloud_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDRANT_CLOUD_INFERENCE", "true")
    encoder = make_sparse_encoder(Settings(_env_file=None))  # type: ignore[call-arg]
    assert isinstance(encoder, CloudBM25Encoder)

    query = encoder.encode_query("scale pits after descaler maintenance")
    assert isinstance(query, models.Document)
    assert query.model == "qdrant/bm25"


def test_tracing_enabled_only_with_both_langfuse_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    assert Settings(_env_file=None).tracing_enabled is False  # type: ignore[call-arg]
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-x")
    assert Settings(_env_file=None).tracing_enabled is True  # type: ignore[call-arg]
