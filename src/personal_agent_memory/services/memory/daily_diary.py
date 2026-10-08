from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from personal_agent_memory.contracts import CreateDailyDiaryInput
from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.providers.summaries import SummaryProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.memory.chunking import chunk_text
from personal_agent_memory.services.memory.diary_preparation import (
    DiarySourceConflict,
    preparation_metadata,
    prepare_diary,
    source_snapshot,
)
from personal_agent_memory.utils.serialization import (
    serialize_event,
    serialize_item,
    serialize_link,
)


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
        if payload.date is None:
            payload = payload.model_copy(
                update={"date": datetime.now(ZoneInfo(self.timezone)).date() - timedelta(days=1)}
            )
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

        source_items = await self.repository.consolidation.diary_sources(
            day=payload.date,
            timezone=self.timezone,
            user_id=user_id,
            candidate_ids=[],
            include_candidates=True,
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

        reply_context = await load_reply_context(self.repository, source_items, user_id=user_id)
        prepared = await prepare_diary(
            source_items,
            summary_factory=self.summary_provider_factory,
            source_max_chars=self.source_max_chars,
            reply_context=reply_context,
        )
        body = prepared["body"]
        if not body:
            return {
                "status": "skipped",
                "created": False,
                "reason": "no_substantive_content",
                "diary": None,
                "source_items": serialize_source_items(source_items),
                "preparation": prepared,
                "links": [],
                "events": [],
            }
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
                "preparation": prepared,
                "links": [],
                "events": [],
            }

        # Finish external provider work before opening the write transaction.
        prepared_chunks = []
        for chunk in chunk_text(body, self.max_chunk_chars, self.chunk_overlap_chars):
            embedding = await self.embedding_provider.embed_text(chunk.content)
            prepared_chunks.append((chunk, embedding))

        async with self.repository.transaction() as conn:
            # Serialize writers for a user's date, including concurrent scheduler retries.
            await conn.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"daily_diary:{user_id}:{payload.date.isoformat()}",),
            )
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
            evidence = [*reply_context, *source_items]
            locked = await self.repository.consolidation.lock_items(
                user_id=user_id,
                item_ids=sorted({s["id"] for s in evidence}),
            )
            if source_snapshot(locked) != source_snapshot(evidence):
                raise DiarySourceConflict("Diary sources changed; retry preparation")
            archived_diary_count = 0
            if existing and payload.force:
                archived_diary_count = await self.repository.memory_items.archive_many(
                    [existing["id"]]
                )

            diary = await self.repository.memory_items.create(
                user_id=user_id,
                item_type="diary",
                record_kind="derived",
                title=title,
                body=body,
                status="active",
                event_date=payload.date.isoformat(),
            )
            for chunk, embedding in prepared_chunks:
                await self.repository.memory_chunks.create(
                    memory_item_id=diary["id"],
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    embedding=embedding,
                    token_count=chunk.token_count,
                )
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
                    "preparation": preparation_metadata(prepared),
                },
            )
            replacements = await self.repository.consolidation.replacements(
                source_ids=[item["id"] for item in source_items],
                user_id=user_id,
            )
            link_targets = {item["id"]: item for item in [*source_items, *replacements]}
            link_results = await self._link_diary_to_sources(
                diary["id"],
                list(link_targets.values()),
            )

            return {
                "status": "accepted",
                "created": True,
                "reason": None,
                "diary": serialize_item(diary),
                "source_items": serialize_source_items(source_items),
                "links": link_results["links"],
                "events": [serialize_event(created_event), *link_results["events"]],
            }

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
                link_type="references" if item.get("record_kind") == "derived" else "derived_from",
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
    reply_context: list[dict] | None = None,
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
                        f"  source_date: {item.get('source_date') or diary_date.isoformat()}",
                        f"  type: {item['type']}",
                        f"  status: {item['status']}",
                        f"  role: {item.get('role') or 'unknown'}",
                        f"  reply_to_ids: {item.get('reply_to_ids', [])}",
                        f"  title: {item['title']}",
                        "  body: |",
                        indent_block(
                            diary_evidence_body(item["body"], role=item.get("role")), prefix="    "
                        ),
                    ]
                )
            )
        blocks.append(f"## {reason}\n" + "\n".join(item_lines))

    source_text = "\n\n".join(blocks)
    if reply_context:
        source_text += (
            "\n\nReply context ONLY (not additional events for this day):\n"
            + json.dumps(
                [
                    {
                        "id": x["id"],
                        "role": x.get("role"),
                        "body": x["body"],
                        "reply_to_ids": x.get("reply_to_ids", []),
                    }
                    for x in reply_context
                ],
                ensure_ascii=False,
            )
        )
    if len(source_text) > source_max_chars:
        raise ValueError(
            "Diary evidence exceeds source budget; refusing to truncate qualifications"
        )

    return (
        f"Create a daily diary entry for {diary_date.isoformat()} from these memory items."
        "\n\n"
        "Output requirements:\n"
        "- Write natural Chinese with original English terms; no headings or bullet lists.\n"
        "- Do not force an overview, insight, takeaway, or concluding lesson.\n"
        "- Preserve important decisions, completed work, personal insights, preferences, "
        "and artifacts.\n"
        "- Omit memory-saving requests, saved/synced acknowledgments and storage destinations.\n"
        "- Avoid mentioning internal ids unless needed for clarity.\n"
        "- Preserve only explicitly stated insights; do not infer feelings, motives, "
        "growth, causality, or broader meaning. Preserve uncertainty and attribution.\n"
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
            "role": item.get("role"),
            "record_kind": item.get("record_kind"),
            "source_message_id": item.get("source_message_id"),
            "reply_to_ids": item.get("reply_to_ids", []),
            "event_date": item.get("event_date").isoformat()
            if hasattr(item.get("event_date"), "isoformat")
            else item.get("event_date"),
            "created_at": item["created_at"].isoformat()
            if hasattr(item.get("created_at"), "isoformat")
            else str(item.get("created_at")),
        }
        for item in items
    ]


