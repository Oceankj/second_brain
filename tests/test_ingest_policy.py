from datetime import UTC, datetime

from personal_agent_memory.services.ingest_policy import evaluate_ingest_policy
from personal_agent_memory.tool_schemas import IngestTurnMetadata


def make_metadata(**overrides: object) -> IngestTurnMetadata:
    values = {
        "timestamp": datetime.now(UTC),
        "source": "test",
    }
    values.update(overrides)
    return IngestTurnMetadata(**values)


def test_ingest_policy_requires_explicit_reason() -> None:
    decision = evaluate_ingest_policy(make_metadata())

    assert not decision.should_ingest
    assert decision.reason is not None
    assert "ingest_reason is required" in decision.reason


def test_ingest_policy_allows_supported_reason() -> None:
    decision = evaluate_ingest_policy(make_metadata(ingest_reason="decision"))

    assert decision.should_ingest
    assert decision.reason is None


def test_ingest_policy_skip_memory_wins_over_reason() -> None:
    decision = evaluate_ingest_policy(
        make_metadata(
            ingest_reason="task_completed",
            skip_memory=True,
        )
    )

    assert not decision.should_ingest
    assert decision.reason == "metadata.skip_memory=true"
