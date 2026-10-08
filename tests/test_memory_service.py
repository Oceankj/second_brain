import pytest

from personal_agent_memory.services.memory import MemoryService


class FakeEmbeddingProvider:
    async def embed_text(self, text: str) -> list[float]:
        return [1.0]


class FakeUserService:
    pass


def test_memory_service_does_not_eagerly_build_summary_provider() -> None:
    def summary_provider_factory():
        raise AssertionError("summary provider should be lazy")

    MemoryService(
        repository=object(),
        embedding_provider=FakeEmbeddingProvider(),
        summary_provider_factory=summary_provider_factory,
        user_service=FakeUserService(),
        max_chunk_chars=1800,
        chunk_overlap_chars=200,
        summary_source_max_chars=24000,
        daily_diary_timezone="UTC",
        recent_diary_max_items=3,
        recent_diary_min_score=0.72,
        recent_diary_max_chars=2000,
        tag_retrieval_min_score=0.72,
        tag_retrieval_max_tags=5,
        tag_retrieval_tag_weight=0.4,
        link_expansion_max_items=3,
        link_expansion_source_limit=5,
        link_expansion_source_weight=0.4,
    )


@pytest.mark.anyio
async def test_diary_read_scopes_lookup_to_authenticated_user():
    from datetime import date
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from test_daily_diary_service import make_source_item

    item = make_source_item("diary-id", "decision")
    repository = SimpleNamespace(
        memory_items=SimpleNamespace(find_diary_by_date=AsyncMock(return_value=item)),
        memory_links=SimpleNamespace(load_for_items=AsyncMock(return_value={})),
    )
    service = object.__new__(MemoryService)
    service.user_service = SimpleNamespace(
        authenticate_token=AsyncMock(return_value={"id": "authenticated-user"})
    )
    service.daily_diary = SimpleNamespace(repository=repository)
    result = await service.get_daily_diary(token="caller-token", diary_date=date(2026, 10, 1))
    repository.memory_items.find_diary_by_date.assert_awaited_once_with(
        user_id="authenticated-user", event_date="2026-10-01",
    )
    repository.memory_links.load_for_items.assert_awaited_once_with(
        ["diary-id"], user_id="authenticated-user",
    )
    assert result["diary"]["id"] == "diary-id"
