from __future__ import annotations

from typing import Any

from personal_agent_memory.embeddings import to_pgvector
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
