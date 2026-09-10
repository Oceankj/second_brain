from datetime import UTC, datetime

import pytest

from personal_agent_memory.contracts import IngestReason, IngestTurnInput
from personal_agent_memory.services.memory.ingestion import (
    created_event_metadata,
    extract_memory_candidates,
    memory_type_for_reason,
)


def make_payload(ingest_reason: IngestReason) -> IngestTurnInput:
    return IngestTurnInput(
        token="test-token",
        user_input="I realized personal insights should stay as notes first.",
        assistant_output="That keeps profile memory conservative until evidence repeats.",
        metadata={
            "timestamp": datetime.now(UTC),
            "source": "test",
            "tags": ["Personal Memory", " Ingestion "],
            "ingest_reason": ingest_reason,
        },
    )


@pytest.mark.parametrize(
    ("reason", "expected_type"),
    [
        ("task_completed", "note"),
        ("explicit_memory_request", "note"),
        ("personal_insight", "note"),
        ("decision", "note"),
        ("stable_artifact", "note"),
        ("manual_import", "note"),
        ("user_preference", "note"),
        ("stable_fact", "note"),
    ],
)
def test_memory_type_for_reason_routes_deterministically(
    reason: IngestReason,
    expected_type: str,
) -> None:
    assert memory_type_for_reason(reason) == expected_type


def test_extract_memory_candidates_builds_single_candidate_from_reason() -> None:
    candidate = extract_memory_candidates(make_payload("personal_insight"))[0]

    assert candidate.item_type == "note"
    assert candidate.reason == "personal_insight"
    assert candidate.evidence_source == "user_input"
    assert candidate.tags == ["personal-memory", "ingestion"]
    assert "User:" in candidate.body
    assert "Assistant:" in candidate.body


def test_created_event_metadata_includes_candidate_provenance() -> None:
    payload = make_payload("stable_fact")
    candidate = extract_memory_candidates(payload)[0]

    metadata = created_event_metadata(payload, candidate)

    assert metadata["ingest_reason"] == "stable_fact"
    assert metadata["candidate"] == {
        "type": "note",
        "reason": "stable_fact",
        "evidence_source": "user_input",
    }


def test_user_preference_stays_note_candidate_with_reason() -> None:
    candidate = extract_memory_candidates(make_payload("user_preference"))[0]

    assert candidate.item_type == "note"
    assert candidate.reason == "user_preference"
    assert candidate.evidence_source == "user_input"
