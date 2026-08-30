from __future__ import annotations

from datetime import date
from typing import Any

from personal_agent_memory.providers.embeddings import to_pgvector
from personal_agent_memory.repository.types import Connect


class MemoryChunksRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def create(
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

    async def search(
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
                  mi.ingest_reason,
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

    async def search_recent_diary(
        self,
        *,
        query_embedding: list[float],
        start_date: date,
        limit: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                select
                  mi.id::text as id,
                  mi.type::text as type,
                  mi.ingest_reason,
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
                  and mi.type = 'diary'
                  and coalesce(mi.event_date, mi.created_at::date) >= %s
                order by mc.embedding <=> %s::vector
                limit %s
                """,
                (
                    to_pgvector(query_embedding),
                    start_date,
                    to_pgvector(query_embedding),
                    limit,
                ),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def search_by_tags(
        self,
        *,
        query_embedding: list[float],
        tag_scores: dict[str, float],
        memory_types: list[str],
        tag_weight: float,
        limit: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0 or not tag_scores:
            return []

        tag_ids = list(tag_scores)
        scores = [float(tag_scores[tag_id]) for tag_id in tag_ids]
        chunk_weight = 1 - tag_weight

        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                with matched_tags(tag_id, tag_score) as (
                  select * from unnest(%s::uuid[], %s::double precision[])
                ),
                tagged_chunks as (
                  select
                    mi.id::text as id,
                    mi.type::text as type,
                    mi.ingest_reason,
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
                    max(mt.tag_score) as tag_score,
                    1 - (mc.embedding <=> %s::vector) as chunk_score
                  from matched_tags mt
                  join memory_item_tags mit on mit.tag_id = mt.tag_id
                  join memory_items mi on mi.id = mit.memory_item_id
                  join memory_chunks mc on mc.memory_item_id = mi.id
                  where mi.status <> 'archived'
                    and mi.type::text = any(%s)
                  group by
                    mi.id,
                    mi.type,
                    mi.ingest_reason,
                    mi.title,
                    mi.body,
                    mi.status,
                    mi.event_date,
                    mi.created_at,
                    mi.updated_at,
                    mc.id,
                    mc.chunk_index,
                    mc.content,
                    mc.token_count,
                    mc.embedding
                )
                select
                  id,
                  type,
                  ingest_reason,
                  title,
                  body,
                  status,
                  event_date,
                  created_at,
                  updated_at,
                  chunk_id,
                  chunk_index,
                  chunk_content,
                  token_count,
                  tag_score,
                  chunk_score,
                  (tag_score * %s + chunk_score * %s) as score
                from tagged_chunks
                order by score desc
                limit %s
                """,
                (
                    tag_ids,
                    scores,
                    to_pgvector(query_embedding),
                    memory_types,
                    tag_weight,
                    chunk_weight,
                    limit,
                ),
            )
            return [dict(row) for row in await cursor.fetchall()]
