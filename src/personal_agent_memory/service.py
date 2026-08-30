from __future__ import annotations

from typing import Any

from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.ingestion import IngestionService
from personal_agent_memory.services.markdown import MarkdownService
from personal_agent_memory.services.retrieval import RetrievalService
from personal_agent_memory.tool_schemas import GetContextInput, IngestTurnInput


class MemoryService:
    """Thin facade that keeps the MCP adapter independent from individual use cases."""

    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        embedding_provider: EmbeddingProvider,
        max_chunk_chars: int,
        chunk_overlap_chars: int,
        recent_diary_max_items: int,
        recent_diary_min_score: float,
        recent_diary_max_chars: int,
        tag_retrieval_min_score: float,
        tag_retrieval_max_tags: int,
        tag_retrieval_tag_weight: float,
    ) -> None:
        self.ingestion = IngestionService(
            repository=repository,
            embedding_provider=embedding_provider,
            max_chunk_chars=max_chunk_chars,
            chunk_overlap_chars=chunk_overlap_chars,
        )
        self.retrieval = RetrievalService(
            repository=repository,
            embedding_provider=embedding_provider,
            recent_diary_max_items=recent_diary_max_items,
            recent_diary_min_score=recent_diary_min_score,
            recent_diary_max_chars=recent_diary_max_chars,
            tag_retrieval_min_score=tag_retrieval_min_score,
            tag_retrieval_max_tags=tag_retrieval_max_tags,
            tag_retrieval_tag_weight=tag_retrieval_tag_weight,
        )
        self.markdown = MarkdownService()

    async def ingest_turn(self, payload: IngestTurnInput) -> dict[str, Any]:
        return await self.ingestion.ingest_turn(payload)

    async def get_context(self, payload: GetContextInput) -> dict[str, Any]:
        return await self.retrieval.get_context(payload)
