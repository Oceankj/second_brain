import asyncio
import json
import sqlite3
import urllib.request

import pytest

from personal_agent_memory.providers.embeddings import (
    CloudflareEmbeddingProvider,
    OllamaEmbeddingProvider,
)
from personal_agent_memory.providers.summaries import CloudflareSummaryProvider
from personal_agent_memory.providers.usage import ledger_path, usage_run, usage_stage


def rows(table):
    with sqlite3.connect(ledger_path()) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(f"select * from {table}")]


def respond(monkeypatch, body):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            return json.dumps(body).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Response())


def provider():
    return CloudflareSummaryProvider(account_id="private-account", api_token="private-secret")


@pytest.mark.anyio
async def test_dry_run_keeps_provider_usage_even_if_later_validation_fails(monkeypatch):
    respond(
        monkeypatch,
        {
            "result": {
                "response": "invalid plan but billable",
                "usage": {"prompt_tokens": 123, "completion_tokens": 45},
            }
        },
    )
    with pytest.raises(ValueError):
        with usage_run("candidate_review", dry_run=True) as run_id:
            with usage_stage("candidate_plan"):
                await provider().summarize(
                    system_prompt="private prompt", user_prompt="private note"
                )
            raise ValueError("private validation error")
    call = rows("model_calls")[0]
    assert (call["input_tokens"], call["output_tokens"], call["total_tokens"]) == (123, 45, 168)
    assert call["total_tokens_source"] == "derived"
    assert call["usage_source"] == "provider" and call["run_id"] == run_id
    assert call["operation"] == "candidate_plan" and call["status"] == "succeeded"
    run = rows("usage_runs")[0]
    assert run["dry_run"] == 1 and run["status"] == "failed"
    dump = json.dumps([call, run])
    for private in (
        "private-account",
        "private-secret",
        "private prompt",
        "private note",
        "invalid plan but billable",
        "private validation error",
    ):
        assert private not in dump


@pytest.mark.anyio
async def test_timeout_is_unknown_not_zero_and_retry_is_separate(monkeypatch):
    def timeout(*a, **k):
        raise TimeoutError("private upstream data")

    monkeypatch.setattr(urllib.request, "urlopen", timeout)
    p = provider()
    with usage_run("daily_diary", dry_run=True):
        with pytest.raises(TimeoutError):
            await p.summarize(system_prompt="same version", user_prompt="note")
        respond(
            monkeypatch,
            {
                "response": "ok",
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 2,
                    "total_tokens": 14,
                },
            },
        )
        await p.summarize(system_prompt="same version", user_prompt="note")
    failed, succeeded = rows("model_calls")
    assert failed["status"] == "failed" and failed["usage_source"] == "unknown"
    assert failed["input_tokens"] is None and failed["output_tokens"] is None
    assert succeeded["total_tokens"] == 14 and succeeded["total_tokens_source"] == "provider"
    assert failed["call_id"] != succeeded["call_id"]
    assert failed["prompt_hash"] == succeeded["prompt_hash"]


@pytest.mark.anyio
async def test_response_validation_failure_still_keeps_reported_tokens(monkeypatch):
    respond(monkeypatch, {"result": {"response": None, "usage": {"prompt_tokens": 10}}})
    with pytest.raises(RuntimeError):
        await provider().summarize(system_prompt="prompt", user_prompt="note")
    call = rows("model_calls")[0]
    assert call["input_tokens"] == 10 and call["status"] == "failed"
    assert call["output_tokens"] is None


@pytest.mark.anyio
async def test_embedding_unknown_and_ollama_reported_counts(monkeypatch):
    respond(monkeypatch, {"result": {"data": [[0.1, 0.2]]}})
    await CloudflareEmbeddingProvider(account_id="a", api_token="b", dimension=2).embed_text("text")
    respond(monkeypatch, {"embeddings": [[0.1, 0.2]], "prompt_eval_count": 7})
    await OllamaEmbeddingProvider(dimension=2).embed_text("text")
    cloudflare, ollama = rows("model_calls")
    assert cloudflare["usage_source"] == "unknown" and cloudflare["input_tokens"] is None
    assert ollama["input_tokens"] == 7 and ollama["usage_source"] == "provider"
    assert ollama["output_tokens"] is None


@pytest.mark.anyio
async def test_concurrent_runs_do_not_mix_context(monkeypatch):
    respond(monkeypatch, {"response": "ok", "usage": {"prompt_tokens": 1}})
    p = provider()

    async def run(name):
        with usage_run(name, dry_run=True) as run_id:
            await p.summarize(system_prompt=name, user_prompt="note")
            return run_id

    ids = await asyncio.gather(run("one"), run("two"))
    assert {r["run_id"] for r in rows("model_calls")} == set(ids)
    assert all(r["status"] == "succeeded" for r in rows("usage_runs"))
