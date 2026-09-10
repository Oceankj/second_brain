from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EMBEDDING_PROVIDERS = {"ollama", "cloudflare"}
SUMMARY_PROVIDERS = {"cloudflare"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    rest_api_enabled: bool = False
    default_user_token: str | None = None
    embedding_provider: str = "ollama"
    embedding_dimension: int = 1024
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: float = 30.0
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    cloudflare_embedding_model: str = "@cf/baai/bge-large-en-v1.5"
    cloudflare_base_url: str = "https://api.cloudflare.com/client/v4"
    cloudflare_timeout_seconds: float = 30.0
    cloudflare_pooling: str | None = None
    summary_provider: str = "cloudflare"
    cloudflare_summary_account_id: str | None = None
    cloudflare_summary_api_token: str | None = None
    cloudflare_summary_model: str = "@cf/meta/llama-3.1-8b-instruct-fp8"
    cloudflare_summary_base_url: str = "https://api.cloudflare.com/client/v4"
    cloudflare_summary_timeout_seconds: float = 60.0
    cloudflare_summary_max_tokens: int = 1200
    cloudflare_summary_temperature: float = 0.2
    summary_source_max_chars: int = 24000
    daily_diary_timezone: str = "UTC"
    max_chunk_chars: int = 1800
    chunk_overlap_chars: int = 200
    recent_diary_lookback_days: int = 2
    recent_diary_max_items: int = 3
    recent_diary_min_score: float = 0.72
    recent_diary_max_chars: int = 2000
    tag_retrieval_min_score: float = 0.72
    tag_retrieval_max_tags: int = 5
    tag_retrieval_tag_weight: float = 0.4
    link_expansion_max_items: int = 3
    link_expansion_source_limit: int = 5
    link_expansion_source_weight: float = 0.4
    mcp_http_enabled: bool = False
    mcp_http_host: str = "127.0.0.1"
    mcp_http_port: int = 8001
    mcp_http_path: str = "/mcp"
    mcp_http_public_url: str = "http://127.0.0.1:8001"
    mcp_http_allowed_hosts: tuple[str, ...] = ("127.0.0.1:*", "localhost:*", "[::1]:*")
    mcp_http_allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    )
    mcp_http_max_request_body_size: int = 4_194_304

    def __post_init__(self) -> None:
        if self.embedding_provider not in EMBEDDING_PROVIDERS:
            allowed = ", ".join(sorted(EMBEDDING_PROVIDERS))
            raise ValueError(f"embedding_provider must be one of: {allowed}")
        if self.embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")
        if not self.ollama_embedding_model:
            raise ValueError("ollama_embedding_model is required")
        if self.ollama_timeout_seconds <= 0:
            raise ValueError("ollama_timeout_seconds must be positive")
        if not self.cloudflare_embedding_model:
            raise ValueError("cloudflare_embedding_model is required")
        if self.cloudflare_timeout_seconds <= 0:
            raise ValueError("cloudflare_timeout_seconds must be positive")
        if self.cloudflare_pooling is not None and self.cloudflare_pooling not in {"mean", "cls"}:
            raise ValueError("cloudflare_pooling must be mean or cls")
        if self.summary_provider not in SUMMARY_PROVIDERS:
            allowed = ", ".join(sorted(SUMMARY_PROVIDERS))
            raise ValueError(f"summary_provider must be one of: {allowed}")
        if not self.cloudflare_summary_model:
            raise ValueError("cloudflare_summary_model is required")
        if self.cloudflare_summary_timeout_seconds <= 0:
            raise ValueError("cloudflare_summary_timeout_seconds must be positive")
        if self.cloudflare_summary_max_tokens <= 0:
            raise ValueError("cloudflare_summary_max_tokens must be positive")
        if not 0 <= self.cloudflare_summary_temperature <= 5:
            raise ValueError("cloudflare_summary_temperature must be between 0 and 5")
        if self.summary_source_max_chars <= 0:
            raise ValueError("summary_source_max_chars must be positive")
        try:
            ZoneInfo(self.daily_diary_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("daily_diary_timezone must be a valid IANA timezone") from exc
        if self.max_chunk_chars <= 0:
            raise ValueError("max_chunk_chars must be positive")
        if self.default_user_token is not None and len(self.default_user_token) < 32:
            raise ValueError("default_user_token must be at least 32 characters")
        if self.chunk_overlap_chars < 0:
            raise ValueError("chunk_overlap_chars cannot be negative")
        if self.chunk_overlap_chars >= self.max_chunk_chars:
            raise ValueError("chunk_overlap_chars must be smaller than max_chunk_chars")
        if not 0 <= self.recent_diary_lookback_days <= 7:
            raise ValueError("recent_diary_lookback_days must be between 0 and 7")
        if self.recent_diary_max_items < 0:
            raise ValueError("recent_diary_max_items cannot be negative")
        if not 0 <= self.recent_diary_min_score <= 1:
            raise ValueError("recent_diary_min_score must be between 0 and 1")
        if self.recent_diary_max_chars < 0:
            raise ValueError("recent_diary_max_chars cannot be negative")
        if not 0 <= self.tag_retrieval_min_score <= 1:
            raise ValueError("tag_retrieval_min_score must be between 0 and 1")
        if self.tag_retrieval_max_tags < 0:
            raise ValueError("tag_retrieval_max_tags cannot be negative")
        if not 0 <= self.tag_retrieval_tag_weight <= 1:
            raise ValueError("tag_retrieval_tag_weight must be between 0 and 1")
        if self.link_expansion_max_items < 0:
            raise ValueError("link_expansion_max_items cannot be negative")
        if self.link_expansion_source_limit < 0:
            raise ValueError("link_expansion_source_limit cannot be negative")
        if not 0 <= self.link_expansion_source_weight <= 1:
            raise ValueError("link_expansion_source_weight must be between 0 and 1")
        if not self.mcp_http_host:
            raise ValueError("mcp_http_host is required")
        if not 1 <= self.mcp_http_port <= 65535:
            raise ValueError("mcp_http_port must be between 1 and 65535")
        if not self.mcp_http_path.startswith("/"):
            raise ValueError("mcp_http_path must start with /")
        parsed_public_url = urlparse(self.mcp_http_public_url)
        if parsed_public_url.scheme not in {"http", "https"} or not parsed_public_url.netloc:
            raise ValueError("mcp_http_public_url must be an http(s) URL")
        if self.mcp_http_max_request_body_size <= 0:
            raise ValueError("mcp_http_max_request_body_size must be positive")


def load_settings() -> Settings:
    load_dotenv()
    memory_config = load_memory_config()
    embedding_config = config_section(memory_config, "embedding")
    ollama_config = config_section(embedding_config, "ollama")
    cloudflare_config = config_section(embedding_config, "cloudflare")
    summary_config = config_section(memory_config, "summary")
    cloudflare_summary_config = config_section(summary_config, "cloudflare")
    daily_diary_config = config_section(memory_config, "daily_diary")
    mcp_http_config = config_section(memory_config, "mcp_http")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run the memory MCP server")

    return Settings(
        database_url=database_url,
        rest_api_enabled=config_bool_from_env("MEMORY_REST_API_ENABLED", default=False),
        default_user_token=os.environ.get("MEMORY_DEFAULT_USER_TOKEN"),
        embedding_provider=config_str(
            embedding_config,
            key="provider",
            default=os.environ.get("EMBEDDING_PROVIDER", "ollama"),
        ),
        embedding_dimension=config_int_from_section(
            embedding_config,
            key="dimension",
            default=int(os.environ.get("MEMORY_EMBEDDING_DIMENSION", "1024")),
        ),
        ollama_embedding_model=config_str(
            ollama_config,
            key="model",
            default=os.environ.get("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b"),
        ),
        ollama_base_url=config_str(
            ollama_config,
            key="base_url",
            default=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        ),
        ollama_timeout_seconds=config_float_from_section(
            ollama_config,
            key="timeout_seconds",
            default=float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "30")),
        ),
        cloudflare_account_id=os.environ.get(
            config_str(
                cloudflare_config,
                key="account_id_env",
                default="CLOUDFLARE_ACCOUNT_ID",
            )
        ),
        cloudflare_api_token=os.environ.get(
            config_str(
                cloudflare_config,
                key="api_token_env",
                default="CLOUDFLARE_API_TOKEN",
            )
        ),
        cloudflare_embedding_model=config_str(
            cloudflare_config,
            key="model",
            default="@cf/baai/bge-large-en-v1.5",
        ),
        cloudflare_base_url=config_str(
            cloudflare_config,
            key="base_url",
            default="https://api.cloudflare.com/client/v4",
        ),
        cloudflare_timeout_seconds=config_float_from_section(
            cloudflare_config,
            key="timeout_seconds",
            default=30.0,
        ),
        cloudflare_pooling=config_optional_str(
            cloudflare_config,
            key="pooling",
        ),
        summary_provider=config_str(
            summary_config,
            key="provider",
            default="cloudflare",
        ),
        cloudflare_summary_account_id=os.environ.get(
            config_str(
                cloudflare_summary_config,
                key="account_id_env",
                default="CLOUDFLARE_ACCOUNT_ID",
            )
        ),
        cloudflare_summary_api_token=os.environ.get(
            config_str(
                cloudflare_summary_config,
                key="api_token_env",
                default="CLOUDFLARE_API_TOKEN",
            )
        ),
        cloudflare_summary_model=config_str(
            cloudflare_summary_config,
            key="model",
            default="@cf/meta/llama-3.1-8b-instruct-fp8",
        ),
        cloudflare_summary_base_url=config_str(
            cloudflare_summary_config,
            key="base_url",
            default="https://api.cloudflare.com/client/v4",
        ),
        cloudflare_summary_timeout_seconds=config_float_from_section(
            cloudflare_summary_config,
            key="timeout_seconds",
            default=60.0,
        ),
        cloudflare_summary_max_tokens=config_int_from_section(
            cloudflare_summary_config,
            key="max_tokens",
            default=1200,
        ),
        cloudflare_summary_temperature=config_float_from_section(
            cloudflare_summary_config,
            key="temperature",
            default=0.2,
        ),
        summary_source_max_chars=config_int_from_section(
            summary_config,
            key="source_max_chars",
            default=24000,
        ),
        daily_diary_timezone=config_str(
            daily_diary_config,
            key="timezone",
            default="UTC",
        ),
        max_chunk_chars=config_int(
            memory_config,
            section="chunking",
            key="max_chars",
            default=1800,
        ),
        chunk_overlap_chars=config_int(
            memory_config,
            section="chunking",
            key="overlap_chars",
            default=200,
        ),
        recent_diary_lookback_days=config_int(
            memory_config,
            section="retrieval",
            key="recent_diary_lookback_days",
            default=2,
        ),
        recent_diary_max_items=config_int(
            memory_config,
            section="retrieval",
            key="recent_diary_max_items",
            default=3,
        ),
        recent_diary_min_score=config_float(
            memory_config,
            section="retrieval",
            key="recent_diary_min_score",
            default=0.72,
        ),
        recent_diary_max_chars=config_int(
            memory_config,
            section="retrieval",
            key="recent_diary_max_chars",
            default=2000,
        ),
        tag_retrieval_min_score=config_float(
            memory_config,
            section="retrieval",
            key="tag_retrieval_min_score",
            default=0.72,
        ),
        tag_retrieval_max_tags=config_int(
            memory_config,
            section="retrieval",
            key="tag_retrieval_max_tags",
            default=5,
        ),
        tag_retrieval_tag_weight=config_float(
            memory_config,
            section="retrieval",
            key="tag_retrieval_tag_weight",
            default=0.4,
        ),
        link_expansion_max_items=config_int(
            memory_config,
            section="retrieval",
            key="link_expansion_max_items",
            default=3,
        ),
        link_expansion_source_limit=config_int(
            memory_config,
            section="retrieval",
            key="link_expansion_source_limit",
            default=5,
        ),
        link_expansion_source_weight=config_float(
            memory_config,
            section="retrieval",
            key="link_expansion_source_weight",
            default=0.4,
        ),
        mcp_http_enabled=config_bool_from_section(
            mcp_http_config,
            key="enabled",
            default=False,
        ),
        mcp_http_host=config_str(
            mcp_http_config,
            key="host",
            default="127.0.0.1",
        ),
        mcp_http_port=config_int_from_section(
            mcp_http_config,
            key="port",
            default=8001,
        ),
        mcp_http_path=config_str(
            mcp_http_config,
            key="path",
            default="/mcp",
        ),
        mcp_http_public_url=config_str(
            mcp_http_config,
            key="public_url",
            default="http://127.0.0.1:8001",
        ),
        mcp_http_allowed_hosts=config_str_tuple(
            mcp_http_config,
            key="allowed_hosts",
            default=("127.0.0.1:*", "localhost:*", "[::1]:*"),
        ),
        mcp_http_allowed_origins=config_str_tuple(
            mcp_http_config,
            key="allowed_origins",
            default=("http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"),
        ),
        mcp_http_max_request_body_size=config_int_from_section(
            mcp_http_config,
            key="max_request_body_size",
            default=4_194_304,
        ),
    )


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
    config_path = path or Path.cwd() / "memory.json"
    if not config_path.exists():
        return {}

    with config_path.open() as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise ValueError("memory.json root must be an object")
    return config


