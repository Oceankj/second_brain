from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Protocol


class SummaryProvider(Protocol):
    async def summarize(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return a generated summary for the supplied prompts."""


class CloudflareSummaryProvider:
    """Summary provider backed by Cloudflare Workers AI text generation."""

    def __init__(
        self,
        *,
        account_id: str,
        api_token: str,
        model: str = "@cf/meta/llama-3.1-8b-instruct-fp8",
        base_url: str = "https://api.cloudflare.com/client/v4",
        timeout_seconds: float = 60.0,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> None:
        if not account_id:
            raise ValueError("account_id is required for CloudflareSummaryProvider")
        if not api_token:
            raise ValueError("api_token is required for CloudflareSummaryProvider")
        if not model:
            raise ValueError("model is required for CloudflareSummaryProvider")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if not 0 <= temperature <= 5:
            raise ValueError("temperature must be between 0 and 5")

        self.account_id = account_id
        self.api_token = api_token
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def summarize(self, *, system_prompt: str, user_prompt: str) -> str:
        return await asyncio.to_thread(
            self._summarize_sync,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    def _summarize_sync(self, *, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, object] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

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
                f"Cloudflare summary request failed with HTTP {exc.code}: {error_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cloudflare summary request failed: {exc.reason}") from exc

        if isinstance(body, dict) and body.get("success") is False:
            errors = body.get("errors")
            raise RuntimeError(f"Cloudflare summary request failed: {errors}")

        try:
            result = body.get("result", body)
            summary = result["response"]
        except (AttributeError, KeyError, TypeError) as exc:
            raise RuntimeError("Cloudflare summary response did not contain text") from exc

        if not isinstance(summary, str) or not summary.strip():
            raise RuntimeError("Cloudflare summary response had an invalid text shape")

        return summary.strip()
