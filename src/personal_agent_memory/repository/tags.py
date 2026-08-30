from __future__ import annotations

from typing import Any

from personal_agent_memory.providers.embeddings import to_pgvector
from personal_agent_memory.repository.types import Connect


class TagsRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def upsert(
        self,
        name: str,
        description: str | None = None,
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                insert into tags (name, description, embedding)
                values (%s, %s, %s::vector)
                on conflict (name) do update
                set description = coalesce(tags.description, excluded.description),
                    embedding = coalesce(tags.embedding, excluded.embedding),
                    updated_at = now()
                returning id::text, name, description, created_at, updated_at
                """,
                (name, description, to_pgvector(embedding) if embedding is not None else None),
            )
            return dict(await row.fetchone())

    async def search(
        self,
        *,
        query_embedding: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                select
                  id::text,
                  name,
                  description,
                  created_at,
                  updated_at,
                  1 - (embedding <=> %s::vector) as score
                from tags
                where embedding is not null
                order by embedding <=> %s::vector
                limit %s
                """,
                (
                    to_pgvector(query_embedding),
                    to_pgvector(query_embedding),
                    limit,
                ),
            )
            return [dict(row) for row in await cursor.fetchall()]
