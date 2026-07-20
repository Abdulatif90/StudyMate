"""Telegram Bot API client — all Bot-API specifics are isolated here.

Verified contract (https://core.telegram.org/bots/api, verified 2026-07-20):
- sendMessage: POST https://api.telegram.org/bot<token>/sendMessage
  with JSON params `chat_id` (required) + `text` (required), optional `parse_mode`.
  A text message is capped at 4096 characters, so callers must truncate first.

Two failure modes, split the same way as tavily.py / embedding.py / llm.py:
- Missing `TELEGRAM_BOT_TOKEN` is a deployment/config mistake → bare `RuntimeError`
  at point of use, so it fails loudly instead of silently dropping replies.
- Any network/HTTP/API failure → `TelegramApiError`, caught by the service so a
  reply failure never leaks a 500 back to Telegram.
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings

TELEGRAM_API_BASE = "https://api.telegram.org"
#: Telegram's hard limit on a single text message (Bot API docs).
MAX_MESSAGE_LENGTH = 4096
_TIMEOUT_SECONDS = 20.0


class TelegramApiError(Exception):
    """Raised when a Bot API call fails (network/HTTP/API error)."""


def _bot_token() -> str:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Add it to backend/.env — see backend/.env.example."
        )
    return settings.telegram_bot_token


def send_message(chat_id: int, text: str) -> None:
    """Send `text` to `chat_id` via the Bot API's sendMessage.

    Missing token → `RuntimeError`; any request/API failure → `TelegramApiError`. Text is
    truncated to Telegram's 4096-char limit here as a safety net (callers should truncate
    with context, but the API would 400 on an over-long message otherwise).
    """
    token = _bot_token()
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH]
    try:
        response = httpx.post(
            f"{TELEGRAM_API_BASE}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:
        raise TelegramApiError(f"Telegram sendMessage failed: {exc}") from exc
