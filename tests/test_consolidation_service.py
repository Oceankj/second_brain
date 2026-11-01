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
from personal_agent_memory.repository.consolidation import ConsolidationRepository
from personal_agent_memory.services.memory.consolidation import (
    REVIEW_PROMPT,
    CandidateReviewService,
    InvalidReview,
    ReviewConflict,
    evidence,
    reply_context_score,
    reply_context_weight,
    select_reply_context,
    split_oversized_body,
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
@pytest.mark.parametrize("error", [RuntimeError("unavailable"), TimeoutError("timeout")])
async def test_summary_failure_promotes_originals_with_auditable_fallback(error):
    item = source("a", "2026-08-29")
    service, repo, summary, _ = setup_review([item])
    summary.summarize.side_effect = error
    result = await service.review(ReviewCandidatesInput(token="t"), user_id="user-local")
    assert result["status"] == "accepted"
    assert result["plan_fallback_reason"] == "summary_unavailable"
    assert result["notes"][0]["body"] == item["body"]
    assert repo.memory_items.archived == ["a"]


@pytest.mark.anyio
async def test_embedding_failure_does_not_consume_candidates():
    service, repo, _, embedding = setup_review([source("a", "2026-08-29")])
    embedding.embed_text = AsyncMock(side_effect=RuntimeError("embedding unavailable"))
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


@pytest.mark.anyio
@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"notes":[{"title":"invented","body":"unsafe","source_ids":["foreign"]}]}',
        '{"notes":[{"title":"invented","body":"unsafe","source_ids":["a"],"related_ids":["foreign"]}]}',
        '{"notes":[{"title":"invented","body":"unsafe","source_ids":["a"]}]}',
    ],
)
async def test_invalid_plan_preserves_all_originals_without_generated_links(raw, dry_run):
    items = [source("a", "2026-08-29"), source("b", "2026-08-29")]
    service, repo, summary, _ = setup_review(items)
    summary.summarize.side_effect = [raw, "Daily findings", "Daily findings"]
    result = await service.review(
        ReviewCandidatesInput(token="t", dry_run=dry_run), user_id="user-local"
    )
    assert result["plan_mode"] == "verbatim_fallback"
    assert result["status"] == ("preview" if dry_run else "accepted")
    assert [(n["title"], n["body"]) for n in result["notes"]] == [
        (n["title"], n["body"]) for n in items
    ]
    if dry_run:
        assert repo.memory_items.created == repo.memory_items.archived == []
    else:
        assert repo.memory_items.archived == ["a", "b"]
        assert not any(x["target_id"] == "foreign" for x in repo.memory_links.created)
        events = [
            e
            for e in repo.memory_item_events.created
            if e["event_type"] == "created" and e["source"] == "candidate_review"
        ]
        assert len(events) == 2
        assert all(e["metadata"]["plan_mode"] == "verbatim_fallback" for e in events)


def test_reply_context_weight_plateaus_at_depth_cap() -> None:
    assert reply_context_weight(0, decay=0.9, depth_cap=5) == 1.0
    assert reply_context_weight(1, decay=0.9, depth_cap=5) == 0.9
    assert reply_context_weight(5, decay=0.9, depth_cap=5) == 0.9**5
    assert reply_context_weight(6, decay=0.9, depth_cap=5) == reply_context_weight(
        5, decay=0.9, depth_cap=5
    )
    assert reply_context_weight(20, decay=0.9, depth_cap=5) == reply_context_weight(
        5, decay=0.9, depth_cap=5
    )
    assert reply_context_score(1.0, 20, decay=0.9, depth_cap=5) == reply_context_score(
        1.0, 5, decay=0.9, depth_cap=5
    )


def _context_item(item_id: str, depth: int, body: str) -> dict:
    return {
        "id": item_id,
        "title": item_id,
        "body": body,
        "reply_depth": depth,
    }


def test_select_reply_context_ranks_relevant_far_over_irrelevant_near() -> None:
    candidate = source("cand", "2026-08-29")
    near = _context_item("near", 1, "n" * 100)
    far = _context_item("far", 10, "f" * 100)
    # Budget fits exactly one ancestor: far alone fits, both together do not.
    budget = len(
        json.dumps(
            {
                "candidates": [evidence(candidate)],
                "related_notes": [],
                "reply_context": [evidence(far)],
            },
            ensure_ascii=False,
        )
    )
    selected, dropped = select_reply_context(
        [near, far],
        candidates=[candidate],
        related=[],
        source_max_chars=budget,
        similarity_by_id={"near": 0.0, "far": 1.0},
        decay=0.9,
        depth_cap=5,
    )
    assert [item["id"] for item in selected] == ["far"]
    assert [item["id"] for item in dropped] == ["near"]


