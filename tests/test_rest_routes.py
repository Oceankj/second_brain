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


@pytest.mark.anyio
async def test_health_is_available_when_rest_api_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rest,
        "get_settings",
        lambda: Settings(
            database_url="postgresql://example",
            rest_api_enabled=False,
        ),
    )

    response = await rest.health(make_request("/health"))

    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "ok"}


@pytest.mark.anyio
async def test_create_daily_diary_endpoint_uses_header_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service = FakeMemoryService()
    monkeypatch.setattr(
        rest,
        "get_settings",
        lambda: Settings(
            database_url="postgresql://example",
            rest_api_enabled=True,
        ),
    )
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


def make_request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
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
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in headers.items()
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
