#!/usr/bin/env python3
"""
Jira integration layer — pulls ticket metadata and enriches task records.

Modes:
  - MOCK (default): generates realistic Jira ticket data matching our employee
    and project lists. No credentials needed.
  - LIVE: connects to a real Jira Cloud instance via REST API v3.
    Set JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN env vars.

The enriched data adds: ticket status, story points, sprint, component,
labels, reopen count (times moved back from Done/Review), and time-in-status.
"""

from __future__ import annotations

import json
import os
import random
from base64 import b64encode
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
JIRA_CACHE = os.path.join(DATA_DIR, "jira_tickets.json")

JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")

LIVE_MODE = bool(JIRA_DOMAIN and JIRA_EMAIL and JIRA_API_TOKEN)

from presets import get_active_preset

def _get_projects():
    return get_active_preset()["projects"]

STATUSES = ["To Do", "In Progress", "In Review", "Done", "Blocked"]
SPRINT_NAMES = [f"Sprint {i}" for i in range(20, 35)]
LABEL_POOL = ["tech-debt", "p0-hotfix", "feature", "bug", "enhancement",
              "security", "performance", "customer-reported", "onboarding"]


# ---------------------------------------------------------------------------
# Live Jira API
# ---------------------------------------------------------------------------

def _jira_headers() -> dict[str, str]:
    creds = b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _jira_get(path: str) -> dict:
    url = f"https://{JIRA_DOMAIN}/rest/api/3/{path}"
    req = Request(url, headers=_jira_headers())
    resp = urlopen(req, timeout=15)
    return json.loads(resp.read().decode())


def fetch_ticket_live(jira_id: str) -> dict | None:
    """Fetch a single ticket from live Jira."""
    try:
        issue = _jira_get(f"issue/{jira_id}?fields=summary,status,labels,"
                          f"components,customfield_10016,sprint,"
                          f"created,resolutiondate")
        fields = issue.get("fields", {})

        changelog = _jira_get(f"issue/{jira_id}?expand=changelog")
        reopen_count = 0
        status_times: dict[str, float] = {}
        prev_status = None
        prev_time = None

        for history in changelog.get("changelog", {}).get("histories", []):
            ts = history.get("created", "")
            for item in history.get("items", []):
                if item.get("field") == "status":
                    from_status = item.get("fromString", "")
                    to_status = item.get("toString", "")
                    if from_status in ("Done", "In Review") and to_status in ("In Progress", "To Do"):
                        reopen_count += 1
                    if prev_status and prev_time and ts:
                        try:
                            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            delta = (t - prev_time).total_seconds() / 3600
                            status_times[prev_status] = status_times.get(prev_status, 0) + delta
                        except (ValueError, TypeError):
                            pass
                    prev_status = to_status
                    try:
                        prev_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        prev_time = None

        sprint_field = fields.get("sprint") or {}
        return {
            "jira_id": jira_id,
            "summary": fields.get("summary", ""),
            "status": fields.get("status", {}).get("name", "Unknown"),
            "story_points": fields.get("customfield_10016"),
            "sprint": sprint_field.get("name", ""),
            "components": [c.get("name", "") for c in fields.get("components", [])],
            "labels": fields.get("labels", []),
            "reopen_count": reopen_count,
            "time_in_status": status_times,
            "created": fields.get("created", ""),
            "resolved": fields.get("resolutiondate", ""),
        }
    except (URLError, OSError, KeyError):
        return None


# ---------------------------------------------------------------------------
# Mock Jira data
# ---------------------------------------------------------------------------

def generate_mock_ticket(jira_id: str, project: str, topic: str,
                         employee: str, struggle_level: float = 1.0) -> dict:
    """Generate a realistic mock Jira ticket.

    struggle_level: 1.0 = normal, >1.5 = struggling (more reopens, longer in-progress).
    """
    proj_info = _get_projects().get(project, {"key": "GEN", "components": ["general"]})
    components = random.sample(proj_info["components"], min(2, len(proj_info["components"])))
    labels = random.sample(LABEL_POOL, random.randint(1, 3))
    sprint = random.choice(SPRINT_NAMES)
    points = random.choice([1, 2, 3, 5, 8, 13])

    base_reopen = 0 if struggle_level < 1.3 else random.randint(0, 1)
    if struggle_level >= 1.5:
        base_reopen = random.randint(1, 3)
    if struggle_level >= 2.0:
        base_reopen = random.randint(2, 5)

    created = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=random.randint(0, 180))

    in_progress_hours = random.gauss(4 * struggle_level, 2 * struggle_level)
    in_review_hours = random.gauss(2, 1)
    blocked_hours = random.gauss(1 * max(0, struggle_level - 1), 0.5) if struggle_level > 1.3 else 0

    is_done = random.random() < (0.95 if struggle_level < 1.5 else 0.7)
    status = "Done" if is_done else random.choice(["In Progress", "In Review", "Blocked"])

    resolved = (created + timedelta(hours=in_progress_hours + in_review_hours + blocked_hours)).isoformat() if is_done else ""

    return {
        "jira_id": jira_id,
        "summary": f"[{topic}] Task for {employee}",
        "status": status,
        "story_points": points,
        "sprint": sprint,
        "components": components,
        "labels": labels,
        "reopen_count": base_reopen,
        "time_in_status": {
            "To Do": round(max(0, random.gauss(2, 1)), 1),
            "In Progress": round(max(1, in_progress_hours), 1),
            "In Review": round(max(0.5, in_review_hours), 1),
            "Blocked": round(max(0, blocked_hours), 1),
        },
        "created": created.isoformat(),
        "resolved": resolved,
    }


