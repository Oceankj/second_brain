from __future__ import annotations

from typing import Any

from personal_agent_memory.repository.types import Connect


class MemoryLinksRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def create(
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

    async def load_for_items(
        self,
        item_ids: list[str],
    ) -> dict[str, dict[str, list[dict[str, Any]]]]:
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

            result = {item_id: {"outgoing_links": [], "backlinks": []} for item_id in item_ids}
            for row in await outgoing_cursor.fetchall():
                result[row["source_id"]]["outgoing_links"].append(dict(row))
            for row in await backlink_cursor.fetchall():
                result[row["target_id"]]["backlinks"].append(dict(row))
            return result
