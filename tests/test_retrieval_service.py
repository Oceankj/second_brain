from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from personal_agent_memory.services.retrieval import RetrievalService, build_retrieval_query
from personal_agent_memory.tool_schemas import GetContextInput


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.texts = []

    async def embed_text(self, text: str) -> list[float]:
        self.texts.append(text)
        return [float(len(self.texts))]


class FakeMemoryChunks:
    def __init__(self, diary_score: float, tag_chunk_score: float) -> None:
        self.diary_score = diary_score
        self.tag_chunk_score = tag_chunk_score
        self.search_recent_diary_calls = []
        self.search_calls = []
        self.search_by_tags_calls = []

    async def search_recent_diary(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_recent_diary_calls.append(kwargs)
        return [
            make_chunk_row(
                item_id="diary-1",
                item_type="diary",
                title="Daily memory work",
                body="Discussed recent diary retrieval and context merging.",
                score=self.diary_score,
            )
        ]

    async def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_calls.append(kwargs)
        return [
            make_chunk_row(
                item_id="note-1",
                item_type="note",
                title="Recent diary layer",
                body="Use relevant recent diary to improve retrieval query context.",
                score=0.9,
            )
        ]

    async def search_by_tags(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_by_tags_calls.append(kwargs)
        tag_score = max(kwargs["tag_scores"].values())
        tag_weight = kwargs["tag_weight"]
        score = tag_score * tag_weight + self.tag_chunk_score * (1 - tag_weight)
        return [
            make_chunk_row(
                item_id="tag-note-1",
                item_type="note",
                title="Tagged retrieval note",
                body="This note is attached to a semantically related tag.",
                score=score,
            )
        ]


class FakeTags:
    def __init__(self, tag_score: float) -> None:
        self.tag_score = tag_score
        self.search_calls = []

    async def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_calls.append(kwargs)
        return [
            {
                "id": "tag-retrieval",
                "name": "retrieval",
                "description": None,
                "created_at": datetime(2026, 8, 30, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 30, tzinfo=UTC),
                "score": self.tag_score,
            }
        ]


class FakeMemoryLinks:
    async def load_for_items(self, item_ids: list[str]) -> dict[str, Any]:
        return {}


class FakeMemoryItemEvents:
    def __init__(self) -> None:
        self.created = []

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.created.append(kwargs)
        return {
            "id": f"event-{len(self.created)}",
            "memory_item_id": kwargs["memory_item_id"],
            "event_type": kwargs["event_type"],
            "source": kwargs["source"],
            "session_id": kwargs["session_id"],
            "metadata": kwargs["metadata"],
            "occurred_at": datetime(2026, 8, 30, tzinfo=UTC),
        }


class FakeRepository:
    def __init__(self, diary_score: float, tag_score: float = 0.0) -> None:
        self.memory_chunks = FakeMemoryChunks(diary_score, tag_chunk_score=0.95)
        self.tags = FakeTags(tag_score)
        self.memory_links = FakeMemoryLinks()
        self.memory_item_events = FakeMemoryItemEvents()


def make_chunk_row(
    *,
    item_id: str,
    item_type: str,
    title: str,
    body: str,
    score: float,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": item_type,
        "ingest_reason": None,
        "title": title,
        "body": body,
        "status": "active",
        "event_date": "2026-08-30" if item_type == "diary" else None,
        "created_at": datetime(2026, 8, 30, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 30, tzinfo=UTC),
        "chunk_id": f"chunk-{item_id}",
        "chunk_index": 0,
        "chunk_content": body,
        "token_count": 12,
        "score": score,
    }


def make_service(repository: FakeRepository, provider: FakeEmbeddingProvider) -> RetrievalService:
    return RetrievalService(
        repository=repository,
        embedding_provider=provider,
        recent_diary_max_items=3,
        recent_diary_min_score=0.72,
        recent_diary_max_chars=2000,
        tag_retrieval_min_score=0.72,
        tag_retrieval_max_tags=5,
        tag_retrieval_tag_weight=0.4,
    )


@pytest.mark.anyio
async def test_get_context_merges_relevant_recent_diary_before_main_search() -> None:
    repository = FakeRepository(diary_score=0.8)
    provider = FakeEmbeddingProvider()
    service = make_service(repository, provider)

    result = await service.get_context(
        GetContextInput(
            input="continue retrieval work",
            user_id="user-local",
            diary_lookback_days=2,
        )
    )

    assert len(provider.texts) == 2
    assert provider.texts[0] == "continue retrieval work"
    assert "Relevant recent diary context:" in provider.texts[1]
    assert "Daily memory work" in provider.texts[1]
    assert repository.memory_chunks.search_calls[0]["query_embedding"] == [2.0]
    assert result["recent_diaries"][0]["id"] == "diary-1"


@pytest.mark.anyio
async def test_get_context_uses_original_embedding_when_recent_diary_is_not_relevant() -> None:
    repository = FakeRepository(diary_score=0.6)
    provider = FakeEmbeddingProvider()
    service = make_service(repository, provider)

    result = await service.get_context(
        GetContextInput(
            input="continue retrieval work",
            user_id="user-local",
            diary_lookback_days=2,
        )
    )

    assert provider.texts == ["continue retrieval work"]
    assert repository.memory_chunks.search_calls[0]["query_embedding"] == [1.0]
    assert result["recent_diaries"] == []


@pytest.mark.anyio
async def test_get_context_adds_tag_candidates_to_seed_rows() -> None:
    repository = FakeRepository(diary_score=0.0, tag_score=0.9)
    provider = FakeEmbeddingProvider()
    service = make_service(repository, provider)

    result = await service.get_context(
        GetContextInput(
            input="continue retrieval work",
            user_id="user-local",
            diary_lookback_days=0,
        )
    )

    assert repository.tags.search_calls[0]["query_embedding"] == [1.0]
    assert repository.memory_chunks.search_by_tags_calls[0]["tag_scores"] == {
        "tag-retrieval": 0.9
    }
    assert repository.memory_chunks.search_by_tags_calls[0]["tag_weight"] == 0.4
    assert result["items"][0]["id"] == "tag-note-1"


def test_build_retrieval_query_respects_recent_diary_char_budget() -> None:
    query = build_retrieval_query(
        "continue retrieval work",
        relevant_diaries=[
            {
                "title": "Daily memory work",
                "body": "a" * 100,
                "event_date": "2026-08-30",
            }
        ],
        max_diary_chars=40,
    )

    assert query.startswith("continue retrieval work")
    assert "Relevant recent diary context:" in query
    assert "Daily memory work" in query
    assert len(query.split("Relevant recent diary context:\n", 1)[1]) <= 40
