"""Human presentation helpers for canonical source-relative media time."""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP

_MILLISECONDS_PER_SECOND = 1_000
_MILLISECONDS_PER_MINUTE = 60 * _MILLISECONDS_PER_SECOND
_MILLISECONDS_PER_HOUR = 60 * _MILLISECONDS_PER_MINUTE


def format_elapsed_timestamp(seconds: float) -> str:
    """Render source-relative seconds as an unwrapped ``HH:MM:SS.mmm`` coordinate.

    Canonical evidence remains numeric seconds. This representation is deliberately a
    presentation value so UI formatting can evolve without changing durable anchors.
    Hours do not wrap at 24 because long recordings are elapsed timelines, not clocks.
    """
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("elapsed seconds must be finite and nonnegative")

    total_milliseconds = int(
        (Decimal(str(seconds)) * _MILLISECONDS_PER_SECOND).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    hours, remainder = divmod(total_milliseconds, _MILLISECONDS_PER_HOUR)
    minutes, remainder = divmod(remainder, _MILLISECONDS_PER_MINUTE)
    whole_seconds, milliseconds = divmod(remainder, _MILLISECONDS_PER_SECOND)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
