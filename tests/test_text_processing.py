from personal_agent_memory.utils.text_processing import detect_wikilinks, make_title, normalize_tags


def test_normalize_tags_deduplicates_and_slugifies() -> None:
    assert normalize_tags(["Personal Memory", "personal   memory", "MCP!"]) == [
        "personal-memory",
        "mcp",
    ]


def test_detect_wikilinks_preserves_order_and_deduplicates() -> None:
    text = "See [[Memory Schema]] then [[Tags]] and [[Memory Schema]]."

    assert detect_wikilinks(text) == ["Memory Schema", "Tags"]


def test_make_title_truncates_long_first_line() -> None:
    title = make_title("x" * 100)

    assert len(title) == 80
    assert title.endswith("...")
