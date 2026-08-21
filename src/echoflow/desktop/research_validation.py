"""Shared validation invariants for Research desktop request adapters."""

from __future__ import annotations


def normalize_research_labels(values: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize user-authored Research labels without changing their display spelling."""
    normalized: dict[str, str] = {}
    for raw in values:
        value = raw.strip()
        if not value:
            raise ValueError("research labels cannot be blank")
        if len(value) > 200:
            raise ValueError("research labels cannot exceed 200 characters")
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError("research labels contain unsupported control characters")
        normalized.setdefault(value.casefold(), value)
    return tuple(normalized[key] for key in sorted(normalized))