# Filter only standalone, unmistakable storage receipts in the Assistant section.
# Statements about debugging/implementing memory storage do not match this grammar.
_RECEIPT = re.compile(
    r"(?:已寫入|已儲存|已保存|已記錄|已同步|已記住)\s*[：:]?\s*"
    r"(?:(?:個人\s*)?(?:MEMORY\.md)(?:[（(][^）)\n]*[）)])?"
    r"|second-brain(?:\s+MCP)?|memory\s+system|MCP)"
    r"(?:\s*[＋+、與和]\s*(?:(?:個人\s*)?MEMORY\.md(?:[（(][^）)\n]*[）)])?"
    r"|second-brain(?:\s+MCP)?|memory\s+system|MCP))*[。.!！]?",
    re.IGNORECASE,
)


def diary_evidence_body(body: str, *, role: str | None = None) -> str:
    if role == "assistant":
        return "\n".join(
            line for line in body.splitlines() if not _RECEIPT.fullmatch(line.strip())
        ).strip()
    if role == "user":
        user, marker, assistant = body, "", ""
    else:
        user, marker, assistant = body.partition("\n\nAssistant:\n")
    # Remove only a standalone trailing request to save to a named memory store.
    # Preserve the preceding thought and all qualifications, and leave the DB row unchanged.
    user = re.sub(
        r"(?:^|(?<=[。！？\n]))(?:幫我|請)(?:寫到|寫入|存入|儲存到)\s*"
        r"(?:memory\s+system|second-brain(?:\s+MCP)?|MCP|MEMORY\.md)[。.!！]?\s*$",
        "",
        user,
        flags=re.IGNORECASE,
    ).rstrip()
    if not marker:
        return user
    lines = [line for line in assistant.splitlines() if not _RECEIPT.fullmatch(line.strip())]
    cleaned = "\n".join(lines).strip()
    return user + marker + cleaned if cleaned else user


async def load_reply_context(repository, sources: list[dict], *, user_id: str) -> list[dict]:
    ids = [s["id"] for s in sources if s.get("source_message_id")]
    if not ids:
        return []
    context = await repository.consolidation.reply_context(user_id=user_id, item_ids=ids)
    all_items = {s["id"]: s for s in [*context, *sources]}
    links = await repository.memory_links.load_for_items(list(all_items), user_id=user_id)
    for item_id, item in all_items.items():
        item["reply_to_ids"] = [
            link["target_id"]
            for link in links.get(item_id, {}).get("outgoing_links", [])
            if link["link_type"] == "replies_to"
        ]
    return [s for s in context if s["id"] not in {x["id"] for x in sources}]
