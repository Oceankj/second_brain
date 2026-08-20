from __future__ import annotations

from dataclasses import dataclass

from personal_agent_memory.tool_schemas import IngestTurnMetadata


@dataclass(frozen=True)
class IngestPolicyDecision:
    should_ingest: bool
    reason: str | None = None


def evaluate_ingest_policy(metadata: IngestTurnMetadata) -> IngestPolicyDecision:
    if metadata.skip_memory:
        return IngestPolicyDecision(
            should_ingest=False,
            reason="metadata.skip_memory=true",
        )

    if metadata.ingest_reason is None:
        return IngestPolicyDecision(
            should_ingest=False,
            reason=(
                "metadata.ingest_reason is required; use one of task_completed, "
                "explicit_memory_request, user_preference, stable_fact, decision, "
                "stable_artifact, manual_import"
            ),
        )

    return IngestPolicyDecision(should_ingest=True)