def generate_mock_tickets(task_records: list[dict],
                          struggle_signals: dict | None = None) -> dict[str, dict]:
    """Generate mock Jira tickets for all task records."""
    tickets: dict[str, dict] = {}
    struggle_signals = struggle_signals or {}

    for record in task_records:
        jira_id = record.get("jira_id", "")
        if not jira_id or jira_id in tickets:
            continue

        employee = record.get("employee", "")
        project = record.get("project", "Valon-Platform")
        topic = record.get("task_name", "task")

        signal = struggle_signals.get(employee, {})
        struggle_level = max(signal.get("duration_mult", 1.0), signal.get("token_mult", 1.0))

        tickets[jira_id] = generate_mock_ticket(jira_id, project, topic, employee, struggle_level)

    return tickets


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def save_tickets(tickets: dict[str, dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(JIRA_CACHE, "w") as f:
        json.dump(tickets, f, indent=2)


def load_tickets() -> dict[str, dict]:
    if os.path.exists(JIRA_CACHE):
        with open(JIRA_CACHE) as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_ticket(jira_id: str) -> dict | None:
    """Fetch a ticket — live if configured, else from cache/mock."""
    if LIVE_MODE:
        return fetch_ticket_live(jira_id)
    cached = load_tickets()
    return cached.get(jira_id)


def enrich_records(records: list[dict]) -> list[dict]:
    """Add Jira fields to task records."""
    tickets = load_tickets()
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
        enriched.append(r)
    return enriched


def main() -> None:
    """CLI: generate mock tickets from existing task data."""
    preset = get_active_preset()

    task_file = os.path.join(DATA_DIR, "task_data.jsonl")
    if not os.path.exists(task_file):
        print("No task_data.jsonl found. Run generate_fake_data.py first.")
        return

    records = []
    with open(task_file) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    emp_struggles: dict[str, dict] = {}
    for (emp, _topic), signal in preset.get("struggle_signals", {}).items():
        if emp not in emp_struggles or signal["duration_mult"] > emp_struggles[emp].get("duration_mult", 1):
            emp_struggles[emp] = signal

    print(f"Preset: {preset['name']} — {preset['company']}")
    print(f"Generating mock Jira tickets for {len(records)} task records...")
    tickets = generate_mock_tickets(records, emp_struggles)
    save_tickets(tickets)
    print(f"Saved {len(tickets)} tickets -> {JIRA_CACHE}")

    reopens = [t["reopen_count"] for t in tickets.values()]
    high_reopen = [jid for jid, t in tickets.items() if t["reopen_count"] >= 2]
    print(f"\nReopen stats: avg={sum(reopens)/len(reopens):.1f}, "
          f"max={max(reopens)}, tickets with >=2 reopens: {len(high_reopen)}")

    if LIVE_MODE:
        print(f"\nLive mode available: {JIRA_DOMAIN}")
    else:
        print("\nMock mode (set JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN for live)")


# ---------------------------------------------------------------------------
# PMProvider adapter — registers Jira in the unified provider system.
# All logic delegates to the existing module-level functions above so
# nothing changes for current consumers.
# ---------------------------------------------------------------------------

try:
    from pm_provider import PMProvider, register_provider

    @register_provider("jira")
    class JiraProvider(PMProvider):
        name = "jira"

        def is_configured(self) -> bool:
            return LIVE_MODE

        def fetch_ticket(self, ticket_id: str) -> dict | None:
            return fetch_ticket(ticket_id)

        def fetch_tickets_bulk(self, ticket_ids: list[str]) -> dict[str, dict]:
            tickets = load_tickets()
            if LIVE_MODE:
                result = {}
                for tid in ticket_ids:
                    t = fetch_ticket_live(tid)
                    if t:
                        result[tid] = t
                return result
            return {tid: tickets[tid] for tid in ticket_ids if tid in tickets}

        def generate_mock_tickets(self, task_records: list[dict],
                                  struggle_signals: dict | None = None) -> dict[str, dict]:
            return generate_mock_tickets(task_records, struggle_signals)

        def save_tickets(self, tickets: dict[str, dict]) -> None:
            save_tickets(tickets)

        def load_tickets(self) -> dict[str, dict]:
            return load_tickets()

        def get_active_sprints(self) -> list[dict]:
            if not LIVE_MODE:
                return []
            try:
                boards = _jira_get("board")
                sprints = []
                for board in boards.get("values", [])[:5]:
                    resp = _jira_get(f"board/{board['id']}/sprint?state=active")
                    for s in resp.get("values", []):
                        sprints.append({
                            "name": s.get("name", ""),
                            "start_date": s.get("startDate", ""),
                            "end_date": s.get("endDate", ""),
                            "ticket_ids": [],
                        })
                return sprints
            except Exception:
                return []

        def get_epics(self) -> list[dict]:
            if not LIVE_MODE:
                return []
            try:
                resp = _jira_get("search?jql=issuetype=Epic&maxResults=50"
                                 "&fields=summary,status")
                epics = []
                for issue in resp.get("issues", []):
                    fields = issue.get("fields", {})
                    epics.append({
                        "id": issue.get("key", ""),
                        "name": fields.get("summary", ""),
                        "status": fields.get("status", {}).get("name", ""),
                        "ticket_ids": [],
                        "target_date": "",
                    })
                return epics
            except Exception:
                return []

except ImportError:
    pass


if __name__ == "__main__":
    main()
