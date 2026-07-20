"""Telegram bot business logic — linking + answering. All logic lives here so the
router stays thin (CLAUDE.md rule 1).

The bot only serves LINKED StudyMate users. Linking flow:
  1. An authenticated StudyMate user calls `create_link_code` → gets a one-time code and
     a `https://t.me/helperstudymatebot?start=<code>` deep link.
  2. They open the deep link; Telegram sends the bot `/start <code>`.
  3. `handle_update` looks the code up, links `chat_id -> owner_id` (upsert), and consumes
     the code. A code carries the owner_id of the user who made it, so it can only ever
     link a chat to that user (cross-tenant safe by construction).

After linking, any plain text from that chat is answered via the existing Research service
(web-agentic, query-only). Answering over the user's OWN uploaded materials needs subject
handling and is a deliberate follow-up TODO — not built here.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.modules.research.service import research
from app.modules.telegram.models import TelegramLink, TelegramLinkCode
from app.modules.telegram.schemas import LinkCodeResponse
from app.modules.telegram.telegram_api import MAX_MESSAGE_LENGTH, send_message

BOT_USERNAME = "helperstudymatebot"

# Same base32 alphabet as referral codes (no 0/1/8/9 to confuse with O/I/B/g). 10 chars =
# 32**10 ≈ 1.1e15 possible codes; the collision loop is a correctness backstop, not a hot
# path. A link code is single-use and short-lived, so it need not be human-memorable, but
# the friendly alphabet costs nothing.
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_CODE_LENGTH = 10
_MAX_GENERATION_ATTEMPTS = 8
# How long a freshly issued code stays usable. Short-lived on purpose: the code proves
# account ownership, so a stale one shouldn't linger.
_CODE_TTL = timedelta(minutes=30)

_INVALID_CODE_REPLY = (
    "That link code is invalid or has expired. Open StudyMate and generate a new one to "
    "connect your account."
)
_UNLINKED_REPLY = (
    "Your Telegram isn't connected to a StudyMate account yet. Open StudyMate, generate a "
    "connection link, and tap it to get started."
)
_START_NO_CODE_REPLY = (
    "Welcome to StudyMate! To connect your account, generate a connection link inside the "
    "StudyMate app and tap it here."
)
_RESEARCH_FAILED_REPLY = "Sorry — I couldn't answer that just now. Please try again in a moment."


def _generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))


def _deep_link(code: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start={code}"


def create_link_code(session: Session, owner_id: str) -> LinkCodeResponse:
    """Issue a fresh single-use link code tied to `owner_id`, plus its deep link.

    A new code every call (unlike referral's one-stable-code-per-user): these are
    one-time, short-lived credentials, so re-issuing is expected and old unused ones simply
    expire.
    """
    for _ in range(_MAX_GENERATION_ATTEMPTS):
        code = _generate_code()
        collision = session.get(TelegramLinkCode, code)
        if collision is None:
            link_code = TelegramLinkCode(code=code, owner_id=owner_id)
            session.add(link_code)
            session.commit()
            return LinkCodeResponse(code=code, deep_link=_deep_link(code))
    raise RuntimeError("Could not generate a unique Telegram link code after retries.")


def is_linked(session: Session, owner_id: str) -> bool:
    """True iff `owner_id` has at least one linked Telegram chat.

    Owner-scoped by construction: `TelegramLink.owner_id` is only ever set from a link
    code's stored owner (see `_link_chat`), never from caller input, so this can't be
    tricked into reporting another user's link.
    """
    existing = session.exec(select(TelegramLink).where(TelegramLink.owner_id == owner_id)).first()
    return existing is not None


def _is_expired(link_code: TelegramLinkCode) -> bool:
    created = link_code.created_at
    # Rows read back from SQLite come out naive (UTC); normalize before comparing so a
    # naive vs aware subtraction can't raise.
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return datetime.now(UTC) - created > _CODE_TTL


def _link_chat(session: Session, link_code: TelegramLinkCode, chat_id: int) -> None:
    """Upsert `chat_id -> owner_id` and consume the code, in one transaction."""
    existing = session.get(TelegramLink, chat_id)
    if existing is None:
        session.add(TelegramLink(telegram_chat_id=chat_id, owner_id=link_code.owner_id))
    else:
        # Re-linking an already-linked chat: point it at the new owner (upsert semantics —
        # the chat id is the PK, one chat maps to exactly one account).
        existing.owner_id = link_code.owner_id
        session.add(existing)
    link_code.used = True
    session.add(link_code)
    session.commit()


def _handle_start(session: Session, chat_id: int, text: str) -> None:
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        send_message(chat_id, _START_NO_CODE_REPLY)
        return

    code = parts[1].strip()
    link_code = session.get(TelegramLinkCode, code)
    if link_code is None or link_code.used or _is_expired(link_code):
        send_message(chat_id, _INVALID_CODE_REPLY)
        return

    _link_chat(session, link_code, chat_id)
    send_message(
        chat_id,
        "Your StudyMate account is connected. Ask me a study question and I'll research it "
        "for you.",
    )


def _format_answer(answer: str, source_urls: list[str]) -> str:
    """Answer text plus a brief sources footer, truncated to Telegram's 4096-char limit.

    Truncation keeps the answer body and drops overflow (the sources footer is trimmed
    first, then the body if it alone still exceeds the limit) so a long research answer
    never 400s the Bot API.
    """
    if source_urls:
        footer = "\n\nSources:\n" + "\n".join(source_urls[:5])
    else:
        footer = ""
    combined = answer + footer
    if len(combined) <= MAX_MESSAGE_LENGTH:
        return combined
    # Overflow: prefer the answer body, dropping the sources footer (and hard-trimming the
    # body itself only if it alone still exceeds the limit).
    return answer[:MAX_MESSAGE_LENGTH]


def _handle_question(session: Session, chat_id: int, text: str) -> None:
    link = session.get(TelegramLink, chat_id)
    if link is None:
        send_message(chat_id, _UNLINKED_REPLY)
        return

    try:
        result = research(text)
    except Exception:
        # research() already degrades TavilyError/ResearchError to a normal response, so
        # this only catches a truly unexpected failure — reply friendly, never a 500.
        send_message(chat_id, _RESEARCH_FAILED_REPLY)
        return

    source_urls = [source.url for source in result.sources]
    send_message(chat_id, _format_answer(result.answer, source_urls))


def handle_update(session: Session, update: dict) -> None:
    """Parse one raw Telegram Update and act on it. Defensive: any missing/unexpected field
    is a no-op (never a 500), since Telegram retries on any non-200 and would otherwise loop
    forever on an update shape we don't handle.

    Update shape (https://core.telegram.org/bots/api, verified 2026-07-20):
    `update.message.chat.id`, `update.message.text`. Non-text messages (photos, stickers,
    edited messages, etc.) are ignored.
    """
    message = update.get("message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat")
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    text = message.get("text")
    if not isinstance(chat_id, int) or not isinstance(text, str) or not text.strip():
        return

    if text.lstrip().startswith("/start"):
        _handle_start(session, chat_id, text.strip())
    else:
        _handle_question(session, chat_id, text.strip())
