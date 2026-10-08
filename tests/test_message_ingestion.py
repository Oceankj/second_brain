from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from personal_agent_memory.contracts.memory import IngestMessagesData
from personal_agent_memory.services.memory.message_ingestion import (
    InvalidMessageBatch,
    MessageConflict,
    ingest_messages,
)


def message(key, role="user", parent=None, **extra):
    return dict(
        source_message_id=key,
        role=role,
        body=f"Content {key}",
        timestamp="2026-10-01T10:00:00Z",
        ingest_reason="decision",
        reply_to_message_id=parent,
        **extra,
    )


def payload(*messages, **extra):
    return IngestMessagesData(source="test", session_id="session", messages=list(messages), **extra)


class Store:
    def __init__(self):
        self.rows = []
        self.links = []
        self.memory_items = SimpleNamespace(create=self.create, find_source=self.find)
        self.memory_links = SimpleNamespace(create=self.link)
        self.memory_chunks = SimpleNamespace(create=AsyncMock())
        self.memory_item_events = SimpleNamespace(create=AsyncMock())
        self.tags = SimpleNamespace(upsert=AsyncMock())
        self.memory_item_tags = SimpleNamespace(attach=AsyncMock())

    @asynccontextmanager
    async def transaction(self):
        rows, links = deepcopy(self.rows), deepcopy(self.links)
        try:
            yield SimpleNamespace(execute=AsyncMock())
        except Exception:
            self.rows, self.links = rows, links
            raise

    async def create(self, **kwargs):
        row = dict(
            kwargs,
            id=str(len(self.rows)),
            type=kwargs["item_type"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.rows.append(row)
        return row

    async def find(self, *, user_id, source, session_id, message_id):
        return next(
            (
                r
                for r in self.rows
                if (r["user_id"], r["source"], r["session_id"], r["source_message_id"])
                == (user_id, source, session_id, message_id)
            ),
            None,
        )

    async def link(self, **kwargs):
        if any(all(row[k] == v for k, v in kwargs.items()) for row in self.links):
            return None
        row = dict(kwargs, id=str(len(self.links)), created_at=datetime.now(UTC))
        self.links.append(row)
        return row


def setup():
    repo = Store()
    service = SimpleNamespace(
        repository=repo,
        max_chunk_chars=1000,
        chunk_overlap_chars=0,
        embedding_provider=SimpleNamespace(embed_text=AsyncMock(return_value=[1.0])),
    )
    return service, repo


@pytest.mark.anyio
async def test_roles_reverse_order_batch_and_idempotency():
    service, repo = setup()
    p = payload(
        message("u2", parent="a1", content_kinds=["thought", "intention"]),
        message("a1", "assistant", "u1"),
        message("u1"),
    )
    first = await ingest_messages(service, p, user_id="alice")
    second = await ingest_messages(service, p, user_id="alice")
    assert first["created_count"] == 3 and second["created_count"] == 0
    assert len(repo.links) == 2
    assert [r["role"] for r in repo.rows] == ["user", "assistant", "user"]
    assert first["candidate_items"][0]["content_kinds"] == ["intention", "thought"]
    assert service.embedding_provider.embed_text.await_count == 3


@pytest.mark.anyio
async def test_existing_parent_and_foreign_owner():
    service, repo = setup()
    await ingest_messages(service, payload(message("a1", "assistant")), user_id="alice")
    with pytest.raises(InvalidMessageBatch):
        await ingest_messages(service, payload(message("u2", parent="a1")), user_id="bob")
    assert len(repo.rows) == 1
    await ingest_messages(service, payload(message("u2", parent="a1")), user_id="alice")
    assert len(repo.links) == 1


@pytest.mark.anyio
async def test_conflicting_retry_does_not_overwrite():
    service, repo = setup()
    p = payload(message("u1"))
    await ingest_messages(service, p, user_id="alice")
    p.messages[0].body = "Changed"
    with pytest.raises(MessageConflict):
        await ingest_messages(service, p, user_id="alice")
    assert repo.rows[0]["body"] == "Content u1"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "messages",
    [
        [message("good"), message("bad", parent="absent")],
        [message("a", parent="b"), message("b", parent="a")],
        [message("a", sequence=3), message("b", parent="a", sequence=2)],
    ],
)
async def test_invalid_batch_rolls_back_all_rows(messages):
    service, repo = setup()
    with pytest.raises(InvalidMessageBatch):
        await ingest_messages(service, payload(*messages), user_id="alice")
    assert repo.rows == [] and repo.links == []


def test_contract_rejects_turn_id_and_duplicate_messages():
    with pytest.raises(ValidationError):
        payload(message("u1"), turn_id="unnecessary")
    with pytest.raises(ValidationError):
        payload(message("u1"), message("u1"))


@pytest.mark.anyio
async def test_reply_context_preserves_role_and_links_in_diary_prompt():
    from datetime import date

    from personal_agent_memory.services.memory.daily_diary import (
        build_daily_diary_prompt,
        load_reply_context,
    )

    source = dict(
        id="u2",
        type="note",
        title="Yes",
        body="好，就這樣做。",
        status="candidate",
        role="user",
        source_message_id="u2",
        ingest_reason="decision",
    )
    parent = dict(id="a1", role="assistant", body="建議使用方案 A。")
    repo = SimpleNamespace(
        consolidation=SimpleNamespace(reply_context=AsyncMock(return_value=[parent])),
        memory_links=SimpleNamespace(
            load_for_items=AsyncMock(
                return_value={
                    "u2": {"outgoing_links": [{"target_id": "a1", "link_type": "replies_to"}]}
                }
            )
        ),
    )
    context = await load_reply_context(repo, [source], user_id="alice")
    prompt = build_daily_diary_prompt(
        diary_date=date(2026, 10, 1),
        source_items=[source],
        source_max_chars=5000,
        reply_context=context,
    )
    assert "reply_to_ids: ['a1']" in prompt
    assert '"role": "assistant"' in prompt
    assert "not additional events for this day" in prompt
    with pytest.raises(ValueError, match="refusing to truncate"):
        build_daily_diary_prompt(
            diary_date=date(2026, 10, 1), source_items=[source], source_max_chars=10
        )


@pytest.mark.anyio
async def test_rest_messages_authentication_and_conflicts(monkeypatch):
    import httpx

    from personal_agent_memory.server.adapters import rest
    from personal_agent_memory.services.users import AuthenticationError

    service = SimpleNamespace(ingest_messages=AsyncMock(return_value={"status": "accepted"}))
    monkeypatch.setattr(rest, "get_memory_service", lambda: service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=rest.app), base_url="http://test"
    ) as client:
        data = payload(message("u1")).model_dump(mode="json")
        response = await client.post(
            "/memory/messages",
            json={**data, "token": "spoofed"},
            headers={"Authorization": "Bearer actual"},
        )
        assert response.status_code == 200
        assert service.ingest_messages.call_args.args[0].token == "actual"
        for exception, code in [
            (AuthenticationError("bad"), 401),
            (MessageConflict("changed"), 409),
            (InvalidMessageBatch("missing"), 422),
        ]:
            service.ingest_messages.side_effect = exception
            response = await client.post(
                "/memory/messages", json=data, headers={"Authorization": "Bearer actual"}
            )
            assert response.status_code == code


def test_explicit_role_controls_receipt_filter_without_parsing_user_quotes():
    from personal_agent_memory.services.memory.daily_diary import diary_evidence_body

    receipt = "已寫入個人MEMORY.md（Preferences）＋ second-brain MCP。"
    assert diary_evidence_body(receipt, role="assistant") == ""
    quote = "Here is a quote:\n\nAssistant:\n" + receipt
    assert diary_evidence_body(quote, role="user") == quote
