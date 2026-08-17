"""Compatibility import for EchoFlow's logging protocol.

Prefer ``echoflow.core.observability.ILogger`` in new code. This shim exists only
to avoid a flag-day import migration inside long-lived integrations.
"""

from echoflow.core.observability import ILogger

__all__ = ["ILogger"]
