from __future__ import annotations

from typing import Any

from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.memory.ingestion import IngestionService
from personal_agent_memory.services.memory.markdown import MarkdownService
from personal_agent_memory.services.memory.retrieval import RetrievalConfig, RetrievalService
from personal_agent_memory.services.users import UserService
from personal_agent_memory.tool_schemas import GetContextInput, IngestTurnInput


class MemoryService:
    """Facade for memory use cases shared by MCP and future adapters."""

    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        embedding_provider: EmbeddingProvider,
        user_service: UserService,
        max_chunk_chars: int,
        chunk_overlap_chars: int,
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
        self.markdown = MarkdownService()

    async def ingest_turn(self, payload: IngestTurnInput) -> dict[str, Any]:
        user = await self.user_service.authenticate_token(payload.token)
        return await self.ingestion.ingest_turn(payload, user_id=user["id"])

    async def get_context(self, payload: GetContextInput) -> dict[str, Any]:
        user = await self.user_service.authenticate_token(payload.token)
        return await self.retrieval.get_context(payload.model_copy(update={"user_id": user["id"]}))
