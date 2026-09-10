from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.providers.summaries import SummaryProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.memory.chunking import chunk_text
from personal_agent_memory.tool_schemas import CreateDailyDiaryInput
from personal_agent_memory.utils.serialization import (
    serialize_event,
    serialize_item,
    serialize_link,
    truncate_text,
)

DAILY_DIARY_SYSTEM_PROMPT = """You write concise daily diary entries for a personal memory system.
Summarize only the supplied memory items. Do not invent events, facts, preferences, or outcomes.
Write in Traditional Chinese unless the source material is mostly English.
Keep the entry specific, useful for future retrieval, and emotionally neutral but humane.
Use Markdown with short sections."""


class DailyDiaryService:
    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        embedding_provider: EmbeddingProvider,
        summary_provider_factory: Callable[[], SummaryProvider],
        max_chunk_chars: int,
        chunk_overlap_chars: int,
        source_max_chars: int,
        timezone: str,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.summary_provider_factory = summary_provider_factory
        self.max_chunk_chars = max_chunk_chars
        self.chunk_overlap_chars = chunk_overlap_chars
        self.source_max_chars = source_max_chars
        self.timezone = timezone

    async def create_daily_diary(
        self,
        payload: CreateDailyDiaryInput,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        existing = await self.repository.memory_items.find_diary_by_date(
            user_id=user_id,
            event_date=payload.date.isoformat(),
        )
        if existing and not payload.force:
            return {
                "status": "skipped",
                "created": False,
                "reason": "already_exists",
                "diary": serialize_item(existing),
                "source_items": [],
                "links": [],
                "events": [],
            }

        start_at, end_at = utc_day_bounds(payload.date, timezone=self.timezone)
        source_items = await self.repository.memory_items.list_daily_diary_sources(
            start_at=start_at,
            end_at=end_at,
            user_id=user_id,
        )

        if not source_items:
            return {
                "status": "skipped",
                "created": False,
                "reason": "no_source_items",
                "diary": None,
                "source_items": [],
                "links": [],
                "events": [],
            }

        user_prompt = build_daily_diary_prompt(
            diary_date=payload.date,
            source_items=source_items,
            source_max_chars=self.source_max_chars,
        )
        body = await self.summary_provider_factory().summarize(
            system_prompt=DAILY_DIARY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        title = f"Daily Diary: {payload.date.isoformat()}"

        if payload.dry_run:
            return {
                "status": "preview",
                "created": False,
                "reason": "dry_run",
                "diary": {
                    "title": title,
                    "type": "diary",
                    "status": "active",
                    "event_date": payload.date.isoformat(),
                    "body": body,
                },
                "source_items": serialize_source_items(source_items),
                "summary_prompt": user_prompt,
                "links": [],
                "events": [],
            }

        archived_diary_count = 0
        if existing and payload.force:
            archived_diary_count = await self.repository.memory_items.archive_many([existing["id"]])

        diary = await self.repository.memory_items.create(
            user_id=user_id,
            item_type="diary",
            title=title,
            body=body,
            status="active",
            event_date=payload.date.isoformat(),
        )
        await self._create_chunks(diary["id"], body)
        created_event = await self.repository.memory_item_events.create(
            memory_item_id=diary["id"],
            event_type="created",
            source="daily_diary",
            session_id=None,
            metadata={
                "date": payload.date.isoformat(),
                "source_item_ids": [item["id"] for item in source_items],
                "source_item_count": len(source_items),
                "archived_existing_diary_count": archived_diary_count,
            },
        )
        link_results = await self._link_diary_to_sources(diary["id"], source_items)

        return {
            "status": "accepted",
            "created": True,
            "reason": None,
            "diary": serialize_item(diary),
            "source_items": serialize_source_items(source_items),
            "links": link_results["links"],
            "events": [serialize_event(created_event), *link_results["events"]],
        }

    async def _create_chunks(self, memory_item_id: str, body: str) -> None:
        for chunk in chunk_text(body, self.max_chunk_chars, self.chunk_overlap_chars):
            embedding = await self.embedding_provider.embed_text(chunk.content)
            await self.repository.memory_chunks.create(
                memory_item_id=memory_item_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                embedding=embedding,
                token_count=chunk.token_count,
            )

    async def _link_diary_to_sources(
        self,
        diary_id: str,
        source_items: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        links = []
        events = []
        for item in source_items:
            link = await self.repository.memory_links.create(
                source_id=diary_id,
                target_id=item["id"],
                link_type="references",
            )
            if link:
                event = await self.repository.memory_item_events.create(
                    memory_item_id=item["id"],
                    event_type="mentioned_in_diary",
                    source="daily_diary",
                    session_id=None,
                    metadata={"diary_id": diary_id, "link_id": link["id"]},
                )
                links.append(serialize_link(link))
                events.append(serialize_event(event))
        return {"links": links, "events": events}


def utc_day_bounds(diary_date: date, *, timezone: str) -> tuple[datetime, datetime]:
    local_tz = ZoneInfo(timezone)
    start_at = datetime.combine(diary_date, time.min, tzinfo=local_tz)
    end_at = start_at + timedelta(days=1)
    return start_at.astimezone(UTC), end_at.astimezone(UTC)


def build_daily_diary_prompt(
    *,
    diary_date: date,
    source_items: list[dict[str, Any]],
    source_max_chars: int,
) -> str:
    blocks = []
    for reason, items in group_items_by_reason(source_items).items():
        item_lines = []
        for item in items:
            created_at = item.get("created_at")
            timestamp = (
                created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
            )
            item_lines.append(
                "\n".join(
                    [
                        f"- id: {item['id']}",
                        f"  created_at: {timestamp}",
                        f"  type: {item['type']}",
                        f"  status: {item['status']}",
                        f"  title: {item['title']}",
                        "  body: |",
                        indent_block(item["body"], prefix="    "),
                    ]
                )
            )
        blocks.append(f"## {reason}\n" + "\n".join(item_lines))

    source_text = "\n\n".join(blocks)
    source_text, did_truncate = truncate_text(source_text, source_max_chars)
    truncation_note = (
        "\nThe source list was truncated to fit the configured budget." if did_truncate else ""
    )

    return (
        f"Create a daily diary entry for {diary_date.isoformat()} from these memory items."
        f"{truncation_note}\n\n"
        "Output requirements:\n"
        "- Start with a one-paragraph overview.\n"
        "- Include sections only when there is relevant evidence.\n"
        "- Preserve important decisions, completed work, personal insights, preferences, "
        "and artifacts.\n"
        "- Avoid mentioning internal ids unless needed for clarity.\n"
        "- Do not add facts that are not present in the source items.\n\n"
        f"{source_text}"
    )


def group_items_by_reason(source_items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for item in source_items:
        grouped[item.get("ingest_reason") or "unspecified"].append(item)
    return dict(sorted(grouped.items()))


def indent_block(text: str, *, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def serialize_source_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "type": item["type"],
            "ingest_reason": item.get("ingest_reason"),
            "title": item["title"],
            "status": item["status"],
            "event_date": item.get("event_date").isoformat()
            if hasattr(item.get("event_date"), "isoformat")
            else item.get("event_date"),
            "created_at": item["created_at"].isoformat()
            if hasattr(item.get("created_at"), "isoformat")
            else str(item.get("created_at")),
        }
        for item in items
    ]
