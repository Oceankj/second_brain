from __future__ import annotations

import json

import pytest
from starlette.requests import Request

from personal_agent_memory.config import Settings
from personal_agent_memory.server.adapters import rest


class FakeMemoryService:
    def __init__(self) -> None:
        self.payloads = []

    async def create_daily_diary(self, payload):
        self.payloads.append(payload)
        return {
            "status": "preview",
            "created": False,
            "reason": "dry_run",
            "diary": {"title": "Daily Diary: 2026-09-08"},
            "source_items": [],
            "links": [],
            "events": [],
        }


class FakeUserService:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    async def authenticate_token(self, token: str) -> dict[str, str]:
        self.tokens.append(token)
        return {"id": "user-1"}

    async def list_users(self) -> list[dict[str, str]]:
        return [{"id": "user-1", "display_name": "Test User"}]


@pytest.mark.anyio
async def test_health_is_public() -> None:
    response = await rest.health(make_request("/health"))

    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "ok"}


@pytest.mark.anyio
async def test_admin_api_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rest,
        "get_settings",
        lambda: Settings(database_url="postgresql://example"),
    )

    response = await rest.list_users(make_request("/users"))

    assert response.status_code == 404
    assert json.loads(response.body) == {"error": "admin_api_disabled"}


@pytest.mark.anyio
async def test_admin_api_authenticates_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service = FakeUserService()
    monkeypatch.setattr(
        rest,
        "get_settings",
        lambda: Settings(
            database_url="postgresql://example",
            admin_api_enabled=True,
        ),
    )
    monkeypatch.setattr(rest, "get_user_service", lambda: fake_service)

    response = await rest.list_users(
        make_request("/users", headers={"authorization": "Bearer admin-token"})
    )

    assert response.status_code == 200
    assert fake_service.tokens == ["admin-token"]
    assert json.loads(response.body) == {"users": [{"id": "user-1", "display_name": "Test User"}]}


@pytest.mark.anyio
async def test_create_daily_diary_endpoint_uses_header_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service = FakeMemoryService()
    monkeypatch.setattr(rest, "get_memory_service", lambda: fake_service)

    request = make_json_request(
        "/maintenance/daily-diary",
        headers={"authorization": "Bearer secret-token"},
        body={"date": "2026-09-08", "dry_run": True},
    )

    response = await rest.create_daily_diary(request)

    assert response.status_code == 200
    assert json.loads(response.body)["status"] == "preview"
    assert fake_service.payloads[0].token == "secret-token"
    assert fake_service.payloads[0].date.isoformat() == "2026-09-08"
    assert fake_service.payloads[0].dry_run is True


def make_request(path: str, *, headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": raw_headers,
        }
    )


def make_json_request(
    path: str,
    *,
    headers: dict[str, str],
    body: dict[str, object],
) -> Request:
    encoded_body = json.dumps(body).encode("utf-8")
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in headers.items()
    ]
    raw_headers.append((b"content-type", b"application/json"))

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": encoded_body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": raw_headers,
        },
        receive,
    )


@pytest.mark.anyio
async def test_get_diary_reads_date_and_header_identity(monkeypatch):
    from unittest.mock import AsyncMock

    service = FakeMemoryService()
    service.get_daily_diary = AsyncMock(return_value={"diary": {"body": "A day"}})
    monkeypatch.setattr(rest, "get_memory_service", lambda: service)
    request = make_request("/diary/2026-10-01", headers={"authorization": "Bearer reader"})
    request.scope["path_params"] = {"date": "2026-10-01"}
    response = await rest.get_daily_diary(request)
    assert response.status_code == 200
    kwargs = service.get_daily_diary.call_args.kwargs
    assert kwargs["token"] == "reader"
    assert kwargs["diary_date"].isoformat() == "2026-10-01"


@pytest.mark.anyio
@pytest.mark.parametrize("outcome,status", [(None, 404), ("auth_error", 401)])
async def test_get_diary_missing_or_unauthorized(monkeypatch, outcome, status):
    from unittest.mock import AsyncMock

    from personal_agent_memory.services.users import AuthenticationError

    service = FakeMemoryService()
    service.get_daily_diary = AsyncMock(return_value=outcome)
    if outcome == "auth_error":
        service.get_daily_diary.side_effect = AuthenticationError("Invalid token")
    monkeypatch.setattr(rest, "get_memory_service", lambda: service)
    request = make_request("/diary/2026-10-01")
    request.scope["path_params"] = {"date": "2026-10-01"}
    assert (await rest.get_daily_diary(request)).status_code == status


@pytest.mark.anyio
async def test_get_diary_rejects_invalid_date():
    request = make_request("/diary/invalid")
    request.scope["path_params"] = {"date": "2026-02-30"}
    assert (await rest.get_daily_diary(request)).status_code == 400


@pytest.mark.anyio
async def test_create_diary_rejects_non_object_json():
    request = make_json_request("/maintenance/daily-diary", headers={}, body=[])
    assert (await rest.create_daily_diary(request)).status_code == 400


@pytest.mark.anyio
async def test_create_diary_validation_does_not_echo_credentials():
    request = make_json_request(
        "/maintenance/daily-diary",
        headers={"authorization": "Bearer private-secret"},
        body={"date": "invalid", "extra": "private-secret"},
    )
    response = await rest.create_daily_diary(request)
    assert response.status_code == 400
    assert b"private-secret" not in response.body


@pytest.mark.anyio
async def test_review_candidates_endpoint_uses_header_and_batch_limit(monkeypatch):
    from unittest.mock import AsyncMock

    service = FakeMemoryService()
    service.review_candidates = AsyncMock(return_value={"status": "preview"})
    monkeypatch.setattr(rest, "get_memory_service", lambda: service)
    response = await rest.review_candidates(
        make_json_request(
            "/maintenance/review-candidates",
            headers={"authorization": "Bearer caller"},
            body={"dry_run": True, "limit": 3, "token": "untrusted-body-token"},
        )
    )
    assert response.status_code == 200
    payload = service.review_candidates.await_args.args[0]
    assert payload.token == "caller" and payload.limit == 3 and payload.dry_run


@pytest.mark.anyio
@pytest.mark.parametrize("error,status", [("conflict", 409), ("invalid", 422), ("provider", 502)])
async def test_review_candidates_endpoint_reports_failures(monkeypatch, error, status):
    from unittest.mock import AsyncMock

    from personal_agent_memory.services.memory.consolidation import InvalidReview, ReviewConflict

    errors = {
        "conflict": ReviewConflict("stale"),
        "invalid": InvalidReview("missing source"),
        "provider": RuntimeError("private upstream data"),
    }
    service = FakeMemoryService()
    service.review_candidates = AsyncMock(side_effect=errors[error])
    monkeypatch.setattr(rest, "get_memory_service", lambda: service)
    response = await rest.review_candidates(
        make_json_request(
            "/maintenance/review-candidates",
            headers={"authorization": "Bearer caller"},
            body={},
        )
    )
    assert response.status_code == status
    assert b"private upstream data" not in response.body
