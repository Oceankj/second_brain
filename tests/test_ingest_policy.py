from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from personal_agent_memory.services.memory.ingest_policy import evaluate_ingest_policy
from personal_agent_memory.tool_schemas import IngestTurnInput, IngestTurnMetadata


def make_metadata(**overrides: object) -> IngestTurnMetadata:
    values = {
        "timestamp": datetime.now(UTC),
        "source": "test",
        "ingest_reason": "decision",
    }
    values.update(overrides)
    return IngestTurnMetadata(**values)


def test_ingest_policy_accepts_valid_metadata() -> None:
    decision = evaluate_ingest_policy(make_metadata())

    assert decision.should_ingest
    assert decision.reason is None


def test_ingest_turn_input_requires_explicit_reason() -> None:
    with pytest.raises(ValidationError):
        IngestTurnInput(
            token="test-token",
            user_input="Remember this.",
            assistant_output="Stored.",
            metadata={
                "timestamp": datetime.now(UTC),
                "source": "test",
            },
        )


def test_ingest_turn_input_rejects_unsupported_reason() -> None:
    with pytest.raises(ValidationError):
        IngestTurnInput(
            token="test-token",
            user_input="Remember this.",
            assistant_output="Stored.",
            metadata={
                "timestamp": datetime.now(UTC),
                "source": "test",
                "ingest_reason": "random_reason",
            },
        )


def test_ingest_turn_input_rejects_transport_level_skip_flag() -> None:
    with pytest.raises(ValidationError):
        IngestTurnInput(
            token="test-token",
            user_input="Remember this.",
            assistant_output="Stored.",
            metadata={
                "timestamp": datetime.now(UTC),
                "source": "test",
                "ingest_reason": "task_completed",
                "skip_memory": True,
            },
        )
