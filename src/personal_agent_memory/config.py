from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    embedding_dimension: int = 1536
    max_chunk_chars: int = 1800
    chunk_overlap_chars: int = 200


def load_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run the memory MCP server")

    return Settings(
        database_url=database_url,
        embedding_dimension=int(os.environ.get("MEMORY_EMBEDDING_DIMENSION", "1536")),
        max_chunk_chars=int(os.environ.get("MEMORY_MAX_CHUNK_CHARS", "1800")),
        chunk_overlap_chars=int(os.environ.get("MEMORY_CHUNK_OVERLAP_CHARS", "200")),
    )
