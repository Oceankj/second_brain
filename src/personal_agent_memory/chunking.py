from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    content: str
    token_count: int | None = None


def chunk_text(text: str, max_chars: int = 1800, overlap_chars: int = 200) -> list[TextChunk]:
    normalized = text.strip()
    if not normalized:
        return []
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars cannot be negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    chunks: list[TextChunk] = []
    start = 0

    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        if end < len(normalized):
            newline = normalized.rfind("\n", start, end)
            sentence = normalized.rfind(". ", start, end)
            boundary = max(newline, sentence)
            if boundary > start + max_chars // 2:
                end = boundary + (1 if boundary == newline else 2)

        content = normalized[start:end].strip()
        if content:
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    content=content,
                    token_count=estimate_token_count(content),
                )
            )

        if end >= len(normalized):
            break
        start = max(0, end - overlap_chars)

    return chunks


def estimate_token_count(text: str) -> int:
    return max(1, len(text) // 4)
