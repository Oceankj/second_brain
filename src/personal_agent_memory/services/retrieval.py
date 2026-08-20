from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.tool_schemas import GetContextInput
from personal_agent_memory.utils.serialization import (
    build_compact_context,
    serialize_context_item,
    truncate_text,
)


class RetrievalService:
    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider

    async def get_context(self, payload: GetContextInput) -> dict[str, Any]:
        query_embedding = await self.embedding_provider.embed_text(payload.input)
        rows = await self.repository.memory_chunks.search(
            query_embedding=query_embedding,
            memory_types=list(payload.memory_types),
            limit=payload.limit * 3,
        )

        ranked_items = self._rank_chunk_rows(
            rows,
            limit=payload.limit,
            include_chunks=payload.include_chunks,
        )
        item_ids = [item["id"] for item in ranked_items]

        await self._log_retrieval_events(item_ids, payload)

        link_map = (
            await self.repository.memory_links.load_for_items(item_ids)
            if payload.include_links
            else {}
        )
        serialized_items = [
            serialize_context_item(
                item,
                include_chunks=payload.include_chunks,
                links=link_map.get(item["id"]),
            )
            for item in ranked_items
        ]

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
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def _rank_chunk_rows(
        self,
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
