from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Protocol


class EmbeddingProvider(Protocol):
    async def embed_text(self, text: str) -> list[float]:
        """Return an embedding vector for text."""


class OllamaEmbeddingProvider:
    """Embedding provider backed by Ollama's local /api/embed endpoint."""

    def __init__(
        self,
        *,
        model: str = "qwen3-embedding:0.6b",
        dimension: int | None = 1024,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not model:
            raise ValueError("model is required for OllamaEmbeddingProvider")
        if dimension is not None and dimension <= 0:
            raise ValueError("dimension must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self.model = model
        self.dimension = dimension
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def embed_text(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._embed_text_sync, text)

    def _embed_text_sync(self, text: str) -> list[float]:
        payload: dict[str, object] = {
            "model": self.model,
            "input": text,
        }

        request = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama embeddings request failed with HTTP {exc.code}: {error_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama embeddings request failed: {exc.reason}") from exc

        try:
            embedding = body["embeddings"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Ollama embeddings response did not contain an embedding") from exc

        if not isinstance(embedding, list) or not all(
            isinstance(value, int | float) for value in embedding
        ):
            raise RuntimeError("Ollama embeddings response had an invalid embedding shape")

        if self.dimension is not None and len(embedding) != self.dimension:
            raise RuntimeError(
                "Ollama embedding dimension mismatch: "
                f"expected {self.dimension}, got {len(embedding)}"
            )

        return [float(value) for value in embedding]


class CloudflareEmbeddingProvider:
    """Embedding provider backed by Cloudflare Workers AI."""

    def __init__(
        self,
        *,
        account_id: str,
        api_token: str,
        model: str = "@cf/baai/bge-large-en-v1.5",
        dimension: int | None = 1024,
        base_url: str = "https://api.cloudflare.com/client/v4",
        timeout_seconds: float = 30.0,
        pooling: str | None = None,
    ) -> None:
        if not account_id:
            raise ValueError("account_id is required for CloudflareEmbeddingProvider")
        if not api_token:
            raise ValueError("api_token is required for CloudflareEmbeddingProvider")
        if not model:
            raise ValueError("model is required for CloudflareEmbeddingProvider")
        if dimension is not None and dimension <= 0:
            raise ValueError("dimension must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if pooling is not None and pooling not in {"mean", "cls"}:
            raise ValueError("pooling must be mean or cls")

        self.account_id = account_id
        self.api_token = api_token
        self.model = model
        self.dimension = dimension
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.pooling = pooling

    async def embed_text(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._embed_text_sync, text)

    def _embed_text_sync(self, text: str) -> list[float]:
        payload: dict[str, object] = {"text": [text]}
        if self.pooling is not None:
            payload["pooling"] = self.pooling

        request = urllib.request.Request(
            f"{self.base_url}/accounts/{self.account_id}/ai/run/{self.model}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Cloudflare embeddings request failed with HTTP {exc.code}: {error_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cloudflare embeddings request failed: {exc.reason}") from exc

        if isinstance(body, dict) and body.get("success") is False:
            errors = body.get("errors")
            raise RuntimeError(f"Cloudflare embeddings request failed: {errors}")

        try:
            result = body.get("result", body)
            embedding = result["data"][0]
        except (AttributeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "Cloudflare embeddings response did not contain an embedding"
            ) from exc

        if not isinstance(embedding, list) or not all(
            isinstance(value, int | float) for value in embedding
        ):
            raise RuntimeError("Cloudflare embeddings response had an invalid embedding shape")

        if self.dimension is not None and len(embedding) != self.dimension:
            raise RuntimeError(
                "Cloudflare embedding dimension mismatch: "
                f"expected {self.dimension}, got {len(embedding)}"
            )

        return [float(value) for value in embedding]


def to_pgvector(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
