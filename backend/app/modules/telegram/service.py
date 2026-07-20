"""Telegram bot business logic — linking + answering. All logic lives here so the
router stays thin (CLAUDE.md rule 1).

The bot only serves LINKED StudyMate users. Linking flow:
  1. An authenticated StudyMate user calls `create_link_code` → gets a one-time code and
     a `https://t.me/helperstudymatebot?start=<code>` deep link.
  2. They open the deep link; Telegram sends the bot `/start <code>`.
  3. `handle_update` looks the code up, links `chat_id -> owner_id` (upsert), and consumes
     the code. A code carries the owner_id of the user who made it, so it can only ever
     link a chat to that user (cross-tenant safe by construction).

After linking, a chat can:
  - `/subjects` — list its own subjects (a numbered picker).
  - `/subject <n|name>` — set the active subject to ask over.
  - a plain question — answered over the ACTIVE subject's own uploaded materials via the
    existing Ask/RAG service (`ask.service.ask_question`), scoped to the linked owner_id.
  - `/research <query>` — an explicit web-research answer (the original bot behaviour).

Access is owner-scoped by construction: every RAG call passes the chat's linked
`owner_id` and an empty `OrgContext` (a Telegram chat has no active-org session), so the
bot can only ever reach the linked user's OWN private subjects — never another user's, and
never an org subject the user is merely a member of. `ask_question`'s own
`require_readable_subject` gate fails closed on anything else.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.core.org import OrgContext
from app.modules.ask.schemas import AskResponse
from app.modules.ask.service import ask_question
from app.modules.research.service import research
from app.modules.subjects.service import SubjectNotFoundError, list_owned_subjects
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
# How many subject filenames to list in an answer's sources footer.
_MAX_SOURCE_LINES = 5

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
_LINKED_REPLY = (
    "Your StudyMate account is connected. Send /subjects to pick a subject and ask about "
    "your own materials, or /research <question> to search the web."
)
_RESEARCH_FAILED_REPLY = "Sorry — I couldn't answer that just now. Please try again in a moment."
_ANSWER_FAILED_REPLY = "Sorry — I couldn't answer that just now. Please try again in a moment."
_NO_SUBJECTS_REPLY = (
    "You don't have any subjects yet. Create one in StudyMate and upload your materials, "
    "then come back and ask about them here. In the meantime, send /research <question> to "
    "search the web."
)
_SUBJECT_NOT_FOUND_REPLY = (
    "I couldn't find that subject. Send /subjects to see your subjects and their numbers, "
    "then /subject <number> to pick one."
)
_SUBJECT_GONE_REPLY = "That subject is no longer available. Send /subjects to pick another one."
_RESEARCH_NO_QUERY_REPLY = "What would you like me to research? Send /research <your question>."
_HELP_REPLY = (
    "I can help you study. Commands:\n"
    "/subjects — list your subjects\n"
    "/subject <number> — pick a subject to ask about\n"
    "/research <question> — search the web\n\n"
    "Once you've picked a subject, just send a question and I'll answer from your own "
    "uploaded materials."
)


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
        # the chat id is the PK, one chat maps to exactly one account). Clear any active
        # subject too — it belonged to the previously linked account.
        existing.owner_id = link_code.owner_id
        existing.active_subject_id = None
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
    send_message(chat_id, _LINKED_REPLY)


def _format_answer(answer: str, source_lines: list[str]) -> str:
    """Answer text plus a brief sources footer, truncated to Telegram's 4096-char limit.

    Truncation keeps the answer body and drops overflow (the sources footer is trimmed
    first, then the body if it alone still exceeds the limit) so a long answer never 400s
    the Bot API.
    """
    if source_lines:
        footer = "\n\nSources:\n" + "\n".join(source_lines[:_MAX_SOURCE_LINES])
    else:
        footer = ""
    combined = answer + footer
    if len(combined) <= MAX_MESSAGE_LENGTH:
        return combined
    # Overflow: prefer the answer body, dropping the sources footer (and hard-trimming the
    # body itself only if it alone still exceeds the limit).
    return answer[:MAX_MESSAGE_LENGTH]


def _answer_via_research(chat_id: int, text: str) -> None:
    """Web-research fallback — the bot's original behaviour, kept for `/research` and for a
    linked user who has no subjects to ask over yet."""
    try:
        result = research(text)
    except Exception:
        # research() already degrades TavilyError/ResearchError to a normal response, so
        # this only catches a truly unexpected failure — reply friendly, never a 500.
        send_message(chat_id, _RESEARCH_FAILED_REPLY)
        return

    source_urls = [source.url for source in result.sources]
    send_message(chat_id, _format_answer(result.answer, source_urls))


def _unique_source_filenames(response: AskResponse) -> list[str]:
    """The distinct document filenames an answer was grounded in, in first-seen order."""
    filenames: list[str] = []
    for source in response.sources:
        if source.filename not in filenames:
            filenames.append(source.filename)
    return filenames


def _answer_over_subject(session: Session, chat_id: int, link: TelegramLink, text: str) -> None:
    """Answer `text` over the chat's active subject via the existing Ask/RAG service.

    Owner-scoped: `ask_question` is called with the chat's linked `owner_id` and an empty
    `OrgContext`, so retrieval can only ever touch this user's own subject. If the subject
    was deleted since it was selected, `ask_question` raises `SubjectNotFoundError` — we
    clear the stale selection and ask the user to pick again rather than 500.
    """
    try:
        response = ask_question(
            session, link.owner_id, link.active_subject_id, text, org_ctx=OrgContext()
        )
    except SubjectNotFoundError:
        link.active_subject_id = None
        session.add(link)
        session.commit()
        send_message(chat_id, _SUBJECT_GONE_REPLY)
        return
    except Exception:
        # ask_question degrades an LLM failure internally (returns an explanatory answer),
        # so this only catches a truly unexpected error (e.g. a misconfigured Cohere key in
        # a real deployment). Reply friendly, never a 500 back to Telegram.
        send_message(chat_id, _ANSWER_FAILED_REPLY)
        return

    send_message(chat_id, _format_answer(response.answer, _unique_source_filenames(response)))


def _subjects_listing(subjects: list, active_subject_id: uuid.UUID | None) -> str:
    lines = ["Your subjects:"]
    for index, subject in enumerate(subjects, start=1):
        marker = "  ← active" if subject.id == active_subject_id else ""
        lines.append(f"{index}. {subject.name}{marker}")
    lines.append("")
    lines.append("Send /subject <number> to pick one, then ask a question.")
    return "\n".join(lines)


def _handle_subjects_command(session: Session, chat_id: int, link: TelegramLink) -> None:
    subjects = list_owned_subjects(session, link.owner_id)
    if not subjects:
        send_message(chat_id, _NO_SUBJECTS_REPLY)
        return
    send_message(chat_id, _subjects_listing(subjects, link.active_subject_id))


def _resolve_subject(subjects: list, arg: str):
    """Pick a subject from `subjects` by 1-based number OR exact (case-insensitive) name.
    Returns the subject, or None if nothing matches."""
    if arg.isdigit():
        index = int(arg)
        if 1 <= index <= len(subjects):
            return subjects[index - 1]
        return None
    lowered = arg.casefold()
    for subject in subjects:
        if subject.name.casefold() == lowered:
            return subject
    return None


def _handle_subject_command(session: Session, chat_id: int, link: TelegramLink, arg: str) -> None:
    subjects = list_owned_subjects(session, link.owner_id)
    if not subjects:
        send_message(chat_id, _NO_SUBJECTS_REPLY)
        return
    if not arg:
        # `/subject` with no argument — show the picker so the user knows the numbers.
        send_message(chat_id, _subjects_listing(subjects, link.active_subject_id))
        return

    selected = _resolve_subject(subjects, arg)
    if selected is None:
        send_message(chat_id, _SUBJECT_NOT_FOUND_REPLY)
        return

    link.active_subject_id = selected.id
    session.add(link)
    session.commit()
    send_message(
        chat_id,
        f'Active subject set to "{selected.name}". Ask me a question about it.',
    )


def _handle_research_command(chat_id: int, arg: str) -> None:
    if not arg:
        send_message(chat_id, _RESEARCH_NO_QUERY_REPLY)
        return
    _answer_via_research(chat_id, arg)


def _answer_question(session: Session, chat_id: int, link: TelegramLink, text: str) -> None:
    """A plain (non-command) question from a linked chat.

    - Active subject selected → answer over that subject's own materials (RAG).
    - No active subject but the user HAS subjects → prompt them to pick one.
    - No subjects at all → fall back to web research so the bot stays useful.
    """
    if link.active_subject_id is not None:
        _answer_over_subject(session, chat_id, link, text)
        return

    subjects = list_owned_subjects(session, link.owner_id)
    if not subjects:
        # No materials to ground an answer in — web research keeps the bot useful.
        _answer_via_research(chat_id, text)
        return

    send_message(chat_id, _subjects_listing(subjects, link.active_subject_id))


def _parse_command(text: str) -> tuple[str, str]:
    """Split `/cmd rest` into a lowercased command (with any `@botname` suffix stripped,
    as Telegram appends in group chats) and the trimmed remainder."""
    parts = text.split(maxsplit=1)
    command = parts[0].lower()
    if "@" in command:
        command = command.split("@", 1)[0]
    arg = parts[1].strip() if len(parts) > 1 else ""
    return command, arg


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

    text = text.strip()

    # /start works for any chat (linked or not) — it's how a chat becomes linked.
    if text.startswith("/start"):
        _handle_start(session, chat_id, text)
        return

    # Everything else requires a linked chat (protects our Claude/Tavily budget).
    link = session.get(TelegramLink, chat_id)
    if link is None:
        send_message(chat_id, _UNLINKED_REPLY)
        return

    if not text.startswith("/"):
        _answer_question(session, chat_id, link, text)
        return

    command, arg = _parse_command(text)
    if command == "/subjects":
        _handle_subjects_command(session, chat_id, link)
    elif command == "/subject":
        _handle_subject_command(session, chat_id, link, arg)
    elif command == "/research":
        _handle_research_command(chat_id, arg)
    else:
        # /help or any unknown command → show what the bot can do.
        send_message(chat_id, _HELP_REPLY)
