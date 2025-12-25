"""Utility helpers for resilient JSON parsing."""

from __future__ import annotations

import re
from typing import Any, Iterable

import json_repair as repair

CODE_FENCE_PATTERN = re.compile(r"^```[a-zA-Z0-9_+-]*\s*$")


def _strip_code_fences(raw: str) -> str:
    """Remove Markdown code fences while keeping inner content."""

    if raw is None:
        return ""

    lines = [line.rstrip() for line in raw.strip().splitlines()]
    if len(lines) >= 2 and CODE_FENCE_PATTERN.match(lines[0]) and CODE_FENCE_PATTERN.match(lines[-1]):
        return "\n".join(lines[1:-1]).strip()

    return raw.strip()


def _extract_json_fragment(raw: str) -> str:
    """Best-effort extraction of the first balanced JSON fragment."""

    for opener, closer in ("{}", "[]"):
        start = raw.find(opener)
        end = raw.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidate = raw[start : end + 1]
            if candidate.count(opener) >= candidate.count(closer):
                return candidate
    return raw


def _iter_possible_payloads(raw: str) -> Iterable[str]:
    cleaned = _strip_code_fences(raw)
    fragment = _extract_json_fragment(cleaned)
    yield fragment

    for line in cleaned.splitlines():
        line = line.strip().rstrip(",")
        if line:
            yield line


def robust_json_loads(raw: str) -> Any:
    """Attempt to parse slightly malformed JSON content.

    The function removes common wrappers (Markdown fences, surrounding text)
    and reuses ``json_repair`` to recover from minor syntax issues. It
    returns ``None`` when parsing fails for all candidates.
    """

    for candidate in _iter_possible_payloads(raw or ""):
        try:
            return repair.loads(candidate)
        except Exception:
            continue

    return None
