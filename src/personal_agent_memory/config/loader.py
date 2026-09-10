from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from personal_agent_memory.config.defaults import (
    CLOUDFLARE_ACCOUNT_ID_ENV,
    CLOUDFLARE_API_TOKEN_ENV,
    DATABASE_URL_ENV,
    DEFAULT_CHUNK_OVERLAP_CHARS,
    DEFAULT_CLOUDFLARE_BASE_URL,
    DEFAULT_CLOUDFLARE_EMBEDDING_MODEL,
    DEFAULT_CLOUDFLARE_SUMMARY_MAX_TOKENS,
    DEFAULT_CLOUDFLARE_SUMMARY_MODEL,
    DEFAULT_CLOUDFLARE_SUMMARY_TEMPERATURE,
    DEFAULT_CLOUDFLARE_SUMMARY_TIMEOUT_SECONDS,
    DEFAULT_CLOUDFLARE_TIMEOUT_SECONDS,
    DEFAULT_DAILY_DIARY_TIMEZONE,
    DEFAULT_DATABASE_POOL_MAX_SIZE,
    DEFAULT_DATABASE_POOL_MIN_SIZE,
    DEFAULT_DATABASE_POOL_TIMEOUT_SECONDS,
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_LINK_EXPANSION_MAX_ITEMS,
    DEFAULT_LINK_EXPANSION_SOURCE_LIMIT,
    DEFAULT_LINK_EXPANSION_SOURCE_WEIGHT,
    DEFAULT_MAX_CHUNK_CHARS,
    DEFAULT_MCP_HTTP_ALLOWED_HOSTS,
    DEFAULT_MCP_HTTP_ALLOWED_ORIGINS,
    DEFAULT_MCP_HTTP_ENABLED,
    DEFAULT_MCP_HTTP_HOST,
    DEFAULT_MCP_HTTP_MAX_REQUEST_BODY_SIZE,
    DEFAULT_MCP_HTTP_PATH,
    DEFAULT_MCP_HTTP_PORT,
    DEFAULT_MCP_HTTP_PUBLIC_URL,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    DEFAULT_RECENT_DIARY_LOOKBACK_DAYS,
    DEFAULT_RECENT_DIARY_MAX_CHARS,
    DEFAULT_RECENT_DIARY_MAX_ITEMS,
    DEFAULT_RECENT_DIARY_MIN_SCORE,
    DEFAULT_SUMMARY_PROVIDER,
    DEFAULT_SUMMARY_SOURCE_MAX_CHARS,
    DEFAULT_TAG_RETRIEVAL_MAX_TAGS,
    DEFAULT_TAG_RETRIEVAL_MIN_SCORE,
    DEFAULT_TAG_RETRIEVAL_TAG_WEIGHT,
    DEFAULT_USER_TOKEN_ENV,
    LEGACY_EMBEDDING_DIMENSION_ENV,
    LEGACY_EMBEDDING_PROVIDER_ENV,
    LEGACY_OLLAMA_BASE_URL_ENV,
    LEGACY_OLLAMA_EMBEDDING_MODEL_ENV,
    LEGACY_OLLAMA_TIMEOUT_SECONDS_ENV,
    MEMORY_CONFIG_PATH_ENV,
    REST_API_ENABLED_ENV,
)
from personal_agent_memory.config.models import Settings
from personal_agent_memory.config.parsing import (
    config_bool_from_section,
    config_float,
    config_float_from_section,
    config_int,
    config_int_from_section,
    config_optional_str,
    config_section,
    config_str,
    config_str_tuple,
    parse_bool,
)


