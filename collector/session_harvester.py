#!/usr/bin/env python3
"""
Session Harvester — auto-extract task records from archived Claude Code sessions.

Only processes sessions that have been explicitly archived (session closed and
marked as done). Active or unarchived sessions are skipped entirely.

Archive detection:
  1. Reads data/.archived_sessions.json — a list of session IDs that have been
     confirmed as archived. This file is populated by:
       a) Running `python3 session_harvester.py --mark-archived <session_id>`
          after archiving a session in Claude Code.
       b) A future hook that auto-marks on archive (see README).
  2. Any session ID in that list AND not already harvested gets parsed.

Keyword classification uses a static term library — no LLM needed. Each term
maps to a canonical keyword used by the analytics pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import getpass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATA_FILE = os.path.join(DATA_DIR, "task_data.jsonl")
RECEIVER_URL = "http://127.0.0.1:8788/submit"

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
SESSIONS_DIR = CLAUDE_DIR / "sessions"

HARVEST_LOG = os.path.join(DATA_DIR, ".harvested_sessions.json")
ARCHIVE_REGISTRY = os.path.join(DATA_DIR, ".archived_sessions.json")

# ---------------------------------------------------------------------------
# Term library: surface form -> canonical keyword
# ---------------------------------------------------------------------------

TERM_LIBRARY: dict[str, str] = {
    # ── Backend & APIs ──
    "python":           "python",
    "python3":          "python",
    "py":               "python",
    "fastapi":          "fastapi",
    "fast-api":         "fastapi",
    "django":           "django",
    "flask":            "django",
    "rest api":         "rest-api",
    "rest-api":         "rest-api",
    "restful":          "rest-api",
    "graphql":          "graphql",
    "gql":              "graphql",
    "endpoint":         "endpoint",
    "endpoints":        "endpoint",
    "route":            "endpoint",
    "routes":           "endpoint",
    "api":              "endpoint",
    "microservice":     "microservice",
    "microservices":    "microservice",
    "grpc":             "grpc",
    "protobuf":         "grpc",
    "middleware":       "middleware",
    "auth":             "authentication",
    "authentication":   "authentication",
    "login":            "authentication",
    "oauth":            "authentication",
    "jwt":              "authentication",
    "serializer":       "endpoint",
    "request":          "endpoint",
    "response":         "endpoint",
    "http":             "endpoint",
    "webhook":          "endpoint",
    "pagination":       "endpoint",

    # ── Frontend & UI ──
    "react":            "react",
    "reactjs":          "react",
    "react.js":         "react",
    "typescript":       "typescript",
    "ts":               "typescript",
    "tsx":              "typescript",
    "javascript":       "typescript",
    "js":               "typescript",
    "nextjs":           "nextjs",
    "next.js":          "nextjs",
    "next":             "nextjs",
    "component":        "component",
    "components":       "component",
    "widget":           "component",
    "hooks":            "hooks",
    "usestate":         "hooks",
    "useeffect":        "hooks",
    "usememo":          "hooks",
    "redux":            "redux",
    "zustand":          "redux",
    "state management": "redux",
    "tailwind":         "tailwind",
    "tailwindcss":      "tailwind",
    "css":              "tailwind",
    "scss":             "tailwind",
    "styled":           "tailwind",
    "responsive":       "responsive",
    "mobile":           "responsive",
    "breakpoint":       "responsive",
    "accessibility":    "accessibility",
    "a11y":             "accessibility",
    "aria":             "accessibility",
    "screen reader":    "accessibility",
    "vite":             "vite",
    "webpack":          "vite",
    "bundler":          "vite",
    "storybook":        "component",
    "jsx":              "react",
    "dom":              "react",
    "html":             "react",
    "ui":               "component",
    "frontend":         "component",
    "front-end":        "component",

    # ── Data & ML ──
    "etl":              "etl",
    "extract":          "etl",
    "transform":        "etl",
    "ingest":           "etl",
    "pipeline":         "pipeline",
    "pipelines":        "pipeline",
    "dag":              "pipeline",
    "airflow":          "pipeline",
    "prefect":          "pipeline",
    "sql":              "sql",
    "query":            "sql",
    "queries":          "sql",
    "select":           "sql",
    "join":             "sql",
    "postgresql":       "sql",
    "postgres":         "sql",
    "mysql":            "sql",
    "sqlite":           "sql",
    "spark":            "spark",
    "pyspark":          "spark",
    "hadoop":           "spark",
    "kafka":            "kafka",
    "rabbitmq":         "kafka",
    "message queue":    "kafka",
    "pub/sub":          "kafka",
    "pubsub":           "kafka",
    "llm":              "llm",
    "language model":   "llm",
    "chatgpt":          "llm",
    "gpt":              "llm",
    "claude":           "llm",
    "anthropic":        "llm",
    "openai":           "llm",
    "embeddings":       "embeddings",
    "embedding":        "embeddings",
    "vector":           "embeddings",
    "vectors":          "embeddings",
    "vector-db":        "embeddings",
    "pinecone":         "embeddings",
    "chromadb":         "embeddings",
    "chroma":           "embeddings",
    "rag":              "rag",
    "retrieval":        "rag",
    "retrieval augmented": "rag",
    "model training":   "model-training",
    "model-training":   "model-training",
    "fine-tune":        "model-training",
    "fine-tuning":      "model-training",
    "finetuning":       "model-training",
    "training":         "model-training",
    "train":            "model-training",
    "inference":        "model-training",
    "mlops":            "mlops",
    "ml ops":           "mlops",
    "model serving":    "mlops",
    "model-serving":    "mlops",
    "ml pipeline":      "mlops",
    "machine learning": "mlops",
    "feature engineering": "mlops",
    "pandas":           "sql",
    "dataframe":        "sql",
    "dbt":              "pipeline",
    "snowflake":        "sql",
    "bigquery":         "sql",
    "warehouse":        "sql",
    "data lake":        "etl",
    "parquet":          "etl",
    "avro":             "etl",
    "data quality":     "pipeline",
    "data model":       "sql",
    "schema":           "sql",
    "migration":        "sql",
    "prompt engineering": "llm",
    "prompt":           "llm",
    "tokenizer":        "llm",
    "langchain":        "llm",

    # ── Infra & DevOps ──
    "docker":           "docker",
    "dockerfile":       "docker",
    "container":        "docker",
    "containers":       "docker",
    "image":            "docker",
    "kubernetes":       "kubernetes",
    "k8s":              "kubernetes",
    "kubectl":          "kubernetes",
    "helm":             "kubernetes",
    "pod":              "kubernetes",
    "pods":             "kubernetes",
    "terraform":        "terraform",
    "hcl":              "terraform",
    "iac":              "terraform",
    "infrastructure as code": "terraform",
    "ansible":          "terraform",
    "cloudformation":   "terraform",
    "ci":               "ci-pipeline",
    "cd":               "ci-pipeline",
    "ci/cd":            "ci-pipeline",
    "ci-cd":            "ci-pipeline",
    "cicd":             "ci-pipeline",
    "github actions":   "ci-pipeline",
    "github-actions":   "ci-pipeline",
    "jenkins":          "ci-pipeline",
    "circleci":         "ci-pipeline",
    "build":            "ci-pipeline",
    "deploy":           "deployment",
    "deployment":       "deployment",
    "deploying":        "deployment",
    "rollback":         "deployment",
    "release":          "deployment",
    "aws":              "aws",
    "amazon":           "aws",
    "ec2":              "aws",
    "s3":               "aws",
    "lambda":           "aws",
    "gcp":              "aws",
    "azure":            "aws",
    "cloud":            "aws",
    "monitoring":       "monitoring",
    "monitor":          "monitoring",
    "observability":    "monitoring",
    "alerting":         "monitoring",
    "alerts":           "monitoring",
    "grafana":          "grafana",
    "datadog":          "grafana",
    "prometheus":       "grafana",
    "pagerduty":        "grafana",
    "dashboard":        "grafana",
    "metrics":          "monitoring",
    "logging":          "logging",
    "logs":             "logging",
    "log":              "logging",
    "tracing":          "monitoring",
    "opentelemetry":    "monitoring",
    "iam":              "iam",
    "permissions":      "iam",
    "roles":            "iam",
    "rbac":             "iam",
    "vpc":              "aws",
    "load balancer":    "aws",
    "auto-scaling":     "aws",
    "dns":              "aws",
    "ssl":              "aws",
    "tls":              "aws",

    # ── Testing ──
    "test":             "pytest",
    "tests":            "pytest",
    "testing":          "pytest",
    "pytest":           "pytest",
    "jest":             "pytest",
    "unittest":         "pytest",
    "unit test":        "pytest",
    "unit-test":        "pytest",
    "integration test": "pytest",
    "e2e":              "pytest",
    "coverage":         "pytest",
    "mock":             "pytest",
    "mocking":          "pytest",
    "fixture":          "pytest",
    "assertion":        "pytest",
    "tdd":              "pytest",
    "regression":       "pytest",
    "snapshot":         "pytest",

    # ── Security ──
    "security":         "authentication",
    "csrf":             "authentication",
    "xss":              "authentication",
    "injection":        "authentication",
    "vulnerability":    "authentication",
    "encryption":       "authentication",
    "vault":            "authentication",
    "secrets":          "authentication",
    "compliance":       "authentication",
    "audit":            "authentication",
    "penetration":      "authentication",

    # ── Code quality ──
    "refactor":         "refactor",
    "refactoring":      "refactor",
    "cleanup":          "refactor",
    "clean up":         "refactor",
    "tech debt":        "refactor",
    "tech-debt":        "refactor",
    "code review":      "refactor",
    "pull request":     "refactor",
    "pr":               "refactor",
    "lint":             "refactor",
    "linting":          "refactor",
    "eslint":           "refactor",
    "prettier":         "refactor",
    "mypy":             "refactor",
    "type checking":    "refactor",
    "type-checking":    "refactor",
    "static analysis":  "refactor",

    # ── Docs ──
    "documentation":    "documentation",
    "docs":             "documentation",
    "readme":           "documentation",
    "changelog":        "documentation",
    "onboarding":       "documentation",
    "tutorial":         "documentation",
    "runbook":          "documentation",
    "wiki":             "documentation",
    "architecture doc": "documentation",
    "adr":              "documentation",
    "diagram":          "documentation",

    # ── Performance ──
    "performance":      "profiling",
    "profiling":        "profiling",
    "profile":          "profiling",
    "caching":          "caching",
    "cache":            "caching",
    "redis":            "caching",
    "memcached":        "caching",
    "latency":          "profiling",
    "throughput":       "profiling",
    "bottleneck":       "profiling",
    "memory leak":      "profiling",
    "optimization":     "profiling",
    "optimize":         "profiling",
    "slow":             "profiling",
    "fast":             "profiling",
    "concurrency":      "profiling",
    "async":            "profiling",
    "parallel":         "profiling",

    # ── Database-specific ──
    "index":            "sql",
    "indexing":         "sql",
    "partition":        "sql",
    "replication":      "sql",
    "transaction":      "sql",
    "deadlock":         "sql",
    "orm":              "sql",
    "sqlalchemy":       "sql",
    "alembic":          "sql",
    "foreign key":      "sql",
    "normalization":    "sql",
}

_TERM_PATTERNS: list[tuple[re.Pattern, str]] = []
for term in sorted(TERM_LIBRARY.keys(), key=len, reverse=True):
    canonical = TERM_LIBRARY[term]
    pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
    _TERM_PATTERNS.append((pattern, canonical))


# ---------------------------------------------------------------------------
# Archive registry
# ---------------------------------------------------------------------------

def load_archive_registry() -> dict[str, dict]:
    """Load the archive registry: {session_id: {archived_at, reason, ...}}."""
    if os.path.exists(ARCHIVE_REGISTRY):
        with open(ARCHIVE_REGISTRY) as f:
            return json.load(f)
    return {}


def save_archive_registry(registry: dict[str, dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ARCHIVE_REGISTRY, "w") as f:
        json.dump(registry, f, indent=2)


def mark_archived(session_id: str, reason: str = "") -> None:
    """Mark a session as archived and ready for harvesting."""
    registry = load_archive_registry()
    registry[session_id] = {
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    save_archive_registry(registry)
    print(f"Marked session {session_id} as archived.")
    print(f"Run `python3 session_harvester.py` to harvest it.")


# ---------------------------------------------------------------------------
# Harvest log (already-processed sessions)
# ---------------------------------------------------------------------------

def load_harvested() -> set[str]:
    if os.path.exists(HARVEST_LOG):
        with open(HARVEST_LOG) as f:
            return set(json.load(f))
    return set()


def save_harvested(harvested: set[str]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HARVEST_LOG, "w") as f:
        json.dump(sorted(harvested), f)


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------

def extract_keywords(text: str) -> list[str]:
    found: set[str] = set()
    for pattern, canonical in _TERM_PATTERNS:
        if pattern.search(text):
            found.add(canonical)
    return sorted(found)


def extract_jira_id(text: str) -> str:
    match = re.search(r'\b([A-Z]{2,10}-\d+)\b', text)
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# Session parsing
# ---------------------------------------------------------------------------

def find_session_jsonl(session_id: str) -> Path | None:
    """Find the JSONL transcript file for a given session ID."""
    if not PROJECTS_DIR.exists():
        return None
    for project_dir in PROJECTS_DIR.iterdir():
        if project_dir.is_dir():
            candidate = project_dir / f"{session_id}.jsonl"
            if candidate.exists():
                return candidate
    return None


def parse_session(jsonl_path: Path) -> dict | None:
    """Parse a Claude Code session JSONL file into a task record."""
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

    all_text_parts: list[str] = []
    total_input_tokens = 0
    total_output_tokens = 0
    first_timestamp = None
    last_timestamp = None
    cwd = ""
    session_id = ""
    first_user_message = ""
    error_count = 0
    tool_calls: list[str] = []

    _ERROR_PATTERNS = re.compile(
        r'(?:error|Error|ERROR|exception|Exception|Traceback|FAILED|'
        r'fatal|FATAL|exit code [1-9]|ModuleNotFoundError|'
        r'ImportError|SyntaxError|TypeError|ValueError|'
        r'KeyError|AttributeError|FileNotFoundError|'
        r'PermissionError|ConnectionRefusedError)', re.IGNORECASE)

    for msg in messages:
        ts = msg.get("timestamp")
        if ts:
            if first_timestamp is None:
                first_timestamp = ts
            last_timestamp = ts

        if not session_id and msg.get("sessionId"):
            session_id = msg["sessionId"]
        if not cwd and msg.get("cwd"):
            cwd = msg["cwd"]

        msg_type = msg.get("type", "")

        if msg_type == "user":
            content = msg.get("message", {}).get("content", "")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            all_text_parts.append(text)
            if not first_user_message and text.strip():
                first_user_message = text.strip()

        elif msg_type == "assistant":
            inner = msg.get("message", {})
            usage = inner.get("usage", {})
            total_input_tokens += usage.get("input_tokens", 0)
            total_output_tokens += usage.get("output_tokens", 0)

            content = inner.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            all_text_parts.append(part.get("text", ""))
                        elif part.get("type") == "tool_use":
                            tool_name = part.get("name", "unknown")
                            inp = part.get("input", {})
                            target = ""
                            if isinstance(inp, dict):
                                target = inp.get("file_path", inp.get("command", ""))[:80]
                                for v in inp.values():
                                    if isinstance(v, str):
                                        all_text_parts.append(v)
                            tool_calls.append(f"{tool_name}:{target}")

        elif msg_type == "tool_result" or msg_type == "result":
            result_content = msg.get("content", "")
            if isinstance(result_content, str) and _ERROR_PATTERNS.search(result_content):
                error_count += 1
            elif isinstance(result_content, list):
                for part in result_content:
                    if isinstance(part, dict) and _ERROR_PATTERNS.search(part.get("text", "")):
                        error_count += 1

    if not first_timestamp or not last_timestamp:
        return None

    try:
        t_start = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
        t_end = datetime.fromisoformat(last_timestamp.replace("Z", "+00:00"))
        duration_minutes = max(1, (t_end - t_start).total_seconds() / 60)
    except (ValueError, TypeError):
        return None

    total_tokens = total_input_tokens + total_output_tokens
    if total_tokens == 0:
        return None

    full_text = " ".join(all_text_parts)
    keywords = extract_keywords(full_text)

    if len(keywords) < 3:
        return None

    project = "Unknown"
    if cwd:
        project = os.path.basename(cwd) or "Unknown"

    jira_id = extract_jira_id(first_user_message)
    if not jira_id:
        jira_id = f"SESSION-{session_id[:8]}" if session_id else "SESSION-unknown"

    task_name = first_user_message[:80].replace("\n", " ").strip()
    if len(first_user_message) > 80:
        task_name += "..."

    retry_count = 0
    seen_calls: set[str] = set()
    for call_sig in tool_calls:
        if call_sig in seen_calls:
            retry_count += 1
        seen_calls.add(call_sig)

    return {
        "employee": getpass.getuser(),
        "jira_id": jira_id,
        "task_name": task_name,
        "project": project,
        "token_usage": total_tokens,
        "keywords": keywords,
        "start_time": t_start.isoformat(),
        "end_time": t_end.isoformat(),
        "source": "claude-code-session",
        "session_id": session_id,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "duration_minutes": round(duration_minutes, 1),
        "error_count": error_count,
        "retry_count": retry_count,
        "tool_call_count": len(tool_calls),
    }


# ---------------------------------------------------------------------------
# Receiver / local save
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Harvest archived Claude Code sessions into task records.")
    parser.add_argument("--mark-archived", metavar="SESSION_ID",
                        help="Mark a session ID as archived (ready for harvesting)")
    parser.add_argument("--auto-harvest", metavar="SESSION_ID",
                        help="Mark archived + harvest in one step (used by SessionEnd hook)")
    parser.add_argument("--reason", default="",
                        help="Reason for archiving (used with --mark-archived)")
    parser.add_argument("--list-archived", action="store_true",
                        help="List all sessions in the archive registry")
    parser.add_argument("--list-pending", action="store_true",
                        help="List archived sessions not yet harvested")
    args = parser.parse_args()

    # --- Auto-harvest: mark + harvest a single session (called by hook) ---
    if args.auto_harvest:
        sid = args.auto_harvest
        harvested = load_harvested()
        if sid in harvested:
            return
        mark_archived(sid, "auto (SessionEnd hook)")
        jsonl_path = find_session_jsonl(sid)
        if not jsonl_path:
            print(f"  [skip] {sid} — transcript not found")
            return
        record = parse_session(jsonl_path)
        if record is None:
            print(f"  [skip] {sid} — could not parse")
            return
        if send_to_receiver(record):
            print(f"  [receiver] {record['jira_id']} — {record['token_usage']:,} tokens")
        else:
            save_locally(record)
            print(f"  [local] {record['jira_id']} — {record['token_usage']:,} tokens")
        harvested.add(sid)
        save_harvested(harvested)
        return

    # --- Mark a session as archived ---
    if args.mark_archived:
        mark_archived(args.mark_archived, args.reason)
        return

    # --- List archived ---
    if args.list_archived:
        registry = load_archive_registry()
        if not registry:
            print("No sessions in archive registry.")
            print("Use --mark-archived <session_id> to add one.")
            return
        print(f"{'Session ID':<40} {'Archived At':<28} Reason")
        print("-" * 90)
        for sid, info in sorted(registry.items(), key=lambda x: x[1].get("archived_at", "")):
            print(f"{sid:<40} {info.get('archived_at', '')[:19]:<28} {info.get('reason', '')}")
        return

    # --- List pending (archived but not yet harvested) ---
    if args.list_pending:
        registry = load_archive_registry()
        harvested = load_harvested()
        pending = {sid: info for sid, info in registry.items() if sid not in harvested}
        if not pending:
            print("No pending sessions to harvest.")
            return
        print(f"{len(pending)} session(s) pending harvest:")
        for sid, info in pending.items():
            path = find_session_jsonl(sid)
            status = "file found" if path else "file NOT found"
            print(f"  {sid}  ({status})  archived: {info.get('archived_at', '')[:19]}")
        return

    # --- Harvest archived sessions ---
    print("Session Harvester")
    print(f"Receiver: {RECEIVER_URL}")
    print()

    registry = load_archive_registry()
    if not registry:
        print("No sessions in archive registry.")
        print()
        print("To use the harvester:")
        print("  1. Archive a session in Claude Code")
        print("  2. Run: python3 session_harvester.py --mark-archived <session_id>")
        print("  3. Run: python3 session_harvester.py")
        print()
        print("To find your session ID, check ~/.claude/sessions/ or run")
        print("  --list-archived to see what's already registered.")
        return

    harvested = load_harvested()
    new_count = 0
    skip_count = 0

    for session_id, archive_info in registry.items():
        if session_id in harvested:
            skip_count += 1
            continue

        jsonl_path = find_session_jsonl(session_id)
        if not jsonl_path:
            print(f"  [skip] {session_id} — transcript file not found")
            skip_count += 1
            continue

        record = parse_session(jsonl_path)
        if record is None:
            print(f"  [skip] {session_id} — could not parse (too short or no tokens)")
            skip_count += 1
            continue

        if send_to_receiver(record):
            dest = "receiver"
        else:
            save_locally(record)
            dest = "local file"

        print(f"  [{dest}] {record['jira_id']} — {len(record['keywords'])} keywords, "
              f"{record['token_usage']:,} tokens, {record['duration_minutes']} min")
        print(f"           Task: {record['task_name'][:60]}")
        print(f"           Keywords: {', '.join(record['keywords'][:10])}")

        harvested.add(session_id)
        new_count += 1

    save_harvested(harvested)

    print(f"\nDone: {new_count} harvested, {skip_count} skipped.")
    if new_count > 0:
        print("Run analytics.py to see updated results.")


if __name__ == "__main__":
    main()