def test_select_reply_context_keeps_all_when_within_budget() -> None:
    candidate = source("cand", "2026-08-29")
    context = [_context_item("a", 1, "a" * 50), _context_item("b", 2, "b" * 50)]
    selected, dropped = select_reply_context(
        context,
        candidates=[candidate],
        related=[],
        source_max_chars=24000,
        similarity_by_id={"a": 0.5, "b": 0.5},
        decay=0.9,
        depth_cap=5,
    )
    assert selected == context
    assert dropped == []


def test_select_reply_context_returns_selected_in_original_order() -> None:
    # Ranking decides inclusion, not presentation order: the prompt must
    # keep conversation (BFS) order even when a far ancestor outranks a near one.
    candidate = source("cand", "2026-08-29")
    near = _context_item("near", 1, "n" * 100)
    mid = _context_item("mid", 2, "m" * 100)
    far = _context_item("far", 10, "f" * 100)
    budget = len(
        json.dumps(
            {
                "candidates": [evidence(candidate)],
                "related_notes": [],
                "reply_context": [evidence(near), evidence(far)],
            },
            ensure_ascii=False,
        )
    )
    selected, dropped = select_reply_context(
        [near, mid, far],
        candidates=[candidate],
        related=[],
        source_max_chars=budget,
        similarity_by_id={"near": 0.0, "mid": 0.0, "far": 1.0},
        decay=0.9,
        depth_cap=5,
    )
    assert [item["id"] for item in selected] == ["near", "far"]
    assert [item["id"] for item in dropped] == ["mid"]


class _FakeCursor:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def fetchall(self) -> list[dict]:
        return self._rows


class _FakeConnection:
    def __init__(self, parents: dict[str, str]) -> None:
        self._parents = parents

    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def execute(self, sql: str, params: tuple) -> _FakeCursor:
        frontier = params[0]
        rows = [
            {"id": self._parents[item_id], "title": self._parents[item_id], "body": "x"}
            for item_id in frontier
            if item_id in self._parents
        ]
        return _FakeCursor(rows)


@pytest.mark.anyio
async def test_reply_context_has_no_50_limit_and_reports_depth() -> None:
    from contextlib import asynccontextmanager

    parents = {f"p{i}": f"p{i + 1}" for i in range(60)}
    parents["cand"] = "p0"

    @asynccontextmanager
    async def connect():
        yield _FakeConnection(parents)

    repository = ConsolidationRepository(connect)  # type: ignore[arg-type]
    result = await repository.reply_context(user_id="user-local", item_ids=["cand"])
    assert len(result) == 61
    assert result[0]["id"] == "p0" and result[0]["reply_depth"] == 1
    assert result[-1]["id"] == "p60" and result[-1]["reply_depth"] == 61


@pytest.mark.anyio
async def test_review_trims_reply_context_by_weighted_rank() -> None:
    candidate = source("cand", "2026-08-29")
    candidate["source_message_id"] = "msg-cand"
    candidate["body"] = "Short candidate body."
    candidate["title"] = "Cand"
    candidate["reply_to_ids"] = []
    near = _context_item("near", 1, "NEAR " + "n" * 95)
    far = _context_item("far", 10, "FAR! " + "f" * 95)
    near["reply_to_ids"] = []
    far["reply_to_ids"] = []
    service, repo, summary, _ = setup_review([candidate])
    repo.consolidation.reply_context = AsyncMock(return_value=[near, far])
    repo.memory_chunks.max_similarity_by_item = AsyncMock(
        return_value={"near": 0.0, "far": 1.0}
    )
    # Budget fits the candidate plus exactly one ancestor.
    service.diary.source_max_chars = len(
        json.dumps(
            {
                "candidates": [evidence(candidate)],
                "related_notes": [],
                "reply_context": [evidence(far)],
            },
            ensure_ascii=False,
        )
    )
    result = await service.review(
        ReviewCandidatesInput(token="t", dry_run=True), user_id="user-local"
    )
    assert result["plan_mode"] == "model_validated"
    assert result["reply_context_dropped"] == 1
    assert result["reply_context_dropped_ids"] == ["near"]
    plan_prompt = summary.summarize.await_args_list[0].kwargs["user_prompt"]
    assert "FAR! " in plan_prompt
    assert "NEAR " not in plan_prompt


@pytest.mark.anyio
async def test_review_falls_back_when_prompt_still_over_budget() -> None:
    candidate = source("cand", "2026-08-29")
    candidate["body"] = "Short candidate body."
    candidate["title"] = "Cand"
    service, repo, summary, _ = setup_review([candidate])
    empty_prompt = json.dumps(
        {
            "candidates": [evidence(candidate)],
            "related_notes": [],
            "reply_context": [],
        },
        ensure_ascii=False,
    )
    proposal = json.dumps([evidence(candidate)], ensure_ascii=False)
    assert len(proposal) < len(empty_prompt)
    service.diary.source_max_chars = len(empty_prompt) - 1
    result = await service.review(
        ReviewCandidatesInput(token="t", dry_run=True), user_id="user-local"
    )
    assert result["plan_mode"] == "verbatim_fallback"
    assert result["plan_fallback_reason"] == "source_budget_exceeded"
    assert result["notes"][0]["body"] == "Short candidate body."
    assert not any(
        call.kwargs.get("system_prompt") == REVIEW_PROMPT
        for call in summary.summarize.await_args_list
    )


