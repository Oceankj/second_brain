from __future__ import annotations

from typing import Any

from personal_agent_memory.repository.types import Connect


class TagsRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def upsert(self, name: str, description: str | None = None) -> dict[str, Any]:
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
