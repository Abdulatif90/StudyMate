"""Telegram HTTP routes — thin: auth/security/DB wiring only (all logic in service.py).

**Two very different trust models live in this file** (like billing/router.py):
  - `POST /telegram/link` is authenticated — `get_current_user_id` gives a Clerk-verified
    owner_id, so a caller can only ever mint a link code for themselves.
  - `POST /telegram/webhook` is **public**: Telegram calls it from the internet with no
    Clerk JWT. Its trust comes from the shared secret Telegram echoes back in the
    `X-Telegram-Bot-Api-Secret-Token` header (set via setWebhook's `secret_token`), which
    we compare against `settings.telegram_webhook_secret`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlmodel import Session

from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.db import get_session
from app.modules.telegram import service
from app.modules.telegram.schemas import LinkCodeResponse, LinkStatusResponse
from app.modules.telegram.telegram_api import TelegramApiError

router = APIRouter(prefix="/telegram", tags=["telegram"])

# Header Telegram sends on every webhook request when a secret_token was set via setWebhook.
_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


@router.post("/link", response_model=LinkCodeResponse)
def create_link(
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> LinkCodeResponse:
    """Issue a one-time Telegram link code + deep link for the authenticated caller.

    The code is tied to the caller's verified `owner_id`, so it can only ever link a
    Telegram chat to this account — a caller can't mint a code for someone else.
    """
    return service.create_link_code(session, owner_id)


@router.get("/status", response_model=LinkStatusResponse)
def get_status(
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> LinkStatusResponse:
    """Whether the authenticated caller currently has a linked Telegram chat."""
    return LinkStatusResponse(linked=service.is_linked(session, owner_id))


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    session: Session = Depends(get_session),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    """Telegram -> us. **Public endpoint, no Clerk auth** (Telegram has no user token).

    Security: when `TELEGRAM_WEBHOOK_SECRET` is configured, the request's
    `X-Telegram-Bot-Api-Secret-Token` header MUST equal it, else 403 (process nothing).
    LIVE BLOCKER: this secret MUST be set in production — while it's unset (before the
    webhook is registered live) the endpoint processes updates unverified, which is a dev
    convenience only.

    Always returns 200 on a processed/ignored update (Telegram retries the SAME update on
    any non-200, which would re-run research and waste budget). A malformed body or a
    transient Bot-API send failure is swallowed to a 200 no-op rather than a 500.
    """
    secret = get_settings().telegram_webhook_secret
    if secret and x_telegram_bot_api_secret_token != secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret.")

    try:
        update = await request.json()
    except Exception:
        # Not JSON / empty body — nothing to process, and retrying won't help.
        return {"status": "ignored"}

    if not isinstance(update, dict):
        return {"status": "ignored"}

    try:
        service.handle_update(session, update)
    except TelegramApiError:
        # A transient Bot-API failure (e.g. Telegram briefly unreachable while sending the
        # reply). Returning non-200 would make Telegram re-deliver and re-run research, so
        # we accept the update instead; the user simply didn't get this one reply.
        return {"status": "send_failed"}

    return {"status": "ok"}
