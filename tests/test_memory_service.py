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
