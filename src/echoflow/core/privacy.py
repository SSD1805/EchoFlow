"""Compatibility imports for log path-disclosure policy.

This module never represented EchoFlow's entire privacy model. The policy now lives
with structured logging in ``echoflow.core.observability`` so the filesystem tree
matches its actual responsibility.
"""

from echoflow.core.observability import PathDisclosure, path_log_context

__all__ = ["PathDisclosure", "path_log_context"]
