"""
Privacy enforcement utilities.

Rules enforced here:
  1. No raw document text may leave the process boundary (no external API
     calls with content).
  2. External network calls for *literature* are allowed only when the
     config flag `privacy.allow_network_for_literature` is True, and only
     for safe metadata queries (keywords / topic – never doc text).
  3. The LLM connector must point to a localhost or LAN address.
  4. Query sanitisation: strip any tokens that appear verbatim in the
     indexed chunks before sending a search query.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Iterable
from urllib.parse import urlparse

from tdrcreator.security.logger import get_logger

_log = get_logger("privacy")

# Literal local address patterns (fast path, no DNS lookup needed)
_LOCAL_PATTERNS = re.compile(
    r"^(localhost|127\.\d+\.\d+\.\d+|::1|0\.0\.0\.0"
    r"|10\.\d+\.\d+\.\d+"
    r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+"
    r"|192\.168\.\d+\.\d+)$",
    re.IGNORECASE,
)


def _resolves_to_private(host: str) -> bool:
    """
    Return True if `host` resolves via DNS to a private/loopback IP.
    This handles Docker service names (e.g. 'ollama' → 172.x.x.x).
    """
    try:
        ip_str = socket.gethostbyname(host)
        addr = ipaddress.ip_address(ip_str)
        return addr.is_private or addr.is_loopback
    except (socket.gaierror, ValueError):
        return False


def assert_local_llm(base_url: str) -> None:
    """
    Raise PrivacyError if the LLM base URL does not resolve to a local/LAN address.

    Accepts:
      - Literal localhost / RFC-1918 / loopback addresses (fast path)
      - Docker service hostnames that DNS-resolve to private IPs (e.g. 'ollama')
    """
    parsed = urlparse(base_url)
    host = parsed.hostname or ""

    if _LOCAL_PATTERNS.match(host):
        _log.info(f"LLM host check: host={host!r} – OK (literal local)")
        return

    if _resolves_to_private(host):
        _log.info(f"LLM host check: host={host!r} resolves to private IP – OK (Docker/LAN)")
        return

    raise PrivacyError(
        f"LLM base_url must point to a local/LAN address, got host={host!r}. "
        "Set llm_base_url to your Ollama instance (e.g. http://localhost:11434 "
        "or http://ollama:11434 in Docker)."
    )


def assert_literature_allowed(allow_network: bool) -> None:
    """Raise PrivacyError if literature network access is disabled."""
    if not allow_network:
        raise PrivacyError(
            "External literature search is disabled "
            "(privacy.allow_network_for_literature = false). "
            "Enable it in config.yaml or skip literature retrieval."
        )


def sanitize_query(query: str, chunk_texts: Iterable[str]) -> str:
    """
    Remove any verbatim fragment of indexed internal document text from a
    query string before it is sent to an external API.

    Strategy: tokenise chunk_texts into word-level n-grams (3–5 words).
    If any n-gram appears in the query string, replace it with a space.
    This is a best-effort guard; queries should be keyword-only to begin with.
    """
    chunk_list = list(chunk_texts)
    if not chunk_list:
        return query

    # Build a set of 4-gram strings from all chunk texts
    ngrams: set[str] = set()
    for text in chunk_list:
        words = text.lower().split()
        for n in (3, 4, 5):
            for i in range(len(words) - n + 1):
                ngrams.add(" ".join(words[i : i + n]))

    q_lower = query.lower()
    for gram in ngrams:
        if gram in q_lower:
            _log.warning(
                f"Privacy guard: removed internal text fragment from query "
                f"(hash={hash(gram) & 0xFFFF:04x})"
            )
            idx = q_lower.find(gram)
            query = query[:idx] + " " + query[idx + len(gram) :]
            q_lower = query.lower()

    return " ".join(query.split())  # normalise whitespace


class PrivacyError(RuntimeError):
    """Raised when a privacy constraint would be violated."""
