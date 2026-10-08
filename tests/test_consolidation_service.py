from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_daily_diary_service import (
    FakeEmbeddingProvider,
    FakeRepository,
    make_service,
    make_source_item,
)

from personal_agent_memory.contracts.memory import ReviewCandidatesInput
from personal_agent_memory.services.memory.consolidation import (
    CandidateReviewService,
    InvalidReview,
    ReviewConflict,
    validate_plan,
)


def source(item_id, day):
    item = make_source_item(item_id, "task_completed")
    item["source_date"] = date.fromisoformat(day)
    return item


def setup_review(items, notes=None):
    repo = FakeRepository(items)
    selected = items[:10]
    repo.consolidation = SimpleNamespace(
        candidates=AsyncMock(return_value=items),
        diary_sources=AsyncMock(
            side_effect=lambda **kw: [x for x in items if x["source_date"] == kw["day"]]
        ),
        lock_items=AsyncMock(return_value=deepcopy(selected)),
        copy_tags=AsyncMock(),
        replacements=AsyncMock(return_value=[]),
    )
    repo.memory_chunks.search = AsyncMock(return_value=[])
    repo.memory_links.load_for_items = AsyncMock(return_value={})
    original_create = repo.memory_items.create

    async def create(**kwargs):
        row = await original_create(**kwargs)
        row["id"] = f"new-{len(repo.memory_items.created)}"
        return row

    repo.memory_items.create = create
    plan = (
        notes
        if notes is not None
        else [
            {
                "title": "Reviewed",
                "body": "Preserved findings",
                "source_ids": [x["id"] for x in selected],
            }
        ]
    )
    summary = SimpleNamespace(
        summarize=AsyncMock(
            side_effect=[
                json.dumps({"notes": plan}),
                *["Daily findings" for _ in items],
            ]
        )
    )
    embedding = FakeEmbeddingProvider()
    diary = make_service(repo, embedding, summary)
    return CandidateReviewService(diary), repo, summary, embedding


@pytest.mark.anyio
async def test_preview_covers_backlog_original_dates_without_mutations():
    service, repo, summary, _ = setup_review(
        [
            source("old", "2026-08-29"),
            source("newer", "2026-09-30"),
        ]
    )
    result = await service.review(
        ReviewCandidatesInput(token="t", dry_run=True), user_id="user-local"
    )
    assert result["status"] == "preview"
    assert [d["date"] for d in result["diaries"]] == ["2026-08-29", "2026-09-30"]
    repo.consolidation.candidates.assert_awaited_once_with(
        user_id="user-local",
        timezone="UTC",
        limit=11,
    )
    assert repo.memory_items.created == repo.memory_items.archived == []
    assert repo.memory_chunks.created == repo.memory_links.created == []
    assert repo.memory_item_events.created == []
    assert len(summary.summarize.await_args_list) == 3
    assert '"source_id": "old"' in summary.summarize.await_args_list[1].kwargs["user_prompt"]


@pytest.mark.anyio
async def test_merge_and_split_preserve_provenance_tags_and_graph():
    a, b = source("a", "2026-08-29"), source("b", "2026-09-30")
    service, repo, _, _ = setup_review(
        [a, b],
        [
            {"title": "Merged", "body": "Shared fact", "source_ids": ["a", "b"]},
            {"title": "Focused", "body": "Separate fact", "source_ids": ["b"]},
        ],
    )
    repo.memory_links.load_for_items.return_value = {
        "a": {"backlinks": [{"source_id": "existing", "target_id": "a"}], "outgoing_links": []}
    }
    result = await service.review(ReviewCandidatesInput(token="t"), user_id="user-local")
    assert result["status"] == "accepted"
    assert len(result["notes"]) == len(result["diaries"]) == 2
    assert result["notes"][0]["event_date"] == "2026-08-29"
    assert repo.memory_items.archived == ["a", "b"]
    assert repo.consolidation.copy_tags.await_args_list[0].kwargs == {
        "source_ids": ["a", "b"],
        "target_id": "new-1",
    }
    links = {(x["source_id"], x["target_id"]) for x in repo.memory_links.created}
    assert {("new-1", "a"), ("new-1", "b"), ("new-2", "b"), ("existing", "new-1")} <= links
    created = repo.memory_item_events.created[0]
    assert created["metadata"]["source_dates"] == ["2026-08-29", "2026-09-30"]


@pytest.mark.parametrize(
    "notes",
    [
        [],
        [{"title": "x", "body": "y", "source_ids": ["unknown"]}],
        [{"title": "x", "body": "y", "source_ids": ["a"], "related_ids": ["foreign"]}],
        [{"title": "x", "body": "y", "source_ids": ["a"]}],
        [{"title": "x", "body": "y", "source_ids": ["a", "a", "b"]}],
    ],
)
def test_plan_rejects_missing_or_untrusted_sources(notes):
    with pytest.raises(InvalidReview):
        validate_plan(json.dumps({"notes": notes}), [{"id": "a"}, {"id": "b"}], [])


