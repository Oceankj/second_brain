from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.tool_schemas import GetContextInput
from personal_agent_memory.utils.serialization import (
    build_compact_context,
    serialize_context_item,
    truncate_text,
)


@dataclass(frozen=True)
class RetrievalQueryPlan:
    retrieval_query: str
    query_embedding: list[float]
    recent_diaries: list[dict[str, Any]]


class RetrievalService:
    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        embedding_provider: EmbeddingProvider,
        recent_diary_max_items: int,
        recent_diary_min_score: float,
        recent_diary_max_chars: int,
        tag_retrieval_min_score: float,
        tag_retrieval_max_tags: int,
        tag_retrieval_tag_weight: float,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.recent_diary_max_items = recent_diary_max_items
        self.recent_diary_min_score = recent_diary_min_score
        self.recent_diary_max_chars = recent_diary_max_chars
        self.tag_retrieval_min_score = tag_retrieval_min_score
        self.tag_retrieval_max_tags = tag_retrieval_max_tags
        self.tag_retrieval_tag_weight = tag_retrieval_tag_weight

    async def get_context(self, payload: GetContextInput) -> dict[str, Any]:
        query_plan = await self._build_query_plan(payload)
        seed_rows = await self._search_seed_rows(payload, query_plan.query_embedding)
        ranked_items = rank_chunk_rows(
            seed_rows,
            limit=payload.limit,
            include_chunks=payload.include_chunks,
        )
        item_ids = [item["id"] for item in ranked_items]

        await self._log_retrieval_events(item_ids, payload)

        serialized_items = await self._serialize_items(
            ranked_items,
            include_chunks=payload.include_chunks,
            include_links=payload.include_links,
        )
        recent_diaries = serialize_items(
            query_plan.recent_diaries,
            include_chunks=payload.include_chunks,
            link_map={},
        )

        return build_context_response(
            payload=payload,
            serialized_items=serialized_items,
            recent_diaries=recent_diaries,
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
            max_diary_chars=self.recent_diary_max_chars,
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
        semantic_rows = await self.repository.memory_chunks.search(
            query_embedding=query_embedding,
            memory_types=list(payload.memory_types),
            limit=payload.limit * 3,
        )
        tag_rows = await self._search_tag_seed_rows(payload, query_embedding)
        return semantic_rows + tag_rows

    async def _search_tag_seed_rows(
        self,
        payload: GetContextInput,
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        if self.tag_retrieval_max_tags <= 0:
            return []

        tags = await self.repository.tags.search(
            query_embedding=query_embedding,
            limit=self.tag_retrieval_max_tags,
        )
        tag_scores = {
            tag["id"]: float(tag["score"] or 0)
            for tag in tags
            if float(tag["score"] or 0) >= self.tag_retrieval_min_score
        }
        if not tag_scores:
            return []

        return await self.repository.memory_chunks.search_by_tags(
            query_embedding=query_embedding,
            tag_scores=tag_scores,
            memory_types=list(payload.memory_types),
            tag_weight=self.tag_retrieval_tag_weight,
            limit=payload.limit * 3,
        )

    async def _serialize_items(
        self,
        items: list[dict[str, Any]],
        *,
        include_chunks: bool,
        include_links: bool,
    ) -> list[dict[str, Any]]:
        item_ids = [item["id"] for item in items]
        link_map = await self._load_link_map(item_ids, include_links=include_links)
        return serialize_items(items, include_chunks=include_chunks, link_map=link_map)

    async def _load_link_map(
        self,
        item_ids: list[str],
        *,
        include_links: bool,
    ) -> dict[str, Any]:
        if not include_links or not item_ids:
            return {}
        return await self.repository.memory_links.load_for_items(item_ids)

    async def _load_relevant_recent_diaries(
        self,
        *,
        payload: GetContextInput,
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        if not payload.diary_lookback_days or self.recent_diary_max_items <= 0:
            return []

        start_date = (datetime.now(UTC) - timedelta(days=payload.diary_lookback_days)).date()
        rows = await self.repository.memory_chunks.search_recent_diary(
            query_embedding=query_embedding,
            start_date=start_date,
            limit=self.recent_diary_max_items * 3,
        )
        relevant_rows = [
            row for row in rows if float(row["score"] or 0) >= self.recent_diary_min_score
        ]
        return rank_chunk_rows(
            relevant_rows,
            limit=self.recent_diary_max_items,
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


def rank_chunk_rows(
    rows: list[dict[str, Any]],
    *,
    limit: int,
    include_chunks: bool,
) -> list[dict[str, Any]]:
    items_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = items_by_id.setdefault(
            row["id"],
            {
                "id": row["id"],
                "type": row["type"],
                "ingest_reason": row["ingest_reason"],
                "title": row["title"],
                "body": row["body"],
                "status": row["status"],
                "event_date": row["event_date"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "score": float(row["score"] or 0),
                "matched_chunks": [],
            },
        )
        item["score"] = max(item["score"], float(row["score"] or 0))
        if include_chunks:
            item["matched_chunks"].append(
                {
                    "id": row["chunk_id"],
                    "memory_item_id": row["id"],
                    "chunk_index": row["chunk_index"],
                    "content": row["chunk_content"],
                    "token_count": row["token_count"],
                    "score": float(row["score"] or 0),
                }
            )

    return sorted(items_by_id.values(), key=lambda item: item["score"], reverse=True)[:limit]


def serialize_items(
    items: list[dict[str, Any]],
    *,
    include_chunks: bool,
    link_map: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        serialize_context_item(
            item,
            include_chunks=include_chunks,
            links=link_map.get(item["id"]),
        )
        for item in items
    ]


def build_context_response(
    *,
    payload: GetContextInput,
    serialized_items: list[dict[str, Any]],
    recent_diaries: list[dict[str, Any]],
) -> dict[str, Any]:
    compact_context, context_truncated = truncate_text(
        build_compact_context(serialized_items),
        payload.max_context_chars,
    )

    return {
        "compact_context": compact_context,
        "compact_context_char_count": len(compact_context),
        "context_truncated": context_truncated,
        "max_context_chars": payload.max_context_chars,
        "items": serialized_items,
        "searched_types": list(payload.memory_types),
        "recent_diaries": recent_diaries,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def build_retrieval_query(
    input_text: str,
    *,
    relevant_diaries: list[dict[str, Any]],
    max_diary_chars: int,
) -> str:
    if not relevant_diaries or max_diary_chars <= 0:
        return input_text

    diary_blocks = []
    remaining_chars = max_diary_chars
    for diary in relevant_diaries:
        event_date = diary.get("event_date") or "undated"
        block = f"[{event_date}] {diary['title']}\n{diary['body']}".strip()
        if not block:
            continue
        if len(block) > remaining_chars:
            block = block[:remaining_chars].rstrip()
        diary_blocks.append(block)
        remaining_chars -= len(block)
        if remaining_chars <= 0:
            break

    if not diary_blocks:
        return input_text

    return (
        f"{input_text.strip()}\n\n"
        "Relevant recent diary context:\n"
        + "\n\n---\n\n".join(diary_blocks)
    )
