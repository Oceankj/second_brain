from __future__ import annotations

from typing import Any

from personal_agent_memory.repository.types import Connect


class MemoryItemsRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def create(
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

    async def find_by_title(self, title: str) -> dict[str, Any] | None:
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
