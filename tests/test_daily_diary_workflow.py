import io
import json
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

WORKFLOW = Path(".github/workflows/daily-diary.yml")


def run_workflow(
    monkeypatch,
    tmp_path,
    results,
    *,
    dry_run="false",
    max_batches="10",
    health_results=None,
):
    source = textwrap.dedent(WORKFLOW.read_text().split("        run: |\n", 1)[1])
    python = source.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    for key, value in {
        "MEMORY_BASE_URL": "https://memory.example",
        "MEMORY_DEFAULT_USER_TOKEN": "private-token",
        "DRY_RUN": dry_run,
        "MAX_BATCHES": max_batches,
        "BATCH_SIZE": "2",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
    }.items():
        monkeypatch.setenv(key, value)
    requests = []
    responses = iter(results)
    health_responses = iter(health_results or [{"status": "ok"}])
    health_calls = []

    def open_request(request, timeout):
        if request.data is None:
            health_calls.append((request.full_url, timeout))
            value = next(health_responses)
            if isinstance(value, Exception):
                raise value
            return io.BytesIO(json.dumps(value).encode())
        requests.append(json.loads(request.data))
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(json.dumps(value).encode())

    def opener(handler):
        assert handler().redirect_request(None, None, 302, "", {}, "https://other.example") is None
        return SimpleNamespace(open=open_request)

    monkeypatch.setattr(urllib.request, "build_opener", opener)
    monkeypatch.setattr("time.sleep", lambda _: None)
    return lambda: exec(compile(python, str(WORKFLOW), "exec"), {}), requests, health_calls


def result(status, remaining=False):
    return {
        "status": status,
        "has_more": remaining,
        "notes": [{"body": "private-note"}],
        "diaries": [{"body": "private-diary"}],
        "usage_run_id": "12345678-1234-1234-1234-123456789012",
    }


def test_preview_is_one_request_and_logs_no_content(monkeypatch, tmp_path, capsys):
    run, requests, health_calls = run_workflow(
        monkeypatch, tmp_path, [result("preview", True)], dry_run="true"
    )
    run()
    assert requests == [{"dry_run": True, "limit": 2}]
    assert health_calls == [("https://memory.example/health", 10)]
    log = capsys.readouterr().out + (tmp_path / "summary.md").read_text()
    assert "12345678-1234-1234-1234-123456789012" in log
    assert "private-note" not in log and "private-diary" not in log and "private-token" not in log


def test_save_drains_batches(monkeypatch, tmp_path):
    run, requests, _ = run_workflow(
        monkeypatch, tmp_path, [result("accepted", True), result("accepted")]
    )
    run()
    assert len(requests) == 2 and all(not r["dry_run"] for r in requests)


def test_batch_limit_stops_without_extra_post(monkeypatch, tmp_path):
    run, requests, _ = run_workflow(
        monkeypatch, tmp_path, [result("accepted", True)], max_batches="1"
    )
    run()
    assert "remaining candidates will continue" in (tmp_path / "summary.md").read_text()
    assert len(requests) == 1


def test_timeout_does_not_retry_uncertain_write(monkeypatch, tmp_path):
    run, requests, _ = run_workflow(monkeypatch, tmp_path, [TimeoutError("private failure")])
    with pytest.raises(SystemExit, match="connection error or timeout"):
        run()
    assert len(requests) == 1
    assert "completion is unknown" in (tmp_path / "summary.md").read_text()


def test_save_rejects_preview_response(monkeypatch, tmp_path):
    run, _, _ = run_workflow(monkeypatch, tmp_path, [result("preview")])
    with pytest.raises(SystemExit, match="unexpected status"):
        run()


def test_health_check_retries_before_post(monkeypatch, tmp_path):
    run, requests, health_calls = run_workflow(
        monkeypatch,
        tmp_path,
        [result("accepted")],
        health_results=[TimeoutError("cold start"), {"status": "ok"}],
    )
    run()
    assert len(health_calls) == 2
    assert len(requests) == 1


def test_health_check_failure_sends_no_post(monkeypatch, tmp_path):
    run, requests, health_calls = run_workflow(
        monkeypatch,
        tmp_path,
        [],
        health_results=[TimeoutError("cold start")] * 6,
    )
    with pytest.raises(SystemExit, match="health check failed"):
        run()
    assert len(health_calls) == 6
    assert requests == []


def test_time_budget_defers_without_another_post(monkeypatch, tmp_path, capsys):
    run, requests, _ = run_workflow(monkeypatch, tmp_path, [result("accepted", True)])
    ticks = iter([0, 0, 1801])
    monkeypatch.setattr("time.monotonic", lambda: next(ticks))
    run()
    assert len(requests) == 1
    assert "::warning::Time budget reached" in capsys.readouterr().out
