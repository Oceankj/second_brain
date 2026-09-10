from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryItemType = Literal["note", "diary", "profile_memory"]
MemoryItemStatus = Literal["candidate", "active", "archived"]
MemoryLinkType = Literal["references"]
IngestReason = Literal[
    "task_completed",
    "explicit_memory_request",
    "user_preference",
    "stable_fact",
    "personal_insight",
    "decision",
    "stable_artifact",
    "manual_import",
]


class GetContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str = Field(min_length=1)
    token: str = Field(
        min_length=1,
        description="API token used to authenticate the caller and resolve user identity.",
    )
    user_id: str = Field(
        default="0",
        min_length=1,
        description="Resolved user identity. Server-side auth overwrites this from token.",
    )
    session_id: str | None = None
    memory_types: list[MemoryItemType] = Field(
        default_factory=lambda: ["note", "diary", "profile_memory"]
    )
    diary_lookback_days: int | None = Field(default=None, ge=0, le=7)
    limit: int = Field(default=10, ge=1, le=50)
    max_context_chars: int = Field(default=6000, ge=500, le=50000)
    link_expansion_depth: int = Field(default=1, ge=0, le=2)
    include_chunks: bool = False


class IngestTurnMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    source: str = Field(min_length=1)
    app: str | None = None
    session_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    ingest_reason: IngestReason


class IngestTurnInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(
        min_length=1,
        description="API token used to authenticate the caller and resolve user identity.",
    )
    user_input: str = Field(min_length=1)
    assistant_output: str = Field(min_length=1)
    metadata: IngestTurnMetadata


class CreateDailyDiaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(
        min_length=1,
        description="API token used to authenticate the caller and resolve user identity.",
    )
    date: date
    dry_run: bool = False
    force: bool = False


def json_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def json_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
