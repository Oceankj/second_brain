from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from personal_agent_memory.services.memory.daily_diary import DailyDiaryService, utc_day_bounds
from personal_agent_memory.tool_schemas import CreateDailyDiaryInput


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.texts = []

    async def embed_text(self, text: str) -> list[float]:
        self.texts.append(text)
        return [1.0, 0.0]


class FakeSummaryProvider:
    def __init__(self) -> None:
        self.calls = []

    async def summarize(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return "今天完成了 memory server 的 daily diary 設計與實作。"


class FakeMemoryItemsRepository:
    def __init__(self, source_items: list[dict[str, Any]]) -> None:
        self.source_items = source_items
        self.created = []
        self.archived = []
        self.existing_diary = None

    async def find_diary_by_date(self, *, user_id: str, event_date: str) -> dict[str, Any] | None:
        return self.existing_diary

    async def list_daily_diary_sources(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        user_id: str,
    ) -> list[dict[str, Any]]:
        return self.source_items

    async def create(
        self,
        *,
        user_id: str,
        item_type: str,
        title: str,
        body: str,
        status: str = "candidate",
        event_date: str | None = None,
        ingest_reason: str | None = None,
    ) -> dict[str, Any]:
        item = {
            "id": "diary-1",
            "user_id": user_id,
            "type": item_type,
            "ingest_reason": ingest_reason,
            "title": title,
            "body": body,
            "status": status,
            "event_date": event_date,
            "created_at": datetime(2026, 9, 8, 23, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 9, 8, 23, 0, tzinfo=UTC),
        }
        self.created.append(item)
        return item

    async def archive_many(self, item_ids: list[str]) -> int:
        self.archived.extend(item_ids)
        return len(item_ids)


class FakeMemoryChunksRepository:
    def __init__(self) -> None:
        self.created = []

    async def create(
        self,
        *,
        memory_item_id: str,
        chunk_index: int,
        content: str,
        embedding: list[float],
        token_count: int | None,
    ) -> dict[str, Any]:
        self.created.append(
            {
                "memory_item_id": memory_item_id,
                "chunk_index": chunk_index,
                "content": content,
                "embedding": embedding,
                "token_count": token_count,
            }
        )
        return {}


class FakeMemoryLinksRepository:
    def __init__(self) -> None:
        self.created = []

    async def create(
        self,
        *,
        source_id: str,
        target_id: str,
        link_type: str = "references",
    ) -> dict[str, Any]:
        link = {
            "id": f"link-{len(self.created) + 1}",
            "source_id": source_id,
            "target_id": target_id,
            "link_type": link_type,
            "created_at": datetime(2026, 9, 8, 23, 1, tzinfo=UTC),
        }
        self.created.append(link)
        return link


class FakeMemoryItemEventsRepository:
    def __init__(self) -> None:
        self.created = []

    async def create(
        self,
        *,
        memory_item_id: str,
        event_type: str,
        source: str | None,
        session_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "id": f"event-{len(self.created) + 1}",
            "memory_item_id": memory_item_id,
            "event_type": event_type,
            "source": source,
            "session_id": session_id,
            "metadata": metadata,
            "occurred_at": datetime(2026, 9, 8, 23, 2, tzinfo=UTC),
        }
        self.created.append(event)
        return event


class FakeRepository:
    def __init__(self, source_items: list[dict[str, Any]]) -> None:
        self.memory_items = FakeMemoryItemsRepository(source_items)
        self.memory_chunks = FakeMemoryChunksRepository()
        self.memory_links = FakeMemoryLinksRepository()
        self.memory_item_events = FakeMemoryItemEventsRepository()


def make_source_item(item_id: str, reason: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "user_id": "user-local",
        "type": "note",
        "ingest_reason": reason,
        "title": "Memory work",
        "body": "User and assistant discussed daily diary generation.",
        "status": "candidate",
        "event_date": None,
        "created_at": datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
    }


def make_service(
    repository: FakeRepository,
    embedding_provider: FakeEmbeddingProvider,
    summary_provider: FakeSummaryProvider,
) -> DailyDiaryService:
    return DailyDiaryService(
        repository=repository,
        embedding_provider=embedding_provider,
        summary_provider_factory=lambda: summary_provider,
        max_chunk_chars=1800,
        chunk_overlap_chars=200,
        source_max_chars=24000,
        timezone="UTC",
    )


def test_utc_day_bounds_uses_configured_timezone() -> None:
    start_at, end_at = utc_day_bounds(date(2026, 9, 8), timezone="America/Los_Angeles")

    assert start_at.isoformat() == "2026-09-08T07:00:00+00:00"
    assert end_at.isoformat() == "2026-09-09T07:00:00+00:00"


@pytest.mark.anyio
async def test_create_daily_diary_dry_run_summarizes_without_writing() -> None:
    repository = FakeRepository([make_source_item("item-1", "task_completed")])
    embedding_provider = FakeEmbeddingProvider()
    summary_provider = FakeSummaryProvider()
    service = make_service(repository, embedding_provider, summary_provider)

    result = await service.create_daily_diary(
        CreateDailyDiaryInput(token="x" * 32, date=date(2026, 9, 8), dry_run=True),
        user_id="user-local",
    )

    assert result["status"] == "preview"
    assert result["created"] is False
    assert result["diary"]["body"] == "今天完成了 memory server 的 daily diary 設計與實作。"
    assert "task_completed" in summary_provider.calls[0]["user_prompt"]
    assert repository.memory_items.created == []
    assert repository.memory_chunks.created == []
    assert repository.memory_links.created == []
    assert repository.memory_item_events.created == []
    assert embedding_provider.texts == []


@pytest.mark.anyio
async def test_create_daily_diary_writes_diary_chunks_links_and_events() -> None:
    repository = FakeRepository(
        [
            make_source_item("item-1", "task_completed"),
            make_source_item("item-2", "decision"),
        ]
    )
    embedding_provider = FakeEmbeddingProvider()
    summary_provider = FakeSummaryProvider()
    service = make_service(repository, embedding_provider, summary_provider)

    result = await service.create_daily_diary(
        CreateDailyDiaryInput(token="x" * 32, date=date(2026, 9, 8)),
        user_id="user-local",
    )

    assert result["status"] == "accepted"
    assert result["created"] is True
    assert result["diary"]["type"] == "diary"
    assert result["diary"]["event_date"] == "2026-09-08"
    assert repository.memory_items.created[0]["status"] == "active"
    assert repository.memory_chunks.created[0]["memory_item_id"] == "diary-1"
    assert repository.memory_links.created == [
        {
            "id": "link-1",
            "source_id": "diary-1",
            "target_id": "item-1",
            "link_type": "references",
            "created_at": datetime(2026, 9, 8, 23, 1, tzinfo=UTC),
        },
        {
            "id": "link-2",
            "source_id": "diary-1",
            "target_id": "item-2",
            "link_type": "references",
            "created_at": datetime(2026, 9, 8, 23, 1, tzinfo=UTC),
        },
    ]
    assert [event["event_type"] for event in repository.memory_item_events.created] == [
        "created",
        "mentioned_in_diary",
        "mentioned_in_diary",
    ]
