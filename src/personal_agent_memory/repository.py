from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from personal_agent_memory.embeddings import to_pgvector


class PostgresMemoryRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def create_memory_item(
        self,
        *,
        item_type: str,
        title: str,
        body: str,
        status: str = "candidate",
        event_date: str | None = None,
    ) -> dict[str, Any]:
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                insert into memory_items (type, title, body, status, event_date)
                values (%s, %s, %s, %s, %s)
                returning id::text, type::text, title, body, status::text, event_date,
                          created_at, updated_at
                """,
                (item_type, title, body, status, event_date),
            )
            return dict(await row.fetchone())

    async def create_chunk(
        self,
        *,
        memory_item_id: str,
        chunk_index: int,
        content: str,
        embedding: list[float],
        token_count: int | None,
    ) -> dict[str, Any]:
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                insert into memory_chunks (
                  memory_item_id, chunk_index, content, embedding, token_count
                )
                values (%s, %s, %s, %s::vector, %s)
                returning id::text, memory_item_id::text, chunk_index, content,
                          token_count, created_at, updated_at
                """,
                (memory_item_id, chunk_index, content, to_pgvector(embedding), token_count),
            )
            return dict(await row.fetchone())

    async def upsert_tag(self, name: str, description: str | None = None) -> dict[str, Any]:
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                insert into tags (name, description)
                values (%s, %s)
                on conflict (name) do update
                set description = coalesce(tags.description, excluded.description),
                    updated_at = now()
                returning id::text, name, description, created_at, updated_at
                """,
                (name, description),
            )
            return dict(await row.fetchone())

    async def attach_tag(self, memory_item_id: str, tag_id: str) -> None:
        async with await self._connect() as conn:
            await conn.execute(
                """
                insert into memory_item_tags (memory_item_id, tag_id)
                values (%s, %s)
                on conflict do nothing
                """,
                (memory_item_id, tag_id),
            )

    async def find_item_by_title(self, title: str) -> dict[str, Any] | None:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                select id::text, type::text, title, body, status::text, event_date,
                       created_at, updated_at
                from memory_items
                where lower(title) = lower(%s)
                  and status <> 'archived'
                order by updated_at desc
                limit 1
                """,
                (title,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_link(
        self,
        *,
        source_id: str,
        target_id: str,
        link_type: str = "references",
    ) -> dict[str, Any] | None:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                insert into memory_links (source_id, target_id, link_type)
                values (%s, %s, %s)
                on conflict do nothing
                returning id::text, source_id::text, target_id::text, link_type::text, created_at
                """,
                (source_id, target_id, link_type),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_event(
        self,
        *,
        memory_item_id: str,
        event_type: str,
        source: str | None,
        session_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                insert into memory_item_events (
                  memory_item_id, event_type, source, session_id, metadata
                )
                values (%s, %s, %s, %s, %s)
                returning id::text, memory_item_id::text, event_type::text, source,
                          session_id, metadata, occurred_at
                """,
                (
                    memory_item_id,
                    event_type,
                    source,
                    session_id,
                    Jsonb(metadata) if metadata is not None else None,
                ),
            )
            return dict(await cursor.fetchone())

    async def search_chunks(
        self,
        *,
        query_embedding: list[float],
        memory_types: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                select
                  mi.id::text as id,
                  mi.type::text as type,
                  mi.title,
                  mi.body,
                  mi.status::text as status,
                  mi.event_date,
                  mi.created_at,
                  mi.updated_at,
                  mc.id::text as chunk_id,
                  mc.chunk_index,
                  mc.content as chunk_content,
                  mc.token_count,
                  1 - (mc.embedding <=> %s::vector) as score
                from memory_chunks mc
                join memory_items mi on mi.id = mc.memory_item_id
                where mi.status <> 'archived'
                  and mi.type::text = any(%s)
                order by mc.embedding <=> %s::vector
                limit %s
                """,
                (
                    to_pgvector(query_embedding),
                    memory_types,
                    to_pgvector(query_embedding),
                    limit,
                ),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def load_links_for_items(self, item_ids: list[str]) -> dict[str, dict[str, list[dict[str, Any]]]]:
        if not item_ids:
            return {}

        async with await self._connect() as conn:
            outgoing_cursor = await conn.execute(
                """
                select id::text, source_id::text, target_id::text, link_type::text, created_at
                from memory_links
                where source_id::text = any(%s)
                """,
                (item_ids,),
            )
            backlink_cursor = await conn.execute(
                """
                select id::text, source_id::text, target_id::text, link_type::text, created_at
                from memory_links
                where target_id::text = any(%s)
                """,
                (item_ids,),
            )

            result = {
                item_id: {"outgoing_links": [], "backlinks": []}
                for item_id in item_ids
            }
            for row in await outgoing_cursor.fetchall():
                result[row["source_id"]]["outgoing_links"].append(dict(row))
            for row in await backlink_cursor.fetchall():
                result[row["target_id"]]["backlinks"].append(dict(row))
            return result

    async def _connect(self) -> psycopg.AsyncConnection:
        return await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row)
