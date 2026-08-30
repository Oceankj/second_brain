from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from personal_agent_memory.tool_schemas import (
    IngestReason,
    MemoryItemStatus,
    MemoryItemType,
    json_date,
    json_datetime,
)
from personal_agent_memory.utils.text_processing import make_title, normalize_tags

FRONT_MATTER_DELIMITER = "---"
KNOWN_FRONT_MATTER_KEYS = {
    "id",
    "type",
    "title",
    "ingest_reason",
    "status",
    "event_date",
    "tags",
    "created_at",
    "updated_at",
}


@dataclass(frozen=True)
class MarkdownMemoryItem:
    item_type: MemoryItemType
    title: str
    body: str
    ingest_reason: IngestReason | None = None
    status: MemoryItemStatus = "candidate"
    event_date: str | None = None
    tags: list[str] = field(default_factory=list)
    id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        payload = {
            "type": self.item_type,
            "title": normalize_title_key(self.title),
            "body": normalize_body_for_hash(self.body),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    @property
    def identity_key(self) -> str:
        if self.id:
            return f"id:{self.id}"
        return f"title:{self.item_type}:{normalize_title_key(self.title)}"

    def to_create_kwargs(self) -> dict[str, Any]:
        return {
            "item_type": self.item_type,
            "title": self.title,
            "body": self.body,
            "status": self.status,
            "event_date": self.event_date,
            "ingest_reason": self.ingest_reason,
        }


class MarkdownService:
    """Convert memory items to and from a small Markdown front matter format."""

    def item_to_markdown(
        self,
        item: dict[str, Any],
        *,
        tags: list[str | dict[str, Any]] | None = None,
    ) -> str:
        front_matter = {
            "type": item["type"],
            "title": item["title"],
            "ingest_reason": item.get("ingest_reason"),
            "status": item.get("status", "candidate"),
            "event_date": json_date(item.get("event_date")),
            "tags": tag_names(tags if tags is not None else item.get("tags", [])),
            "id": item.get("id"),
            "created_at": json_datetime(item.get("created_at")),
            "updated_at": json_datetime(item.get("updated_at")),
        }
        body = str(item["body"]).rstrip()
        return f"{render_front_matter(front_matter)}\n\n{body}\n"

    def markdown_to_item(
        self,
        markdown: str,
        *,
        default_type: MemoryItemType = "note",
        default_status: MemoryItemStatus = "candidate",
    ) -> MarkdownMemoryItem:
        front_matter, body = split_front_matter(markdown)
        title = coerce_non_empty_string(front_matter.get("title")) or infer_title(body)
        item_type = coerce_memory_item_type(front_matter.get("type"), default_type)
        ingest_reason = coerce_ingest_reason(front_matter.get("ingest_reason"))
        status = coerce_memory_item_status(front_matter.get("status"), default_status)
        event_date = coerce_optional_string(front_matter.get("event_date"))

        return MarkdownMemoryItem(
            id=coerce_optional_string(front_matter.get("id")),
            item_type=item_type,
            title=title,
            body=body.strip("\n"),
            ingest_reason=ingest_reason,
            status=status,
            event_date=event_date,
            tags=normalize_tags(coerce_tags(front_matter.get("tags"))),
            created_at=coerce_optional_string(front_matter.get("created_at")),
            updated_at=coerce_optional_string(front_matter.get("updated_at")),
            metadata={
                key: value
                for key, value in front_matter.items()
                if key not in KNOWN_FRONT_MATTER_KEYS
            },
        )


def render_front_matter(values: dict[str, Any]) -> str:
    lines = [FRONT_MATTER_DELIMITER]
    for key, value in values.items():
        if value is None or value == []:
            continue
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append(FRONT_MATTER_DELIMITER)
    return "\n".join(lines)


def split_front_matter(markdown: str) -> tuple[dict[str, Any], str]:
    normalized = markdown.replace("\r\n", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        return {}, normalized

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONT_MATTER_DELIMITER:
            front_matter = parse_front_matter("\n".join(lines[1:index]))
            body = "\n".join(lines[index + 1 :])
            return front_matter, body.lstrip("\n")

    raise ValueError("Markdown front matter is missing a closing delimiter")


def parse_front_matter(front_matter: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in front_matter.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"Invalid front matter line: {line}")
        key, raw_value = stripped.split(":", 1)
        values[key.strip()] = parse_front_matter_value(raw_value.strip())
    return values


def parse_front_matter_value(raw_value: str) -> Any:
    if raw_value == "":
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def tag_names(tags: list[str | dict[str, Any]]) -> list[str]:
    names = []
    for tag in tags:
        if isinstance(tag, dict):
            name = tag.get("name")
        else:
            name = tag
        if isinstance(name, str):
            names.append(name)
    return normalize_tags(names)


def coerce_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    raise ValueError("Markdown tags front matter must be a string or list of strings")


def coerce_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def coerce_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def coerce_memory_item_type(value: Any, default: MemoryItemType) -> MemoryItemType:
    if value in {"note", "diary", "profile_memory"}:
        return value
    if value is None:
        return default
    raise ValueError(f"Unsupported memory item type: {value}")


def coerce_ingest_reason(value: Any) -> IngestReason | None:
    if value in {
        "task_completed",
        "explicit_memory_request",
        "user_preference",
        "stable_fact",
        "personal_insight",
        "decision",
        "stable_artifact",
        "manual_import",
    }:
        return value
    if value is None:
        return None
    raise ValueError(f"Unsupported ingest reason: {value}")


def coerce_memory_item_status(value: Any, default: MemoryItemStatus) -> MemoryItemStatus:
    if value in {"candidate", "active", "archived"}:
        return value
    if value is None:
        return default
    raise ValueError(f"Unsupported memory item status: {value}")


def infer_title(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                return make_title(heading)
        if stripped:
            return make_title(stripped)
    raise ValueError("Markdown body is empty and front matter has no title")


def normalize_title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def normalize_body_for_hash(body: str) -> str:
    lines = [re.sub(r"\s+", " ", line.strip()) for line in body.splitlines()]
    return "\n".join(line for line in lines if line)
