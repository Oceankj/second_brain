from __future__ import annotations

import re
from pathlib import Path

import psycopg

from url_env import MIGRATIONS_DIR, load_database_url_settings


def main() -> None:
    settings = load_database_url_settings()

    print("Applying SQL migrations to DATABASE_URL target...")
    print(f"Using embedding_dimension={settings.embedding_dimension}")

    with psycopg.connect(settings.database_url, autocommit=True, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database(), current_user")
            database_name, user_name = cur.fetchone()
            print(f"Connected to database '{database_name}' as '{user_name}'.")

            for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                print(f"Applying {migration.name}...")
                cur.execute(render_migration(migration, settings.embedding_dimension))

    print("Migrations applied successfully.")


def render_migration(path: Path, embedding_dimension: int) -> str:
    sql_lines = []
    for line in path.read_text().splitlines():
        if line.lstrip().startswith("\\"):
            continue
        sql_lines.append(line)

    sql = "\n".join(sql_lines)
    return re.sub(r":embedding_dimension\b", str(embedding_dimension), sql)


if __name__ == "__main__":
    main()
