from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    database_url: str
    rest_api_enabled: bool = False
    default_user_token: str | None = None
    embedding_dimension: int = 1024
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: float = 30.0
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

    def __post_init__(self) -> None:
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


def load_settings() -> Settings:
    load_dotenv()
    memory_config = load_memory_config()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run the memory MCP server")

    return Settings(
        database_url=database_url,
        rest_api_enabled=config_bool_from_env("MEMORY_REST_API_ENABLED", default=False),
        default_user_token=os.environ.get("MEMORY_DEFAULT_USER_TOKEN"),
        embedding_dimension=int(os.environ.get("MEMORY_EMBEDDING_DIMENSION", "1024")),
        ollama_embedding_model=os.environ.get(
            "OLLAMA_EMBEDDING_MODEL",
            "qwen3-embedding:0.6b",
        ),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_timeout_seconds=float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "30")),
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


def config_int(
    config: Mapping[str, Any],
    *,
    section: str,
    key: str,
    default: int,
) -> int:
    section_values = config.get(section, {})
    if section_values is None:
        section_values = {}
    if not isinstance(section_values, Mapping):
        raise ValueError(f"memory.json {section} must be an object")

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
    section_values = config.get(section, {})
    if section_values is None:
        section_values = {}
    if not isinstance(section_values, Mapping):
        raise ValueError(f"memory.json {section} must be an object")

    value = section_values.get(key)
    if value is None:
        value = default
    return float(value)


def config_bool_from_env(key: str, *, default: bool) -> bool:
    raw_value = os.environ.get(key)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean value")
