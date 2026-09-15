from pathlib import Path

import pytest

from personal_agent_memory.config import Settings, load_memory_config, load_settings


def test_load_memory_config_reads_repo_local_json(tmp_path: Path) -> None:
    config_path = tmp_path / "memory.json"
    config_path.write_text(
        """{
  "chunking": {
    "max_chars": 2400,
    "overlap_chars": 240
  },
  "embedding": {
    "provider": "cloudflare",
    "dimension": 1024,
    "ollama": {
      "model": "qwen3-embedding:0.6b",
      "base_url": "http://ollama.example.test",
      "timeout_seconds": 7
    },
    "cloudflare": {
      "model": "@cf/baai/bge-large-en-v1.5",
      "account_id_env": "TEST_CLOUDFLARE_ACCOUNT_ID",
      "api_token_env": "TEST_CLOUDFLARE_API_TOKEN",
      "timeout_seconds": 9,
      "pooling": "cls"
    }
  },
  "summary": {
    "provider": "cloudflare",
    "source_max_chars": 12000,
    "cloudflare": {
      "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
      "account_id_env": "TEST_CLOUDFLARE_ACCOUNT_ID",
      "api_token_env": "TEST_CLOUDFLARE_API_TOKEN",
      "timeout_seconds": 10,
      "max_tokens": 900,
      "temperature": 0.1
    }
  },
  "daily_diary": {
    "timezone": "America/Los_Angeles"
  },
  "mcp_http": {
    "host": "0.0.0.0",
    "port": 9001,
    "path": "/memory-mcp",
    "public_url": "https://memory.example.test",
    "allowed_hosts": ["memory.example.test"],
    "allowed_origins": ["https://agent.example.test"],
    "max_request_body_size": 12345
  },
  "retrieval": {
    "recent_diary_lookback_days": 4,
    "recent_diary_max_items": 5,
    "recent_diary_min_score": 0.8,
    "recent_diary_max_chars": 3000,
    "tag_retrieval_min_score": 0.81,
    "tag_retrieval_max_tags": 7,
    "tag_retrieval_tag_weight": 0.35,
    "link_expansion_max_items": 4,
    "link_expansion_source_limit": 6,
    "link_expansion_source_weight": 0.45
  }
}
"""
    )

    assert load_memory_config(config_path) == {
        "chunking": {
            "max_chars": 2400,
            "overlap_chars": 240,
        },
        "embedding": {
            "provider": "cloudflare",
            "dimension": 1024,
            "ollama": {
                "model": "qwen3-embedding:0.6b",
                "base_url": "http://ollama.example.test",
                "timeout_seconds": 7,
            },
            "cloudflare": {
                "model": "@cf/baai/bge-large-en-v1.5",
                "account_id_env": "TEST_CLOUDFLARE_ACCOUNT_ID",
                "api_token_env": "TEST_CLOUDFLARE_API_TOKEN",
                "timeout_seconds": 9,
                "pooling": "cls",
            },
        },
        "summary": {
            "provider": "cloudflare",
            "source_max_chars": 12000,
            "cloudflare": {
                "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
                "account_id_env": "TEST_CLOUDFLARE_ACCOUNT_ID",
                "api_token_env": "TEST_CLOUDFLARE_API_TOKEN",
                "timeout_seconds": 10,
                "max_tokens": 900,
                "temperature": 0.1,
            },
        },
        "daily_diary": {
            "timezone": "America/Los_Angeles",
        },
        "mcp_http": {
            "host": "0.0.0.0",
            "port": 9001,
            "path": "/memory-mcp",
            "public_url": "https://memory.example.test",
            "allowed_hosts": ["memory.example.test"],
            "allowed_origins": ["https://agent.example.test"],
            "max_request_body_size": 12345,
        },
        "retrieval": {
            "recent_diary_lookback_days": 4,
            "recent_diary_max_items": 5,
            "recent_diary_min_score": 0.8,
            "recent_diary_max_chars": 3000,
            "tag_retrieval_min_score": 0.81,
            "tag_retrieval_max_tags": 7,
            "tag_retrieval_tag_weight": 0.35,
            "link_expansion_max_items": 4,
            "link_expansion_source_limit": 6,
            "link_expansion_source_weight": 0.45,
        },
    }


def test_load_memory_config_uses_memory_config_path_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "memory.production.json"
    config_path.write_text("""{"chunking": {"max_chars": 3333}}""")
    monkeypatch.setenv("MEMORY_CONFIG_PATH", str(config_path))

    assert load_memory_config() == {"chunking": {"max_chars": 3333}}


