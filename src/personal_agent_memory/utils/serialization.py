from __future__ import annotations

from typing import Any

from personal_agent_memory.tool_schemas import json_date, json_datetime


def serialize_item(
    item: dict[str, Any],
    tags: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
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


# TODO: Use more elegant truncation strategy.
def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False

    suffix = "\n\n[context truncated]"
    if max_chars <= len(suffix):
        return suffix[:max_chars], True

    return text[: max_chars - len(suffix)].rstrip() + suffix, True
