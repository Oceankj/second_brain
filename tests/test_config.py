from pathlib import Path

import pytest

from personal_agent_memory.config import Settings, load_memory_config, load_settings


def test_load_memory_config_reads_repo_local_json(tmp_path: Path) -> None:
    config_path = tmp_path / "memory.json"
    config_path.write_text(
        """{
  "chunking": {
    "max_chars": 2400,
    "overlap_chars": 240
  }
}
"""
    )

    assert load_memory_config(config_path) == {
        "chunking": {
            "max_chars": 2400,
            "overlap_chars": 240,
        }
    }


def test_load_settings_uses_memory_json_for_chunking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("MEMORY_MAX_CHUNK_CHARS", "1111")
    monkeypatch.setenv("MEMORY_CHUNK_OVERLAP_CHARS", "111")
    (tmp_path / "memory.json").write_text(
        """{
  "chunking": {
    "max_chars": 2400,
    "overlap_chars": 240
  }
}
"""
    )

    settings = load_settings()

    assert settings.max_chunk_chars == 2400
    assert settings.chunk_overlap_chars == 240


def test_load_settings_does_not_read_chunking_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("MEMORY_MAX_CHUNK_CHARS", "1111")
    monkeypatch.setenv("MEMORY_CHUNK_OVERLAP_CHARS", "111")

    settings = load_settings()

    assert settings.max_chunk_chars == 1800
    assert settings.chunk_overlap_chars == 200


def test_settings_rejects_invalid_chunk_overlap() -> None:
    with pytest.raises(ValueError, match="overlap_chars must be smaller"):
        Settings(
            database_url="postgresql://example",
            max_chunk_chars=100,
            chunk_overlap_chars=100,
        )