def load_settings() -> Settings:
    load_dotenv()
    memory_config = load_memory_config()

    database_url = os.environ.get(DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run the memory MCP server")

    return Settings(
        database_url=database_url,
        rest_api_enabled=config_bool_from_env(REST_API_ENABLED_ENV, default=False),
        default_user_token=os.environ.get(DEFAULT_USER_TOKEN_ENV),
        **load_database_settings(memory_config),
        **load_embedding_settings(memory_config),
        **load_summary_settings(memory_config),
        **load_daily_diary_settings(memory_config),
        **load_chunking_settings(memory_config),
        **load_retrieval_settings(memory_config),
        **load_mcp_http_settings(memory_config),
    )


def load_database_settings(memory_config: Mapping[str, Any]) -> dict[str, Any]:
    database_config = config_section(memory_config, "database")
    return {
        "database_pool_min_size": config_int_from_section(
            database_config,
            key="pool_min_size",
            default=DEFAULT_DATABASE_POOL_MIN_SIZE,
        ),
        "database_pool_max_size": config_int_from_section(
            database_config,
            key="pool_max_size",
            default=DEFAULT_DATABASE_POOL_MAX_SIZE,
        ),
        "database_pool_timeout_seconds": config_float_from_section(
            database_config,
            key="pool_timeout_seconds",
            default=DEFAULT_DATABASE_POOL_TIMEOUT_SECONDS,
        ),
    }


def load_embedding_settings(memory_config: Mapping[str, Any]) -> dict[str, Any]:
    embedding_config = config_section(memory_config, "embedding")
    ollama_config = config_section(embedding_config, "ollama")
    cloudflare_config = config_section(embedding_config, "cloudflare")

    return {
        "embedding_provider": config_str(
            embedding_config,
            key="provider",
            default=os.environ.get(LEGACY_EMBEDDING_PROVIDER_ENV, DEFAULT_EMBEDDING_PROVIDER),
        ),
        "embedding_dimension": config_int_from_section(
            embedding_config,
            key="dimension",
            default=int(
                os.environ.get(
                    LEGACY_EMBEDDING_DIMENSION_ENV,
                    DEFAULT_EMBEDDING_DIMENSION,
                )
            ),
        ),
        "ollama_embedding_model": config_str(
            ollama_config,
            key="model",
            default=os.environ.get(
                LEGACY_OLLAMA_EMBEDDING_MODEL_ENV,
                DEFAULT_OLLAMA_EMBEDDING_MODEL,
            ),
        ),
        "ollama_base_url": config_str(
            ollama_config,
            key="base_url",
            default=os.environ.get(LEGACY_OLLAMA_BASE_URL_ENV, DEFAULT_OLLAMA_BASE_URL),
        ),
        "ollama_timeout_seconds": config_float_from_section(
            ollama_config,
            key="timeout_seconds",
            default=float(
                os.environ.get(
                    LEGACY_OLLAMA_TIMEOUT_SECONDS_ENV,
                    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
                )
            ),
        ),
        "cloudflare_account_id": os.environ.get(
            config_str(
                cloudflare_config,
                key="account_id_env",
                default=CLOUDFLARE_ACCOUNT_ID_ENV,
            )
        ),
        "cloudflare_api_token": os.environ.get(
            config_str(
                cloudflare_config,
                key="api_token_env",
                default=CLOUDFLARE_API_TOKEN_ENV,
            )
        ),
        "cloudflare_embedding_model": config_str(
            cloudflare_config,
            key="model",
            default=DEFAULT_CLOUDFLARE_EMBEDDING_MODEL,
        ),
        "cloudflare_base_url": config_str(
            cloudflare_config,
            key="base_url",
            default=DEFAULT_CLOUDFLARE_BASE_URL,
        ),
        "cloudflare_timeout_seconds": config_float_from_section(
            cloudflare_config,
            key="timeout_seconds",
            default=DEFAULT_CLOUDFLARE_TIMEOUT_SECONDS,
        ),
        "cloudflare_pooling": config_optional_str(
            cloudflare_config,
            key="pooling",
        ),
    }


def load_summary_settings(memory_config: Mapping[str, Any]) -> dict[str, Any]:
    summary_config = config_section(memory_config, "summary")
    cloudflare_summary_config = config_section(summary_config, "cloudflare")

    return {
        "summary_provider": config_str(
            summary_config,
            key="provider",
            default=DEFAULT_SUMMARY_PROVIDER,
        ),
        "cloudflare_summary_account_id": os.environ.get(
            config_str(
                cloudflare_summary_config,
                key="account_id_env",
                default=CLOUDFLARE_ACCOUNT_ID_ENV,
            )
        ),
        "cloudflare_summary_api_token": os.environ.get(
            config_str(
                cloudflare_summary_config,
                key="api_token_env",
                default=CLOUDFLARE_API_TOKEN_ENV,
            )
        ),
        "cloudflare_summary_model": config_str(
            cloudflare_summary_config,
            key="model",
            default=DEFAULT_CLOUDFLARE_SUMMARY_MODEL,
        ),
        "cloudflare_summary_base_url": config_str(
            cloudflare_summary_config,
            key="base_url",
            default=DEFAULT_CLOUDFLARE_BASE_URL,
        ),
        "cloudflare_summary_timeout_seconds": config_float_from_section(
            cloudflare_summary_config,
            key="timeout_seconds",
            default=DEFAULT_CLOUDFLARE_SUMMARY_TIMEOUT_SECONDS,
        ),
        "cloudflare_summary_max_tokens": config_int_from_section(
            cloudflare_summary_config,
            key="max_tokens",
            default=DEFAULT_CLOUDFLARE_SUMMARY_MAX_TOKENS,
        ),
        "cloudflare_summary_temperature": config_float_from_section(
            cloudflare_summary_config,
            key="temperature",
            default=DEFAULT_CLOUDFLARE_SUMMARY_TEMPERATURE,
        ),
        "summary_source_max_chars": config_int_from_section(
            summary_config,
            key="source_max_chars",
            default=DEFAULT_SUMMARY_SOURCE_MAX_CHARS,
        ),
    }


def load_daily_diary_settings(memory_config: Mapping[str, Any]) -> dict[str, Any]:
    daily_diary_config = config_section(memory_config, "daily_diary")
    return {
        "daily_diary_timezone": config_str(
            daily_diary_config,
            key="timezone",
            default=DEFAULT_DAILY_DIARY_TIMEZONE,
        ),
    }


def load_chunking_settings(memory_config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "max_chunk_chars": config_int(
            memory_config,
            section="chunking",
            key="max_chars",
            default=DEFAULT_MAX_CHUNK_CHARS,
        ),
        "chunk_overlap_chars": config_int(
            memory_config,
            section="chunking",
            key="overlap_chars",
            default=DEFAULT_CHUNK_OVERLAP_CHARS,
        ),
    }


def load_retrieval_settings(memory_config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "recent_diary_lookback_days": config_int(
            memory_config,
            section="retrieval",
            key="recent_diary_lookback_days",
            default=DEFAULT_RECENT_DIARY_LOOKBACK_DAYS,
        ),
        "recent_diary_max_items": config_int(
            memory_config,
            section="retrieval",
            key="recent_diary_max_items",
            default=DEFAULT_RECENT_DIARY_MAX_ITEMS,
        ),
        "recent_diary_min_score": config_float(
            memory_config,
            section="retrieval",
            key="recent_diary_min_score",
            default=DEFAULT_RECENT_DIARY_MIN_SCORE,
        ),
        "recent_diary_max_chars": config_int(
            memory_config,
            section="retrieval",
            key="recent_diary_max_chars",
            default=DEFAULT_RECENT_DIARY_MAX_CHARS,
        ),
        "tag_retrieval_min_score": config_float(
            memory_config,
            section="retrieval",
            key="tag_retrieval_min_score",
            default=DEFAULT_TAG_RETRIEVAL_MIN_SCORE,
        ),
        "tag_retrieval_max_tags": config_int(
            memory_config,
            section="retrieval",
            key="tag_retrieval_max_tags",
            default=DEFAULT_TAG_RETRIEVAL_MAX_TAGS,
        ),
        "tag_retrieval_tag_weight": config_float(
            memory_config,
            section="retrieval",
            key="tag_retrieval_tag_weight",
            default=DEFAULT_TAG_RETRIEVAL_TAG_WEIGHT,
        ),
        "link_expansion_max_items": config_int(
            memory_config,
            section="retrieval",
            key="link_expansion_max_items",
            default=DEFAULT_LINK_EXPANSION_MAX_ITEMS,
        ),
        "link_expansion_source_limit": config_int(
            memory_config,
            section="retrieval",
            key="link_expansion_source_limit",
            default=DEFAULT_LINK_EXPANSION_SOURCE_LIMIT,
        ),
        "link_expansion_source_weight": config_float(
            memory_config,
            section="retrieval",
            key="link_expansion_source_weight",
            default=DEFAULT_LINK_EXPANSION_SOURCE_WEIGHT,
        ),
    }


def load_mcp_http_settings(memory_config: Mapping[str, Any]) -> dict[str, Any]:
    mcp_http_config = config_section(memory_config, "mcp_http")
    return {
        "mcp_http_enabled": config_bool_from_section(
            mcp_http_config,
            key="enabled",
            default=DEFAULT_MCP_HTTP_ENABLED,
        ),
        "mcp_http_host": config_str(
            mcp_http_config,
            key="host",
            default=DEFAULT_MCP_HTTP_HOST,
        ),
        "mcp_http_port": config_int_from_section(
            mcp_http_config,
            key="port",
            default=DEFAULT_MCP_HTTP_PORT,
        ),
        "mcp_http_path": config_str(
            mcp_http_config,
            key="path",
            default=DEFAULT_MCP_HTTP_PATH,
        ),
        "mcp_http_public_url": config_str(
            mcp_http_config,
            key="public_url",
            default=DEFAULT_MCP_HTTP_PUBLIC_URL,
        ),
        "mcp_http_allowed_hosts": config_str_tuple(
            mcp_http_config,
            key="allowed_hosts",
            default=DEFAULT_MCP_HTTP_ALLOWED_HOSTS,
        ),
        "mcp_http_allowed_origins": config_str_tuple(
            mcp_http_config,
            key="allowed_origins",
            default=DEFAULT_MCP_HTTP_ALLOWED_ORIGINS,
        ),
        "mcp_http_max_request_body_size": config_int_from_section(
            mcp_http_config,
            key="max_request_body_size",
            default=DEFAULT_MCP_HTTP_MAX_REQUEST_BODY_SIZE,
        ),
    }


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or Path.cwd() / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_memory_config(path: Path | None = None) -> dict[str, Any]:
    config_path = resolve_memory_config_path(path)
    if not config_path.exists():
        return {}

    with config_path.open() as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise ValueError("memory.json root must be an object")
    return config


def resolve_memory_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return path

    env_path = os.environ.get(MEMORY_CONFIG_PATH_ENV)
    if env_path:
        return Path(env_path).expanduser()

    return Path.cwd() / "memory.json"


def config_bool_from_env(key: str, *, default: bool) -> bool:
    raw_value = os.environ.get(key)
    if raw_value is None:
        return default

    return parse_bool(raw_value, name=key)
