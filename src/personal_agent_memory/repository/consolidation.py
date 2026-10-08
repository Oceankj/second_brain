from __future__ import annotations

from datetime import date
from typing import Any

from personal_agent_memory.repository.types import Connect

# Ingest metadata is validated as a datetime before persistence. Legacy/imported
# notes without a timestamp fall back to their original creation time.
SOURCE_DATE = """coalesce(mi.event_date,
    (coalesce(mi.source_timestamp, (select (e.metadata->>'timestamp')::timestamptz
        from memory_item_events e where e.memory_item_id = mi.id
        and e.event_type = 'created' and e.metadata->>'timestamp' is not null
        order by e.occurred_at asc limit 1), mi.created_at) at time zone %s)::date)"""
FIELDS = """mi.id::text, mi.user_id, mi.type::text, mi.ingest_reason, mi.title, mi.body,
    mi.status::text, mi.event_date, mi.created_at, mi.updated_at,
    mi.record_kind, mi.role, mi.source, mi.session_id, mi.source_message_id, mi.sequence,
                  mi.source_timestamp, mi.content_kinds"""


class ConsolidationRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def candidates(self, *, user_id: str, timezone: str, limit: int) -> list[dict]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                f"""select {FIELDS}, {SOURCE_DATE} as source_date from memory_items mi
                where mi.user_id = %s and mi.type = 'note' and mi.status = 'candidate'
                order by source_date, mi.created_at, mi.id limit %s""",
                (timezone, user_id, limit),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def diary_sources(
        self,
        *,
        user_id: str,
        timezone: str,
        day: date,
        candidate_ids: list[str],
        include_candidates: bool = False,
    ) -> list[dict]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                f"""select {FIELDS}, {SOURCE_DATE} as source_date from memory_items mi
                where mi.user_id = %s and mi.type = 'note' and mi.record_kind <> 'derived'
                and (mi.id::text = any(%s) or mi.status = 'active'
                    or (%s and mi.status = 'candidate')
                    or exists (select 1 from memory_item_events e
                        where e.memory_item_id = mi.id and e.event_type = 'archived'
                        and e.source = 'candidate_review'))
                and not exists (select 1 from memory_item_events e
                    where e.memory_item_id = mi.id and e.event_type = 'created'
                    and e.source = 'candidate_review')
                and {SOURCE_DATE} = %s
                order by mi.created_at, mi.id""",
                (timezone, user_id, candidate_ids, include_candidates, timezone, day),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def lock_items(self, *, user_id: str, item_ids: list[str]) -> list[dict]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                f"""select {FIELDS} from memory_items mi
                where mi.user_id = %s and mi.id::text = any(%s)
                order by mi.id for update""",
                (user_id, item_ids),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def copy_tags(self, *, source_ids: list[str], target_id: str) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """insert into memory_item_tags(memory_item_id, tag_id)
                select %s::uuid, tag_id from memory_item_tags
                where memory_item_id::text = any(%s) on conflict do nothing""",
                (target_id, source_ids),
            )

    async def replacements(self, *, source_ids: list[str], user_id: str) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                f"""select distinct {FIELDS} from memory_items mi
                join memory_links ml on ml.source_id = mi.id
                where mi.user_id = %s and mi.status = 'active' and mi.type = 'note'
                and ml.target_id::text = any(%s)
                and exists (select 1 from memory_item_events e
                    where e.memory_item_id = mi.id and e.event_type = 'created'
                    and e.source = 'candidate_review')""",
                (user_id, source_ids),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def reply_context(self, *, user_id: str, item_ids: list[str]) -> list[dict]:
        """Bounded ancestor closure, including archived sources. Never invent adjacency."""
        seen = set(item_ids)
        frontier = item_ids
        result = []
        while frontier:
            async with self._connect() as conn:
                cursor = await conn.execute(
                    f"""select distinct {FIELDS} from memory_links ml
                    join memory_items mi on mi.id = ml.target_id
                    where ml.source_id::text = any(%s) and mi.user_id = %s
                    and ml.link_type = 'replies_to'""",
                    (frontier, user_id),
                )
                parents = [dict(row) for row in await cursor.fetchall()]
            frontier = []
            for item in parents:
                if item["id"] not in seen:
                    seen.add(item["id"])
                    frontier.append(item["id"])
                    result.append(item)
            if len(result) > 50:
                raise ValueError("Reply context exceeds 50 sources; review a smaller batch")
        return result