def config_section(config: Mapping[str, Any], section: str) -> Mapping[str, Any]:
    section_values = config.get(section, {})
    if section_values is None:
        return {}
    if not isinstance(section_values, Mapping):
        raise ValueError(f"memory.json {section} must be an object")
    return section_values


def config_int(
    config: Mapping[str, Any],
    *,
    section: str,
    key: str,
    default: int,
) -> int:
    section_values = config_section(config, section)
    return config_int_from_section(section_values, key=key, default=default)


def config_int_from_section(
    section_values: Mapping[str, Any],
    *,
    key: str,
    default: int,
) -> int:
    value = section_values.get(key)
    if value is None:
        value = default
    return int(value)


def config_float(
    config: Mapping[str, Any],
    *,
    section: str,
    key: str,
    default: float,
) -> float:
    section_values = config_section(config, section)
    return config_float_from_section(section_values, key=key, default=default)


def config_float_from_section(
    section_values: Mapping[str, Any],
    *,
    key: str,
    default: float,
) -> float:
    value = section_values.get(key)
    if value is None:
        value = default
    return float(value)


def config_str(section_values: Mapping[str, Any], *, key: str, default: str) -> str:
    value = section_values.get(key)
    if value is None:
        value = default
    return str(value)


def config_optional_str(section_values: Mapping[str, Any], *, key: str) -> str | None:
    value = section_values.get(key)
    if value is None:
        return None
    return str(value)


def config_str_tuple(
    section_values: Mapping[str, Any],
    *,
    key: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    value = section_values.get(key)
    if value is None:
        return default
    if not isinstance(value, list | tuple):
        raise ValueError(f"memory.json {key} must be a list")
    return tuple(str(item) for item in value)


def config_bool_from_section(
    section_values: Mapping[str, Any],
    *,
    key: str,
    default: bool,
) -> bool:
    raw_value = section_values.get(key)
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    return parse_bool(str(raw_value), name=f"memory.json {key}")


def config_bool_from_env(key: str, *, default: bool) -> bool:
    raw_value = os.environ.get(key)
    if raw_value is None:
        return default

    return parse_bool(raw_value, name=key)


def parse_bool(raw_value: str, *, name: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")
