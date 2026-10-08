import pytest


@pytest.fixture(autouse=True)
def isolated_usage_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_USAGE_LOG_PATH", str(tmp_path / "usage.sqlite3"))
