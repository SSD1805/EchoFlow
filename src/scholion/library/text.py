"""Shared deterministic text semantics for transcript retrieval and navigation."""

from __future__ import annotations

import re

_TOKEN_PATTERN = re.compile(r"\w+(?:['’]\w+)*", re.UNICODE)


def lexical_tokens(text: str) -> tuple[str, ...]:
    """Return the Unicode-aware tokens used by lexical ranking and highlighting."""
    return tuple(match.group(0).casefold() for match in _TOKEN_PATTERN.finditer(text))
