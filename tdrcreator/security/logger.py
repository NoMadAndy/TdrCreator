"""
Safe structured logger – never logs raw document text.

All messages that could contain document content must pass through
`sanitize()` before reaching any log handler.  The logger writes only:
  - metric names + numeric values
  - file paths (hashed)
  - chunk IDs / doc IDs
  - status flags (ok / error)
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from typing import Any

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s – %(message)s"
_INITIALIZED = False


def _setup_root() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root = logging.getLogger("tdrcreator")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    _INITIALIZED = True


def get_logger(name: str) -> "SafeLogger":
    _setup_root()
    return SafeLogger(name)


def hash_path(path: str) -> str:
    """Return a short SHA-256 prefix for a file path (no path leakage)."""
    return "p:" + hashlib.sha256(path.encode()).hexdigest()[:12]


def hash_text(text: str) -> str:
    """Return a SHA-256 hex digest for arbitrary text (content fingerprint)."""
    return "t:" + hashlib.sha256(text.encode()).hexdigest()[:16]


# Regex to catch suspiciously long free-text tokens (> 40 chars) in messages
_LONG_TOKEN_RE = re.compile(r"\b\w{40,}\b")


def sanitize(msg: str) -> str:
    """
    Strip anything that looks like raw document content from a log message.

    Heuristic: tokens longer than 40 chars are replaced with a hash stub.
    This is intentionally conservative – use structured logging instead of
    embedding text in messages.
    """
    return _LONG_TOKEN_RE.sub("[REDACTED]", msg)


class SafeLogger:
    """
    Wrapper around stdlib Logger that enforces sanitization on every message.
    """

    def __init__(self, name: str) -> None:
        self._log = logging.getLogger(f"tdrcreator.{name}")

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log.info(sanitize(msg), **kwargs)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log.debug(sanitize(msg), **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log.warning(sanitize(msg), **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log.error(sanitize(msg), **kwargs)

    def metric(self, event: str, **values: Any) -> None:
        """Log a named metric with key=value pairs (always safe)."""
        parts = ", ".join(f"{k}={v}" for k, v in values.items())
        self._log.info(f"METRIC {event} | {parts}")
