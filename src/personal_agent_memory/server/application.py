from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from personal_agent_memory.config import Settings, load_settings
from personal_agent_memory.providers.embeddings import (
    CloudflareEmbeddingProvider,
    EmbeddingProvider,
    OllamaEmbeddingProvider,
)
from personal_agent_memory.providers.summaries import CloudflareSummaryProvider, SummaryProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.memory import MemoryService
from personal_agent_memory.services.users import UserService


class ApplicationContext:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self._repository: PostgresMemoryRepository | None = None
        self._embedding_provider: EmbeddingProvider | None = None
        self._summary_provider: SummaryProvider | None = None
        self._memory_service: MemoryService | None = None
        self._user_service: UserService | None = None
        self._started = False

    def repository(self) -> PostgresMemoryRepository:
        if self._repository is None:
            self._repository = PostgresMemoryRepository(self.settings.database_url)
        return self._repository

    def embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            self._embedding_provider = build_embedding_provider(self.settings)
        return self._embedding_provider

    def summary_provider(self) -> SummaryProvider:
        if self._summary_provider is None:
            self._summary_provider = build_summary_provider(self.settings)
        return self._summary_provider

    def user_service(self) -> UserService:
        if self._user_service is None:
            self._user_service = UserService(
                repository=self.repository(),
                default_user_token=self.settings.default_user_token,
            )
        return self._user_service

    def memory_service(self) -> MemoryService:
        if self._memory_service is None:
            settings = self.settings
            self._memory_service = MemoryService(
                repository=self.repository(),
                embedding_provider=self.embedding_provider(),
                summary_provider_factory=self.summary_provider,
                user_service=self.user_service(),
                max_chunk_chars=settings.max_chunk_chars,
                chunk_overlap_chars=settings.chunk_overlap_chars,
                summary_source_max_chars=settings.summary_source_max_chars,
                daily_diary_timezone=settings.daily_diary_timezone,
                recent_diary_max_items=settings.recent_diary_max_items,
                recent_diary_min_score=settings.recent_diary_min_score,
                recent_diary_max_chars=settings.recent_diary_max_chars,
                tag_retrieval_min_score=settings.tag_retrieval_min_score,
                tag_retrieval_max_tags=settings.tag_retrieval_max_tags,
                tag_retrieval_tag_weight=settings.tag_retrieval_tag_weight,
                link_expansion_max_items=settings.link_expansion_max_items,
                link_expansion_source_limit=settings.link_expansion_source_limit,
                link_expansion_source_weight=settings.link_expansion_source_weight,
            )
        return self._memory_service

    async def startup(self) -> None:
        if self._started:
            return

        await self.repository().open_pool(
            min_size=self.settings.database_pool_min_size,
            max_size=self.settings.database_pool_max_size,
            timeout_seconds=self.settings.database_pool_timeout_seconds,
        )
        self._started = True

    async def shutdown(self) -> None:
        if self._repository is not None:
            await self._repository.close_pool()
        self._started = False

    @asynccontextmanager
    async def lifespan(self, _server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        await self.startup()
        try:
            yield {"application_context": self}
        finally:
            await self.shutdown()


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "ollama":
        return OllamaEmbeddingProvider(
            model=settings.ollama_embedding_model,
            dimension=settings.embedding_dimension,
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    if settings.embedding_provider == "cloudflare":
        if settings.cloudflare_account_id is None:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is required for Cloudflare embeddings")
        if settings.cloudflare_api_token is None:
            raise RuntimeError("CLOUDFLARE_API_TOKEN is required for Cloudflare embeddings")
        return CloudflareEmbeddingProvider(
            account_id=settings.cloudflare_account_id,
            api_token=settings.cloudflare_api_token,
            model=settings.cloudflare_embedding_model,
            dimension=settings.embedding_dimension,
            base_url=settings.cloudflare_base_url,
            timeout_seconds=settings.cloudflare_timeout_seconds,
            pooling=settings.cloudflare_pooling,
        )
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")


def build_summary_provider(settings: Settings) -> SummaryProvider:
    if settings.summary_provider == "cloudflare":
        if settings.cloudflare_summary_account_id is None:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is required for Cloudflare summaries")
        if settings.cloudflare_summary_api_token is None:
            raise RuntimeError("CLOUDFLARE_API_TOKEN is required for Cloudflare summaries")
        return CloudflareSummaryProvider(
            account_id=settings.cloudflare_summary_account_id,
            api_token=settings.cloudflare_summary_api_token,
            model=settings.cloudflare_summary_model,
            base_url=settings.cloudflare_summary_base_url,
            timeout_seconds=settings.cloudflare_summary_timeout_seconds,
            max_tokens=settings.cloudflare_summary_max_tokens,
            temperature=settings.cloudflare_summary_temperature,
        )
    raise ValueError(f"Unsupported summary provider: {settings.summary_provider}")
