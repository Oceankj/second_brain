import asyncio
import json
import urllib.request

import pytest

from personal_agent_memory.providers.summaries import CloudflareSummaryProvider


def test_cloudflare_summary_provider_posts_messages_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "success": True,
                    "result": {"response": "Daily diary summary."},
                    "errors": [],
                    "messages": [],
                }
            ).encode("utf-8")

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads((request.data or b"").decode("utf-8"))
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = CloudflareSummaryProvider(
        account_id="account-123",
        api_token="secret-token",
        model="@cf/meta/llama-3.1-8b-instruct-fp8",
        base_url="https://cloudflare.example.test/client/v4",
        timeout_seconds=4,
        max_tokens=900,
        temperature=0.1,
    )

    summary = asyncio.run(
        provider.summarize(
            system_prompt="Write a diary.",
            user_prompt="Summarize this day.",
        )
    )

    assert summary == "Daily diary summary."
    assert captured["url"] == (
        "https://cloudflare.example.test/client/v4/accounts/account-123"
        "/ai/run/@cf/meta/llama-3.1-8b-instruct-fp8"
    )
    assert captured["timeout"] == 4
    assert captured["payload"] == {
        "messages": [
            {"role": "system", "content": "Write a diary."},
            {"role": "user", "content": "Summarize this day."},
        ],
        "max_tokens": 900,
        "temperature": 0.1,
    }
    assert captured["headers"] == {
        "Authorization": "Bearer secret-token",
        "Content-type": "application/json",
    }
