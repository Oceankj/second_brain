from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT_DIR / "migrations"


@dataclass(frozen=True)
class DatabaseUrlSettings:
    database_url: str
    embedding_dimension: int


def load_database_url_settings() -> DatabaseUrlSettings:
    load_dotenv(ROOT_DIR / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise SystemExit(
            "DATABASE_URL must be a PostgreSQL connection string starting with "
            "postgresql:// or postgres://. Supabase project API URLs that start "
            "with https:// cannot be used for database migrations or checks."
        )

    embedding_dimension = int(os.environ.get("MEMORY_EMBEDDING_DIMENSION", "1024"))
    if embedding_dimension <= 0:
        raise SystemExit("MEMORY_EMBEDDING_DIMENSION must be positive")

    return DatabaseUrlSettings(
        database_url=database_url,
        embedding_dimension=embedding_dimension,
    )


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
