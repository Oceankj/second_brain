from __future__ import annotations

from collections.abc import Callable
from typing import Any

from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.providers.summaries import SummaryProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.memory.daily_diary import DailyDiaryService
from personal_agent_memory.services.memory.ingestion import IngestionService
from personal_agent_memory.services.memory.markdown import MarkdownService
from personal_agent_memory.services.memory.retrieval import RetrievalConfig, RetrievalService
from personal_agent_memory.services.users import UserService
from personal_agent_memory.tool_schemas import (
    CreateDailyDiaryInput,
    GetContextInput,
    IngestTurnInput,
)


class MemoryService:
    """Facade for memory use cases shared by MCP and future adapters."""

    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        embedding_provider: EmbeddingProvider,
        summary_provider_factory: Callable[[], SummaryProvider],
        user_service: UserService,
        max_chunk_chars: int,
        chunk_overlap_chars: int,
        summary_source_max_chars: int,
        daily_diary_timezone: str,
        recent_diary_max_items: int,
        recent_diary_min_score: float,
        recent_diary_max_chars: int,
        tag_retrieval_min_score: float,
        tag_retrieval_max_tags: int,
        tag_retrieval_tag_weight: float,
        link_expansion_max_items: int,
        link_expansion_source_limit: int,
        link_expansion_source_weight: float,
    ) -> None:
        self.user_service = user_service
        self.ingestion = IngestionService(
            repository=repository,
            embedding_provider=embedding_provider,
            max_chunk_chars=max_chunk_chars,
            chunk_overlap_chars=chunk_overlap_chars,
        )
        self.retrieval = RetrievalService(
            repository=repository,
            embedding_provider=embedding_provider,
            config=RetrievalConfig(
                recent_diary_max_items=recent_diary_max_items,
                recent_diary_min_score=recent_diary_min_score,
                recent_diary_max_chars=recent_diary_max_chars,
                tag_retrieval_min_score=tag_retrieval_min_score,
                tag_retrieval_max_tags=tag_retrieval_max_tags,
                tag_retrieval_tag_weight=tag_retrieval_tag_weight,
                link_expansion_max_items=link_expansion_max_items,
                link_expansion_source_limit=link_expansion_source_limit,
                link_expansion_source_weight=link_expansion_source_weight,
            ),
        )
        self.daily_diary = DailyDiaryService(
            repository=repository,
            embedding_provider=embedding_provider,
            summary_provider_factory=summary_provider_factory,
            max_chunk_chars=max_chunk_chars,
            chunk_overlap_chars=chunk_overlap_chars,
            source_max_chars=summary_source_max_chars,
            timezone=daily_diary_timezone,
        )
        self.markdown = MarkdownService()

    async def ingest_turn(self, payload: IngestTurnInput) -> dict[str, Any]:
        user = await self.user_service.authenticate_token(payload.token)
        return await self.ingestion.ingest_turn(payload, user_id=user["id"])

    async def get_context(self, payload: GetContextInput) -> dict[str, Any]:
        user = await self.user_service.authenticate_token(payload.token)
        return await self.retrieval.get_context(payload.model_copy(update={"user_id": user["id"]}))

    async def create_daily_diary(self, payload: CreateDailyDiaryInput) -> dict[str, Any]:
        user = await self.user_service.authenticate_token(payload.token)
        return await self.daily_diary.create_daily_diary(payload, user_id=user["id"])
