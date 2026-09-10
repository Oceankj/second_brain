from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from personal_agent_memory.contracts import GetContextInput
from personal_agent_memory.utils.serialization import (
    build_compact_context,
    serialize_context_item,
    truncate_text,
)


@dataclass(frozen=True)
class RetrievalConfig:
    recent_diary_max_items: int
    recent_diary_min_score: float
    recent_diary_max_chars: int
    tag_retrieval_min_score: float
    tag_retrieval_max_tags: int
    tag_retrieval_tag_weight: float
    link_expansion_max_items: int
    link_expansion_source_limit: int
    link_expansion_source_weight: float


@dataclass(frozen=True)
class RetrievalQueryPlan:
    retrieval_query: str
    query_embedding: list[float]
    recent_diaries: list[dict[str, Any]]


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
                "user_id": row["user_id"],
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


def link_expansion_budget(*, limit: int, max_linked_items: int) -> int:
    if limit <= 1 or max_linked_items <= 0:
        return 0
    return min(max_linked_items, max(1, limit // 3))


def collect_linked_source_scores(
    *,
    source_items: list[dict[str, Any]],
    link_map: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, float]:
    source_ids = {item["id"] for item in source_items}
    linked_scores: dict[str, float] = {}

    for item in source_items:
        source_id = item["id"]
        source_score = float(item["score"] or 0)
        links = link_map.get(source_id, {})
        linked_ids = [
            link["target_id"] for link in links.get("outgoing_links", [])
        ] + [
            link["source_id"] for link in links.get("backlinks", [])
        ]
        for linked_id in linked_ids:
            if linked_id in source_ids:
                continue
            linked_scores[linked_id] = max(linked_scores.get(linked_id, 0), source_score)

    return linked_scores


def merge_seed_and_linked_items(
    *,
    seed_items: list[dict[str, Any]],
    linked_items: list[dict[str, Any]],
    limit: int,
    linked_limit: int,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    if not linked_items or linked_limit <= 0:
        return seed_items[:limit]

    seed_ids = {item["id"] for item in seed_items}
    selected_linked = [
        item for item in linked_items if item["id"] not in seed_ids
    ][: min(linked_limit, limit)]
    if not selected_linked:
        return seed_items[:limit]

    seed_budget = max(limit - len(selected_linked), 0)
    return seed_items[:seed_budget] + selected_linked


def serialize_items(
    items: list[dict[str, Any]],
    *,
    include_chunks: bool,
) -> list[dict[str, Any]]:
    return [
        serialize_context_item(
            item,
            include_chunks=include_chunks,
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
