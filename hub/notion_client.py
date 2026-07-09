#!/usr/bin/env python3
"""
Notion integration layer — stub implementation.

Architecture is ready; implementation pending.  When activated, this will
pull ticket/task data from Notion databases and normalize it into the same
schema that jira_client produces, so the analytics pipeline works unchanged.

Notion API mapping:
    Notion concept          → Normalized field
    ─────────────────────────────────────────────
    Database                → Project board
    Page                    → Ticket
    Page title              → summary
    Status property         → status (mapped via STATUS_MAP)
    Select/Number prop      → story_points
    Relation to sprint DB   → sprint
    Multi-select prop       → components, labels
    Page parent (relation)  → parent_id (epic)
    Created time            → created
    Last edited time        → resolved (when status=done)
    Page history (versions) → reopen_count, time_in_status

Env vars (not yet used):
    NOTION_API_TOKEN        — Internal integration token
    NOTION_DATABASE_ID      — Primary task database ID
    NOTION_SPRINT_DB_ID     — Sprint/iteration database ID (optional)
    NOTION_EPIC_DB_ID       — Epic database ID (optional)

Status mapping (configurable per workspace):
    Notion statuses vary by workspace.  Default mapping below covers
    common patterns; override via NOTION_STATUS_MAP env var (JSON).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from pm_provider import (
    PMProvider, register_provider, normalize_status, DATA_DIR,
)

NOTION_CACHE = os.path.join(DATA_DIR, "notion_tickets.json")

NOTION_API_TOKEN = os.environ.get("NOTION_API_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
NOTION_SPRINT_DB_ID = os.environ.get("NOTION_SPRINT_DB_ID", "")
NOTION_EPIC_DB_ID = os.environ.get("NOTION_EPIC_DB_ID", "")

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"

STATUS_MAP = {
    "Not started": "to_do",
    "To Do": "to_do",
    "Backlog": "to_do",
    "In progress": "in_progress",
    "In Progress": "in_progress",
    "Doing": "in_progress",
    "In review": "in_review",
    "Review": "in_review",
    "Done": "done",
    "Complete": "done",
    "Completed": "done",
    "Archived": "done",
    "Blocked": "blocked",
    "On Hold": "blocked",
}

PROPERTY_NAMES = {
    "status": "Status",
    "story_points": "Story Points",
    "sprint": "Sprint",
    "components": "Components",
    "labels": "Labels",
    "assignee": "Assignee",
    "epic": "Epic",
    "priority": "Priority",
}


def _notion_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {NOTION_API_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }


def _notion_get(path: str) -> dict:
    """GET request to Notion API. Not yet active."""
    from urllib.request import Request, urlopen
    url = f"{NOTION_API_BASE}/{path}"
    req = Request(url, headers=_notion_headers())
    resp = urlopen(req, timeout=15)
    return json.loads(resp.read().decode())


def _notion_post(path: str, body: dict) -> dict:
    """POST request to Notion API. Not yet active."""
    from urllib.request import Request, urlopen
    url = f"{NOTION_API_BASE}/{path}"
    req = Request(url, data=json.dumps(body).encode(),
                  headers=_notion_headers(), method="POST")
    resp = urlopen(req, timeout=15)
    return json.loads(resp.read().decode())


def _extract_title(page: dict) -> str:
    """Extract page title from Notion page properties."""
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            titles = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in titles)
    return ""


def _extract_status(page: dict) -> str:
    """Extract and normalize status from Notion page."""
    prop = page.get("properties", {}).get(PROPERTY_NAMES["status"], {})
    if prop.get("type") == "status":
        raw = prop.get("status", {}).get("name", "")
    elif prop.get("type") == "select":
        raw = prop.get("select", {}).get("name", "") if prop.get("select") else ""
    else:
        raw = ""
    return STATUS_MAP.get(raw, normalize_status(raw))


def _extract_number(page: dict, prop_name: str) -> int | None:
    """Extract a number property."""
    prop = page.get("properties", {}).get(prop_name, {})
    if prop.get("type") == "number":
        return prop.get("number")
    return None


def _extract_select(page: dict, prop_name: str) -> str:
    """Extract a select property value."""
    prop = page.get("properties", {}).get(prop_name, {})
    if prop.get("type") == "select" and prop.get("select"):
        return prop["select"].get("name", "")
    return ""


def _extract_multi_select(page: dict, prop_name: str) -> list[str]:
    """Extract a multi-select property as list of names."""
    prop = page.get("properties", {}).get(prop_name, {})
    if prop.get("type") == "multi_select":
        return [item.get("name", "") for item in prop.get("multi_select", [])]
    return []


def _extract_relation_ids(page: dict, prop_name: str) -> list[str]:
    """Extract relation IDs from a relation property."""
    prop = page.get("properties", {}).get(prop_name, {})
    if prop.get("type") == "relation":
        return [r.get("id", "") for r in prop.get("relation", [])]
    return []


def _extract_assignee(page: dict) -> str:
    """Extract assignee name from a people property."""
    prop = page.get("properties", {}).get(PROPERTY_NAMES["assignee"], {})
    if prop.get("type") == "people":
        people = prop.get("people", [])
        if people:
            return people[0].get("name", "")
    return ""


def _page_to_ticket(page: dict) -> dict:
    """Convert a Notion page to normalized ticket dict."""
    page_id = page.get("id", "")
    created = page.get("created_time", "")
    last_edited = page.get("last_edited_time", "")

    status = _extract_status(page)
    resolved = last_edited if status == "done" else ""

    epic_ids = _extract_relation_ids(page, PROPERTY_NAMES["epic"])

    return {
        "ticket_id": f"notion-{page_id[:8]}",
        "summary": _extract_title(page),
        "status": status,
        "story_points": _extract_number(page, PROPERTY_NAMES["story_points"]),
        "sprint": _extract_select(page, PROPERTY_NAMES["sprint"]),
        "components": _extract_multi_select(page, PROPERTY_NAMES["components"]),
        "labels": _extract_multi_select(page, PROPERTY_NAMES["labels"]),
        "reopen_count": 0,
        "time_in_status": {},
        "created": created,
        "resolved": resolved,
        "assignee": _extract_assignee(page),
        "parent_id": epic_ids[0] if epic_ids else "",
        "provider": "notion",
        "notion_page_id": page_id,
    }


@register_provider("notion")
class NotionProvider(PMProvider):
    name = "notion"

    def is_configured(self) -> bool:
        return bool(NOTION_API_TOKEN and NOTION_DATABASE_ID)

    def fetch_ticket(self, ticket_id: str) -> dict | None:
        if not self.is_configured():
            return self._from_cache(ticket_id)
        page = _notion_get(f"pages/{ticket_id}")
        return _page_to_ticket(page) if page else None

    def fetch_tickets_bulk(self, ticket_ids: list[str]) -> dict[str, dict]:
        if not self.is_configured():
            cached = self.load_tickets()
            return {tid: cached[tid] for tid in ticket_ids if tid in cached}
        result = {}
        for tid in ticket_ids:
            t = self.fetch_ticket(tid)
            if t:
                result[t["ticket_id"]] = t
        return result

    def _query_database(self, database_id: str,
                        filter_obj: dict | None = None,
                        page_size: int = 100) -> list[dict]:
        """Query a Notion database with optional filter. Returns pages."""
        if not self.is_configured():
            return []

        body: dict = {"page_size": page_size}
        if filter_obj:
            body["filter"] = filter_obj

        pages = []
        has_more = True
        while has_more:
            resp = _notion_post(f"databases/{database_id}/query", body)
            pages.extend(resp.get("results", []))
            has_more = resp.get("has_more", False)
            if has_more:
                body["start_cursor"] = resp.get("next_cursor", "")
        return pages

    def _fetch_all_tickets(self) -> dict[str, dict]:
        """Fetch all tickets from the configured database."""
        pages = self._query_database(NOTION_DATABASE_ID)
        tickets = {}
        for page in pages:
            t = _page_to_ticket(page)
            tickets[t["ticket_id"]] = t
        return tickets

    def _compute_reopens(self, page_id: str) -> int:
        """Count reopens by scanning page version history.
        Notion doesn't expose granular status change history via API,
        so this checks page property versions (requires integration access)."""
        return 0

    def generate_mock_tickets(self, task_records: list[dict],
                              struggle_signals: dict | None = None) -> dict[str, dict]:
        """Generate mock Notion-style tickets mirroring jira_client behavior."""
        import random
        from presets import get_active_preset

        preset = get_active_preset()
        struggle_signals = struggle_signals or {}
        tickets: dict[str, dict] = {}

        sprint_names = [f"Sprint {i}" for i in range(20, 35)]
        label_pool = ["tech-debt", "p0-hotfix", "feature", "bug", "enhancement",
                       "security", "performance", "customer-reported"]

        for record in task_records:
            ticket_id = record.get("jira_id", "")
            if not ticket_id or ticket_id in tickets:
                continue

            employee = record.get("employee", "")
            project = record.get("project", "")
            topic = record.get("task_name", "task")

            signal = struggle_signals.get(employee, {})
            struggle = max(signal.get("duration_mult", 1.0),
                           signal.get("token_mult", 1.0))

            reopen = 0
            if struggle >= 1.5:
                reopen = random.randint(1, 3)
            elif struggle >= 1.3:
                reopen = random.randint(0, 1)

            is_done = random.random() < (0.95 if struggle < 1.5 else 0.7)
            status = "done" if is_done else random.choice(["in_progress", "in_review", "blocked"])

            from datetime import timedelta
            created = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(
                days=random.randint(0, 180))
            in_progress_h = random.gauss(4 * struggle, 2 * struggle)
            resolved = (created + timedelta(hours=in_progress_h)).isoformat() if is_done else ""

            tickets[ticket_id] = {
                "ticket_id": ticket_id,
                "summary": f"[{topic}] Task for {employee}",
                "status": status,
                "story_points": random.choice([1, 2, 3, 5, 8, 13]),
                "sprint": random.choice(sprint_names),
                "components": [project] if project else [],
                "labels": random.sample(label_pool, random.randint(1, 3)),
                "reopen_count": reopen,
                "time_in_status": {
                    "to_do": round(max(0, random.gauss(2, 1)), 1),
                    "in_progress": round(max(1, in_progress_h), 1),
                    "in_review": round(max(0.5, random.gauss(2, 1)), 1),
                    "blocked": round(max(0, random.gauss(0.5, 0.5)), 1) if struggle > 1.3 else 0,
                },
                "created": created.isoformat(),
                "resolved": resolved,
                "assignee": employee,
                "parent_id": "",
                "provider": "notion",
            }

        return tickets

    def save_tickets(self, tickets: dict[str, dict]) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(NOTION_CACHE, "w") as f:
            json.dump(tickets, f, indent=2)

    def load_tickets(self) -> dict[str, dict]:
        if os.path.exists(NOTION_CACHE):
            with open(NOTION_CACHE) as f:
                return json.load(f)
        return {}

    def _from_cache(self, ticket_id: str) -> dict | None:
        return self.load_tickets().get(ticket_id)

    def get_active_sprints(self) -> list[dict]:
        """Fetch active sprints from sprint database."""
        if not self.is_configured() or not NOTION_SPRINT_DB_ID:
            return []

        pages = self._query_database(
            NOTION_SPRINT_DB_ID,
            filter_obj={
                "property": "Status",
                "status": {"equals": "In Progress"},
            },
        )

        sprints = []
        for page in pages:
            sprints.append({
                "name": _extract_title(page),
                "start_date": "",
                "end_date": "",
                "ticket_ids": _extract_relation_ids(page, "Tasks"),
            })
        return sprints

    def get_epics(self) -> list[dict]:
        """Fetch epics from epic database."""
        if not self.is_configured() or not NOTION_EPIC_DB_ID:
            return []

        pages = self._query_database(NOTION_EPIC_DB_ID)

        epics = []
        for page in pages:
            epics.append({
                "id": page.get("id", ""),
                "name": _extract_title(page),
                "status": _extract_status(page),
                "ticket_ids": _extract_relation_ids(page, "Tasks"),
                "target_date": "",
            })
        return epics
