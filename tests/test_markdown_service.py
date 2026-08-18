from datetime import UTC, date, datetime

from personal_agent_memory.services.markdown import MarkdownService


def test_item_to_markdown_renders_front_matter_and_body() -> None:
    service = MarkdownService()
    item = {
        "id": "item-1",
        "type": "note",
        "title": "Markdown service",
        "body": "Use Markdown as a portable memory format.",
        "status": "active",
        "event_date": date(2026, 8, 18),
        "tags": [{"name": "Memory IO"}, {"name": "memory io"}],
        "created_at": datetime(2026, 8, 18, 1, 2, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 18, 3, 4, tzinfo=UTC),
    }

    markdown = service.item_to_markdown(item)

    assert 'type: "note"' in markdown
    assert 'title: "Markdown service"' in markdown
    assert 'event_date: "2026-08-18"' in markdown
    assert 'tags: ["memory-io"]' in markdown
    assert markdown.endswith("Use Markdown as a portable memory format.\n")


def test_markdown_to_item_parses_front_matter() -> None:
    service = MarkdownService()
    markdown = """---
type: "diary"
title: "Daily notes"
status: "active"
event_date: "2026-08-18"
tags: ["Daily", "daily", "Codex Work"]
source_path: "notes/2026-08-18.md"
---

Worked on [[Markdown service]].
"""

    item = service.markdown_to_item(markdown)

    assert item.item_type == "diary"
    assert item.title == "Daily notes"
    assert item.status == "active"
    assert item.event_date == "2026-08-18"
    assert item.tags == ["daily", "codex-work"]
    assert item.body == "Worked on [[Markdown service]]."
    assert item.metadata == {"source_path": "notes/2026-08-18.md"}
    assert item.to_create_kwargs() == {
        "item_type": "diary",
        "title": "Daily notes",
        "body": "Worked on [[Markdown service]].",
        "status": "active",
        "event_date": "2026-08-18",
    }


def test_markdown_to_item_infers_title_without_front_matter() -> None:
    service = MarkdownService()

    item = service.markdown_to_item("# Imported note\n\nBody text")

    assert item.item_type == "note"
    assert item.title == "Imported note"
    assert item.body == "# Imported note\n\nBody text"


def test_markdown_item_identity_key_prefers_id_and_content_hash_is_normalized() -> None:
    service = MarkdownService()

    item = service.markdown_to_item(
        """---
id: "abc"
title: "Same Title"
---

Line one.

Line two.
"""
    )
    same_content = service.markdown_to_item(
        """---
title: " same   title "
---

Line one.
Line   two.
"""
    )

    assert item.identity_key == "id:abc"
    assert same_content.identity_key == "title:note:same title"
    assert item.content_hash == same_content.content_hash
