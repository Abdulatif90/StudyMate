"""Shared pytest fixtures.

Every router now depends on `get_org_context` (Phase 5 increment 2 — org-owned shared
subjects) alongside `get_current_user_id`. The existing per-file `_isolated_db` fixtures
override `get_session` + `get_current_user_id` but not the new org dependency, so this
autouse fixture supplies a DEFAULT override — `OrgContext()`, i.e. *no active org* — for
every test. That default reproduces the legacy private-subject behavior exactly (a
caller with no active org sees/owns only their own content), so all pre-org tests keep
passing untouched.

A test that needs a specific org context (teacher/member of some org) reassigns
`app.dependency_overrides[get_org_context]` inside the test body — the same in-test
reassignment pattern the existing suite already uses for `get_current_user_id` (see
`test_subjects.py::test_subjects_are_scoped_to_owner`). Set up and torn down per test,
never at import time, so nothing leaks between modules.
"""

from __future__ import annotations

import pytest

from app.core.auth import get_org_context
from app.core.org import OrgContext
from app.main import app


@pytest.fixture(autouse=True)
def _default_no_org_context():
    app.dependency_overrides[get_org_context] = lambda: OrgContext()
    yield
    app.dependency_overrides.pop(get_org_context, None)
