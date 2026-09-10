from __future__ import annotations

from typing import Literal

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
