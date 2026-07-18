"""Unit tests for app.shared.language — the resolver used by summary/flashcards/quiz
prompt-building to turn a UI locale code into the full language name Claude is asked
to respond in.
"""

from __future__ import annotations

from app.shared import language


def test_language_name_resolves_known_codes():
    assert language.language_name("en") == "English"
    assert language.language_name("uz") == "Uzbek"
    assert language.language_name("ko") == "Korean"
    assert language.language_name("ru") == "Russian"


def test_language_name_falls_back_to_english_for_unknown_code():
    assert language.language_name("fr") == "English"


def test_language_name_falls_back_to_english_when_none():
    assert language.language_name(None) == "English"
