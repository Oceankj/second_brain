import pytest

from personal_agent_memory.config import Settings
from personal_agent_memory.providers.embeddings import (
    CloudflareEmbeddingProvider,
    OllamaEmbeddingProvider,
)
from personal_agent_memory.providers.summaries import CloudflareSummaryProvider
from personal_agent_memory.server.dependencies import (
    build_embedding_provider,
    build_summary_provider,
)


def test_build_embedding_provider_defaults_to_ollama() -> None:
    provider = build_embedding_provider(
        Settings(
            database_url="postgresql://example",
            embedding_dimension=2,
            ollama_embedding_model="local-model",
            ollama_base_url="http://ollama.example.test",
            ollama_timeout_seconds=3,
        )
    )

    assert isinstance(provider, OllamaEmbeddingProvider)
    assert provider.model == "local-model"
    assert provider.dimension == 2
    assert provider.base_url == "http://ollama.example.test"
    assert provider.timeout_seconds == 3


def test_build_embedding_provider_selects_cloudflare() -> None:
    provider = build_embedding_provider(
        Settings(
            database_url="postgresql://example",
            embedding_provider="cloudflare",
            embedding_dimension=1024,
            cloudflare_account_id="account-123",
            cloudflare_api_token="secret-token",
            cloudflare_embedding_model="@cf/baai/bge-large-en-v1.5",
            cloudflare_base_url="https://cloudflare.example.test/client/v4",
            cloudflare_timeout_seconds=4,
            cloudflare_pooling="cls",
        )
    )

    assert isinstance(provider, CloudflareEmbeddingProvider)
    assert provider.account_id == "account-123"
    assert provider.api_token == "secret-token"
    assert provider.model == "@cf/baai/bge-large-en-v1.5"
    assert provider.dimension == 1024
    assert provider.base_url == "https://cloudflare.example.test/client/v4"
    assert provider.timeout_seconds == 4
    assert provider.pooling == "cls"


def test_build_embedding_provider_requires_cloudflare_account_id() -> None:
    with pytest.raises(RuntimeError, match="CLOUDFLARE_ACCOUNT_ID"):
        build_embedding_provider(
            Settings(
                database_url="postgresql://example",
                embedding_provider="cloudflare",
                cloudflare_api_token="secret-token",
            )
        )


def test_build_embedding_provider_requires_cloudflare_api_token() -> None:
    with pytest.raises(RuntimeError, match="CLOUDFLARE_API_TOKEN"):
        build_embedding_provider(
            Settings(
                database_url="postgresql://example",
                embedding_provider="cloudflare",
                cloudflare_account_id="account-123",
            )
        )


def test_build_summary_provider_selects_cloudflare() -> None:
    provider = build_summary_provider(
        Settings(
            database_url="postgresql://example",
            cloudflare_summary_account_id="account-123",
            cloudflare_summary_api_token="secret-token",
            cloudflare_summary_model="@cf/meta/llama-3.1-8b-instruct-fp8",
            cloudflare_summary_base_url="https://cloudflare.example.test/client/v4",
            cloudflare_summary_timeout_seconds=4,
            cloudflare_summary_max_tokens=900,
            cloudflare_summary_temperature=0.1,
        )
    )

    assert isinstance(provider, CloudflareSummaryProvider)
    assert provider.account_id == "account-123"
    assert provider.api_token == "secret-token"
    assert provider.model == "@cf/meta/llama-3.1-8b-instruct-fp8"
    assert provider.base_url == "https://cloudflare.example.test/client/v4"
    assert provider.timeout_seconds == 4
    assert provider.max_tokens == 900
    assert provider.temperature == 0.1


def test_build_summary_provider_requires_cloudflare_account_id() -> None:
    with pytest.raises(RuntimeError, match="CLOUDFLARE_ACCOUNT_ID"):
        build_summary_provider(
            Settings(
                database_url="postgresql://example",
                cloudflare_summary_api_token="secret-token",
            )
        )


def test_build_summary_provider_requires_cloudflare_api_token() -> None:
    with pytest.raises(RuntimeError, match="CLOUDFLARE_API_TOKEN"):
        build_summary_provider(
            Settings(
                database_url="postgresql://example",
                cloudflare_summary_account_id="account-123",
            )
        )
