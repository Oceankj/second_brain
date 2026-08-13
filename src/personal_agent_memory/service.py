from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from personal_agent_memory.chunking import chunk_text
from personal_agent_memory.embeddings import EmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.schemas import (
    GetContextInput,
    IngestTurnInput,
    json_date,
    json_datetime,
)

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


class MemoryService:
    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        embedding_provider: EmbeddingProvider,
        max_chunk_chars: int,
        chunk_overlap_chars: int,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.max_chunk_chars = max_chunk_chars
        self.chunk_overlap_chars = chunk_overlap_chars

    async def ingest_turn(self, payload: IngestTurnInput) -> dict[str, Any]:
        body = build_turn_body(payload.user_input, payload.assistant_output)
        item = await self.repository.create_memory_item(
            item_type="note",
            title=make_title(payload.user_input),
            body=body,
            status="candidate",
        )

        for chunk in chunk_text(body, self.max_chunk_chars, self.chunk_overlap_chars):
            embedding = await self.embedding_provider.embed_text(chunk.content)
            await self.repository.create_chunk(
                memory_item_id=item["id"],
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                embedding=embedding,
                token_count=chunk.token_count,
            )

        tags = []
        for tag_name in normalize_tags(payload.metadata.tags):
            tag = await self.repository.upsert_tag(tag_name)
            await self.repository.attach_tag(item["id"], tag["id"])
            tags.append(serialize_tag(tag))

        links = []
        for target_title in detect_wikilinks(body):
            target = await self.repository.find_item_by_title(target_title)
            if target and target["id"] != item["id"]:
                link = await self.repository.create_link(
                    source_id=item["id"],
                    target_id=target["id"],
                    link_type="references",
                )
                if link:
                    links.append(serialize_link(link))

        created_event = await self.repository.create_event(
            memory_item_id=item["id"],
            event_type="created",
            source=payload.metadata.source,
            session_id=payload.metadata.session_id,
            metadata=payload.metadata.model_dump(mode="json"),
        )

        return {
            "status": "accepted",
            "candidate_items": [serialize_item(item, tags=tags)],
            "profile_memory_updates": [],
            "diary_material_enqueued": False,
            "tags": tags,
            "links": links,
            "events": [serialize_event(created_event)],
        }

    async def get_context(self, payload: GetContextInput) -> dict[str, Any]:
        query_embedding = await self.embedding_provider.embed_text(payload.input)
        rows = await self.repository.search_chunks(
            query_embedding=query_embedding,
            memory_types=list(payload.memory_types),
            limit=payload.limit * 3,
        )

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
            if payload.include_chunks:
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

        ranked_items = sorted(items_by_id.values(), key=lambda item: item["score"], reverse=True)[
            : payload.limit
        ]
        item_ids = [item["id"] for item in ranked_items]

        for item_id in item_ids:
            await self.repository.create_event(
                memory_item_id=item_id,
                event_type="retrieved",
                source="personal-agent-memory",
                session_id=payload.session_id,
                metadata={
                    "user_id": payload.user_id,
                    "query": payload.input,
                },
            )

        link_map = await self.repository.load_links_for_items(item_ids) if payload.include_links else {}
        serialized_items = [
            serialize_context_item(
                item,
                include_chunks=payload.include_chunks,
                links=link_map.get(item["id"]),
            )
            for item in ranked_items
        ]

        return {
            "compact_context": build_compact_context(serialized_items),
            "items": serialized_items,
            "searched_types": list(payload.memory_types),
            "generated_at": datetime.now(UTC).isoformat(),
        }


def build_turn_body(user_input: str, assistant_output: str) -> str:
    return f"User:\n{user_input.strip()}\n\nAssistant:\n{assistant_output.strip()}"


def make_title(user_input: str) -> str:
    first_line = user_input.strip().splitlines()[0].strip()
    if len(first_line) <= 80:
        return first_line
    return first_line[:77].rstrip() + "..."


def normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        name = re.sub(r"\s+", "-", tag.strip().lower())
        name = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]", "", name)
        if name and name not in seen:
            seen.add(name)
            normalized.append(name)
    return normalized


def detect_wikilinks(text: str) -> list[str]:
    links = []
    seen = set()
    for match in WIKILINK_RE.finditer(text):
        title = match.group(1).strip()
        if title and title not in seen:
            seen.add(title)
            links.append(title)
    return links


def serialize_item(item: dict[str, Any], tags: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": item["id"],
        "type": item["type"],
        "title": item["title"],
        "body": item["body"],
        "status": item["status"],
        "event_date": json_date(item.get("event_date")),
        "tags": tags or [],
        "created_at": json_datetime(item["created_at"]),
        "updated_at": json_datetime(item["updated_at"]),
    }


def serialize_context_item(
    item: dict[str, Any],
    *,
    include_chunks: bool,
    links: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, Any]:
    serialized = serialize_item(item)
    serialized["score"] = item["score"]
    serialized.pop("tags", None)
    if include_chunks:
        serialized["matched_chunks"] = item["matched_chunks"]
    if links:
        serialized["outgoing_links"] = [serialize_link(link) for link in links["outgoing_links"]]
        serialized["backlinks"] = [serialize_link(link) for link in links["backlinks"]]
    return serialized


def serialize_tag(tag: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": tag["id"],
        "name": tag["name"],
        "description": tag["description"],
        "created_at": json_datetime(tag["created_at"]),
        "updated_at": json_datetime(tag["updated_at"]),
    }


def serialize_link(link: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": link["id"],
        "source_id": link["source_id"],
        "target_id": link["target_id"],
        "link_type": link["link_type"],
        "created_at": json_datetime(link["created_at"]),
    }


def serialize_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event["id"],
        "memory_item_id": event["memory_item_id"],
        "event_type": event["event_type"],
        "source": event["source"],
        "session_id": event["session_id"],
        "metadata": event["metadata"],
        "occurred_at": json_datetime(event["occurred_at"]),
    }


def build_compact_context(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    blocks = []
    for item in items:
        blocks.append(f"[{item['type']}] {item['title']}\n{item['body']}")
    return "\n\n---\n\n".join(blocks)
