"""Local operational usage ledger, independent of memory transactions and retrieval."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from contextlib import closing, contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from uuid import uuid4

_RUN: ContextVar[dict | None] = ContextVar("usage_run", default=None)
_STAGE: ContextVar[str | None] = ContextVar("usage_stage", default=None)
_CALL: ContextVar[dict | None] = ContextVar("usage_call", default=None)


def ledger_path() -> Path:
    return Path(os.environ.get("MEMORY_USAGE_LOG_PATH", "logs/model-usage.sqlite3")).expanduser()


@contextmanager
def ledger():
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=10)) as conn, conn:
        conn.execute("""create table if not exists usage_runs (
            run_id text primary key, operation text not null, dry_run integer,
            started_at text not null, finished_at text, status text not null,
            error_type text)""")
        conn.execute("""create table if not exists model_calls (
            call_id text primary key, run_id text, provider text not null, model text not null,
            operation text not null, prompt_hash text, started_at text not null,
            elapsed_ms integer, status text not null, error_type text,
            input_tokens integer, output_tokens integer, total_tokens integer,
            usage_source text not null default 'unknown', total_tokens_source text,
            max_output_tokens integer, temperature real)""")
        yield conn


def now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def usage_run(operation: str, *, dry_run: bool | None = None):
    """Keep run outcome even when validation or a memory DB transaction fails."""
    run = {"run_id": str(uuid4()), "operation": operation, "dry_run": dry_run}
    with ledger() as conn:
        conn.execute(
            "insert into usage_runs values (?, ?, ?, ?, null, 'running', null)",
            (run["run_id"], operation, dry_run, now()),
        )
    token = _RUN.set(run)
    status, error = "succeeded", None
    try:
        yield run["run_id"]
    except BaseException as exc:
        status, error = "failed", type(exc).__name__
        raise
    finally:
        _RUN.reset(token)
        with ledger() as conn:
            conn.execute(
                "update usage_runs set status=?, error_type=?, finished_at=? where run_id=?",
                (status, error, now(), run["run_id"]),
            )


@contextmanager
def usage_stage(operation: str):
    token = _STAGE.set(operation)
    try:
        yield
    finally:
        _STAGE.reset(token)


def _count(mapping: dict, *names: str) -> int | None:
    for name in names:
        value = mapping.get(name)
        if type(value) is int and value >= 0:
            return value
    return None


def observe_usage(body: object) -> None:
    """Capture only numeric usage fields; never persist response text or credentials."""
    call = _CALL.get()
    if call is None or not isinstance(body, dict):
        return
    result = body.get("result", body)
    usage = result.get("usage") if isinstance(result, dict) else None
    if not isinstance(usage, dict):
        usage = body.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = _count(usage, "prompt_tokens", "input_tokens")
    output_tokens = _count(usage, "completion_tokens", "output_tokens")
    # Ollama reports embedding input counts at the top level.
    if input_tokens is None and call["provider"] == "ollama":
        input_tokens = _count(body, "prompt_eval_count")
    total = _count(usage, "total_tokens")
    total_source = "provider" if total is not None else "unknown"
    if total is None and input_tokens is not None and output_tokens is not None:
        total, total_source = input_tokens + output_tokens, "derived"
    call.update(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
        total_tokens_source=total_source,
        usage_source="provider"
        if any(x is not None for x in (input_tokens, output_tokens, total))
        else "unknown",
    )


def track_usage(*, provider: str, operation: str):
    """Record every synchronous provider attempt, including failures and invalid responses.

    asyncio.to_thread propagates contextvars, so concurrent runs stay independent.
    An interrupted process leaves a 'started' row with unknown usage, never a false zero.
    """

    def decorate(fn):
        @wraps(fn)
        def wrapped(self, *args, **kwargs):
            run = _RUN.get()
            call_id = str(uuid4())
            prompt = kwargs.get("system_prompt")
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest() if prompt else None
            with ledger() as conn:
                conn.execute(
                    """insert into model_calls (
                    call_id, run_id, provider, model, operation, prompt_hash, started_at, status,
                    max_output_tokens, temperature)
                    values (?, ?, ?, ?, ?, ?, ?, 'started', ?, ?)""",
                    (
                        call_id,
                        run["run_id"] if run else None,
                        provider,
                        self.model,
                        _STAGE.get() or operation,
                        prompt_hash,
                        now(),
                        getattr(self, "max_tokens", None),
                        getattr(self, "temperature", None),
                    ),
                )
            stats = {"provider": provider}
            token = _CALL.set(stats)
            started = time.monotonic()
            status, error = "succeeded", None
            try:
                return fn(self, *args, **kwargs)
            except BaseException as exc:
                status, error = "failed", type(exc).__name__
                raise
            finally:
                _CALL.reset(token)
                elapsed_ms = round((time.monotonic() - started) * 1000)
                with ledger() as conn:
                    conn.execute(
                        """update model_calls set elapsed_ms=?, status=?, error_type=?,
                        input_tokens=?, output_tokens=?, total_tokens=?, usage_source=?,
                        total_tokens_source=? where call_id=?""",
                        (
                            elapsed_ms,
                            status,
                            error,
                            stats.get("input_tokens"),
                            stats.get("output_tokens"),
                            stats.get("total_tokens"),
                            stats.get("usage_source", "unknown"),
                            stats.get("total_tokens_source", "unknown"),
                            call_id,
                        ),
                    )

        return wrapped

    return decorate
