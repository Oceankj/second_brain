import io
import json
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

WORKFLOW = Path(".github/workflows/daily-diary.yml")


def run_workflow(monkeypatch, tmp_path, results, *, dry_run="false", max_batches="10"):
    source = textwrap.dedent(WORKFLOW.read_text().split("        run: |\n", 1)[1])
    python = source.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    for key, value in {
        "MEMORY_BASE_URL": "https://memory.example",
        "MEMORY_DIARY_TOKEN": "private-token",
        "DRY_RUN": dry_run,
        "MAX_BATCHES": max_batches,
        "BATCH_SIZE": "2",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
    }.items():
        monkeypatch.setenv(key, value)
    requests = []
    responses = iter(results)

    def open_request(request, timeout):
        requests.append(json.loads(request.data))
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(json.dumps(value).encode())

    def opener(handler):
        assert handler().redirect_request(None, None, 302, "", {}, "https://other.example") is None
        return SimpleNamespace(open=open_request)

    monkeypatch.setattr(urllib.request, "build_opener", opener)
    return lambda: exec(compile(python, str(WORKFLOW), "exec"), {}), requests


def result(status, remaining=False):
    return {
        "status": status,
        "has_more": remaining,
        "notes": [{"body": "private-note"}],
        "diaries": [{"body": "private-diary"}],
        "usage_run_id": "12345678-1234-1234-1234-123456789012",
    }


def test_preview_is_one_request_and_logs_no_content(monkeypatch, tmp_path, capsys):
    run, requests = run_workflow(monkeypatch, tmp_path, [result("preview", True)], dry_run="true")
    run()
    assert requests == [{"dry_run": True, "limit": 2}]
    log = capsys.readouterr().out + (tmp_path / "summary.md").read_text()
    assert "12345678-1234-1234-1234-123456789012" in log
    assert "private-note" not in log and "private-diary" not in log and "private-token" not in log


def test_save_drains_batches(monkeypatch, tmp_path):
    run, requests = run_workflow(
        monkeypatch, tmp_path, [result("accepted", True), result("accepted")]
    )
    run()
    assert len(requests) == 2 and all(not r["dry_run"] for r in requests)


def test_batch_limit_stops_without_extra_post(monkeypatch, tmp_path):
    run, requests = run_workflow(monkeypatch, tmp_path, [result("accepted", True)], max_batches="1")
    with pytest.raises(SystemExit, match="Batch limit"):
        run()
    assert len(requests) == 1


def test_timeout_does_not_retry_uncertain_write(monkeypatch, tmp_path):
    run, requests = run_workflow(monkeypatch, tmp_path, [TimeoutError("private failure")])
    with pytest.raises(SystemExit, match="connection error or timeout"):
        run()
    assert len(requests) == 1
    assert "completion is unknown" in (tmp_path / "summary.md").read_text()


def test_save_rejects_preview_response(monkeypatch, tmp_path):
    run, _ = run_workflow(monkeypatch, tmp_path, [result("preview")])
    with pytest.raises(SystemExit, match="unexpected status"):
        run()
