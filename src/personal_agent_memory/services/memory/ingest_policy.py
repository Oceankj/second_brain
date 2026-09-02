from __future__ import annotations

from dataclasses import dataclass

from personal_agent_memory.tool_schemas import IngestTurnMetadata


@dataclass(frozen=True)
class IngestPolicyDecision:
    should_ingest: bool
    reason: str | None = None


def evaluate_ingest_policy(metadata: IngestTurnMetadata) -> IngestPolicyDecision:
    return IngestPolicyDecision(should_ingest=True)
