"""Split extracted document text into overlapping chunks for future embedding.

Sliding window over character positions, but each window's end is nudged back to the
nearest paragraph/sentence/word boundary within a small look-back range, so chunks don't
routinely cut mid-word. Overlap carries the tail of one chunk into the next chunk's
head, so a sentence split across a chunk boundary still appears whole in at least one
chunk — this matters once retrieval (Phase 1's Ask endpoint) searches chunks
individually, not the whole document.
"""

from __future__ import annotations

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150
_BOUNDARY_LOOKBACK = 200


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        hard_end = min(start + chunk_size, length)
        end = hard_end if hard_end >= length else _find_boundary(text, start, hard_end)

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= length:
            break

        next_start = end - overlap
        start = next_start if next_start > start else end

    return chunks


def _find_boundary(text: str, start: int, hard_end: int) -> int:
    """Look backward from `hard_end` for a paragraph, sentence, or word boundary."""
    window_start = max(start, hard_end - _BOUNDARY_LOOKBACK)

    paragraph_break = text.rfind("\n\n", window_start, hard_end)
    if paragraph_break != -1:
        return paragraph_break + 2

    for punctuation in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
        index = text.rfind(punctuation, window_start, hard_end)
        if index != -1:
            return index + len(punctuation)

    space = text.rfind(" ", window_start, hard_end)
    if space != -1:
        return space + 1

    return hard_end
