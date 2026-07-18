"""Target-language codes shared by the generation flows (summary, flashcards, quiz).

Codes mirror the frontend's next-intl locales (frontend/src/i18n/locales.ts) so the
UI language switcher's current selection can be sent straight through as each
generation request's target language, with one map to keep in sync rather than a
separate copy per module.
"""

from __future__ import annotations

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "uz": "Uzbek",
    "ko": "Korean",
    "ru": "Russian",
}

DEFAULT_LANGUAGE = "en"


def language_name(code: str | None) -> str:
    """Resolve a language code to its full English name, for interpolation into an
    LLM prompt (Claude follows "respond in Uzbek" far more reliably than a raw ISO
    code). Anything unset or not in `SUPPORTED_LANGUAGES` — a stale client, a typo —
    falls back to English rather than being trusted verbatim into the prompt.
    """
    return SUPPORTED_LANGUAGES.get(code or DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES[DEFAULT_LANGUAGE])