@pytest.mark.anyio
async def test_review_verbatim_fallback_preserves_oversized_body() -> None:
    candidate = source("big", "2026-08-29")
    candidate["body"] = "x" * 30000
    candidate["title"] = "Big Note"
    service, repo, summary, _ = setup_review([candidate])
    service.diary.source_max_chars = 50000
    summary.summarize.side_effect = [RuntimeError("provider down"), "Daily findings"]
    result = await service.review(
        ReviewCandidatesInput(token="t", dry_run=True), user_id="user-local"
    )
    assert result["plan_mode"] == "verbatim_fallback"
    assert result["plan_fallback_reason"] == "summary_unavailable"
    assert result["notes"][0]["body"] == "x" * 30000


def test_split_oversized_body_preserves_exact_content() -> None:
    body = ("A" * 400 + "\n\n" + "B" * 400 + "\n\n" + "C" * 400)
    pieces = split_oversized_body(body, max_body_chars=720)
    assert "".join(pieces) == body
    assert len(pieces) == 3
    assert all(len(piece) <= 720 for piece in pieces)
    assert pieces[0] == "A" * 400 + "\n\n"
    assert pieces[1] == "B" * 400 + "\n\n"
    assert pieces[2] == "C" * 400


def test_split_oversized_body_hard_cuts_without_boundaries() -> None:
    body = "x" * 1000
    pieces = split_oversized_body(body, max_body_chars=400)
    assert "".join(pieces) == body
    assert all(len(piece) <= 400 for piece in pieces)
    assert len(pieces) == 3


def test_split_oversized_body_returns_single_piece_when_fitting() -> None:
    assert split_oversized_body("short", max_body_chars=400) == ["short"]


def _oversized_candidate() -> dict:
    candidate = source("big", "2026-08-29")
    candidate["title"] = "Big Note"
    candidate["body"] = "A" * 400 + "\n\n" + "B" * 400 + "\n\n" + "C" * 400
    return candidate


@pytest.mark.anyio
async def test_review_splits_single_oversized_candidate_dry_run() -> None:
    candidate = _oversized_candidate()
    service, repo, summary, _ = setup_review([candidate])
    service.diary.source_max_chars = 1000
    result = await service.review(
        ReviewCandidatesInput(token="t", dry_run=True), user_id="user-local"
    )
    assert result["status"] == "preview"
    assert result["candidate_ids"] == ["big"]
    assert result["plan_mode"] == "verbatim_fallback"
    assert result["plan_fallback_reason"] == "oversized_candidate_split"
    assert result["reply_context_dropped"] == 0
    assert [n["title"] for n in result["notes"]] == [
        "Big Note (part 1/3)",
        "Big Note (part 2/3)",
        "Big Note (part 3/3)",
    ]
    # VerbatimReviewedNote strips leading/trailing whitespace, so the "\n\n"
    # separators at piece boundaries are stripped in the saved notes; joining
    # the clean paragraphs with "\n\n" reconstructs the original exactly.
    assert [n["body"] for n in result["notes"]] == ["A" * 400, "B" * 400, "C" * 400]
    assert "\n\n".join(n["body"] for n in result["notes"]) == candidate["body"]
    assert all(n["source_ids"] == ["big"] for n in result["notes"])
    assert summary.summarize.await_count == 0
    assert repo.memory_items.created == []


@pytest.mark.anyio
async def test_review_splits_single_oversized_candidate_accepted() -> None:
    candidate = _oversized_candidate()
    service, repo, summary, _ = setup_review([candidate])
    service.diary.source_max_chars = 1000
    result = await service.review(
        ReviewCandidatesInput(token="t", dry_run=False), user_id="user-local"
    )
    assert result["status"] == "accepted"
    assert result["plan_mode"] == "verbatim_fallback"
    assert result["plan_fallback_reason"] == "oversized_candidate_split"
    assert len(result["notes"]) == 3
    assert [n["body"] for n in result["notes"]] == ["A" * 400, "B" * 400, "C" * 400]
    assert "\n\n".join(n["body"] for n in result["notes"]) == candidate["body"]
    assert len(result["diaries"]) == 1
    assert repo.memory_items.archived == ["big"]
    events = [
        e
        for e in repo.memory_item_events.created
        if e["event_type"] == "created" and e["source"] == "candidate_review"
    ]
    assert len(events) == 3
    assert all(e["metadata"]["plan_mode"] == "verbatim_fallback" for e in events)
    assert all(
        e["metadata"]["plan_fallback_reason"] == "oversized_candidate_split"
        for e in events
    )
