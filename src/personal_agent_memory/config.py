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
    embedding_dimension: int = 1024
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: float = 30.0
    max_chunk_chars: int = 1800
    chunk_overlap_chars: int = 200

    def __post_init__(self) -> None:
        if self.max_chunk_chars <= 0:
            raise ValueError("max_chunk_chars must be positive")
        if self.chunk_overlap_chars < 0:
            raise ValueError("chunk_overlap_chars cannot be negative")
        if self.chunk_overlap_chars >= self.max_chunk_chars:
            raise ValueError("chunk_overlap_chars must be smaller than max_chunk_chars")


def load_settings() -> Settings:
    load_dotenv()
    memory_config = load_memory_config()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run the memory MCP server")

    return Settings(
        database_url=database_url,
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
