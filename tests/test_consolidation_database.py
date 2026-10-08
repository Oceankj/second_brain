"""Real PostgreSQL checks using session-local tables, always rolled back."""

from __future__ import annotations

import json
import os
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from test_daily_diary_service import FakeEmbeddingProvider, make_service

from personal_agent_memory.contracts.memory import ReviewCandidatesInput
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.memory.consolidation import CandidateReviewService


@pytest.fixture
async def review_database():
    dsn = os.environ.get("MEMORY_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("MEMORY_TEST_DATABASE_URL is not configured")
    async with (
        await psycopg.AsyncConnection.connect(
            dsn,
            row_factory=dict_row,
            autocommit=True,
            connect_timeout=15,
            prepare_threshold=None,
        ) as conn,
        conn.transaction(force_rollback=True),
    ):
        await conn.execute("""
            create temp table memory_items (
                id uuid primary key default gen_random_uuid(), user_id text not null,
                type text not null, ingest_reason text, title text, body text,
                status text, event_date date, created_at timestamptz default now(),
                updated_at timestamptz default now());
            create temp table memory_chunks (
                id uuid default gen_random_uuid(), memory_item_id uuid references memory_items,
                chunk_index int, content text, embedding vector(2), token_count int,
                created_at timestamptz default now(), updated_at timestamptz default now());
            create temp table memory_links (
                id uuid default gen_random_uuid(), source_id uuid references memory_items,
                target_id uuid references memory_items, link_type text default 'references',
                created_at timestamptz default now(), unique(source_id,target_id,link_type),
                check(source_id <> target_id));
            create temp table memory_item_events (
                id uuid default gen_random_uuid(), memory_item_id uuid references memory_items,
                event_type text, source text, session_id text, metadata jsonb,
                occurred_at timestamptz default now());
            create temp table memory_item_tags (
                memory_item_id uuid references memory_items, tag_id uuid,
                unique(memory_item_id,tag_id));
        """)
        from pathlib import Path

        migration = Path("migrations/007_message_sources.sql").read_text()
        # All DDL targets session-local tables/functions; the outer transaction rolls back.
        migration = migration.replace(
            "function validate_memory_relation()", "function pg_temp.validate_memory_relation()"
        )
        await conn.execute(migration)
        repo = PostgresMemoryRepository(dsn)
        token = repo._transaction_connection.set(conn)
        try:
            yield conn, repo
        finally:
            repo._transaction_connection.reset(token)


async def seed(repo, *, title="source", user="alice", timestamp="2026-08-29T23:00:00Z"):
    item = await repo.memory_items.create(
        user_id=user,
        item_type="note",
        title=title,
        body="An evidenced decision.",
        status="candidate",
        ingest_reason="decision",
    )
    await repo.memory_item_events.create(
        memory_item_id=item["id"],
        event_type="created",
        source="test",
        session_id=None,
        metadata={"timestamp": timestamp},
    )
    return item


def service_for(repo, ids):
    from test_diary_preparation import classifier

    def response(**kwargs):
        if "candidates" in json.loads(kwargs["user_prompt"]):
            return json.dumps(
                {
                    "notes": [
                        {
                            "title": "Consolidated",
                            "body": "An evidenced decision.",
                            "source_ids": ids,
                            "related_ids": [],
                        }
                    ]
                }
            )
        return classifier(**kwargs)

    summary = SimpleNamespace(summarize=AsyncMock(side_effect=response))
    diary = make_service(repo, FakeEmbeddingProvider(), summary)
    diary.timezone = "America/Los_Angeles"
    return CandidateReviewService(diary)


@pytest.mark.anyio
async def test_real_review_preserves_sources_links_tags_and_is_idempotent(review_database):
    conn, repo = review_database
    first = await seed(repo)
    second = await seed(repo, title="same topic")
    foreign = await seed(repo, user="bob")
    tag_id = str(uuid4())
    await repo.memory_item_tags.attach(first["id"], tag_id)
    existing = await repo.memory_items.create(
        user_id="alice", item_type="note", title="existing", body="Related", status="active"
    )
    await repo.memory_links.create(source_id=existing["id"], target_id=first["id"])
    review = service_for(repo, [first["id"], second["id"]])
    result = await review.review(ReviewCandidatesInput(token="test"), user_id="alice")
    assert result["status"] == "accepted"
    assert len(result["notes"]) == len(result["diaries"]) == 1
    assert result["diaries"][0]["event_date"] == "2026-08-29"
    reviewed_id = result["notes"][0]["id"]
    rows = await repo.consolidation.lock_items(
        user_id="alice", item_ids=[first["id"], second["id"]]
    )
    assert {row["status"] for row in rows} == {"archived"}
    links = await repo.memory_links.load_for_items([reviewed_id], user_id="alice")
    assert any(x["source_id"] == existing["id"] for x in links[reviewed_id]["backlinks"])
    assert any(
        x["source_id"] == result["diaries"][0]["id"] for x in links[reviewed_id]["backlinks"]
    )
    cursor = await conn.execute(
        "select tag_id::text from memory_item_tags where memory_item_id=%s", (reviewed_id,)
    )
    assert (await cursor.fetchone())["tag_id"] == tag_id
    sources = await repo.consolidation.diary_sources(
        user_id="alice",
        timezone="America/Los_Angeles",
        day=date(2026, 8, 29),
        candidate_ids=[],
    )
    assert {x["id"] for x in sources} == {first["id"], second["id"]}
    again = await review.review(ReviewCandidatesInput(token="test"), user_id="alice")
    assert again["reason"] == "no_candidates"
    others = await repo.consolidation.candidates(user_id="bob", timezone="UTC", limit=10)
    assert [x["id"] for x in others] == [foreign["id"]]


@pytest.mark.anyio
async def test_real_failure_rolls_back_notes_archives_and_diary(review_database):
    _, repo = review_database
    original = await seed(repo)
    existing = await repo.memory_items.create(
        user_id="alice",
        item_type="diary",
        title="old diary",
        body="Previous text",
        status="active",
        event_date="2026-08-29",
    )
    review = service_for(repo, [original["id"]])
    original_create = repo.memory_chunks.create
    calls = 0

    async def fail_on_diary(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated chunk failure")
        return await original_create(**kwargs)

    repo.memory_chunks.create = fail_on_diary
    with pytest.raises(RuntimeError, match="simulated chunk failure"):
        await review.review(ReviewCandidatesInput(token="test"), user_id="alice")
    pending = await repo.consolidation.candidates(user_id="alice", timezone="UTC", limit=10)
    assert [x["id"] for x in pending] == [original["id"]]
    diary = await repo.memory_items.find_diary_by_date(user_id="alice", event_date="2026-08-29")
    assert diary["id"] == existing["id"]
    async with repo._connect() as conn:
        for table, expected in (
            ("memory_items", 2),
            ("memory_chunks", 0),
            ("memory_links", 0),
            ("memory_item_events", 1),
        ):
            cursor = await conn.execute(f"select count(*) as n from {table}")
            assert (await cursor.fetchone())["n"] == expected


@pytest.mark.anyio
async def test_source_timestamp_timezone_and_late_candidates_refresh_diary(review_database):
    _, repo = review_database
    original = await seed(repo, timestamp="2026-08-30T01:00:00Z")
    first = await service_for(repo, [original["id"]]).review(
        ReviewCandidatesInput(token="test"),
        user_id="alice",
    )
    late = await seed(repo, timestamp="2026-08-30T02:00:00Z")
    second = await service_for(repo, [late["id"]]).review(
        ReviewCandidatesInput(token="test"),
        user_id="alice",
    )
    assert second["diaries"][0]["event_date"] == "2026-08-29"
    assert second["diaries"][0]["id"] != first["diaries"][0]["id"]
    old = await repo.consolidation.lock_items(user_id="alice", item_ids=[first["diaries"][0]["id"]])
    assert old[0]["status"] == "archived"
    links = await repo.memory_links.load_for_items([second["diaries"][0]["id"]], user_id="alice")
    targets = {x["target_id"] for x in links[second["diaries"][0]["id"]]["outgoing_links"]}
    assert {
        original["id"],
        late["id"],
        first["notes"][0]["id"],
        second["notes"][0]["id"],
    } <= targets


@pytest.mark.anyio
async def test_real_message_import_atomic_replay_and_reply_context(review_database):
    from test_message_ingestion import message, payload

    from personal_agent_memory.services.memory.message_ingestion import (
        InvalidMessageBatch,
        MessageConflict,
        ingest_messages,
    )

    conn, repo = review_database
    service = SimpleNamespace(
        repository=repo,
        embedding_provider=FakeEmbeddingProvider(),
        max_chunk_chars=1000,
        chunk_overlap_chars=0,
    )
    p = payload(message("u1"), message("a1", "assistant", "u1"), message("u2", parent="a1"))
    result = await ingest_messages(service, p, user_id="alice")
    assert result["created_count"] == 3
    assert (await ingest_messages(service, p, user_id="alice"))["created_count"] == 0
    context = await repo.consolidation.reply_context(
        user_id="alice",
        item_ids=[result["candidate_items"][2]["id"]],
    )
    assert {x["source_message_id"] for x in context} == {"u1", "a1"}
    with pytest.raises(InvalidMessageBatch):
        await ingest_messages(
            service, payload(message("new"), message("bad", parent="missing")), user_id="alice"
        )
    assert (
        await repo.memory_items.find_source(
            user_id="alice", source="test", session_id="session", message_id="new"
        )
        is None
    )
    p.messages[0].body = "conflicting evidence"
    with pytest.raises(MessageConflict):
        await ingest_messages(service, p, user_id="alice")
    with pytest.raises(InvalidMessageBatch):
        await ingest_messages(service, payload(message("foreign", parent="a1")), user_id="bob")
    # Check the database trigger too, not only application-level ownership checks.
    foreign = await repo.memory_items.create(
        user_id="bob",
        item_type="note",
        title="foreign",
        body="foreign",
        record_kind="source",
        role="user",
    )
    with pytest.raises(psycopg.errors.RaiseException):
        async with conn.transaction():
            await repo.memory_links.create(
                source_id=foreign["id"], target_id=result["candidate_items"][0]["id"]
            )


@pytest.mark.anyio
async def test_source_metadata_survives_vector_and_tag_queries(review_database):
    from test_message_ingestion import message, payload

    from personal_agent_memory.services.memory.message_ingestion import ingest_messages
    from personal_agent_memory.services.memory.retrieval.policy import rank_chunk_rows

    conn, repo = review_database
    service = SimpleNamespace(
        repository=repo,
        embedding_provider=FakeEmbeddingProvider(),
        max_chunk_chars=1000,
        chunk_overlap_chars=0,
    )
    result = await ingest_messages(
        service, payload(message("u1", content_kinds=["thought"])), user_id="alice"
    )
    item_id = result["candidate_items"][0]["id"]
    tag_id = str(uuid4())
    await repo.memory_item_tags.attach(item_id, tag_id)
    rows = await repo.memory_chunks.search(
        query_embedding=[0.1, 0.2], user_id="alice", memory_types=["note"], limit=10
    )
    tagged = await repo.memory_chunks.search_by_tags(
        query_embedding=[0.1, 0.2],
        user_id="alice",
        tag_scores={tag_id: 1.0},
        memory_types=["note"],
        tag_weight=0.5,
        limit=10,
    )
    for found in [rows, tagged]:
        item = rank_chunk_rows(found, limit=10, include_chunks=False)[0]
        assert item["role"] == "user" and item["content_kinds"] == ["thought"]
        assert item["source_message_id"] == "u1"
