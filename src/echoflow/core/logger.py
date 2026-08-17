"""Compatibility imports for the consolidated observability module.

New code should import logging capabilities from ``echoflow.core.observability``.
This module remains temporarily so existing imports and older integrations do not
break during the internal cleanup.
"""

from echoflow.core.observability import (
    ILogger,
    PathDisclosure,
    StructlogAdapter,
    configure_logging,
    path_log_context,
    reset_logging,
)

__all__ = [
    "ILogger",
    "PathDisclosure",
    "StructlogAdapter",
    "configure_logging",
    "path_log_context",
    "reset_logging",
]
