#!/usr/bin/env python3
"""
Slack Connector — comprehensive Slack workspace ingestion for team analytics.

Pulls activity signals, task acquisition/completion patterns, and workload
indicators from Slack channels. Designed to handle how different teams
actually use Slack: some use threads for tasks, some use channels per project,
some use emoji reactions for acknowledgment, etc.

Signals extracted:
  - Activity patterns: volume, response times, active hours, thread depth
  - Task signals: requests, assignments, completions, blockers, escalations
  - Workload indicators: @mention load, open threads, help-seeking, review asks
  - Collaboration: cross-channel activity, knowledge sharing, pairing

Requires a Slack Bot Token with these scopes:
  channels:history, channels:read, groups:history, groups:read,
  reactions:read, users:read, search:read

Usage:
    python3 slack_connector.py --token xoxb-... --channels general,engineering
    python3 slack_connector.py --config slack_config.json
    python3 slack_connector.py --token xoxb-... --scan-all --days 30
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "data")
SLACK_DATA_FILE = os.path.join(DATA_DIR, "slack_signals.json")
CONFIG_FILE = os.path.join(DATA_DIR, "slack_config.json")

SLACK_API = "https://slack.com/api"


# ─── Slack API Client ────────────────────────────────────────────────────

class SlackClient:
    """Minimal Slack Web API client using only stdlib."""

    def __init__(self, token: str):
        self.token = token
        self._user_cache: dict[str, dict] = {}
        self._channel_cache: dict[str, dict] = {}
        self._ssl_ctx = ssl.create_default_context()

    def _call(self, method: str, params: dict | None = None) -> dict:
        url = f"{SLACK_API}/{method}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
            url = f"{url}?{query}"

        req = Request(url, headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/x-www-form-urlencoded",
        })

        try:
            with urlopen(req, context=self._ssl_ctx, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except HTTPError as e:
            body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"Slack API {method} failed ({e.code}): {body}") from e
        except URLError as e:
            raise RuntimeError(f"Slack API {method} unreachable: {e.reason}") from e

        if not data.get("ok"):
            err = data.get("error", "unknown_error")
            if err == "ratelimited":
                retry_after = int(data.get("headers", {}).get("Retry-After", 5))
                time.sleep(retry_after)
                return self._call(method, params)
            raise RuntimeError(f"Slack API {method}: {err}")

        return data

    def get_user(self, user_id: str) -> dict:
        if user_id not in self._user_cache:
            data = self._call("users.info", {"user": user_id})
            self._user_cache[user_id] = data.get("user", {})
        return self._user_cache[user_id]

    def get_user_name(self, user_id: str) -> str:
        user = self.get_user(user_id)
        return user.get("real_name") or user.get("name") or user_id

    def list_channels(self, types: str = "public_channel,private_channel") -> list[dict]:
        channels = []
        cursor = None
        while True:
            params = {"types": types, "limit": "200", "exclude_archived": "true"}
            if cursor:
                params["cursor"] = cursor
            data = self._call("conversations.list", params)
            channels.extend(data.get("channels", []))
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return channels

    def get_channel_history(self, channel_id: str, oldest: float | None = None,
                           latest: float | None = None, limit: int = 200) -> list[dict]:
        messages = []
        cursor = None
        while True:
            params = {
                "channel": channel_id,
                "limit": str(min(limit - len(messages), 200)),
            }
            if oldest:
                params["oldest"] = str(oldest)
            if latest:
                params["latest"] = str(latest)
            if cursor:
                params["cursor"] = cursor
            data = self._call("conversations.history", params)
            messages.extend(data.get("messages", []))
            if len(messages) >= limit:
                break
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return messages

    def get_thread_replies(self, channel_id: str, thread_ts: str) -> list[dict]:
        data = self._call("conversations.replies", {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": "200",
        })
        return data.get("messages", [])

    def get_reactions(self, channel_id: str, timestamp: str) -> list[dict]:
        try:
            data = self._call("reactions.get", {
                "channel": channel_id,
                "timestamp": timestamp,
            })
            msg = data.get("message", {})
            return msg.get("reactions", [])
        except RuntimeError:
            return []


# ─── Signal Detection Patterns ────────────────────────────────────────────

TASK_REQUEST_PATTERNS = [
    re.compile(r'\b(?:can you|could you|please|need you to|would you)\b', re.I),
    re.compile(r'\b(?:todo|to-do|action item|task|ticket)\b', re.I),
    re.compile(r'\b(?:assign|assigned|take on|pick up|own this|handle this)\b', re.I),
    re.compile(r'\b(?:by eod|by end of day|by tomorrow|deadline|due date|asap|urgent)\b', re.I),
    re.compile(r'\b(?:priority|p0|p1|p2|critical|blocker)\b', re.I),
]

TASK_COMPLETION_PATTERNS = [
    re.compile(r'\b(?:done|completed|finished|shipped|merged|deployed|resolved|closed)\b', re.I),
    re.compile(r'\b(?:fixed|landed|released|pushed|live|in prod)\b', re.I),
    re.compile(r'\b(?:pr merged|pull request merged|pr approved)\b', re.I),
    re.compile(r':white_check_mark:|:heavy_check_mark:|:rocket:|:tada:|:shipit:', re.I),
]

BLOCKER_PATTERNS = [
    re.compile(r'\b(?:blocked|blocking|stuck|can\'t proceed|waiting on|depends on)\b', re.I),
    re.compile(r'\b(?:need help|anyone know|how do i|struggling with)\b', re.I),
    re.compile(r'\b(?:broken|down|outage|incident|fire|emergency)\b', re.I),
]

REVIEW_REQUEST_PATTERNS = [
    re.compile(r'\b(?:review|pr review|code review|eyes on|lgtm needed|feedback)\b', re.I),
    re.compile(r'\b(?:ptal|please take a look|can someone review)\b', re.I),
    re.compile(r'github\.com/[^\s]+/pull/\d+', re.I),
]

ESCALATION_PATTERNS = [
    re.compile(r'\b(?:escalat|escalaing|raised to|flagging for|cc\'ing|looping in)\b', re.I),
    re.compile(r'\b(?:still waiting|no response|follow up|following up|bumping)\b', re.I),
]

ACKNOWLEDGMENT_REACTIONS = {"eyes", "thumbsup", "+1", "ok_hand", "white_check_mark",
                            "heavy_check_mark", "raised_hands", "saluting_face"}
COMPLETION_REACTIONS = {"white_check_mark", "heavy_check_mark", "rocket", "tada",
                        "shipit", "done", "merged"}
BLOCKER_REACTIONS = {"octagonal_sign", "no_entry", "x", "warning", "rotating_light"}

JIRA_PATTERN = re.compile(r'\b([A-Z][A-Z0-9]+-\d+)\b')
PR_PATTERN = re.compile(r'(?:github|gitlab)\.com/[^\s/]+/[^\s/]+/(?:pull|merge_requests)/(\d+)')


# ─── Channel Classification ──────────────────────────────────────────────

CHANNEL_TYPE_PATTERNS = {
    "engineering": re.compile(r'(?:eng|dev|backend|frontend|infra|platform|sre|devops)', re.I),
    "project": re.compile(r'(?:proj|epic|sprint|team-|squad-)', re.I),
    "support": re.compile(r'(?:help|support|questions|ask-|how-to)', re.I),
    "incident": re.compile(r'(?:incident|oncall|on-call|alerts|pages|outage)', re.I),
    "deploy": re.compile(r'(?:deploy|release|ship|staging|prod)', re.I),
    "review": re.compile(r'(?:review|pr-|pull-request|code-review)', re.I),
    "general": re.compile(r'(?:general|random|watercooler|social)', re.I),
    "standup": re.compile(r'(?:standup|stand-up|daily|check-in|sync)', re.I),
}


def classify_channel(name: str, topic: str = "", purpose: str = "") -> str:
    text = f"{name} {topic} {purpose}"
    for ctype, pattern in CHANNEL_TYPE_PATTERNS.items():
        if pattern.search(text):
            return ctype
    return "other"


# ─── Message Analysis ─────────────────────────────────────────────────────

def _match_patterns(text: str, patterns: list[re.Pattern]) -> int:
    return sum(1 for p in patterns if p.search(text))


def _extract_mentions(text: str) -> list[str]:
    return re.findall(r'<@(U[A-Z0-9]+)>', text)


def _extract_links(text: str) -> dict:
    jira_ids = JIRA_PATTERN.findall(text)
    pr_numbers = PR_PATTERN.findall(text)
    urls = re.findall(r'https?://[^\s>]+', text)
    return {"jira_ids": jira_ids, "pr_numbers": pr_numbers, "url_count": len(urls)}


def analyze_message(msg: dict, channel_type: str) -> dict:
    """Extract all signals from a single message."""
    text = msg.get("text", "")
    user = msg.get("user", "")
    ts = float(msg.get("ts", 0))
    thread_ts = msg.get("thread_ts")
    is_thread_reply = thread_ts is not None and thread_ts != msg.get("ts")
    reactions = msg.get("reactions", [])

    signals = {
        "user": user,
        "timestamp": ts,
        "datetime": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
        "channel_type": channel_type,
        "is_thread_reply": is_thread_reply,
        "is_thread_parent": thread_ts == msg.get("ts") and msg.get("reply_count", 0) > 0,
        "reply_count": msg.get("reply_count", 0),
        "reply_users_count": msg.get("reply_users_count", 0),
        "text_length": len(text),
        "has_code_block": "```" in text,
        "has_attachment": bool(msg.get("files") or msg.get("attachments")),

        "task_request_score": _match_patterns(text, TASK_REQUEST_PATTERNS),
        "task_completion_score": _match_patterns(text, TASK_COMPLETION_PATTERNS),
        "blocker_score": _match_patterns(text, BLOCKER_PATTERNS),
        "review_request_score": _match_patterns(text, REVIEW_REQUEST_PATTERNS),
        "escalation_score": _match_patterns(text, ESCALATION_PATTERNS),

        "mentions": _extract_mentions(text),
        "links": _extract_links(text),

        "ack_reactions": sum(r["count"] for r in reactions
                            if r["name"] in ACKNOWLEDGMENT_REACTIONS),
        "completion_reactions": sum(r["count"] for r in reactions
                                   if r["name"] in COMPLETION_REACTIONS),
        "blocker_reactions": sum(r["count"] for r in reactions
                                if r["name"] in BLOCKER_REACTIONS),
    }
    return signals


# ─── Per-Employee Aggregation ─────────────────────────────────────────────

def aggregate_employee_signals(messages_signals: list[dict],
                               client: SlackClient) -> dict[str, dict]:
    """Aggregate raw message signals into per-employee metrics."""
    emp: dict[str, dict] = defaultdict(lambda: {
        "message_count": 0,
        "thread_starts": 0,
        "thread_replies": 0,
        "total_text_length": 0,
        "code_blocks_shared": 0,
        "attachments_shared": 0,
        "tasks_requested_of_others": 0,
        "tasks_completed_announced": 0,
        "blockers_raised": 0,
        "reviews_requested": 0,
        "escalations": 0,
        "mentions_sent": 0,
        "mentions_received": 0,
        "ack_reactions_received": 0,
        "completion_reactions_received": 0,
        "threads_started_with_replies": 0,
        "avg_thread_depth": 0,
        "jira_references": [],
        "pr_references": [],
        "active_hours": defaultdict(int),
        "active_channels": defaultdict(int),
        "response_times": [],
        "help_seeking_count": 0,
    })

    thread_parents: dict[str, dict] = {}
    for sig in messages_signals:
        if sig.get("is_thread_parent"):
            thread_parents[str(sig["timestamp"])] = sig

    for sig in messages_signals:
        uid = sig["user"]
        if not uid:
            continue

        e = emp[uid]
        e["message_count"] += 1
        e["total_text_length"] += sig["text_length"]

        if sig["has_code_block"]:
            e["code_blocks_shared"] += 1
        if sig["has_attachment"]:
            e["attachments_shared"] += 1

        if sig["is_thread_parent"]:
            e["thread_starts"] += 1
            if sig["reply_count"] > 0:
                e["threads_started_with_replies"] += 1
        if sig["is_thread_reply"]:
            e["thread_replies"] += 1

        if sig["task_request_score"] >= 2:
            e["tasks_requested_of_others"] += 1
        if sig["task_completion_score"] >= 1:
            e["tasks_completed_announced"] += 1
        if sig["blocker_score"] >= 2:
            e["blockers_raised"] += 1
            e["help_seeking_count"] += 1
        elif sig["blocker_score"] >= 1:
            e["help_seeking_count"] += 1
        if sig["review_request_score"] >= 1:
            e["reviews_requested"] += 1
        if sig["escalation_score"] >= 1:
            e["escalations"] += 1

        e["mentions_sent"] += len(sig["mentions"])
        e["ack_reactions_received"] += sig["ack_reactions"]
        e["completion_reactions_received"] += sig["completion_reactions"]

        for mentioned_uid in sig["mentions"]:
            emp[mentioned_uid]["mentions_received"] += 1

        e["jira_references"].extend(sig["links"]["jira_ids"])
        e["pr_references"].extend(sig["links"]["pr_numbers"])

        if sig["datetime"]:
            hour = datetime.fromisoformat(sig["datetime"]).hour
            e["active_hours"][hour] += 1

        e["active_channels"][sig["channel_type"]] += 1

    result = {}
    for uid, metrics in emp.items():
        try:
            name = client.get_user_name(uid)
        except Exception:
            name = uid

        if metrics["message_count"] == 0:
            continue

        thread_depths = []
        for sig in messages_signals:
            if sig["user"] == uid and sig.get("is_thread_parent") and sig["reply_count"] > 0:
                thread_depths.append(sig["reply_count"])

        jira_unique = list(set(metrics["jira_references"]))
        pr_unique = list(set(metrics["pr_references"]))

        peak_hours = sorted(metrics["active_hours"].items(), key=lambda x: -x[1])[:3]
        top_channel_types = sorted(metrics["active_channels"].items(), key=lambda x: -x[1])

        result[name] = {
            "slack_user_id": uid,
            "message_count": metrics["message_count"],
            "thread_starts": metrics["thread_starts"],
            "thread_replies": metrics["thread_replies"],
            "threads_with_engagement": metrics["threads_started_with_replies"],
            "avg_message_length": round(metrics["total_text_length"] / metrics["message_count"]),
            "code_blocks_shared": metrics["code_blocks_shared"],
            "attachments_shared": metrics["attachments_shared"],

            "tasks_requested_of_others": metrics["tasks_requested_of_others"],
            "tasks_completed_announced": metrics["tasks_completed_announced"],
            "blockers_raised": metrics["blockers_raised"],
            "reviews_requested": metrics["reviews_requested"],
            "escalations": metrics["escalations"],
            "help_seeking_count": metrics["help_seeking_count"],

            "mentions_sent": metrics["mentions_sent"],
            "mentions_received": metrics["mentions_received"],
            "mention_ratio": round(metrics["mentions_received"] /
                                   max(metrics["mentions_sent"], 1), 2),
            "ack_reactions_received": metrics["ack_reactions_received"],
            "completion_reactions_received": metrics["completion_reactions_received"],

            "jira_tickets_referenced": jira_unique,
            "jira_reference_count": len(jira_unique),
            "pr_references": pr_unique,
            "pr_reference_count": len(pr_unique),

            "avg_thread_depth": round(sum(thread_depths) / max(len(thread_depths), 1), 1),
            "peak_hours": [{"hour": h, "count": c} for h, c in peak_hours],
            "channel_type_distribution": dict(top_channel_types),

            "demand_score": _compute_demand_score(metrics),
            "throughput_score": _compute_throughput_score(metrics),
            "collaboration_score": _compute_collaboration_score(metrics),
        }

    return result


def _compute_demand_score(m: dict) -> float:
    """How much demand/pressure is on this person (higher = more loaded)."""
    score = (
        m["mentions_received"] * 2.0
        + m["blockers_raised"] * 3.0
        + m["escalations"] * 4.0
        + m["help_seeking_count"] * 1.5
    )
    return round(score / max(m["message_count"], 1), 2)


def _compute_throughput_score(m: dict) -> float:
    """How much work this person is completing/shipping."""
    score = (
        m["tasks_completed_announced"] * 3.0
        + m["completion_reactions_received"] * 2.0
        + len(set(m["pr_references"])) * 2.5
        + len(set(m["jira_references"])) * 1.5
    )
    return round(score / max(m["message_count"], 1), 2)


def _compute_collaboration_score(m: dict) -> float:
    """How collaborative this person is (mentoring, reviewing, cross-channel)."""
    score = (
        m["thread_replies"] * 1.0
        + m["mentions_sent"] * 0.5
        + m["code_blocks_shared"] * 2.0
        + m["reviews_requested"] * 1.5
        + m["threads_started_with_replies"] * 1.0
        + len(m["active_channels"]) * 0.5
    )
    return round(score / max(m["message_count"], 1), 2)


# ─── Channel-Level Aggregation ────────────────────────────────────────────

def aggregate_channel_signals(messages_signals: list[dict],
                              channel_name: str, channel_type: str) -> dict:
    """Aggregate signals at the channel level for team pattern detection."""
    if not messages_signals:
        return {}

    total = len(messages_signals)
    task_requests = sum(1 for s in messages_signals if s["task_request_score"] >= 2)
    completions = sum(1 for s in messages_signals if s["task_completion_score"] >= 1)
    blockers = sum(1 for s in messages_signals if s["blocker_score"] >= 1)
    reviews = sum(1 for s in messages_signals if s["review_request_score"] >= 1)
    escalations = sum(1 for s in messages_signals if s["escalation_score"] >= 1)
    threads = sum(1 for s in messages_signals if s["is_thread_parent"])
    thread_replies = sum(1 for s in messages_signals if s["is_thread_reply"])
    code_msgs = sum(1 for s in messages_signals if s["has_code_block"])

    unique_users = len(set(s["user"] for s in messages_signals if s["user"]))

    timestamps = sorted(s["timestamp"] for s in messages_signals if s["timestamp"])
    if len(timestamps) >= 2:
        span_days = (timestamps[-1] - timestamps[0]) / 86400
        msgs_per_day = total / max(span_days, 1)
    else:
        msgs_per_day = 0

    return {
        "channel_name": channel_name,
        "channel_type": channel_type,
        "total_messages": total,
        "unique_users": unique_users,
        "messages_per_day": round(msgs_per_day, 1),
        "task_requests": task_requests,
        "completions": completions,
        "blockers": blockers,
        "reviews": reviews,
        "escalations": escalations,
        "thread_count": threads,
        "thread_reply_count": thread_replies,
        "thread_ratio": round(thread_replies / max(threads, 1), 1),
        "code_message_ratio": round(code_msgs / max(total, 1), 2),
        "task_completion_ratio": round(completions / max(task_requests, 1), 2),
        "blocker_rate": round(blockers / max(total, 1), 3),
        "escalation_rate": round(escalations / max(total, 1), 3),
    }


# ─── Team Workflow Pattern Detection ──────────────────────────────────────

def detect_workflow_patterns(employee_signals: dict[str, dict],
                            channel_signals: list[dict]) -> dict:
    """Detect how the team uses Slack for task management."""
    patterns = {
        "task_acquisition": "unknown",
        "completion_tracking": "unknown",
        "review_culture": "unknown",
        "help_seeking": "unknown",
        "workload_distribution": "unknown",
        "observations": [],
    }

    if not employee_signals:
        return patterns

    employees = list(employee_signals.values())

    # Task acquisition pattern
    total_task_requests = sum(e["tasks_requested_of_others"] for e in employees)
    total_jira_refs = sum(e["jira_reference_count"] for e in employees)
    total_mentions = sum(e["mentions_sent"] for e in employees)

    if total_jira_refs > total_task_requests * 2:
        patterns["task_acquisition"] = "ticket-driven"
        patterns["observations"].append(
            "Team primarily acquires tasks through Jira tickets referenced in Slack")
    elif total_task_requests > total_mentions * 0.3:
        patterns["task_acquisition"] = "request-driven"
        patterns["observations"].append(
            "Tasks are frequently assigned via direct Slack requests and @mentions")
    elif total_mentions > total_task_requests * 3:
        patterns["task_acquisition"] = "mention-driven"
        patterns["observations"].append(
            "Work is coordinated through @mentions rather than formal task requests")
    else:
        patterns["task_acquisition"] = "mixed"
        patterns["observations"].append(
            "Team uses a mix of tickets, direct requests, and @mentions for task flow")

    # Completion tracking
    total_completions = sum(e["tasks_completed_announced"] for e in employees)
    total_completion_reactions = sum(e["completion_reactions_received"] for e in employees)
    total_pr_refs = sum(e["pr_reference_count"] for e in employees)

    if total_pr_refs > total_completions:
        patterns["completion_tracking"] = "pr-driven"
        patterns["observations"].append(
            "Completions are primarily tracked through PR references in Slack")
    elif total_completion_reactions > total_completions * 2:
        patterns["completion_tracking"] = "reaction-driven"
        patterns["observations"].append(
            "Team uses emoji reactions heavily to acknowledge completed work")
    elif total_completions > 0:
        patterns["completion_tracking"] = "announcement-driven"
        patterns["observations"].append(
            "Team members announce completions in channel messages")
    else:
        patterns["completion_tracking"] = "minimal"
        patterns["observations"].append(
            "Little completion signaling in Slack — work may be tracked elsewhere")

    # Review culture
    total_reviews = sum(e["reviews_requested"] for e in employees)
    review_channels = [c for c in channel_signals if c.get("channel_type") == "review"]
    if review_channels:
        patterns["review_culture"] = "dedicated-channel"
        patterns["observations"].append(
            "Team has dedicated review channels for code review coordination")
    elif total_reviews > len(employees) * 2:
        patterns["review_culture"] = "active-inline"
        patterns["observations"].append(
            "Reviews are actively requested inline across channels")
    else:
        patterns["review_culture"] = "minimal"
        patterns["observations"].append(
            "Limited review coordination in Slack — may use GitHub/GitLab directly")

    # Help-seeking pattern
    total_help = sum(e["help_seeking_count"] for e in employees)
    total_blockers = sum(e["blockers_raised"] for e in employees)
    support_channels = [c for c in channel_signals if c.get("channel_type") == "support"]
    if support_channels:
        patterns["help_seeking"] = "support-channel"
        patterns["observations"].append(
            "Team has dedicated help/support channels for technical questions")
    elif total_help > len(employees) * 3:
        patterns["help_seeking"] = "distributed"
        patterns["observations"].append(
            "Help-seeking is distributed across channels (no dedicated support channel)")
    else:
        patterns["help_seeking"] = "low"
        patterns["observations"].append(
            "Relatively few help requests in Slack — team may be self-sufficient or using other channels")

    # Workload distribution
    if employees:
        demand_scores = [e["demand_score"] for e in employees]
        avg_demand = sum(demand_scores) / len(demand_scores)
        max_demand = max(demand_scores)
        demand_spread = max_demand / max(avg_demand, 0.01)

        if demand_spread > 3.0:
            patterns["workload_distribution"] = "highly-uneven"
            overloaded = [name for name, e in employee_signals.items()
                          if e["demand_score"] > avg_demand * 2]
            patterns["observations"].append(
                f"Workload is highly uneven — {', '.join(overloaded[:3])} carry "
                f"disproportionate demand")
        elif demand_spread > 1.8:
            patterns["workload_distribution"] = "somewhat-uneven"
            patterns["observations"].append(
                "Moderate workload imbalance detected across team members")
        else:
            patterns["workload_distribution"] = "balanced"
            patterns["observations"].append(
                "Workload appears relatively balanced across team members")

    return patterns


# ─── Main Ingestion Pipeline ──────────────────────────────────────────────

def ingest_slack(token: str, channel_names: list[str] | None = None,
                 scan_all: bool = False, days: int = 14,
                 include_threads: bool = True) -> dict:
    """Run the full Slack ingestion pipeline.

    Returns a dict with employee_signals, channel_signals, workflow_patterns,
    and metadata.
    """
    client = SlackClient(token)
    print("[slack] Connecting to Slack workspace...")

    # Resolve channels
    all_channels = client.list_channels()
    print(f"[slack] Found {len(all_channels)} channels in workspace")

    if scan_all:
        targets = all_channels
    elif channel_names:
        name_set = {n.lower().strip("#") for n in channel_names}
        targets = [c for c in all_channels if c["name"].lower() in name_set]
        found = {c["name"].lower() for c in targets}
        missing = name_set - found
        if missing:
            print(f"[slack] Warning: channels not found: {', '.join(missing)}")
    else:
        targets = all_channels[:10]
        print(f"[slack] No channels specified — scanning first 10")

    oldest = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    all_msg_signals: list[dict] = []
    channel_summaries: list[dict] = []

    for ch in targets:
        ch_name = ch["name"]
        ch_id = ch["id"]
        ch_type = classify_channel(ch_name, ch.get("topic", {}).get("value", ""),
                                    ch.get("purpose", {}).get("value", ""))

        print(f"[slack] Scanning #{ch_name} ({ch_type})...")
        messages = client.get_channel_history(ch_id, oldest=oldest, limit=1000)

        if not messages:
            continue

        # Enrich with thread data and reactions
        msg_signals = []
        for msg in messages:
            if msg.get("subtype") in ("channel_join", "channel_leave", "bot_message"):
                continue

            sig = analyze_message(msg, ch_type)

            # Fetch thread replies for parent messages
            if include_threads and sig["is_thread_parent"] and sig["reply_count"] > 0:
                try:
                    replies = client.get_thread_replies(ch_id, msg["ts"])
                    for reply in replies[1:]:
                        reply_sig = analyze_message(reply, ch_type)
                        msg_signals.append(reply_sig)
                except Exception:
                    pass

            # Fetch reactions if not already in message
            if not msg.get("reactions"):
                try:
                    reactions = client.get_reactions(ch_id, msg["ts"])
                    if reactions:
                        sig["ack_reactions"] = sum(
                            r["count"] for r in reactions
                            if r["name"] in ACKNOWLEDGMENT_REACTIONS)
                        sig["completion_reactions"] = sum(
                            r["count"] for r in reactions
                            if r["name"] in COMPLETION_REACTIONS)
                except Exception:
                    pass

            msg_signals.append(sig)

        all_msg_signals.extend(msg_signals)
        ch_summary = aggregate_channel_signals(msg_signals, ch_name, ch_type)
        if ch_summary:
            channel_summaries.append(ch_summary)
            print(f"  {ch_summary['total_messages']} msgs, "
                  f"{ch_summary['unique_users']} users, "
                  f"{ch_summary['task_requests']} task requests, "
                  f"{ch_summary['completions']} completions")

    print(f"\n[slack] Aggregating signals for {len(all_msg_signals)} messages...")
    employee_signals = aggregate_employee_signals(all_msg_signals, client)

    print(f"[slack] Detected {len(employee_signals)} active employees")
    workflow_patterns = detect_workflow_patterns(employee_signals, channel_summaries)

    result = {
        "metadata": {
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "days_scanned": days,
            "channels_scanned": len(targets),
            "total_messages_analyzed": len(all_msg_signals),
            "employees_detected": len(employee_signals),
        },
        "employee_signals": employee_signals,
        "channel_signals": channel_summaries,
        "workflow_patterns": workflow_patterns,
    }

    # Save to disk
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SLACK_DATA_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"[slack] Signals saved to {SLACK_DATA_FILE}")

    return result


# ─── Config ───────────────────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(config: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


# ─── Name Matching ────────────────────────────────────────────────────────

def match_slack_to_employees(slack_signals: dict[str, dict],
                             preset_employees: list[str]) -> dict[str, str]:
    """Best-effort match Slack display names to preset employee names.

    Returns {slack_name: preset_employee_name} for matches found.
    """
    matches = {}
    preset_lower = {e.lower(): e for e in preset_employees}
    preset_parts = {}
    for e in preset_employees:
        parts = e.lower().split()
        for p in parts:
            preset_parts.setdefault(p, []).append(e)

    for slack_name in slack_signals:
        sn_lower = slack_name.lower()
        if sn_lower in preset_lower:
            matches[slack_name] = preset_lower[sn_lower]
            continue

        sn_parts = sn_lower.split()
        best_match = None
        best_score = 0
        for preset_name in preset_employees:
            pn_parts = preset_name.lower().split()
            overlap = len(set(sn_parts) & set(pn_parts))
            if overlap > best_score:
                best_score = overlap
                best_match = preset_name
        if best_score > 0 and best_match:
            matches[slack_name] = best_match

    return matches


# ─── CLI ──────────────────────────────────────────────────────────────────

def print_summary(result: dict) -> None:
    meta = result["metadata"]
    print(f"\n{'='*60}")
    print("SLACK INGESTION SUMMARY")
    print(f"{'='*60}")
    print(f"Period: last {meta['days_scanned']} days")
    print(f"Channels scanned: {meta['channels_scanned']}")
    print(f"Messages analyzed: {meta['total_messages_analyzed']}")
    print(f"Employees detected: {meta['employees_detected']}")

    wp = result["workflow_patterns"]
    print(f"\nWORKFLOW PATTERNS")
    print(f"  Task acquisition: {wp['task_acquisition']}")
    print(f"  Completion tracking: {wp['completion_tracking']}")
    print(f"  Review culture: {wp['review_culture']}")
    print(f"  Help-seeking: {wp['help_seeking']}")
    print(f"  Workload distribution: {wp['workload_distribution']}")
    for obs in wp["observations"]:
        print(f"  → {obs}")

    print(f"\nTOP EMPLOYEES BY DEMAND")
    emp = result["employee_signals"]
    by_demand = sorted(emp.items(), key=lambda x: -x[1]["demand_score"])[:5]
    for name, sig in by_demand:
        print(f"  {name}: demand={sig['demand_score']}, "
              f"throughput={sig['throughput_score']}, "
              f"collab={sig['collaboration_score']}, "
              f"msgs={sig['message_count']}")

    print(f"\nCHANNEL ACTIVITY")
    for ch in sorted(result["channel_signals"], key=lambda x: -x["total_messages"]):
        print(f"  #{ch['channel_name']} ({ch['channel_type']}): "
              f"{ch['total_messages']} msgs, "
              f"{ch['task_requests']} tasks, "
              f"{ch['completions']} done, "
              f"{ch['blockers']} blockers")


def main():
    parser = argparse.ArgumentParser(description="Slack workspace ingestion for team analytics")
    parser.add_argument("--token", help="Slack Bot Token (xoxb-...)")
    parser.add_argument("--channels", help="Comma-separated channel names to scan")
    parser.add_argument("--scan-all", action="store_true", help="Scan all channels")
    parser.add_argument("--days", type=int, default=14, help="Days of history to scan (default: 14)")
    parser.add_argument("--no-threads", action="store_true", help="Skip thread replies (faster)")
    parser.add_argument("--config", help="Path to config JSON file")
    parser.add_argument("--save-config", action="store_true",
                        help="Save token and channels to config for reuse")
    args = parser.parse_args()

    config = {}
    if args.config:
        with open(args.config) as f:
            config = json.load(f)
    elif os.path.exists(CONFIG_FILE):
        config = load_config()

    token = args.token or os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("Error: No Slack token provided.")
        print("  Use --token xoxb-... or set SLACK_BOT_TOKEN env var.")
        return

    channel_names = None
    if args.channels:
        channel_names = [c.strip() for c in args.channels.split(",")]
    elif config.get("channels"):
        channel_names = config["channels"]

    if args.save_config:
        save_config({
            "channels": channel_names or [],
            "days": args.days,
        })
        print(f"[slack] Config saved to {CONFIG_FILE}")
        print("[slack] Note: Slack token is NOT saved — use --token or SLACK_BOT_TOKEN env var.")
        return

    result = ingest_slack(
        token=token,
        channel_names=channel_names,
        scan_all=args.scan_all,
        days=args.days,
        include_threads=not args.no_threads,
    )

    print_summary(result)


if __name__ == "__main__":
    main()
