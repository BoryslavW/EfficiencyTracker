#!/usr/bin/env python3
"""
Live demo harvester — parses your real Claude Code sessions and writes
them directly into data/task_data.jsonl. No collector, no networking,
no pairing. Just run it and refresh the dashboard.

Usage:
    python3 demo/live_harvest.py              # harvest all sessions
    python3 demo/live_harvest.py --recent 5   # only last 5 sessions
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "task_data.jsonl")

CLAUDE_DIR = Path.home() / ".claude" / "projects"

# Outlier guards — a single realistic coding task stays well under these.
# Anything larger is a long-lived / demo-building session that would dominate
# the heatmap and skew analytics, so it's skipped.
MAX_SESSION_TOKENS = 200_000
MAX_SESSION_MINUTES = 480          # 8 hours

TERM_LIBRARY = {
    "python": "python", "fastapi": "fastapi", "django": "django",
    "react": "react", "typescript": "typescript", "nextjs": "nextjs",
    "docker": "docker", "kubernetes": "kubernetes", "terraform": "terraform",
    "sql": "sql", "postgresql": "sql", "graphql": "graphql",
    "api": "endpoint", "endpoint": "endpoint", "rest": "rest-api",
    "auth": "authentication", "oauth": "authentication", "jwt": "authentication",
    "test": "testing", "testing": "testing", "jest": "testing",
    "security": "security", "encryption": "security", "vault": "security",
    "llm": "llm", "gpt": "llm", "claude": "llm", "openai": "llm",
    "pipeline": "pipeline", "etl": "etl", "kafka": "kafka",
    "ci": "ci-pipeline", "cd": "ci-pipeline", "deploy": "deployment",
    "aws": "cloud", "gcp": "cloud", "azure": "cloud",
    "css": "frontend", "html": "frontend", "component": "frontend",
    "database": "database", "migration": "database", "schema": "database",
    "redis": "caching", "cache": "caching", "performance": "performance",
    "refactor": "refactor", "bug": "bugfix", "fix": "bugfix",
    "dashboard": "dashboard", "nicegui": "dashboard", "pywebview": "dashboard",
    "git": "git", "github": "git", "commit": "git",
    "slack": "slack-integration", "jira": "jira-integration",
    "analytics": "analytics", "heatmap": "analytics", "matplotlib": "analytics",
    "ollama": "llm", "prompt": "llm", "model": "llm",
}

SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|api[_-]?token|access[_-]?token|secret[_-]?key|auth[_-]?token|bearer)\s*[=:]\s*["\']?([A-Za-z0-9_\-/.]{20,})["\']?'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----'),
    re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'),
    re.compile(r'gh[ps]_[A-Za-z0-9_]{30,}'),
    re.compile(r'xox[bpras]-[A-Za-z0-9-]+'),
    re.compile(r'(?i)(password|passwd|pwd|secret)\s*[=:]\s*["\']?([^\s"\']{6,})["\']?'),
]

ERROR_PATTERNS = re.compile(
    r'(?:error|Error|ERROR|exception|Exception|Traceback|FAILED|fatal|FATAL)',
    re.IGNORECASE
)


def scrub(text):
    for p in SECRET_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text


def extract_keywords(text):
    found = set()
    text_lower = text.lower()
    for term, canonical in TERM_LIBRARY.items():
        if term in text_lower:
            found.add(canonical)
    return sorted(found)


def parse_session(jsonl_path, employee_name):
    messages = []
    try:
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        return None

    if len(messages) < 2:
        return None

    all_text = []
    total_input = 0
    total_output = 0
    first_ts = None
    last_ts = None
    session_id = ""
    cwd = ""
    first_user_msg = ""
    error_count = 0

    for msg in messages:
        ts = msg.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
        if not session_id and msg.get("sessionId"):
            session_id = msg["sessionId"]
        if not cwd and msg.get("cwd"):
            cwd = msg["cwd"]

        msg_type = msg.get("type", "")
        if msg_type == "user":
            content = msg.get("message", {}).get("content", "")
            text = content if isinstance(content, str) else " ".join(
                p.get("text", "") for p in (content if isinstance(content, list) else [])
                if isinstance(p, dict) and p.get("type") == "text"
            )
            all_text.append(text)
            if not first_user_msg and text.strip():
                first_user_msg = text.strip()
        elif msg_type == "assistant":
            inner = msg.get("message", {})
            usage = inner.get("usage", {})
            total_input += usage.get("input_tokens", 0)
            total_output += usage.get("output_tokens", 0)
            content = inner.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        all_text.append(part.get("text", ""))
        elif msg_type in ("tool_result", "result"):
            rc = msg.get("content", "")
            if isinstance(rc, str) and ERROR_PATTERNS.search(rc):
                error_count += 1

    if not first_ts or not last_ts:
        return None
    total_tokens = total_input + total_output
    if total_tokens == 0:
        return None

    try:
        t_start = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
        t_end = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        duration = max(1, (t_end - t_start).total_seconds() / 60)
    except (ValueError, TypeError):
        return None

    # Skip runaway sessions (e.g. a long-lived session left open for hours/days,
    # or the demo-building session itself). These are outliers that would
    # dominate the heatmap and skew every analytic. A realistic single coding
    # task is well under these bounds.
    if total_tokens > MAX_SESSION_TOKENS or duration > MAX_SESSION_MINUTES:
        return "SKIP_OUTLIER"

    full_text = scrub(" ".join(all_text))
    keywords = extract_keywords(full_text)

    project = os.path.basename(cwd) if cwd else "Unknown"
    task_name = scrub(first_user_msg[:80].replace("\n", " ").strip())

    return {
        "employee": employee_name,
        "jira_id": f"LIVE-{session_id[:8]}",
        "task_name": task_name or "Coding session",
        "project": project,
        "token_usage": total_tokens,
        "keywords": keywords if keywords else ["general"],
        "start_time": t_start.isoformat(),
        "end_time": t_end.isoformat(),
        "duration_minutes": round(duration, 1),
        "error_count": error_count,
        "source": "live-demo",
    }


def find_sessions():
    sessions = []
    if not CLAUDE_DIR.exists():
        return sessions
    for project_dir in CLAUDE_DIR.iterdir():
        if project_dir.is_dir():
            for f in project_dir.glob("*.jsonl"):
                sessions.append(f)
    return sorted(sessions, key=lambda p: p.stat().st_mtime, reverse=True)


def _default_name():
    """Pick a sensible display name. Avoids 'root' when run under sudo."""
    name = os.environ.get("DEMO_NAME")
    if name:
        return name
    for candidate in (os.environ.get("SUDO_USER"), os.environ.get("USER")):
        if candidate and candidate != "root":
            return candidate
    try:
        login = os.getlogin()
        if login and login != "root":
            return login
    except OSError:
        pass
    return "You"


def main():
    employee = _default_name()
    limit = None

    if "--recent" in sys.argv:
        idx = sys.argv.index("--recent")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    sessions = find_sessions()
    if not sessions:
        print("  No Claude Code sessions found.")
        return

    os.makedirs(DATA_DIR, exist_ok=True)

    existing_ids = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("jira_id", "").startswith("LIVE-"):
                        existing_ids.add(rec["jira_id"])
                except json.JSONDecodeError:
                    pass

    added = 0
    skipped = 0
    outliers = 0
    with open(OUTPUT_FILE, "a") as out:
        for path in sessions:
            if limit and added >= limit:
                break
            record = parse_session(path, employee)
            if record is None:
                continue
            if record == "SKIP_OUTLIER":
                outliers += 1
                continue
            if record["jira_id"] in existing_ids:
                skipped += 1
                continue
            out.write(json.dumps(record) + "\n")
            existing_ids.add(record["jira_id"])
            added += 1
            print(f"  + {record['jira_id']}: {record['task_name'][:60]}  ({record['token_usage']} tokens, {record['duration_minutes']}min)")

    summary = f"\n  {added} sessions added as '{employee}', {skipped} already existed"
    if outliers:
        summary += f", {outliers} outlier(s) skipped"
    print(summary + ".")
    if added > 0:
        print(f"  Refresh the dashboard to see them.")


if __name__ == "__main__":
    main()
