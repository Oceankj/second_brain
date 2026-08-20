import asyncio
import json
import urllib.request

import pytest

from personal_agent_memory.providers.embeddings import (
    OllamaEmbeddingProvider,
    to_pgvector,
)


def test_to_pgvector_formats_vector_literal() -> None:
    assert to_pgvector([0.1, -0.2]) == "[0.10000000,-0.20000000]"


def test_ollama_embedding_provider_posts_embedding_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"embeddings": [[0.25, -0.75]]}).encode("utf-8")

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads((request.data or b"").decode("utf-8"))
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = OllamaEmbeddingProvider(
        model="qwen3-embedding:0.6b",
        dimension=2,
        base_url="http://ollama.example.test",
        timeout_seconds=3,
    )

    embedding = asyncio.run(provider.embed_text("personal memory"))

    assert embedding == [0.25, -0.75]
    assert captured == {
        "url": "http://ollama.example.test/api/embed",
        "timeout": 3,
        "payload": {
            "input": "personal memory",
            "model": "qwen3-embedding:0.6b",
        },
    }
