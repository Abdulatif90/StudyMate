"""Tests for the Sentry init wiring (app/core/sentry.py) — no-op-when-unset and the
PlanLimitExceededError filter. `sentry_sdk.init` itself is mocked; no real network, no
real DSN.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core import sentry


class _FakeIgnoredError(Exception):
    """Stand-in for an app exception the caller wants filtered out of Sentry."""


class _FakeOtherError(Exception):
    """A genuinely unexpected error — must NOT be filtered."""


def test_init_sentry_is_a_noop_when_dsn_unset(monkeypatch):
    monkeypatch.setattr(sentry, "get_settings", lambda: SimpleNamespace(sentry_dsn=None))
    fake_init = MagicMock()
    monkeypatch.setattr(sentry.sentry_sdk, "init", fake_init)

    sentry.init_sentry()

    fake_init.assert_not_called()


def test_init_sentry_calls_sentry_sdk_init_when_dsn_set(monkeypatch):
    monkeypatch.setattr(
        sentry,
        "get_settings",
        lambda: SimpleNamespace(sentry_dsn="https://fake@sentry.example/1", environment="test"),
    )
    fake_init = MagicMock()
    monkeypatch.setattr(sentry.sentry_sdk, "init", fake_init)

    sentry.init_sentry()

    fake_init.assert_called_once()
    kwargs = fake_init.call_args.kwargs
    assert kwargs["dsn"] == "https://fake@sentry.example/1"
    assert kwargs["environment"] == "test"
    assert callable(kwargs["before_send"])


def test_before_send_drops_an_ignored_exception():
    before_send = sentry._build_before_send([_FakeIgnoredError])
    event = {"message": "irrelevant"}
    hint = {"exc_info": (_FakeIgnoredError, _FakeIgnoredError("hit the cap"), None)}

    assert before_send(event, hint) is None


def test_before_send_keeps_an_unlisted_exception():
    before_send = sentry._build_before_send([_FakeIgnoredError])
    event = {"message": "irrelevant"}
    hint = {"exc_info": (_FakeOtherError, _FakeOtherError("boom"), None)}

    assert before_send(event, hint) is event


def test_before_send_keeps_events_with_no_exception():
    # A plain captureMessage() call has no exc_info at all — must pass through.
    before_send = sentry._build_before_send([_FakeIgnoredError])
    event = {"message": "just a message"}

    assert before_send(event, {}) is event
