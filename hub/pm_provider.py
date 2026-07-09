#!/usr/bin/env python3
"""
Project management provider abstraction.

Defines a unified interface that any PM tool (Jira, Notion, Linear, etc.)
must implement so the analytics pipeline can consume ticket data from any
backend through a single contract.

Normalized ticket schema (provider-agnostic):
    ticket_id       str     — unique ID (e.g. "VAL-123", "notion-abc123")
    summary         str     — ticket title / name
    status          str     — normalized: "to_do", "in_progress", "in_review", "done", "blocked"
    story_points    int|None
    sprint          str     — sprint / iteration name, empty if not in one
    components      list[str]
    labels          list[str]
    reopen_count    int     — times moved backwards (done/review → in_progress/to_do)
    time_in_status  dict[str, float]  — hours spent in each status
    created         str     — ISO datetime
    resolved        str     — ISO datetime, empty if unresolved
    assignee        str     — employee name
    parent_id       str     — epic / parent ticket ID, empty if top-level
    provider        str     — "jira", "notion", "linear", etc.

Consumers should use the `pm_` prefix for enriched record fields when
multiple providers coexist (e.g. `pm_status`, `pm_sprint`).  The current
codebase uses `jira_` prefixed fields; a migration shim in get_provider()
maps the normalized fields back to `jira_*` keys for backwards compat.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "data")

STATUS_MAP_CANONICAL = {
    "to do": "to_do",
    "todo": "to_do",
    "not started": "to_do",
    "open": "to_do",
    "in progress": "in_progress",
    "in review": "in_review",
    "review": "in_review",
    "done": "done",
    "closed": "done",
    "complete": "done",
    "completed": "done",
    "blocked": "blocked",
}


def normalize_status(raw: str) -> str:
    return STATUS_MAP_CANONICAL.get(raw.lower().strip(), raw.lower().strip())


class PMProvider(ABC):
    """Abstract base for project management integrations."""

    name: str = "base"

    @abstractmethod
    def fetch_ticket(self, ticket_id: str) -> dict | None:
        """Fetch a single ticket by ID. Returns normalized ticket dict or None."""

    @abstractmethod
    def fetch_tickets_bulk(self, ticket_ids: list[str]) -> dict[str, dict]:
        """Fetch multiple tickets. Returns {ticket_id: normalized_ticket}."""

    @abstractmethod
    def generate_mock_tickets(self, task_records: list[dict],
                              struggle_signals: dict | None = None) -> dict[str, dict]:
        """Generate synthetic ticket data for demo/testing."""

    @abstractmethod
    def save_tickets(self, tickets: dict[str, dict]) -> None:
        """Persist tickets to local cache."""

    @abstractmethod
    def load_tickets(self) -> dict[str, dict]:
        """Load tickets from local cache."""

    def enrich_records(self, records: list[dict]) -> list[dict]:
        """Add PM fields to task records using `jira_` prefix for compat."""
        tickets = self.load_tickets()
        enriched = []
        for record in records:
            r = dict(record)
            ticket = tickets.get(r.get("jira_id", ""))
            if ticket:
                r["jira_status"] = ticket.get("status", "")
                r["jira_story_points"] = ticket.get("story_points")
                r["jira_sprint"] = ticket.get("sprint", "")
                r["jira_components"] = ticket.get("components", [])
                r["jira_labels"] = ticket.get("labels", [])
                r["jira_reopen_count"] = ticket.get("reopen_count", 0)
                r["jira_time_in_status"] = ticket.get("time_in_status", {})
                r["jira_created"] = ticket.get("created", "")
                r["jira_resolved"] = ticket.get("resolved", "")
                r["pm_provider"] = self.name
            enriched.append(r)
        return enriched

    @abstractmethod
    def get_active_sprints(self) -> list[dict]:
        """Return active sprints/iterations.
        Each: {name, start_date, end_date, ticket_ids}."""

    @abstractmethod
    def get_epics(self) -> list[dict]:
        """Return epics/parent items.
        Each: {id, name, status, ticket_ids, target_date}."""

    @abstractmethod
    def is_configured(self) -> bool:
        """True if live credentials are set (not mock mode)."""


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type[PMProvider]] = {}


def register_provider(name: str):
    """Decorator to register a PMProvider subclass."""
    def wrapper(cls: type[PMProvider]):
        _PROVIDERS[name] = cls
        return cls
    return wrapper


def get_provider(name: str | None = None) -> PMProvider:
    """Get a provider instance by name. Defaults to env var PM_PROVIDER or 'jira'."""
    if name is None:
        name = os.environ.get("PM_PROVIDER", "jira")

    if name not in _PROVIDERS:
        available = ", ".join(_PROVIDERS.keys()) or "(none registered)"
        raise ValueError(f"Unknown PM provider '{name}'. Available: {available}")

    return _PROVIDERS[name]()


def list_providers() -> list[str]:
    return list(_PROVIDERS.keys())


def _ensure_providers_imported() -> None:
    """Import known provider modules so they register themselves."""
    for mod_name in ("jira_client", "notion_client"):
        try:
            __import__(mod_name)
        except Exception:
            pass


def load_all_tickets() -> dict[str, dict]:
    """Load tickets from all registered providers, merging results.

    Tries every registered provider; silently skips any that fail or have
    no cached data. Returns empty dict if nothing is available.
    """
    _ensure_providers_imported()
    all_tickets: dict[str, dict] = {}
    for name in list(_PROVIDERS.keys()):
        try:
            provider = _PROVIDERS[name]()
            tickets = provider.load_tickets()
            all_tickets.update(tickets)
        except Exception:
            pass
    return all_tickets


def enrich_records_any_provider(records: list[dict]) -> list[dict]:
    """Enrich task records with ticket data from whichever providers have data.

    Looks up tickets by the record's ``jira_id`` field (the generic ticket key
    used in task records regardless of which PM tool issued it).  Adds
    ``jira_*`` prefixed fields for backwards-compat with the analytics pipeline.
    """
    tickets = load_all_tickets()
    if not tickets:
        return records

    enriched = []
    for record in records:
        r = dict(record)
        ticket_key = r.get("jira_id", "")
        ticket = tickets.get(ticket_key)
        if ticket:
            raw_status = ticket.get("status", "")
            r["jira_status"] = raw_status
            r["jira_story_points"] = ticket.get("story_points")
            r["jira_sprint"] = ticket.get("sprint", "")
            r["jira_components"] = ticket.get("components", [])
            r["jira_labels"] = ticket.get("labels", [])
            r["jira_reopen_count"] = ticket.get("reopen_count", 0)
            r["jira_time_in_status"] = ticket.get("time_in_status", {})
            r["jira_created"] = ticket.get("created", "")
            r["jira_resolved"] = ticket.get("resolved", "")
            r["pm_provider"] = ticket.get("provider", "unknown")
        enriched.append(r)
    return enriched
