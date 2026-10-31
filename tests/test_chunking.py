from personal_agent_memory.services.memory.chunking import chunk_text


def test_chunk_text_returns_ordered_chunks_with_overlap() -> None:
    text = "a" * 120

    chunks = chunk_text(text, max_chars=50, overlap_chars=10)

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert chunks[0].content == "a" * 50
    assert chunks[1].content == "a" * 50
    assert chunks[2].content == "a" * 40


def test_chunk_text_rejects_invalid_overlap() -> None:
    try:
        chunk_text("hello", max_chars=10, overlap_chars=10)
    except ValueError as exc:
        assert "overlap_chars" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_chunk_text_rejects_overlap_above_half_of_max_chars() -> None:
    # Regression test for issue #5: with overlap above half of max_chars,
    # a sentence boundary landing early sent the next window back to the
    # same start, looping forever. This must now fail fast instead.
    text = "x" * 59 + ". " + "y" * 200
    try:
        chunk_text(text, max_chars=100, overlap_chars=80)
    except ValueError as exc:
        assert "must not exceed half" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_chunk_text_allows_overlap_at_half_of_max_chars() -> None:
    chunks = chunk_text("a" * 250, max_chars=100, overlap_chars=50)

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2, 3]
    assert chunks[0].content == "a" * 100
    assert chunks[-1].content == "a" * 100
