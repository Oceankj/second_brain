from __future__ import annotations

from datetime import date as CalendarDate
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from personal_agent_memory.contracts.types import IngestReason, MemoryItemType


class GetContextData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str = Field(min_length=1)
    user_id: str = Field(
        default="0",
        min_length=1,
        description="Resolved user identity. Overwritten by server-side authentication.",
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


class GetContextInput(GetContextData):
    token: str = Field(
        min_length=1,
        description="API token used to authenticate the caller and resolve user identity.",
    )


class IngestTurnMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    source: str = Field(min_length=1)
    app: str | None = None
    session_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    ingest_reason: IngestReason


class IngestTurnData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_input: str = Field(min_length=1)
    assistant_output: str = Field(min_length=1)
    metadata: IngestTurnMetadata


class IngestTurnInput(IngestTurnData):
    token: str = Field(
        min_length=1,
        description="API token used to authenticate the caller and resolve user identity.",
    )


class CreateDailyDiaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(
        min_length=1,
        description="API token used to authenticate the caller and resolve user identity.",
    )
    date: CalendarDate | None = None
    dry_run: bool = False
    force: bool = False


class ReviewCandidatesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)
    dry_run: bool = False
    limit: int = Field(default=10, ge=1, le=50)


class SourceMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_message_id: str = Field(min_length=1)
    role: Literal["user", "assistant"]
    body: str = Field(min_length=1)
    timestamp: AwareDatetime
    sequence: int | None = Field(default=None, ge=0)
    reply_to_message_id: str | None = Field(default=None, min_length=1)
    ingest_reason: IngestReason
    tags: list[str] = Field(default_factory=list)
    content_kinds: list[Literal["event", "thought", "intention"]] = Field(default_factory=list)


class IngestMessagesData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    messages: list[SourceMessage] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_messages(self):
        ids = [message.source_message_id for message in self.messages]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate source_message_id in batch")
        return self


class IngestMessagesInput(IngestMessagesData):
    token: str = Field(min_length=1)
