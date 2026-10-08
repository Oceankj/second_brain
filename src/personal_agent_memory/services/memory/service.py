from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from personal_agent_memory.contracts import (
    CreateDailyDiaryInput,
    GetContextInput,
    IngestTurnInput,
)
from personal_agent_memory.contracts.memory import (
    GetContextData,
    IngestMessagesData,
    IngestMessagesInput,
    IngestTurnData,
    ReviewCandidatesInput,
)
from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.providers.summaries import SummaryProvider
from personal_agent_memory.providers.usage import usage_run
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.memory.consolidation import CandidateReviewService
from personal_agent_memory.services.memory.daily_diary import DailyDiaryService
from personal_agent_memory.services.memory.ingestion import IngestionService
from personal_agent_memory.services.memory.markdown import MarkdownService
from personal_agent_memory.services.memory.message_ingestion import ingest_messages
from personal_agent_memory.services.memory.retrieval import RetrievalConfig, RetrievalService
from personal_agent_memory.services.users import UserService
from personal_agent_memory.utils.serialization import serialize_item, serialize_link


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
        return await self.ingest_turn_as_user(payload, user_id=user["id"])

    async def ingest_messages(self, payload: IngestMessagesInput) -> dict[str, Any]:
        user = await self.user_service.authenticate_token(payload.token)
        return await self.ingest_messages_as_user(payload, user_id=user["id"])

    async def ingest_messages_as_user(self, payload: IngestMessagesData, *, user_id: str) -> dict:
        if not user_id:
            raise ValueError("Missing authenticated user identity")
        with usage_run("ingest_messages") as run_id:
            result = await ingest_messages(self.ingestion, payload, user_id=user_id)
            return {**result, "usage_run_id": run_id}

    async def get_context(self, payload: GetContextInput) -> dict[str, Any]:
        user = await self.user_service.authenticate_token(payload.token)
        return await self.get_context_as_user(payload, user_id=user["id"])

    async def ingest_turn_as_user(self, payload: IngestTurnData, *, user_id: str) -> dict[str, Any]:
        """Internal entry point; callers must supply an authenticated identity."""
        if not user_id:
            raise ValueError("Missing authenticated user identity")
        with usage_run("ingest_turn"):
            return await self.ingestion.ingest_turn(payload, user_id=user_id)

    async def get_context_as_user(self, payload: GetContextData, *, user_id: str) -> dict[str, Any]:
        """Internal entry point; never trust a user_id from the payload."""
        if not user_id:
            raise ValueError("Missing authenticated user identity")
        with usage_run("get_context"):
            return await self.retrieval.get_context(payload.model_copy(update={"user_id": user_id}))

    async def create_daily_diary(self, payload: CreateDailyDiaryInput) -> dict[str, Any]:
        user = await self.user_service.authenticate_token(payload.token)
        with usage_run("daily_diary", dry_run=payload.dry_run) as run_id:
            result = await self.daily_diary.create_daily_diary(payload, user_id=user["id"])
            return {**result, "usage_run_id": run_id}

    async def review_candidates(self, payload: ReviewCandidatesInput) -> dict[str, Any]:
        user = await self.user_service.authenticate_token(payload.token)
        with usage_run("candidate_review", dry_run=payload.dry_run) as run_id:
            result = await CandidateReviewService(self.daily_diary).review(
                payload, user_id=user["id"]
            )
            return {**result, "usage_run_id": run_id}

    async def get_daily_diary(self, *, token: str, diary_date: date) -> dict[str, Any] | None:
        user = await self.user_service.authenticate_token(token)
        repository = self.daily_diary.repository
        diary = await repository.memory_items.find_diary_by_date(
            user_id=user["id"],
            event_date=diary_date.isoformat(),
        )
        if diary is None:
            return None
        links = await repository.memory_links.load_for_items([diary["id"]], user_id=user["id"])
        return {
            "diary": serialize_item(diary),
            **{
                kind: [serialize_link(link) for link in values]
                for kind, values in links.get(
                    diary["id"],
                    {"outgoing_links": [], "backlinks": []},
                ).items()
            },
        }
