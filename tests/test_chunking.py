from personal_agent_memory.chunking import chunk_text


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
