from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from personal_agent_memory.contracts import CreateDailyDiaryInput
from personal_agent_memory.services.memory.daily_diary import DailyDiaryService, utc_day_bounds


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
        record_kind: str = "unknown",
        content_kinds: list[str] | None = None,
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
        self.consolidation = SimpleNamespace(
            diary_sources=AsyncMock(return_value=source_items),
            replacements=AsyncMock(return_value=[]),
            lock_items=AsyncMock(return_value=source_items),
        )
        self.memory_chunks = FakeMemoryChunksRepository()
        self.memory_links = FakeMemoryLinksRepository()
        self.memory_item_events = FakeMemoryItemEventsRepository()
        self.connection = type("Connection", (), {"execute": AsyncMock()})()

    @asynccontextmanager
    async def transaction(self):
        yield self.connection


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
    assert "User and assistant discussed daily diary generation." in result["diary"]["body"]
    assert result["preparation"]["sources"][0]["validation"] == "fallback_invalid_plan"
    assert "item-1" in summary_provider.calls[0]["user_prompt"]
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
            "link_type": "derived_from",
            "created_at": datetime(2026, 9, 8, 23, 1, tzinfo=UTC),
        },
        {
            "id": "link-2",
            "source_id": "diary-1",
            "target_id": "item-2",
            "link_type": "derived_from",
            "created_at": datetime(2026, 9, 8, 23, 1, tzinfo=UTC),
        },
    ]
    assert [event["event_type"] for event in repository.memory_item_events.created] == [
        "created",
        "mentioned_in_diary",
        "mentioned_in_diary",
    ]


@pytest.mark.parametrize("day,hours", [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_day_bounds_follow_dst(day, hours):
    start, end = utc_day_bounds(day, timezone="America/Los_Angeles")
    assert end - start == timedelta(hours=hours)


@pytest.mark.anyio
async def test_existing_diary_skips_providers():
    repository = FakeRepository([])
    repository.memory_items.existing_diary = make_source_item("existing", "decision")
    summary = FakeSummaryProvider()
    result = await make_service(repository, FakeEmbeddingProvider(), summary).create_daily_diary(
        CreateDailyDiaryInput(token="token", date=date(2026, 9, 8)),
        user_id="user-local",
    )
    assert result["reason"] == "already_exists"
    assert summary.calls == []


@pytest.mark.anyio
async def test_empty_day_skips_summary_and_writes():
    repository = FakeRepository([])
    summary = FakeSummaryProvider()
    result = await make_service(repository, FakeEmbeddingProvider(), summary).create_daily_diary(
        CreateDailyDiaryInput(token="token"),
        user_id="user-local",
    )
    assert result["reason"] == "no_source_items"
    assert summary.calls == []
    assert repository.memory_items.created == []


@pytest.mark.anyio
async def test_default_date_is_previous_local_day(monkeypatch):
    import personal_agent_memory.services.memory.daily_diary as module

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 2, 1, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(module, "datetime", FixedDatetime)
    repository = FakeRepository([make_source_item("source", "decision")])
    service = make_service(repository, FakeEmbeddingProvider(), FakeSummaryProvider())
    service.timezone = "America/Los_Angeles"
    result = await service.create_daily_diary(
        CreateDailyDiaryInput(token="token", dry_run=True),
        user_id="user-local",
    )
    assert result["diary"]["event_date"] == "2026-09-30"


@pytest.mark.anyio
async def test_embedding_failure_preserves_existing_diary():
    repository = FakeRepository([make_source_item("source", "decision")])
    repository.memory_items.existing_diary = make_source_item("existing", "decision")
    embedding = FakeEmbeddingProvider()
    embedding.embed_text = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await make_service(repository, embedding, FakeSummaryProvider()).create_daily_diary(
            CreateDailyDiaryInput(token="token", date=date(2026, 9, 8), force=True),
            user_id="user-local",
        )
    assert repository.memory_items.archived == []
    assert repository.memory_items.created == []


@pytest.mark.anyio
async def test_concurrent_writer_is_rechecked_before_insert():
    repository = FakeRepository([make_source_item("source", "decision")])
    repository.memory_items.find_diary_by_date = AsyncMock(
        side_effect=[None, make_source_item("winner", "decision")]
    )
    result = await make_service(
        repository,
        FakeEmbeddingProvider(),
        FakeSummaryProvider(),
    ).create_daily_diary(
        CreateDailyDiaryInput(token="token", date=date(2026, 9, 8)),
        user_id="user-local",
    )
    assert result["reason"] == "already_exists"
    assert result["diary"]["id"] == "winner"
    assert repository.memory_items.created == []


def test_diary_evidence_removes_only_storage_receipts():
    from personal_agent_memory.services.memory.daily_diary import diary_evidence_body

    body = (
        "User:\n喜歡這個 framework。\n\nAssistant:\n"
        "已寫入：個人 MEMORY.md（Preferences）＋ second-brain MCP。"
    )
    assert diary_evidence_body(body) == "User:\n喜歡這個 framework。"
    engineering = "User:\n修正記憶系統\n\nAssistant:\n已寫入資料庫，但回滾功能測試失敗。"
    assert diary_evidence_body(engineering) == engineering
    substantive = "User:\n偏好\n\nAssistant:\n已記住：偏好低風險的策略。"
    assert diary_evidence_body(substantive) == substantive
    assert body.endswith("second-brain MCP。")  # The original evidence remains unchanged.


def test_diary_evidence_omits_save_request_without_removing_thought():
    from personal_agent_memory.services.memory.daily_diary import diary_evidence_body

    original = "User:\nConnection 是推定，不能當成引文。幫我寫到 memory system。"
    assert diary_evidence_body(original) == "User:\nConnection 是推定，不能當成引文。"
    actual_work = "User:\n開發 memory system 寫入功能，並測試資料是否保留。"
    assert diary_evidence_body(actual_work) == actual_work


@pytest.mark.anyio
async def test_changed_evidence_aborts_before_writing_diary():
    from personal_agent_memory.services.memory.diary_preparation import DiarySourceConflict

    item = make_source_item("source", "decision")
    repo = FakeRepository([item])
    repo.consolidation.lock_items.return_value = [{**item, "body": "Changed after classification"}]
    with pytest.raises(DiarySourceConflict):
        await make_service(repo, FakeEmbeddingProvider(), FakeSummaryProvider()).create_daily_diary(
            CreateDailyDiaryInput(token="token", date=date(2026, 9, 8)),
            user_id="user-local",
        )
    assert repo.memory_items.created == [] and repo.memory_items.archived == []
