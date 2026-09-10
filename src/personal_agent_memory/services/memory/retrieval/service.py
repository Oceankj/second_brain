from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from personal_agent_memory.contracts import GetContextInput
from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.memory.retrieval.policy import (
    RetrievalConfig,
    RetrievalQueryPlan,
    build_context_response,
    build_retrieval_query,
    collect_linked_source_scores,
    link_expansion_budget,
    merge_seed_and_linked_items,
    rank_chunk_rows,
    serialize_items,
)


class RetrievalService:
    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        embedding_provider: EmbeddingProvider,
        config: RetrievalConfig,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.config = config

    async def get_context(self, payload: GetContextInput) -> dict[str, Any]:
        query_plan = await self._build_query_plan(payload)
        seed_items = await self._retrieve_seed_items(
            payload=payload,
            query_embedding=query_plan.query_embedding,
        )
        linked_items = await self._retrieve_linked_items(
            payload=payload,
            query_embedding=query_plan.query_embedding,
            seed_items=seed_items,
        )
        final_items = merge_seed_and_linked_items(
            seed_items=seed_items,
            linked_items=linked_items,
            limit=payload.limit,
            linked_limit=link_expansion_budget(
                limit=payload.limit,
                max_linked_items=self.config.link_expansion_max_items,
            ),
        )
        item_ids = [item["id"] for item in final_items]

        await self._log_retrieval_events(item_ids, payload)

        serialized_items = await self._serialize_items(
            final_items,
            include_chunks=payload.include_chunks,
        )
        recent_diaries = serialize_items(
            query_plan.recent_diaries,
            include_chunks=payload.include_chunks,
        )

        return build_context_response(
            payload=payload,
            serialized_items=serialized_items,
            recent_diaries=recent_diaries,
        )

    async def _retrieve_seed_items(
        self,
        *,
        payload: GetContextInput,
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        seed_rows = await self._search_seed_rows(payload, query_embedding)
        return rank_chunk_rows(
            seed_rows,
            limit=payload.limit,
            include_chunks=payload.include_chunks,
        )

    async def _build_query_plan(self, payload: GetContextInput) -> RetrievalQueryPlan:
        input_embedding = await self.embedding_provider.embed_text(payload.input)
        relevant_diaries = await self._load_relevant_recent_diaries(
            payload=payload,
            query_embedding=input_embedding,
        )
        retrieval_query = build_retrieval_query(
            payload.input,
            relevant_diaries=relevant_diaries,
            max_diary_chars=self.config.recent_diary_max_chars,
        )
        if retrieval_query == payload.input:
            return RetrievalQueryPlan(
                retrieval_query=payload.input,
                query_embedding=input_embedding,
                recent_diaries=relevant_diaries,
            )

        return RetrievalQueryPlan(
            retrieval_query=retrieval_query,
            query_embedding=await self.embedding_provider.embed_text(retrieval_query),
            recent_diaries=relevant_diaries,
        )

    async def _search_seed_rows(
        self,
        payload: GetContextInput,
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        semantic_rows = await self._search_semantic_seed_rows(payload, query_embedding)
        tag_rows = await self._search_tag_seed_rows(payload, query_embedding)
        return semantic_rows + tag_rows

    async def _search_semantic_seed_rows(
        self,
        payload: GetContextInput,
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        return await self.repository.memory_chunks.search(
            query_embedding=query_embedding,
            user_id=payload.user_id,
            memory_types=list(payload.memory_types),
            limit=payload.limit * 3,
        )

    async def _search_tag_seed_rows(
        self,
        payload: GetContextInput,
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        if self.config.tag_retrieval_max_tags <= 0:
            return []

        tags = await self.repository.tags.search(
            query_embedding=query_embedding,
            limit=self.config.tag_retrieval_max_tags,
        )
        tag_scores = {
            tag["id"]: float(tag["score"] or 0)
            for tag in tags
            if float(tag["score"] or 0) >= self.config.tag_retrieval_min_score
        }
        if not tag_scores:
            return []

        return await self.repository.memory_chunks.search_by_tags(
            query_embedding=query_embedding,
            user_id=payload.user_id,
            tag_scores=tag_scores,
            memory_types=list(payload.memory_types),
            tag_weight=self.config.tag_retrieval_tag_weight,
            limit=payload.limit * 3,
        )

    async def _retrieve_linked_items(
        self,
        *,
        payload: GetContextInput,
        query_embedding: list[float],
        seed_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        linked_limit = link_expansion_budget(
            limit=payload.limit,
            max_linked_items=self.config.link_expansion_max_items,
        )
        if (
            payload.link_expansion_depth <= 0
            or linked_limit <= 0
            or self.config.link_expansion_source_limit <= 0
        ):
            return []

        source_items = seed_items[: self.config.link_expansion_source_limit]
        source_ids = [item["id"] for item in source_items]
        link_map = await self.repository.memory_links.load_for_items(
            source_ids,
            user_id=payload.user_id,
        )
        linked_source_scores = collect_linked_source_scores(
            source_items=source_items,
            link_map=link_map,
        )
        if not linked_source_scores:
            return []

        linked_rows = await self.repository.memory_chunks.search_by_linked_items(
            query_embedding=query_embedding,
            user_id=payload.user_id,
            item_source_scores=linked_source_scores,
            memory_types=list(payload.memory_types),
            source_weight=self.config.link_expansion_source_weight,
            limit=linked_limit * 3,
        )
        return rank_chunk_rows(
            linked_rows,
            limit=linked_limit,
            include_chunks=payload.include_chunks,
        )

    async def _serialize_items(
        self,
        items: list[dict[str, Any]],
        *,
        include_chunks: bool,
    ) -> list[dict[str, Any]]:
        return serialize_items(items, include_chunks=include_chunks)

    async def _load_relevant_recent_diaries(
        self,
        *,
        payload: GetContextInput,
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        if not payload.diary_lookback_days or self.config.recent_diary_max_items <= 0:
            return []

        start_date = (datetime.now(UTC) - timedelta(days=payload.diary_lookback_days)).date()
        rows = await self.repository.memory_chunks.search_recent_diary(
            query_embedding=query_embedding,
            user_id=payload.user_id,
            start_date=start_date,
            limit=self.config.recent_diary_max_items * 3,
        )
        relevant_rows = [
            row for row in rows if float(row["score"] or 0) >= self.config.recent_diary_min_score
        ]
        return rank_chunk_rows(
            relevant_rows,
            limit=self.config.recent_diary_max_items,
            include_chunks=True,
        )

    async def _log_retrieval_events(
        self,
        item_ids: list[str],
        payload: GetContextInput,
    ) -> None:
        for item_id in item_ids:
            await self.repository.memory_item_events.create(
                memory_item_id=item_id,
                event_type="retrieved",
                source="personal-agent-memory",
                session_id=payload.session_id,
                metadata={
                    "user_id": payload.user_id,
                    "query": payload.input,
                },
            )