def test_load_settings_uses_memory_json_for_chunking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("MEMORY_EMBEDDING_DIMENSION", "777")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "ignored-env-model")
    monkeypatch.setenv("TEST_CLOUDFLARE_ACCOUNT_ID", "test-account")
    monkeypatch.setenv("TEST_CLOUDFLARE_API_TOKEN", "test-token")
    monkeypatch.setenv("MEMORY_MAX_CHUNK_CHARS", "1111")
    monkeypatch.setenv("MEMORY_CHUNK_OVERLAP_CHARS", "111")
    (tmp_path / "memory.json").write_text(
        """{
  "database": {
    "pool_min_size": 2,
    "pool_max_size": 12,
    "pool_timeout_seconds": 15
  },
  "chunking": {
    "max_chars": 2400,
    "overlap_chars": 240
  },
  "embedding": {
    "provider": "cloudflare",
    "dimension": 1024,
    "ollama": {
      "model": "qwen3-embedding:0.6b",
      "base_url": "http://ollama.example.test",
      "timeout_seconds": 7
    },
    "cloudflare": {
      "model": "@cf/baai/bge-large-en-v1.5",
      "account_id_env": "TEST_CLOUDFLARE_ACCOUNT_ID",
      "api_token_env": "TEST_CLOUDFLARE_API_TOKEN",
      "timeout_seconds": 9,
      "pooling": "cls"
    }
  },
  "summary": {
    "provider": "cloudflare",
    "source_max_chars": 12000,
    "cloudflare": {
      "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
      "account_id_env": "TEST_CLOUDFLARE_ACCOUNT_ID",
      "api_token_env": "TEST_CLOUDFLARE_API_TOKEN",
      "timeout_seconds": 10,
      "max_tokens": 900,
      "temperature": 0.1
    }
  },
  "daily_diary": {
    "timezone": "America/Los_Angeles"
  },
  "mcp_http": {
    "host": "0.0.0.0",
    "port": 9001,
    "path": "/memory-mcp",
    "public_url": "https://memory.example.test",
    "allowed_hosts": ["memory.example.test"],
    "allowed_origins": ["https://agent.example.test"],
    "max_request_body_size": 12345
  },
  "retrieval": {
    "recent_diary_lookback_days": 4,
    "recent_diary_max_items": 5,
    "recent_diary_min_score": 0.8,
    "recent_diary_max_chars": 3000,
    "tag_retrieval_min_score": 0.81,
    "tag_retrieval_max_tags": 7,
    "tag_retrieval_tag_weight": 0.35,
    "link_expansion_max_items": 4,
    "link_expansion_source_limit": 6,
    "link_expansion_source_weight": 0.45
  }
}
"""
    )

    settings = load_settings()

    assert settings.database_pool_min_size == 2
    assert settings.database_pool_max_size == 12
    assert settings.database_pool_timeout_seconds == 15
    assert settings.embedding_provider == "cloudflare"
    assert settings.embedding_dimension == 1024
    assert settings.ollama_embedding_model == "qwen3-embedding:0.6b"
    assert settings.ollama_base_url == "http://ollama.example.test"
    assert settings.ollama_timeout_seconds == 7
    assert settings.cloudflare_account_id == "test-account"
    assert settings.cloudflare_api_token == "test-token"
    assert settings.cloudflare_embedding_model == "@cf/baai/bge-large-en-v1.5"
    assert settings.cloudflare_timeout_seconds == 9
    assert settings.cloudflare_pooling == "cls"
    assert settings.summary_provider == "cloudflare"
    assert settings.summary_source_max_chars == 12000
    assert settings.cloudflare_summary_account_id == "test-account"
    assert settings.cloudflare_summary_api_token == "test-token"
    assert settings.cloudflare_summary_model == "@cf/meta/llama-3.1-8b-instruct-fp8"
    assert settings.cloudflare_summary_timeout_seconds == 10
    assert settings.cloudflare_summary_max_tokens == 900
    assert settings.cloudflare_summary_temperature == 0.1
    assert settings.daily_diary_timezone == "America/Los_Angeles"
    assert settings.mcp_http_host == "0.0.0.0"
    assert settings.mcp_http_port == 9001
    assert settings.mcp_http_path == "/memory-mcp"
    assert settings.mcp_http_public_url == "https://memory.example.test"
    assert settings.mcp_http_allowed_hosts == ("memory.example.test",)
    assert settings.mcp_http_allowed_origins == ("https://agent.example.test",)
    assert settings.mcp_http_max_request_body_size == 12345
    assert settings.max_chunk_chars == 2400
    assert settings.chunk_overlap_chars == 240
    assert settings.recent_diary_lookback_days == 4
    assert settings.recent_diary_max_items == 5
    assert settings.recent_diary_min_score == 0.8
    assert settings.recent_diary_max_chars == 3000
    assert settings.tag_retrieval_min_score == 0.81
    assert settings.tag_retrieval_max_tags == 7
    assert settings.tag_retrieval_tag_weight == 0.35
    assert settings.link_expansion_max_items == 4
    assert settings.link_expansion_source_limit == 6
    assert settings.link_expansion_source_weight == 0.45


