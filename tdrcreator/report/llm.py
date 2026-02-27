"""
Local LLM connector via Ollama HTTP API.

PRIVACY: The LLM endpoint MUST be local (enforced by privacy.assert_local_llm).
Document text is sent to the local Ollama process – it never leaves the machine.
"""

from __future__ import annotations

import json
from typing import Iterator

import requests

from tdrcreator.security.logger import get_logger
from tdrcreator.security.privacy import assert_local_llm

_log = get_logger("report.llm")


def generate(
    prompt: str,
    base_url: str,
    model: str,
    temperature: float = 0.2,
    timeout: int = 120,
    stream: bool = False,
) -> str:
    """
    Call Ollama's /api/generate endpoint and return the full response text.

    Args:
        prompt:      Full prompt string (system + user content).
        base_url:    Ollama base URL, e.g. "http://localhost:11434".
        model:       Model name, e.g. "llama3" or "mistral".
        temperature: Sampling temperature (lower = more deterministic).
        timeout:     HTTP timeout in seconds.
        stream:      If True, stream tokens; still returns full string.
    """
    assert_local_llm(base_url)  # Privacy check: must be localhost/LAN

    url = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "")
        _log.metric(
            "llm_generate",
            model=model,
            prompt_len=len(prompt),
            response_len=len(text),
            done=data.get("done", False),
        )
        return text
    except requests.ConnectionError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {base_url}. "
            "Is Ollama running? Start it with: ollama serve"
        )
    except requests.Timeout:
        raise RuntimeError(
            f"LLM request timed out after {timeout}s. "
            "Try increasing llm_timeout in config.yaml or use a faster model."
        )
    except requests.HTTPError as e:
        raise RuntimeError(f"LLM HTTP error: {e}")


def list_models(base_url: str) -> list[str]:
    """Return list of locally available Ollama models."""
    assert_local_llm(base_url)
    try:
        resp = requests.get(base_url.rstrip("/") + "/api/tags", timeout=10)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []
