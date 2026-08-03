from enum import StrEnum
from pathlib import Path


class PathDisclosure(StrEnum):
    """Control whether routine diagnostic logs may contain local paths."""

    REDACT = "redact"
    FULL = "full"


def path_log_context(
    policy: PathDisclosure,
    **paths: str | Path,
) -> dict[str, str]:
    """Return path fields only when a user explicitly enables disclosure."""
    if policy is PathDisclosure.REDACT:
        return {}
    return {name: str(path) for name, path in paths.items()}
