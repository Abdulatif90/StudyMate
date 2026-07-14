"""Unit tests for app.modules.documents.chunking — pure function, no DB, no HTTP."""

from __future__ import annotations

from app.modules.documents.chunking import chunk_text


def test_chunk_text_returns_empty_list_for_empty_string():
    assert chunk_text("") == []


def test_chunk_text_returns_empty_list_for_whitespace_only():
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_returns_single_chunk_when_under_limit():
    text = "This is a short document."
    assert chunk_text(text, chunk_size=1000, overlap=150) == [text]


def test_chunk_text_splits_long_text_and_preserves_order():
    text = " ".join(f"This is sentence number {i}." for i in range(200))
    chunks = chunk_text(text, chunk_size=200, overlap=40)

    assert len(chunks) > 1
    # every chunk is a literal (stripped) substring of the source
    assert all(chunk in text for chunk in chunks)
    # unique sentence numbers mean .index() finds the right occurrence, not an
    # earlier duplicate, so this also confirms chunks come out in source order
    positions = [text.index(chunk) for chunk in chunks]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


def test_chunk_text_consecutive_chunks_overlap():
    text = " ".join(f"This is sentence number {i}." for i in range(200))
    chunks = chunk_text(text, chunk_size=200, overlap=40)
    positions = [text.index(chunk) for chunk in chunks]

    for i in range(len(chunks) - 1):
        current_chunk_end = positions[i] + len(chunks[i])
        assert positions[i + 1] < current_chunk_end


def test_chunk_text_respects_sentence_boundaries():
    text = " ".join(f"This is sentence number {i}." for i in range(200))
    chunks = chunk_text(text, chunk_size=200, overlap=40)

    for chunk in chunks[:-1]:
        assert chunk.endswith(".")


def test_chunk_text_hard_splits_a_single_unbreakable_word():
    text = "x" * 500  # no spaces/punctuation anywhere to snap a boundary to
    chunks = chunk_text(text, chunk_size=200, overlap=40)

    assert len(chunks) > 1
    assert all(set(chunk) == {"x"} for chunk in chunks)
