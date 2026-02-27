"""
Query Guard – shows every outgoing search query to the user and requests
confirmation before sending it to an external API.

This satisfies the privacy requirement that external queries must be "safe"
(topic/keywords only, never verbatim document text) and that the user can
inspect and approve them.
"""

from __future__ import annotations

import sys
from typing import Callable

from rich.console import Console
from rich.panel import Panel

_console = Console(stderr=True)


class QueryGuard:
    """
    Intercepts literature search queries and optionally prompts the user
    for approval before sending.

    Args:
        enabled:   If False, all queries pass through without prompting.
        auto_yes:  If True (non-interactive mode), auto-approve all queries.
        callback:  Optional function called with (query, approved) for logging.
    """

    def __init__(
        self,
        enabled: bool = True,
        auto_yes: bool = False,
        callback: Callable[[str, bool], None] | None = None,
    ) -> None:
        self.enabled = enabled
        self.auto_yes = auto_yes
        self.callback = callback
        self._approved_log: list[str] = []
        self._rejected_log: list[str] = []

    def approve(self, query: str, source: str = "") -> bool:
        """
        Check if a query is approved.

        Returns:
            True  → query may be sent
            False → query must be suppressed
        """
        if not self.enabled:
            return True

        label = f"[{source}] " if source else ""
        _console.print(
            Panel(
                f"[bold yellow]Safe Query:[/bold yellow] {label}[cyan]{query}[/cyan]",
                title="Query Guard – Externe Literatursuche",
                border_style="yellow",
            )
        )

        if self.auto_yes or not sys.stdin.isatty():
            _console.print("[dim]Auto-approved (non-interactive mode)[/dim]")
            approved = True
        else:
            answer = input("Query senden? [J/n] ").strip().lower()
            approved = answer in ("", "j", "y", "ja", "yes")

        if self.callback:
            self.callback(query, approved)

        if approved:
            self._approved_log.append(query)
            _console.print("[green]✓ Genehmigt[/green]")
        else:
            self._rejected_log.append(query)
            _console.print("[red]✗ Abgelehnt – Query wird nicht gesendet[/red]")

        return approved

    def approved_queries(self) -> list[str]:
        return list(self._approved_log)

    def rejected_queries(self) -> list[str]:
        return list(self._rejected_log)
