from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    embedding_dimension: int = 1536
    max_chunk_chars: int = 1800
    chunk_overlap_chars: int = 200


def load_settings() -> Settings:
    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run the memory MCP server")

    return Settings(
        database_url=database_url,
        embedding_dimension=int(os.environ.get("MEMORY_EMBEDDING_DIMENSION", "1536")),
        max_chunk_chars=int(os.environ.get("MEMORY_MAX_CHUNK_CHARS", "1800")),
        chunk_overlap_chars=int(os.environ.get("MEMORY_CHUNK_OVERLAP_CHARS", "200")),
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
