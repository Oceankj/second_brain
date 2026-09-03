from __future__ import annotations

from typing import Any

import psycopg

from url_env import load_database_url_settings


REQUIRED_EXTENSIONS = {"pgcrypto", "vector"}
REQUIRED_TABLES = {
    "users",
    "memory_items",
    "memory_chunks",
    "memory_links",
    "tags",
    "memory_item_tags",
    "memory_item_events",
}
REQUIRED_ENUMS = {
    "memory_item_type",
    "memory_item_status",
    "memory_link_type",
    "memory_item_event_type",
}
REQUIRED_INDEXES = {
    "memory_items_type_idx",
    "memory_items_status_idx",
    "memory_items_event_date_idx",
    "memory_items_ingest_reason_idx",
    "memory_items_created_at_idx",
    "memory_items_user_status_idx",
    "users_api_token_hash_idx",
    "memory_chunks_item_idx",
    "memory_chunks_embedding_idx",
    "memory_links_source_idx",
    "memory_links_target_idx",
    "memory_item_tags_tag_idx",
    "memory_item_events_item_idx",
    "memory_item_events_type_idx",
    "memory_item_events_occurred_at_idx",
}


def main() -> None:
    settings = load_database_url_settings()
    failures: list[str] = []

    print("Inspecting DATABASE_URL target...")
    print(f"Expected embedding dimension: {settings.embedding_dimension}")

    with psycopg.connect(
        settings.database_url,
        autocommit=True,
        prepare_threshold=None,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database(), current_user, version()")
            database_name, user_name, version = cur.fetchone()
            print(f"Connected to database '{database_name}' as '{user_name}'.")
            print(f"PostgreSQL: {version.split(',', 1)[0]}")

            installed_extensions = get_installed_extensions(cur)
            print_section("Installed extensions", installed_extensions)
            failures.extend(missing_messages(REQUIRED_EXTENSIONS, installed_extensions, "extension"))

            memory_tables = get_memory_tables(cur)
            print_section("Memory tables", memory_tables)
            failures.extend(missing_messages(REQUIRED_TABLES, memory_tables, "table"))

            enum_types = get_enum_types(cur)
            print_section("Memory enum types", enum_types)
            failures.extend(missing_messages(REQUIRED_ENUMS, enum_types, "enum type"))

            memory_indexes = get_memory_indexes(cur)
            print_section("Memory indexes", memory_indexes)
            failures.extend(missing_messages(REQUIRED_INDEXES, memory_indexes, "index"))

            chunk_embedding_type = get_column_type(cur, "memory_chunks", "embedding")
            tag_embedding_type = get_column_type(cur, "tags", "embedding")
            expected_vector_type = f"vector({settings.embedding_dimension})"

            print()
            print("Embedding columns:")
            print(f"  memory_chunks.embedding: {chunk_embedding_type or 'missing'}")
            print(f"  tags.embedding: {tag_embedding_type or 'missing'}")

            if chunk_embedding_type != expected_vector_type:
                failures.append(
                    "memory_chunks.embedding has unexpected type: "
                    f"expected {expected_vector_type}, got {chunk_embedding_type or 'missing'}"
                )
            if tag_embedding_type != expected_vector_type:
                failures.append(
                    "tags.embedding has unexpected type: "
                    f"expected {expected_vector_type}, got {tag_embedding_type or 'missing'}"
                )

    if failures:
        print()
        print("Doctor found problems:")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)

    print()
    print("DATABASE_URL target looks healthy.")


def get_installed_extensions(cur: psycopg.Cursor[Any]) -> set[str]:
    cur.execute(
        """
        select extname
        from pg_extension
        where extname in ('pgcrypto', 'vector')
        order by extname
        """
    )
    return {row[0] for row in cur.fetchall()}


def get_memory_tables(cur: psycopg.Cursor[Any]) -> set[str]:
    cur.execute(
        """
        select table_name
        from information_schema.tables
        where table_schema = 'public'
          and (table_name like 'memory_%' or table_name in ('tags', 'users'))
        order by table_name
        """
    )
    return {row[0] for row in cur.fetchall()}


def get_enum_types(cur: psycopg.Cursor[Any]) -> set[str]:
    cur.execute(
        """
        select t.typname
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where n.nspname = 'public'
          and t.typtype = 'e'
          and t.typname like 'memory_%'
        order by t.typname
        """
    )
    return {row[0] for row in cur.fetchall()}


def get_memory_indexes(cur: psycopg.Cursor[Any]) -> set[str]:
    cur.execute(
        """
        select indexname
        from pg_indexes
        where schemaname = 'public'
          and (
            tablename like 'memory_%'
            or tablename in ('tags', 'users')
          )
        order by indexname
        """
    )
    return {row[0] for row in cur.fetchall()}


def get_column_type(cur: psycopg.Cursor[Any], table_name: str, column_name: str) -> str | None:
    cur.execute(
        """
        select format_type(a.atttypid, a.atttypmod) as column_type
        from pg_attribute a
        where a.attrelid = %s::regclass
          and a.attname = %s
          and not a.attisdropped
        """,
        (table_name, column_name),
    )
    row = cur.fetchone()
    return row[0] if row else None


def print_section(title: str, values: set[str]) -> None:
    print()
    print(f"{title}:")
    for value in sorted(values):
        print(f"  - {value}")
    if not values:
        print("  <none>")


def missing_messages(required: set[str], actual: set[str], noun: str) -> list[str]:
    return [f"missing {noun}: {name}" for name in sorted(required - actual)]


if __name__ == "__main__":
    main()
