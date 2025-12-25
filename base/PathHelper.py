"""Runtime path utilities for locating bundled resources."""
from __future__ import annotations

import os
import sys
from typing import Iterable

# Project root when running from source
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def _candidate_roots() -> Iterable[str]:
    """Yield possible base paths where resources may live."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        yield meipass

    if getattr(sys, "frozen", False):
        yield os.path.dirname(sys.executable)

    yield _PROJECT_ROOT


def get_resource_path(*segments: str) -> str:
    """Resolve a resource path that works for source and PyInstaller builds."""
    for root in _candidate_roots():
        candidate = os.path.join(root, *segments)
        if os.path.exists(candidate):
            return candidate

    # Fall back to the last candidate even if it does not exist yet.
    fallback_root = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _PROJECT_ROOT
    return os.path.join(fallback_root, *segments)