@pytest.mark.anyio
async def test_changed_candidate_aborts_before_writes():
    service, repo, _, _ = setup_review([source("a", "2026-08-29")])
    repo.consolidation.lock_items.return_value[0]["status"] = "archived"
    with pytest.raises(ReviewConflict):
        await service.review(ReviewCandidatesInput(token="t"), user_id="user-local")
    assert repo.memory_items.created == repo.memory_items.archived == []


@pytest.mark.anyio
async def test_provider_failure_keeps_candidates_pending():
    service, repo, summary, _ = setup_review([source("a", "2026-08-29")])
    summary.summarize.side_effect = RuntimeError("provider unavailable")
    with pytest.raises(RuntimeError):
        await service.review(ReviewCandidatesInput(token="t"), user_id="user-local")
    assert repo.memory_items.created == repo.memory_items.archived == []


@pytest.mark.anyio
async def test_oversized_candidate_is_not_silently_consumed():
    service, repo, _, _ = setup_review([source("a", "2026-08-29")])
    service.diary.source_max_chars = 1
    with pytest.raises(InvalidReview, match="Oldest candidate"):
        await service.review(ReviewCandidatesInput(token="t"), user_id="user-local")
    assert repo.memory_items.created == []


@pytest.mark.anyio
async def test_rerun_with_no_candidates_does_not_call_providers():
    service, repo, summary, embedding = setup_review([])
    result = await service.review(ReviewCandidatesInput(token="t"), user_id="user-local")
    assert result["reason"] == "no_candidates"
    summary.summarize.assert_not_awaited()
    assert embedding.texts == []


@pytest.mark.anyio
async def test_batch_limit_reports_remaining_backlog():
    items = [source(str(i), "2026-08-29") for i in range(11)]
    service, _, _, _ = setup_review(items)
    result = await service.review(
        ReviewCandidatesInput(token="t", dry_run=True), user_id="user-local"
    )
    assert result["has_more"] is True
    assert len(result["candidate_ids"]) == 10


@pytest.mark.anyio
async def test_related_active_note_is_linked_but_not_rewritten():
    service, repo, summary, _ = setup_review(
        [source("a", "2026-08-29")],
        [
            {
                "title": "Organized",
                "body": "A concrete reference",
                "source_ids": ["a"],
                "related_ids": ["related"],
            },
        ],
    )
    related = source("related", "2026-08-01")
    related.update(status="active", score=0.9)
    repo.memory_chunks.search.return_value = [related]
    repo.consolidation.lock_items.return_value.append(related)
    result = await service.review(ReviewCandidatesInput(token="t"), user_id="user-local")
    prompt = json.loads(summary.summarize.await_args_list[0].kwargs["user_prompt"])
    assert [x["id"] for x in prompt["related_notes"]] == ["related"]
    assert repo.memory_items.archived == ["a"]
    assert any(
        x["target_id"] == "related" and x["source_id"] == result["notes"][0]["id"]
        for x in repo.memory_links.created
    )


@pytest.mark.anyio
async def test_diary_changed_during_preparation_aborts_write():
    service, repo, _, _ = setup_review([source("a", "2026-08-29")])
    repo.memory_items.find_diary_by_date = AsyncMock(
        side_effect=[None, source("raced", "2026-08-29")]
    )
    with pytest.raises(ReviewConflict, match="Diary changed"):
        await service.review(ReviewCandidatesInput(token="t"), user_id="user-local")
    assert repo.memory_items.created == repo.memory_items.archived == []


def test_one_fenced_plan_is_accepted_but_ambiguous_blocks_are_not():
    raw = json.dumps({"notes": [{"title": "x", "body": "y", "source_ids": ["a"]}]})
    wrapped = "Here is the output:\n```json\n" + raw + "\n```\nEnd of output."
    assert validate_plan(wrapped, [{"id": "a", "title": "Original", "body": "Evidence"}], []).notes[
        0
    ].source_ids == ["a"]
    with pytest.raises(InvalidReview):
        validate_plan(wrapped + wrapped, [{"id": "a"}], [])
    with pytest.raises(InvalidReview, match="unknown"):
        validate_plan(wrapped, [{"id": "b"}], [])


def test_single_note_promotion_preserves_original_chinese():
    original = {"id": "a", "title": "成功連接上 ChatGPT。", "body": "已確認連線成功。"}
    raw = json.dumps({"notes": [{"title": "我了吃上", "body": "亂碼", "source_ids": ["a"]}]})
    note = validate_plan(raw, [original], []).notes[0]
    assert note.title == original["title"]
    assert note.body == original["body"]
