from __future__ import annotations

from personal_agent_memory.repository.types import Connect


class MemoryItemTagsRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def attach(self, memory_item_id: str, tag_id: str) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                insert into memory_item_tags (memory_item_id, tag_id)
                values (%s, %s)
                on conflict do nothing
                """,
                (memory_item_id, tag_id),
            )
