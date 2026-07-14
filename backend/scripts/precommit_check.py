"""Pre-commit entry point: run ruff + pytest against backend/.

A script (not inline YAML) so the check always runs from `backend/`
regardless of pre-commit's cwd (the repo root), keeping it identical to
the commands documented in CLAUDE.md (`ruff check .`, `pytest tests`).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def run(*args: str) -> int:
    return subprocess.call([sys.executable, *args], cwd=BACKEND_DIR)


def main() -> int:
    ruff_status = run("-m", "ruff", "check", ".")
    test_status = run("-m", "pytest", "tests", "-q")
    return ruff_status or test_status


if __name__ == "__main__":
    raise SystemExit(main())
