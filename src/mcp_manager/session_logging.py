"""Context-local suppression of third-party transport payload diagnostics."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_PRIVATE: ContextVar[bool] = ContextVar("mcp_manager_private_session", default=False)


class _SessionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # SDK errors may include raw payloads, URLs, session IDs and exception inputs.
        # The caller returns a sanitized diagnostic instead of forwarding these records.
        return not _PRIVATE.get()


_FILTER = _SessionFilter()


@contextmanager
def private_session_logs() -> Iterator[None]:
    """Shield SDK tasks while preserving unrelated concurrent callers' diagnostics.

    Compatibility imports the SDK transports before entering here, so their loggers
    are registered. Filters remain installed but are inert outside this task context;
    removing them on exit would race with concurrent health checks.
    """
    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(logger, logging.Logger) and name.split(".")[0] in {
            "mcp",
            "httpx",
            "httpx2",
            "httpcore",
            "httpcore2",
        }:
            logger.addFilter(_FILTER)
    token = _PRIVATE.set(True)
    try:
        yield
    finally:
        _PRIVATE.reset(token)
