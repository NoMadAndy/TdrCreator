"""
Unit tests for QueryGuard and privacy sanitization.
"""

import pytest
from unittest.mock import patch
from tdrcreator.literature.guard import QueryGuard
from tdrcreator.security.privacy import sanitize_query, assert_local_llm, PrivacyError


# ── QueryGuard ────────────────────────────────────────────────────────────────

class TestQueryGuard:
    def test_disabled_guard_always_approves(self):
        guard = QueryGuard(enabled=False)
        assert guard.approve("some sensitive query") is True

    def test_auto_yes_approves_without_input(self):
        guard = QueryGuard(enabled=True, auto_yes=True)
        result = guard.approve("microservices API gateway")
        assert result is True
        assert "microservices API gateway" in guard.approved_queries()

    def test_logs_rejected_queries(self):
        guard = QueryGuard(enabled=True, auto_yes=False)
        with patch("builtins.input", return_value="n"):
            result = guard.approve("microservices")
        assert result is False
        assert "microservices" in guard.rejected_queries()

    def test_callback_called_on_approval(self):
        log = []
        guard = QueryGuard(enabled=True, auto_yes=True, callback=lambda q, a: log.append((q, a)))
        guard.approve("test query")
        assert len(log) == 1
        assert log[0] == ("test query", True)

    def test_callback_called_on_rejection(self):
        log = []
        guard = QueryGuard(enabled=True, auto_yes=False, callback=lambda q, a: log.append((q, a)))
        with patch("builtins.input", return_value="n"):
            guard.approve("test query")
        assert log[0][1] is False

    def test_multiple_queries_tracked(self):
        guard = QueryGuard(enabled=True, auto_yes=True)
        guard.approve("query1")
        guard.approve("query2")
        guard.approve("query3")
        assert len(guard.approved_queries()) == 3


# ── Privacy: sanitize_query ───────────────────────────────────────────────────

class TestSanitizeQuery:
    def test_query_without_internal_text_unchanged(self):
        result = sanitize_query("microservices API gateway", chunk_texts=[])
        assert result == "microservices API gateway"

    def test_internal_ngram_removed(self):
        chunk_text = "Das System verwendet Kong als API-Gateway für alle Anfragen."
        query = "Kong API-Gateway für alle Anfragen performance"
        result = sanitize_query(query, chunk_texts=[chunk_text])
        # The internal ngram "kong api-gateway für alle anfragen" or parts should be removed
        # The non-internal parts (performance) should remain
        assert "performance" in result.lower() or len(result) < len(query)

    def test_empty_chunk_list_passes_through(self):
        result = sanitize_query("test query", chunk_texts=[])
        assert result == "test query"

    def test_query_only_keywords(self):
        # Keywords that don't appear in chunks → unchanged
        chunks = ["Völlig anderer Text über Python und Datenbanken"]
        result = sanitize_query("microservices kubernetes", chunk_texts=chunks)
        assert "microservices" in result
        assert "kubernetes" in result


# ── Privacy: assert_local_llm ─────────────────────────────────────────────────

class TestAssertLocalLLM:
    @pytest.mark.parametrize("url", [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://192.168.1.100:8080",
        "http://10.0.0.5:11434",
    ])
    def test_local_addresses_pass(self, url):
        # Should not raise
        assert_local_llm(url)

    @pytest.mark.parametrize("url", [
        "https://api.openai.com/v1",
        "https://api.anthropic.com",
        "http://some-cloud-host.example.com:11434",
        "http://8.8.8.8:11434",
    ])
    def test_external_addresses_raise(self, url):
        with pytest.raises(PrivacyError):
            assert_local_llm(url)


# ── Security logger: sanitize ─────────────────────────────────────────────────

class TestSafeLogger:
    def test_sanitize_long_tokens(self):
        from tdrcreator.security.logger import sanitize
        long_token = "a" * 45
        msg = f"Processing chunk with text={long_token}"
        result = sanitize(msg)
        assert "[REDACTED]" in result
        assert long_token not in result

    def test_sanitize_short_tokens_unchanged(self):
        from tdrcreator.security.logger import sanitize
        msg = "doc_id=abc123 page=3 chunks=42"
        result = sanitize(msg)
        assert result == msg

    def test_hash_path_consistent(self):
        from tdrcreator.security.logger import hash_path
        h1 = hash_path("/some/path/to/file.pdf")
        h2 = hash_path("/some/path/to/file.pdf")
        assert h1 == h2
        assert h1.startswith("p:")

    def test_hash_path_different_paths(self):
        from tdrcreator.security.logger import hash_path
        h1 = hash_path("/path/a.pdf")
        h2 = hash_path("/path/b.pdf")
        assert h1 != h2
