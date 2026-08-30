from __future__ import annotations

from datetime import datetime
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
        ingest_reason: str | None = None,
    ) -> dict[str, Any]:
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                insert into memory_items (type, ingest_reason, title, body, status, event_date)
                values (%s, %s, %s, %s, %s, %s)
                returning id::text, type::text, ingest_reason, title, body, status::text,
                          event_date, created_at, updated_at
                """,
                (item_type, ingest_reason, title, body, status, event_date),
            )
            return dict(await row.fetchone())

    async def find_by_title(self, title: str) -> dict[str, Any] | None:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                select id::text, type::text, ingest_reason, title, body, status::text,
                       event_date, created_at, updated_at
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

    async def list_created_between(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        statuses: list[str] | None = None,
        ingest_reasons: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                select id::text, type::text, ingest_reason, title, body, status::text,
                       event_date, created_at, updated_at
                from memory_items
                where created_at >= %s
                  and created_at < %s
                  and (%s::text[] is null or status::text = any(%s))
                  and (%s::text[] is null or ingest_reason = any(%s))
                order by created_at asc
                """,
                (
                    start_at,
                    end_at,
                    statuses,
                    statuses,
                    ingest_reasons,
                    ingest_reasons,
                ),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def archive_many(self, item_ids: list[str]) -> int:
        if not item_ids:
            return 0

        async with await self._connect() as conn:
            result = await conn.execute(
                """
                update memory_items
                set status = 'archived'
                where id::text = any(%s)
                  and status <> 'archived'
                """,
                (item_ids,),
            )
            return result.rowcount or 0
