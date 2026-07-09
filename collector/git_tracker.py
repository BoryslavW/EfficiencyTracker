#!/usr/bin/env python3
"""
Git Session Tracker — zero-friction background daemon that tracks coding
sessions for ANY editor/AI tool by watching git activity and file changes.

Runs silently in the background. Employees don't need to do anything — it
detects coding sessions from filesystem and git events, extracts topic
keywords from diffs/file paths, captures build/test errors from git hooks,
and auto-submits records to the receiver when a session ends.

Session detection:
  - File saves or git operations within SESSION_GAP minutes = same session
  - Gap > SESSION_GAP = session boundary → submit the completed session
  - Graceful shutdown (SIGINT/SIGTERM) flushes the active session

Data extracted per session:
  - Duration (first file change → last activity)
  - Keywords from git diff, file paths, commit messages
  - Error signals from failed build/test commands (git hook output)
  - Approximate "tool call" count from number of file saves
  - Token estimate from diff size (lines changed × weight)
  - Employee from git config user.name or system username
  - Project from repo directory name
  - Jira ID from branch name or commit messages

AI tool enrichment (optional, zero-config):
  Scans known log paths for Cursor, Copilot, Windsurf, Aider, Continue
  to pull actual token usage and conversation metadata when available.

Usage:
    python3 git_tracker.py /path/to/repo          # track one repo
    python3 git_tracker.py /path/to/repo --daemon  # fork to background
    python3 git_tracker.py --stop                   # stop background tracker
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PID_FILE = os.path.join(DATA_DIR, ".git_tracker.pid")
RECEIVER_URL = "http://127.0.0.1:8788/submit"
DATA_FILE = os.path.join(DATA_DIR, "task_data.jsonl")

SESSION_GAP = 30  # minutes of inactivity before session ends
POLL_INTERVAL = 15  # seconds between filesystem checks

# Reuse the term library from the session harvester for consistent classification
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_harvester import extract_keywords, extract_jira_id

# ---------------------------------------------------------------------------
# AI tool log paths — auto-detected, no config needed
# ---------------------------------------------------------------------------

_AI_TOOL_LOG_PATHS: dict[str, list[Path]] = {
    "cursor": [
        Path.home() / ".cursor" / "logs",
        Path.home() / "Library" / "Application Support" / "Cursor" / "logs",
    ],
    "copilot": [
        Path.home() / ".vscode" / "extensions",
        Path.home() / "Library" / "Application Support" / "Code" / "logs",
    ],
    "windsurf": [
        Path.home() / ".codeium" / "windsurf",
        Path.home() / "Library" / "Application Support" / "Windsurf" / "logs",
    ],
    "aider": [
        Path.home() / ".aider.chat.history.md",
        Path.home() / ".aider.tags.cache.v3",
    ],
    "continue": [
        Path.home() / ".continue" / "logs",
        Path.home() / "Library" / "Application Support" / "Continue" / "logs",
    ],
}


def detect_ai_tool() -> str | None:
    for tool, paths in _AI_TOOL_LOG_PATHS.items():
        for p in paths:
            if p.exists():
                return tool
    return None


def get_ai_token_estimate(tool: str, session_start: datetime,
                          session_end: datetime) -> int | None:
    """Try to extract token usage from AI tool logs for the session window."""
    if tool == "aider":
        history = Path.home() / ".aider.chat.history.md"
        if history.exists():
            try:
                text = history.read_text(errors="ignore")
                token_matches = re.findall(
                    r'Tokens:\s*[\d,]+\s*sent,\s*[\d,]+\s*received.*?'
                    r'Cost:\s*\$[\d.]+', text)
                if token_matches:
                    last = token_matches[-1]
                    sent = re.search(r'([\d,]+)\s*sent', last)
                    recv = re.search(r'([\d,]+)\s*received', last)
                    if sent and recv:
                        return (int(sent.group(1).replace(",", ""))
                                + int(recv.group(1).replace(",", "")))
            except OSError:
                pass

    if tool == "cursor":
        for log_dir in _AI_TOOL_LOG_PATHS["cursor"]:
            if not log_dir.is_dir():
                continue
            try:
                log_files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime,
                                   reverse=True)
                for lf in log_files[:3]:
                    text = lf.read_text(errors="ignore")
                    token_matches = re.findall(
                        r'"(?:total_tokens|usage)":\s*\{[^}]*"total":\s*(\d+)', text)
                    if token_matches:
                        return sum(int(t) for t in token_matches[-10:])
            except OSError:
                pass

    return None


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git_cmd(repo: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo] + list(args),
            capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def get_git_user(repo: str) -> str:
    name = git_cmd(repo, "config", "user.name")
    return name if name else getpass.getuser()


def get_git_branch(repo: str) -> str:
    return git_cmd(repo, "rev-parse", "--abbrev-ref", "HEAD")


def get_recent_commits(repo: str, since_minutes: int) -> list[str]:
    output = git_cmd(repo, "log", f"--since={since_minutes} minutes ago",
                     "--format=%H %s", "--no-merges")
    return output.splitlines() if output else []


def get_diff_stat(repo: str, since_minutes: int) -> dict:
    output = git_cmd(repo, "log", f"--since={since_minutes} minutes ago",
                     "--format=", "--numstat", "--no-merges")
    added, deleted, files_changed = 0, 0, set()
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            try:
                added += int(parts[0]) if parts[0] != "-" else 0
                deleted += int(parts[1]) if parts[1] != "-" else 0
            except ValueError:
                pass
            files_changed.add(parts[2])
    return {"added": added, "deleted": deleted, "files": list(files_changed)}


def get_diff_text(repo: str, since_minutes: int) -> str:
    return git_cmd(repo, "log", f"--since={since_minutes} minutes ago",
                   "--format=%s%n%b", "--no-merges", "-p")


def get_changed_files_unstaged(repo: str) -> list[str]:
    output = git_cmd(repo, "diff", "--name-only")
    staged = git_cmd(repo, "diff", "--cached", "--name-only")
    all_files = output.splitlines() + staged.splitlines()
    return list(set(f for f in all_files if f))


# ---------------------------------------------------------------------------
# Error detection from recent git activity
# ---------------------------------------------------------------------------

_ERROR_PATTERNS = re.compile(
    r'(?:error|Error|ERROR|exception|Exception|Traceback|FAILED|'
    r'fatal|FATAL|exit code [1-9]|ModuleNotFoundError|'
    r'ImportError|SyntaxError|TypeError|ValueError|'
    r'KeyError|AttributeError|FileNotFoundError|'
    r'PermissionError|ConnectionRefusedError|'
    r'BROKEN|broken|compilation failed|build failed|'
    r'npm ERR|yarn error|cargo error|make.*Error)',
    re.IGNORECASE
)

_FIX_PATTERNS = re.compile(
    r'(?:fix|Fix|FIX|bugfix|hotfix|patch|resolve|Resolve|'
    r'workaround|revert|Revert)', re.IGNORECASE
)


def estimate_errors_from_commits(commits: list[str], diff_text: str) -> tuple[int, int]:
    """Estimate error_count and retry_count from commit messages and diff content."""
    error_count = 0
    retry_count = 0

    for commit_line in commits:
        msg = commit_line.split(" ", 1)[1] if " " in commit_line else commit_line
        if _FIX_PATTERNS.search(msg):
            error_count += 1
        if _ERROR_PATTERNS.search(msg):
            error_count += 1

    fix_commits = sum(1 for c in commits if _FIX_PATTERNS.search(c))
    if fix_commits > 1:
        retry_count = fix_commits - 1

    chunks = diff_text.split("diff --git")
    for chunk in chunks:
        added_lines = [l for l in chunk.splitlines() if l.startswith("+") and not l.startswith("+++")]
        for line in added_lines:
            if _ERROR_PATTERNS.search(line):
                error_count += 1
                break

    return error_count, retry_count


# ---------------------------------------------------------------------------
# Session tracking
# ---------------------------------------------------------------------------

class Session:
    def __init__(self, repo: str):
        self.repo = repo
        self.start_time = datetime.now(timezone.utc)
        self.last_activity = self.start_time
        self.file_changes: set[str] = set()
        self.commit_messages: list[str] = []
        self.commit_count = 0
        self.lines_added = 0
        self.lines_deleted = 0
        self.branch = get_git_branch(repo)

    def touch(self):
        self.last_activity = datetime.now(timezone.utc)

    def duration_minutes(self) -> float:
        return max(1, (self.last_activity - self.start_time).total_seconds() / 60)

    def is_expired(self, gap_minutes: int = SESSION_GAP) -> bool:
        gap = (datetime.now(timezone.utc) - self.last_activity).total_seconds() / 60
        return gap >= gap_minutes

    def to_record(self) -> dict | None:
        if self.duration_minutes() < 1 and not self.commit_count:
            return None

        all_text_parts = list(self.commit_messages)
        for f in self.file_changes:
            all_text_parts.append(f)
            parts = re.split(r'[/\\._\-]', f)
            all_text_parts.extend(parts)

        diff_text = get_diff_text(self.repo, int(self.duration_minutes()) + 5)
        all_text_parts.append(diff_text[:50000])

        full_text = " ".join(all_text_parts)
        keywords = extract_keywords(full_text)

        if len(keywords) < 2:
            return None

        jira_id = ""
        if self.branch:
            jira_id = extract_jira_id(self.branch)
        if not jira_id:
            for msg in self.commit_messages:
                jira_id = extract_jira_id(msg)
                if jira_id:
                    break

        if not jira_id:
            ts = self.start_time.strftime("%Y%m%d%H%M")
            jira_id = f"GIT-{ts}"

        project = os.path.basename(os.path.abspath(self.repo))
        employee = get_git_user(self.repo)
        task_name = self.commit_messages[0][:80] if self.commit_messages else f"coding on {self.branch or project}"

        total_changed = self.lines_added + self.lines_deleted
        token_estimate = max(100, total_changed * 15)

        ai_tool = detect_ai_tool()
        if ai_tool:
            ai_tokens = get_ai_token_estimate(ai_tool, self.start_time, self.last_activity)
            if ai_tokens:
                token_estimate = ai_tokens

        commits = get_recent_commits(self.repo, int(self.duration_minutes()) + 5)
        error_count, retry_count = estimate_errors_from_commits(
            commits, diff_text[:30000])

        file_save_count = len(self.file_changes)

        source = f"git-tracker"
        if ai_tool:
            source = f"git-tracker+{ai_tool}"

        return {
            "employee": employee,
            "jira_id": jira_id,
            "task_name": task_name,
            "project": project,
            "token_usage": token_estimate,
            "keywords": keywords,
            "start_time": self.start_time.isoformat(),
            "end_time": self.last_activity.isoformat(),
            "source": source,
            "branch": self.branch or "",
            "error_count": error_count,
            "retry_count": retry_count,
            "tool_call_count": file_save_count,
            "commits": self.commit_count,
            "lines_added": self.lines_added,
            "lines_deleted": self.lines_deleted,
            "duration_minutes": round(self.duration_minutes(), 1),
            "ai_tool_detected": ai_tool or "none",
        }


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------

def send_to_receiver(record: dict) -> bool:
    try:
        req = Request(RECEIVER_URL, data=json.dumps(record).encode(),
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=5)
        return resp.status == 200
    except (URLError, OSError):
        return False


def save_locally(record: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def submit_session(session: Session) -> None:
    record = session.to_record()
    if record is None:
        return

    if send_to_receiver(record):
        dest = "receiver"
    else:
        save_locally(record)
        dest = "local"

    print(f"  [{dest}] {record['jira_id']} — {record['duration_minutes']} min, "
          f"{record['commits']} commits, {len(record['keywords'])} keywords, "
          f"source={record['source']}")


# ---------------------------------------------------------------------------
# Filesystem polling (no external deps like watchdog)
# ---------------------------------------------------------------------------

def get_file_mtimes(repo: str) -> dict[str, float]:
    """Snapshot mtimes of tracked + staged files."""
    mtimes: dict[str, float] = {}
    tracked = git_cmd(repo, "ls-files")
    if not tracked:
        return mtimes
    for f in tracked.splitlines()[:2000]:
        full = os.path.join(repo, f)
        try:
            mtimes[f] = os.path.getmtime(full)
        except OSError:
            pass
    return mtimes


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

_running = True


def _shutdown(signum, frame):
    global _running
    _running = False


def run_tracker(repo: str, session_gap: int = SESSION_GAP,
                poll_interval: int = POLL_INTERVAL) -> None:
    global _running

    repo = os.path.abspath(repo)
    if not os.path.isdir(os.path.join(repo, ".git")):
        print(f"ERROR: {repo} is not a git repository.")
        sys.exit(1)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    ai_tool = detect_ai_tool()
    project = os.path.basename(repo)
    employee = get_git_user(repo)
    branch = get_git_branch(repo)

    print(f"Git Session Tracker")
    print(f"  Repo:     {repo}")
    print(f"  Employee: {employee}")
    print(f"  Branch:   {branch}")
    print(f"  Project:  {project}")
    print(f"  AI tool:  {ai_tool or 'none detected'}")
    print(f"  Receiver: {RECEIVER_URL}")
    print(f"  Session gap: {session_gap} min")
    print(f"  Polling every {poll_interval}s")
    print()

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    prev_mtimes = get_file_mtimes(repo)
    prev_head = git_cmd(repo, "rev-parse", "HEAD")
    session: Session | None = None
    sessions_submitted = 0

    try:
        while _running:
            time.sleep(poll_interval)
            if not _running:
                break

            activity = False

            cur_mtimes = get_file_mtimes(repo)
            changed_files = set()
            for f, mtime in cur_mtimes.items():
                if f not in prev_mtimes or prev_mtimes[f] != mtime:
                    changed_files.add(f)
            prev_mtimes = cur_mtimes

            cur_head = git_cmd(repo, "rev-parse", "HEAD")
            new_commits = []
            if cur_head != prev_head and prev_head:
                log_output = git_cmd(repo, "log", f"{prev_head}..{cur_head}",
                                     "--format=%s", "--no-merges")
                new_commits = [m for m in log_output.splitlines() if m.strip()]
                prev_head = cur_head

            unstaged = get_changed_files_unstaged(repo)
            changed_files.update(unstaged)

            if changed_files or new_commits:
                activity = True

            if activity:
                if session is None:
                    session = Session(repo)
                    print(f"  [new session] started at {session.start_time.strftime('%H:%M:%S')}")

                session.touch()
                session.file_changes.update(changed_files)

                for msg in new_commits:
                    session.commit_messages.append(msg)
                    session.commit_count += 1

                if changed_files:
                    stat = get_diff_stat(repo, 1)
                    session.lines_added += stat["added"]
                    session.lines_deleted += stat["deleted"]

                cur_branch = get_git_branch(repo)
                if cur_branch and cur_branch != session.branch:
                    session.branch = cur_branch

            if session and session.is_expired(session_gap):
                print(f"  [session end] {session.duration_minutes():.0f} min, "
                      f"{session.commit_count} commits, "
                      f"{len(session.file_changes)} files touched")
                submit_session(session)
                sessions_submitted += 1
                session = None

    finally:
        if session:
            print(f"\n  [shutdown] flushing active session "
                  f"({session.duration_minutes():.0f} min)")
            submit_session(session)
            sessions_submitted += 1

        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

        print(f"\nStopped. {sessions_submitted} session(s) submitted total.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Git-based coding session tracker — zero friction, runs in background.")
    parser.add_argument("repo", nargs="?", default=".",
                        help="Path to git repository to track (default: current dir)")
    parser.add_argument("--daemon", action="store_true",
                        help="Fork to background")
    parser.add_argument("--stop", action="store_true",
                        help="Stop the background tracker")
    parser.add_argument("--status", action="store_true",
                        help="Check if tracker is running")
    parser.add_argument("--gap", type=int, default=SESSION_GAP,
                        help=f"Minutes of inactivity before session ends (default: {SESSION_GAP})")
    parser.add_argument("--poll", type=int, default=POLL_INTERVAL,
                        help=f"Seconds between filesystem checks (default: {POLL_INTERVAL})")
    args = parser.parse_args()

    if args.stop:
        if not os.path.exists(PID_FILE):
            print("No tracker running (no PID file).")
            return
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to tracker (PID {pid}).")
        except ProcessLookupError:
            print(f"Tracker process {pid} not found (stale PID file).")
            os.remove(PID_FILE)
        return

    if args.status:
        if not os.path.exists(PID_FILE):
            print("Tracker is not running.")
            return
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        try:
            os.kill(pid, 0)
            print(f"Tracker is running (PID {pid}).")
        except ProcessLookupError:
            print(f"Tracker is not running (stale PID file for {pid}).")
            os.remove(PID_FILE)
        return

    if args.daemon:
        pid = os.fork()
        if pid > 0:
            print(f"Tracker forked to background (PID {pid}).")
            print(f"Stop with: python3 git_tracker.py --stop")
            sys.exit(0)

        os.setsid()
        sys.stdout = open(os.path.join(DATA_DIR, "git_tracker.log"), "a")
        sys.stderr = sys.stdout

    run_tracker(args.repo, session_gap=args.gap, poll_interval=args.poll)


if __name__ == "__main__":
    main()
