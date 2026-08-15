from __future__ import annotations

import re

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def build_turn_body(user_input: str, assistant_output: str) -> str:
    return f"User:\n{user_input.strip()}\n\nAssistant:\n{assistant_output.strip()}"


def make_title(user_input: str) -> str:
    first_line = user_input.strip().splitlines()[0].strip()
    if len(first_line) <= 80:
        return first_line
    return first_line[:77].rstrip() + "..."


def normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        name = re.sub(r"\s+", "-", tag.strip().lower())
        name = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]", "", name)
        if name and name not in seen:
            seen.add(name)
            normalized.append(name)
    return normalized


def detect_wikilinks(text: str) -> list[str]:
    links = []
    seen = set()
    for match in WIKILINK_RE.finditer(text):
        title = match.group(1).strip()
        if title and title not in seen:
            seen.add(title)
            links.append(title)
    return links
