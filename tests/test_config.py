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
  },
  "retrieval": {
    "recent_diary_lookback_days": 4,
    "recent_diary_max_items": 5,
    "recent_diary_min_score": 0.8,
    "recent_diary_max_chars": 3000,
    "tag_retrieval_min_score": 0.81,
    "tag_retrieval_max_tags": 7,
    "tag_retrieval_tag_weight": 0.35
  }
}
"""
    )

    assert load_memory_config(config_path) == {
        "chunking": {
            "max_chars": 2400,
            "overlap_chars": 240,
        },
        "retrieval": {
            "recent_diary_lookback_days": 4,
            "recent_diary_max_items": 5,
            "recent_diary_min_score": 0.8,
            "recent_diary_max_chars": 3000,
            "tag_retrieval_min_score": 0.81,
            "tag_retrieval_max_tags": 7,
            "tag_retrieval_tag_weight": 0.35,
        },
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
  },
  "retrieval": {
    "recent_diary_lookback_days": 4,
    "recent_diary_max_items": 5,
    "recent_diary_min_score": 0.8,
    "recent_diary_max_chars": 3000,
    "tag_retrieval_min_score": 0.81,
    "tag_retrieval_max_tags": 7,
    "tag_retrieval_tag_weight": 0.35
  }
}
"""
    )

    settings = load_settings()

    assert settings.max_chunk_chars == 2400
    assert settings.chunk_overlap_chars == 240
    assert settings.recent_diary_lookback_days == 4
    assert settings.recent_diary_max_items == 5
    assert settings.recent_diary_min_score == 0.8
    assert settings.recent_diary_max_chars == 3000
    assert settings.tag_retrieval_min_score == 0.81
    assert settings.tag_retrieval_max_tags == 7
    assert settings.tag_retrieval_tag_weight == 0.35


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
    assert settings.recent_diary_lookback_days == 2
    assert settings.recent_diary_max_items == 3
    assert settings.recent_diary_min_score == 0.72
    assert settings.recent_diary_max_chars == 2000
    assert settings.tag_retrieval_min_score == 0.72
    assert settings.tag_retrieval_max_tags == 5
    assert settings.tag_retrieval_tag_weight == 0.4


def test_settings_rejects_invalid_chunk_overlap() -> None:
    with pytest.raises(ValueError, match="overlap_chars must be smaller"):
        Settings(
            database_url="postgresql://example",
            max_chunk_chars=100,
            chunk_overlap_chars=100,
        )


def test_settings_rejects_invalid_recent_diary_lookback_days() -> None:
    with pytest.raises(ValueError, match="recent_diary_lookback_days"):
        Settings(
            database_url="postgresql://example",
            recent_diary_lookback_days=8,
        )


def test_settings_rejects_invalid_recent_diary_min_score() -> None:
    with pytest.raises(ValueError, match="recent_diary_min_score"):
        Settings(
            database_url="postgresql://example",
            recent_diary_min_score=1.1,
        )


def test_settings_rejects_invalid_tag_retrieval_weight() -> None:
    with pytest.raises(ValueError, match="tag_retrieval_tag_weight"):
        Settings(
            database_url="postgresql://example",
            tag_retrieval_tag_weight=1.1,
        )
