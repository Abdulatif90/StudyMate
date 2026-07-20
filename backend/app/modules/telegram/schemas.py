"""Request/response schemas for the Telegram link endpoint.

The webhook body is a raw Telegram Update dict, parsed defensively in the service
(missing fields → no-op, never a 500), so it has no schema here on purpose — pydantic
validation of an external, evolving payload would turn a harmless unknown-shape update
into a 422 that Telegram would then retry forever.
"""

from __future__ import annotations

from pydantic import BaseModel


class LinkCodeResponse(BaseModel):
    """Returned by POST /telegram/link: the one-time code plus a ready-to-tap deep link
    (`https://t.me/<bot>?start=<code>`) that opens the bot and sends `/start <code>`."""

    code: str
    deep_link: str