def test_load_settings_does_not_read_chunking_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("MEMORY_MAX_CHUNK_CHARS", "1111")
    monkeypatch.setenv("MEMORY_CHUNK_OVERLAP_CHARS", "111")

    settings = load_settings()

    assert settings.max_chunk_chars == 1800
    assert settings.chunk_overlap_chars == 200
    assert settings.recent_diary_lookback_days == 2
    assert settings.recent_diary_max_items == 3
    assert settings.recent_diary_min_score == 0.72
    assert settings.recent_diary_max_chars == 2000
    assert settings.tag_retrieval_min_score == 0.72
    assert settings.tag_retrieval_max_tags == 5
    assert settings.tag_retrieval_tag_weight == 0.4
    assert settings.link_expansion_max_items == 3
    assert settings.link_expansion_source_limit == 5
    assert settings.link_expansion_source_weight == 0.4


def test_load_settings_uses_legacy_embedding_env_as_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("MEMORY_EMBEDDING_DIMENSION", "777")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "legacy-model")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://legacy-ollama.example.test")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "8")

    settings = load_settings()

    assert settings.embedding_provider == "ollama"
    assert settings.embedding_dimension == 777
    assert settings.ollama_embedding_model == "legacy-model"
    assert settings.ollama_base_url == "http://legacy-ollama.example.test"
    assert settings.ollama_timeout_seconds == 8


def test_load_settings_reads_rest_api_enabled_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("MEMORY_REST_API_ENABLED", "true")

    settings = load_settings()

    assert settings.rest_api_enabled is True


def test_load_settings_uses_mcp_http_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")

    settings = load_settings()

    assert settings.mcp_http_host == "127.0.0.1"
    assert settings.mcp_http_port == 8001
    assert settings.mcp_http_path == "/mcp"
    assert settings.mcp_http_public_url == "http://127.0.0.1:8001"
    assert settings.mcp_http_allowed_hosts == ("127.0.0.1:*", "localhost:*", "[::1]:*")
    assert settings.mcp_http_allowed_origins == (
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    )


def test_load_settings_uses_platform_port_for_http_bind_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("PORT", "4123")
    (tmp_path / "memory.json").write_text(
        """{
  "mcp_http": {
    "port": 9001
  }
}
"""
    )

    settings = load_settings()

    assert settings.mcp_http_port == 4123


def test_settings_rejects_short_default_user_token() -> None:
    with pytest.raises(ValueError, match="default_user_token"):
        Settings(
            database_url="postgresql://example",
            default_user_token="too-short",
        )


def test_settings_rejects_invalid_chunk_overlap() -> None:
    with pytest.raises(ValueError, match="overlap_chars must be smaller"):
        Settings(
            database_url="postgresql://example",
            max_chunk_chars=100,
            chunk_overlap_chars=100,
        )


def test_settings_rejects_invalid_database_pool_size() -> None:
    with pytest.raises(ValueError, match="database_pool_min_size"):
        Settings(
            database_url="postgresql://example",
            database_pool_min_size=5,
            database_pool_max_size=4,
        )


def test_settings_rejects_invalid_recent_diary_lookback_days() -> None:
    with pytest.raises(ValueError, match="recent_diary_lookback_days"):
        Settings(
            database_url="postgresql://example",
            recent_diary_lookback_days=8,
        )


def test_settings_rejects_invalid_recent_diary_min_score() -> None:
    with pytest.raises(ValueError, match="recent_diary_min_score"):
        Settings(
            database_url="postgresql://example",
            recent_diary_min_score=1.1,
        )


def test_settings_rejects_invalid_tag_retrieval_weight() -> None:
    with pytest.raises(ValueError, match="tag_retrieval_tag_weight"):
        Settings(
            database_url="postgresql://example",
            tag_retrieval_tag_weight=1.1,
        )


def test_settings_rejects_invalid_link_expansion_weight() -> None:
    with pytest.raises(ValueError, match="link_expansion_source_weight"):
        Settings(
            database_url="postgresql://example",
            link_expansion_source_weight=1.1,
        )
