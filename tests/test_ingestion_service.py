from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from personal_agent_memory.contracts import IngestTurnInput
from personal_agent_memory.services.memory.ingestion import IngestionService


class FakeEmbeddingProvider:
    async def embed_text(self, text: str) -> list[float]:
        return [float(len(text))]


class FakeMemoryItems:
    def __init__(self) -> None:
        self.created = []
        self.by_title = {
            "Existing Note": {
                "id": "target-item",
                "user_id": "0",
                "type": "note",
                "ingest_reason": "stable_fact",
                "title": "Existing Note",
                "body": "Existing body",
                "status": "active",
                "event_date": None,
                "created_at": datetime(2026, 8, 29, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 29, tzinfo=UTC),
            }
        }

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        item = {
            "id": "source-item",
            "user_id": kwargs["user_id"],
            "type": kwargs["item_type"],
            "ingest_reason": kwargs["ingest_reason"],
            "title": kwargs["title"],
            "body": kwargs["body"],
            "status": kwargs["status"],
            "event_date": kwargs.get("event_date"),
            "created_at": datetime(2026, 8, 29, tzinfo=UTC),
            "updated_at": datetime(2026, 8, 29, tzinfo=UTC),
        }
        self.created.append(item)
        return item

    async def find_by_title(self, title: str, *, user_id: str) -> dict[str, Any] | None:
        return self.by_title.get(title)


class FakeMemoryChunks:
    def __init__(self) -> None:
        self.created = []

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.created.append(kwargs)
        return kwargs


class FakeTags:
    async def upsert(
        self,
        name: str,
        description: str | None = None,
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": f"tag-{name}",
            "name": name,
            "description": description,
            "created_at": datetime(2026, 8, 29, tzinfo=UTC),
            "updated_at": datetime(2026, 8, 29, tzinfo=UTC),
        }


class FakeMemoryItemTags:
    async def attach(self, memory_item_id: str, tag_id: str) -> None:
        return None


class FakeUsers:
    def __init__(self) -> None:
        self.upserted = []

    async def upsert(self, user_id: str, display_name: str | None = None) -> dict[str, Any]:
        self.upserted.append((user_id, display_name))
        return {
            "id": user_id,
            "display_name": display_name,
            "created_at": datetime(2026, 8, 29, tzinfo=UTC),
            "updated_at": datetime(2026, 8, 29, tzinfo=UTC),
        }

    async def find_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        return None

    async def set_token_hash(self, user_id: str, token_hash: str) -> dict[str, Any] | None:
        return None


class FakeMemoryLinks:
    def __init__(self) -> None:
        self.created = []

    async def create(self, **kwargs: Any) -> dict[str, Any] | None:
        link = {
            "id": "link-1",
            "source_id": kwargs["source_id"],
            "target_id": kwargs["target_id"],
            "link_type": kwargs["link_type"],
            "created_at": datetime(2026, 8, 29, tzinfo=UTC),
        }
        self.created.append(link)
        return link


class FakeMemoryItemEvents:
    def __init__(self) -> None:
        self.created = []

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        event = {
            "id": f"event-{len(self.created) + 1}",
            "memory_item_id": kwargs["memory_item_id"],
            "event_type": kwargs["event_type"],
            "source": kwargs["source"],
            "session_id": kwargs["session_id"],
            "metadata": kwargs["metadata"],
            "occurred_at": datetime(2026, 8, 29, tzinfo=UTC),
        }
        self.created.append(event)
        return event


class FakeRepository:
    def __init__(self) -> None:
        self.memory_items = FakeMemoryItems()
        self.memory_chunks = FakeMemoryChunks()
        self.tags = FakeTags()
        self.users = FakeUsers()
        self.memory_item_tags = FakeMemoryItemTags()
        self.memory_links = FakeMemoryLinks()
        self.memory_item_events = FakeMemoryItemEvents()


def make_payload() -> IngestTurnInput:
    return IngestTurnInput(
        token="test-token",
        user_input="Please remember this references [[Existing Note]].",
        assistant_output="Stored the linked note relationship.",
        metadata={
            "timestamp": datetime(2026, 8, 29, tzinfo=UTC),
            "source": "test",
            "session_id": "session-1",
            "ingest_reason": "decision",
        },
    )


@pytest.mark.anyio
async def test_ingest_turn_logs_linked_from_new_note_event_for_created_wikilink() -> None:
    repository = FakeRepository()
    service = IngestionService(
        repository=repository,
        embedding_provider=FakeEmbeddingProvider(),
        max_chunk_chars=1000,
        chunk_overlap_chars=100,
    )

    result = await service.ingest_turn(make_payload(), user_id="0")

    assert repository.memory_items.created[0]["user_id"] == "0"
    assert result["links"] == [
        {
            "id": "link-1",
            "source_id": "source-item",
            "target_id": "target-item",
            "link_type": "references",
            "created_at": "2026-08-29T00:00:00+00:00",
        }
    ]
    assert [event["event_type"] for event in result["events"]] == [
        "created",
        "linked_from_new_note",
    ]

    linked_event = repository.memory_item_events.created[1]
    assert linked_event["memory_item_id"] == "target-item"
    assert linked_event["metadata"]["link"] == {
        "id": "link-1",
        "source_id": "source-item",
        "target_id": "target-item",
        "link_type": "references",
        "target_title": "Existing Note",
    }
