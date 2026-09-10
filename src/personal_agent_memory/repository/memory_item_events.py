from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from personal_agent_memory.repository.types import Connect


class MemoryItemEventsRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def create(
        self,
        *,
        memory_item_id: str,
        event_type: str,
        source: str | None,
        session_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with self._connect() as conn:
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
