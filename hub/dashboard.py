#!/usr/bin/env python3
"""
NiceGUI Dashboard — unified view of team analytics, effort tracking,
blind spot remediation, and project predictions.

Tabs:
  1. Overview   — team ranking (strengths / availability), key metrics, model distribution
  2. Efforts    — epic-level effort tracking, cost/time estimation
  3. Team Health — blind spots, education plan (live Ollama), curated links
  4. Predictions — estimate new efforts, predict in-progress completion, team pairing

Usage:
    python3 dashboard.py
"""

from __future__ import annotations

import json
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from nicegui import app, ui

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

app.native.window_args["background_color"] = "#0a0a0f"

from presets import get_active_preset
from model_baselines import (
    MODEL_BASELINES, REFERENCE_MODEL, normalize_tokens,
    resolve_model, get_baseline, compute_efficiency_score,
)
from pm_provider import load_all_tickets
from code_insight import build_insight_data, load_insights, save_insights

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "output")
TASK_FILE = os.path.join(DATA_DIR, "task_data.jsonl")
SLACK_FILE = os.path.join(DATA_DIR, "slack_signals.json")

# ─── Theme ────────────────────────────────────────────────────────────────

# Light professional palette: white surfaces, one navy accent,
# muted green/red reserved for good/bad semantics only.
# (Variable names kept from the dark theme so every usage flips automatically:
#  DARK_BG is now the page background, TEXT is dark ink.)
DARK_BG = "#f4f5f7"
SURFACE = "#ffffff"
SURFACE2 = "#eceef2"
BORDER = "#d7dae1"
TEXT = "#191c24"
SUBTEXT = "#5d6370"
BLUE = "#31518a"      # navy accent
GREEN = "#25704f"     # muted green — positive
RED = "#a83a4e"       # muted red — negative
PEACH = "#7d6a52"     # warm gray-brown — mild warning
YELLOW = "#7c7147"    # muted olive
MAUVE = "#4d5578"     # slate — headings
PINK = "#7d5468"      # muted plum
CYAN = "#2e6a84"      # muted teal — nav accent
SIDEBAR_BG = "#ffffff"
SIDEBAR_W = "52px"
SIDEBAR_W_EXPANDED = "200px"

CUSTOM_CSS = f"""
<style>
:root {{
    --nicegui-default-padding: 0;
    --nicegui-default-gap: 0;
}}
body, .q-page, .nicegui-content {{
    background: {DARK_BG} !important;
    color: {TEXT} !important;
    overflow-x: hidden;
}}
body, body * {{
    font-family: "Helvetica Neue", Helvetica, "Segoe UI", Arial, sans-serif !important;
}}
pre, code, .monospace {{
    font-family: "SF Mono", Menlo, Consolas, monospace !important;
}}
/* Sharp, squared edges everywhere */
#main-content div, #main-content span, .q-card, .q-btn, .q-field__control {{
    border-radius: 0 !important;
}}
/* ── Sidebar ── */
#sidebar {{
    position: fixed;
    top: 0; left: 0; bottom: 0;
    width: {SIDEBAR_W};
    background: {SIDEBAR_BG};
    border-right: 1px solid {BORDER};
    z-index: 1000;
    display: flex;
    flex-direction: column;
    transition: width 0.2s ease;
    overflow: hidden;
}}
#sidebar:hover {{
    width: {SIDEBAR_W_EXPANDED};
}}
#sidebar .brand {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 16px 12px;
    border-bottom: 1px solid {BORDER};
    white-space: nowrap;
    min-height: 56px;
}}
#sidebar .brand .brand-icon {{
    width: 28px; height: 28px;
    background: {BLUE};
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 14px; color: {DARK_BG};
    flex-shrink: 0;
}}
#sidebar .brand .brand-text {{
    font-size: 15px; font-weight: 700; color: {TEXT};
    opacity: 0;
    transition: opacity 0.15s ease 0.05s;
}}
#sidebar:hover .brand .brand-text {{ opacity: 1; }}
.nav-item {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    cursor: pointer;
    border-left: 3px solid transparent;
    transition: all 0.15s ease;
    white-space: nowrap;
}}
.nav-item:hover {{
    background: {SURFACE2};
}}
.nav-item.active {{
    border-left-color: {CYAN};
    background: {SURFACE};
}}
.nav-item .nav-icon {{
    width: 24px; height: 24px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
}}
.nav-item .nav-label {{
    font-size: 15px;
    color: {SUBTEXT};
    font-weight: 500;
    opacity: 0;
    transition: opacity 0.15s ease 0.05s;
}}
#sidebar:hover .nav-label {{ opacity: 1; }}
.nav-item.active .nav-icon {{ color: {CYAN}; }}
.nav-item.active .nav-label {{ color: {TEXT}; font-weight: 600; }}
/* ── Main content ── */
#main-content {{
    margin-left: {SIDEBAR_W};
    min-height: 100vh;
    transition: margin-left 0.2s ease;
    zoom: 1.5;                /* across-the-board larger text / fill screen */
}}
.page-section {{ display: none; padding: 36px 48px; max-width: 1450px; margin: 0 auto; }}
.page-section.active {{ display: block; }}
/* ── Components ── */
.q-card {{
    background: {SURFACE} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 0 !important;
    color: {TEXT} !important;
    box-shadow: none !important;
    padding: 8px !important;
}}
.section-title {{
    color: {TEXT};
    font-size: 23px;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin-bottom: 10px;
}}
.stat-value {{
    font-size: 40px;
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.15;
}}
.stat-label {{
    font-size: 14px;
    color: {SUBTEXT};
    margin-top: 3px;
}}
.status-chip {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 0;
    font-size: 13px;
    font-weight: 600;
}}
.status-done {{ background: {MAUVE}20; color: {MAUVE}; }}
.status-in_progress {{ background: {PEACH}20; color: {PEACH}; }}
.status-planning {{ background: {PEACH}20; color: {PEACH}; }}
.blind-spot-tag {{
    background: {RED}20;
    color: {RED};
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 600;
}}
.q-field__native, .q-field__input {{
    color: {TEXT} !important;
}}
.q-field__label {{
    color: {SUBTEXT} !important;
}}
.q-select__dropdown {{
    background: {SURFACE2} !important;
    color: {TEXT} !important;
}}
.advisor-output {{
    background: transparent;
    font-size: 15px;
    line-height: 1.65;
    max-height: 700px;
    overflow-y: auto;
}}
.advisor-output .pipeline {{
    display: flex;
    align-items: stretch;
    gap: 0;
    margin: 20px 0 28px 0;
}}
.advisor-output .pipeline-step {{
    flex: 1;
    position: relative;
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 16px 18px;
    min-width: 0;
}}
.advisor-output .pipeline-step .step-num {{
    display: inline-block;
    background: {MAUVE}30;
    color: {MAUVE};
    font-size: 12px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 10px;
    margin-bottom: 6px;
}}
.advisor-output .pipeline-arrow {{
    display: flex;
    align-items: center;
    padding: 0 4px;
    color: {BORDER};
    font-size: 20px;
}}
.advisor-output .topic-block {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 20px;
}}
.advisor-output .topic-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid {BORDER};
}}
.advisor-output .topic-icon {{
    width: 36px;
    height: 36px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
}}
.advisor-output .topic-name {{
    font-size: 16px;
    font-weight: 700;
    color: {TEXT};
}}
.advisor-output .section-label {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin: 14px 0 8px 0;
    padding-bottom: 4px;
}}
.advisor-output .section-label .dot {{
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
}}
.advisor-output ul {{
    margin: 0 0 4px 0;
    padding-left: 18px;
}}
.advisor-output li {{
    margin-bottom: 5px;
    color: {SUBTEXT};
    font-size: 13px;
}}
.advisor-output li strong {{
    color: {TEXT};
}}
.advisor-output .trend-block {{
    background: linear-gradient(135deg, {SURFACE} 0%, {PEACH}08 100%);
    border: 1px solid {PEACH}40;
    border-radius: 10px;
    padding: 20px 24px;
    margin-top: 8px;
}}
.prediction-card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 20px;
}}
.range-bar {{
    height: 8px;
    border-radius: 4px;
    position: relative;
}}
/* Fix for pywebview native mode — Quasar ripple overlay blocks clicks */
.q-btn .q-ripple {{ display: none !important; }}
.q-btn .q-focus-helper {{ display: none !important; }}
</style>
"""


# ─── Data Loading ─────────────────────────────────────────────────────────

def load_all_data() -> dict:
    preset = get_active_preset()
    records = []
    if os.path.exists(TASK_FILE):
        with open(TASK_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

    tickets = load_all_tickets()

    for r in records:
        t = tickets.get(r.get("jira_id", ""), {})
        r["jira_reopen_count"] = t.get("reopen_count", 0)
        r["jira_status"] = t.get("status", "")
        r["jira_sprint"] = t.get("sprint", "")
        r["jira_components"] = t.get("components", [])
        r["jira_story_points"] = t.get("story_points", 0)

        model = r.get("model", "unknown")
        raw_tokens = r.get("token_usage", 0)
        r["normalized_tokens"] = normalize_tokens(raw_tokens, model)

        start = datetime.fromisoformat(r["start_time"])
        end = datetime.fromisoformat(r["end_time"])
        r["duration_minutes"] = max(1, (end - start).total_seconds() / 60)

    slack_data = {}
    if os.path.exists(SLACK_FILE):
        with open(SLACK_FILE) as f:
            slack_data = json.load(f)

    return {
        "preset": preset,
        "records": records,
        "tickets": tickets,
        "epics": preset.get("epics", []),
        "slack": slack_data,
    }


def compute_metrics(records: list[dict]) -> dict:
    if not records:
        return {}

    total_tasks = len(records)
    total_tokens = sum(r.get("token_usage", 0) for r in records)
    total_norm_tokens = sum(r.get("normalized_tokens", 0) for r in records)
    total_duration = sum(r.get("duration_minutes", 0) for r in records)
    total_errors = sum(r.get("error_count", 0) for r in records)
    employees = set(r["employee"] for r in records)
    topics = set()

    topic_kw = {t: set(cfg["keywords"])
                for t, cfg in get_active_preset()["topics"].items()}
    for r in records:
        kw = set(r.get("keywords", []))
        best, best_s = "Unknown", 0
        for t, pool in topic_kw.items():
            s = len(kw & pool)
            if s > best_s:
                best, best_s = t, s
        r["_topic"] = best
        topics.add(best)

    model_counts = defaultdict(int)
    for r in records:
        m = r.get("model", "unknown")
        display = MODEL_BASELINES.get(m, {}).get("display_name", m)
        model_counts[display] += 1

    return {
        "total_tasks": total_tasks,
        "total_tokens": total_tokens,
        "total_norm_tokens": total_norm_tokens,
        "total_duration_hrs": total_duration / 60,
        "total_errors": total_errors,
        "avg_errors_per_task": total_errors / total_tasks,
        "employee_count": len(employees),
        "topic_count": len(topics),
        "model_counts": dict(model_counts),
    }


def compute_team_ranking(records: list[dict]) -> list[dict]:
    """Rank employees by performance vs team benchmarks.

    For each employee/topic pair (min 3 tasks), compare avg errors, duration
    and tokens against the team's topic average. A ratio < 1 means better
    than the team. Strengths are the topics with the best ratios, weaknesses
    the worst. Ticket count doubles as an availability signal.

    Relies on r["_topic"] set by compute_metrics().
    """
    team_topic: dict[str, dict] = defaultdict(lambda: {"err": [], "dur": [], "tok": []})
    per_emp: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: {"err": [], "dur": [], "tok": []}))

    for r in records:
        topic = r.get("_topic", "Unknown")
        if topic == "Unknown":
            continue
        err = r.get("error_count", 0)
        dur = r.get("duration_minutes", 0)
        tok = r.get("normalized_tokens") or r.get("token_usage", 0)
        team_topic[topic]["err"].append(err)
        team_topic[topic]["dur"].append(dur)
        team_topic[topic]["tok"].append(tok)
        per_emp[r["employee"]][topic]["err"].append(err)
        per_emp[r["employee"]][topic]["dur"].append(dur)
        per_emp[r["employee"]][topic]["tok"].append(tok)

    def _avg(lst):
        return sum(lst) / len(lst) if lst else 0

    bench = {t: {k: _avg(v[k]) for k in ("err", "dur", "tok")}
             for t, v in team_topic.items()}

    def _ratio(emp_avg, team_avg):
        if team_avg <= 0:
            return 1.0
        return emp_avg / team_avg

    ranking = []
    for emp, topics in per_emp.items():
        topic_scores = []       # (topic, combined_ratio, task_count)
        tickets = 0
        for topic, vals in topics.items():
            n = len(vals["err"])
            tickets += n
            b = bench[topic]
            combined = (0.45 * _ratio(_avg(vals["err"]), b["err"])
                        + 0.30 * _ratio(_avg(vals["dur"]), b["dur"])
                        + 0.25 * _ratio(_avg(vals["tok"]), b["tok"]))
            topic_scores.append((topic, combined, n))

        if not topic_scores:
            continue

        total_n = sum(n for _, _, n in topic_scores)
        mean_ratio = sum(s * n for _, s, n in topic_scores) / total_n
        vs_team_pct = (1 - mean_ratio) * 100        # positive = better than team

        # Strengths/weaknesses need at least 2 tasks in a topic to count.
        qualified = [(t, s) for t, s, n in sorted(topic_scores, key=lambda x: x[1])
                     if n >= 2]
        strengths = [(t, (1 - s) * 100) for t, s in qualified if s <= 0.92][:4]
        weaknesses = [(t, (s - 1) * 100) for t, s in reversed(qualified) if s >= 1.08][:3]

        ranking.append({
            "employee": emp,
            "vs_team_pct": vs_team_pct,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "tickets": tickets,
        })

    ranking.sort(key=lambda x: -x["vs_team_pct"])
    avg_tickets = _avg([r["tickets"] for r in ranking])
    for r in ranking:
        r["load"] = ("light" if r["tickets"] < avg_tickets * 0.85
                     else "heavy" if r["tickets"] > avg_tickets * 1.15
                     else "normal")
    return ranking


def compute_epic_data(records: list[dict], epics: list[dict]) -> list[dict]:
    """Compute effort/cost/time estimates per epic from task data."""
    topic_kw = {t: set(cfg["keywords"])
                for t, cfg in get_active_preset()["topics"].items()}

    topic_stats: dict[str, dict] = defaultdict(lambda: {
        "durations": [], "tokens": [], "norm_tokens": [],
        "errors": [], "retries": [], "reopens": [],
    })

    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    for r in records:
        try:
            ts = datetime.fromisoformat(r["start_time"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            continue
        if ts < cutoff:
            continue

        kw = set(r.get("keywords", []))
        best, best_s = "Unknown", 0
        for t, pool in topic_kw.items():
            s = len(kw & pool)
            if s > best_s:
                best, best_s = t, s

        s = topic_stats[best]
        s["durations"].append(r.get("duration_minutes", 0))
        s["tokens"].append(r.get("token_usage", 0))
        s["norm_tokens"].append(r.get("normalized_tokens", 0))
        s["errors"].append(r.get("error_count", 0))
        s["retries"].append(r.get("retry_count", 0))
        s["reopens"].append(r.get("jira_reopen_count", 0))

    def _avg(lst):
        return sum(lst) / len(lst) if lst else 0

    topic_avgs = {}
    for t, s in topic_stats.items():
        topic_avgs[t] = {
            "avg_duration": _avg(s["durations"]),
            "avg_tokens": _avg(s["tokens"]),
            "avg_norm_tokens": _avg(s["norm_tokens"]),
            "avg_errors": _avg(s["errors"]),
            "count": len(s["durations"]),
            "std_duration": (sum((d - _avg(s["durations"]))**2 for d in s["durations"]) / max(1, len(s["durations"])))**0.5,
        }

    epic_results = []
    for epic in epics:
        total_dur_opt = 0
        total_dur_exp = 0
        total_dur_pes = 0
        total_tokens = 0
        total_norm_tokens = 0
        total_errors = 0
        ticket_count = epic.get("ticket_count", 20)

        for topic in epic.get("topics", []):
            avg = topic_avgs.get(topic, topic_avgs.get("Unknown", {
                "avg_duration": 60, "avg_tokens": 2000, "avg_norm_tokens": 2000,
                "avg_errors": 2, "std_duration": 20, "count": 0,
            }))
            n = ticket_count // len(epic["topics"])
            std = avg.get("std_duration", 20)
            total_dur_opt += n * max(5, avg["avg_duration"] - std * 0.5)
            total_dur_exp += n * avg["avg_duration"]
            total_dur_pes += n * (avg["avg_duration"] + std * 0.7)
            total_tokens += n * avg["avg_tokens"]
            total_norm_tokens += n * avg["avg_norm_tokens"]
            total_errors += n * avg["avg_errors"]

        # Compute completion % for in-progress epics
        done_count = 0
        if epic["status"] == "done":
            done_count = ticket_count
        elif epic["status"] == "in_progress":
            done_count = int(ticket_count * random.uniform(0.3, 0.75))

        remaining = ticket_count - done_count
        pct_done = (done_count / ticket_count * 100) if ticket_count else 0

        blended_cost = total_norm_tokens * 9.0 / 1_000_000

        epic_results.append({
            **epic,
            "done_count": done_count,
            "remaining": remaining,
            "pct_done": round(pct_done, 1),
            "est_duration_opt_hrs": round(total_dur_opt / 60, 1),
            "est_duration_exp_hrs": round(total_dur_exp / 60, 1),
            "est_duration_pes_hrs": round(total_dur_pes / 60, 1),
            "est_remaining_opt_hrs": round(total_dur_opt / 60 * remaining / max(1, ticket_count), 1),
            "est_remaining_exp_hrs": round(total_dur_exp / 60 * remaining / max(1, ticket_count), 1),
            "est_remaining_pes_hrs": round(total_dur_pes / 60 * remaining / max(1, ticket_count), 1),
            "est_tokens": int(total_tokens),
            "est_norm_tokens": int(total_norm_tokens),
            "est_errors": round(total_errors, 1),
            "est_cost": round(blended_cost, 2),
        })

    return epic_results


RESOURCE_URLS = {
    "OpenAPI 3.1": "https://spec.openapis.org/oas/v3.1.0",
    "gRPC best practices": "https://grpc.io/docs/guides/",
    "FastAPI": "https://github.com/tiangolo/fastapi",
    "Swagger/OpenAPI codegen": "https://github.com/OpenAPITools/openapi-generator",
    "Pact (contract testing)": "https://github.com/pact-foundation/pact-python",
    "API Design Patterns (book)": "https://www.manning.com/books/api-design-patterns",
    "FastAPI docs tutorial (free)": "https://fastapi.tiangolo.com/tutorial/",
    "DORA metrics": "https://dora.dev/guides/dora-metrics-four-keys/",
    "12-factor app": "https://12factor.net/",
    "GitHub Actions": "https://github.com/features/actions",
    "ArgoCD": "https://github.com/argoproj/argo-cd",
    "Renovate": "https://github.com/renovatebot/renovate",
    "Google SRE Book (free)": "https://sre.google/sre-book/table-of-contents/",
    "DevOps Handbook": "https://itrevolution.com/product/the-devops-handbook-second-edition/",
    "AWS Well-Architected": "https://aws.amazon.com/architecture/well-architected/",
    "Terraform": "https://github.com/hashicorp/terraform",
    "Pulumi": "https://github.com/pulumi/pulumi",
    "Infracost": "https://github.com/infracost/infracost",
    "Cloud Design Patterns (Microsoft)": "https://learn.microsoft.com/en-us/azure/architecture/patterns/",
    "SonarQube": "https://github.com/SonarSource/sonarqube",
    "ESLint": "https://github.com/eslint/eslint",
    "CodeClimate": "https://codeclimate.com/",
    "Refactoring Guru (free)": "https://refactoring.guru/",
    "Clean Code (book)": "https://www.oreilly.com/library/view/clean-code-a/9780136083238/",
    "Apache Airflow": "https://github.com/apache/airflow",
    "dbt": "https://github.com/dbt-labs/dbt-core",
    "Great Expectations": "https://github.com/great-expectations/great_expectations",
    "Designing Data-Intensive Applications (book)": "https://dataintensive.net/",
    "PostgreSQL": "https://www.postgresql.org/docs/",
    "Alembic": "https://github.com/sqlalchemy/alembic",
    "pganalyze": "https://pganalyze.com/",
    "Database Reliability Engineering (book)": "https://www.oreilly.com/library/view/database-reliability-engineering/9781491925935/",
    "React": "https://github.com/facebook/react",
    "Storybook": "https://github.com/storybookjs/storybook",
    "Playwright": "https://github.com/microsoft/playwright",
    "web.dev (free)": "https://web.dev/",
    "MLflow": "https://github.com/mlflow/mlflow",
    "Weights & Biases": "https://github.com/wandb/wandb",
    "LangChain": "https://github.com/langchain-ai/langchain",
    "Designing Machine Learning Systems (book)": "https://www.oreilly.com/library/view/designing-machine-learning/9781098107956/",
    "Prometheus": "https://github.com/prometheus/prometheus",
    "Grafana": "https://github.com/grafana/grafana",
    "OpenTelemetry": "https://github.com/open-telemetry/opentelemetry-python",
    "Observability Engineering (book)": "https://www.oreilly.com/library/view/observability-engineering/9781492076438/",
    "k6": "https://github.com/grafana/k6",
    "Locust": "https://github.com/locustio/locust",
    "py-spy": "https://github.com/benfred/py-spy",
    "High Performance Python (book)": "https://www.oreilly.com/library/view/high-performance-python/9781492055013/",
    "OWASP Top 10": "https://owasp.org/www-project-top-ten/",
    "Snyk": "https://github.com/snyk/cli",
    "Trivy": "https://github.com/aquasecurity/trivy",
    "HashiCorp Vault": "https://github.com/hashicorp/vault",
    "NIST Cybersecurity Framework": "https://www.nist.gov/cyberframework",
    "pytest": "https://github.com/pytest-dev/pytest",
    "Hypothesis": "https://github.com/HypothesisWorks/hypothesis",
    "Coverage.py": "https://github.com/nedbat/coveragepy",
    "Python Testing with pytest (book)": "https://pragprog.com/titles/bopytest2/python-testing-with-pytest-second-edition/",
}


def _resource_link(name: str) -> str:
    """Return an HTML link for a resource, or plain text if no URL known."""
    import html as _html
    url = RESOURCE_URLS.get(name)
    safe = _html.escape(name)
    if url:
        return f'<a href="{url}" target="_blank" style="color:{BLUE}; text-decoration:none">{safe}</a>'
    return f'<span style="color:{SUBTEXT}">{safe}</span>'


def _format_advisor_report(raw_text: str) -> str:
    """Parse advisor plain-text report into styled HTML with pipeline visuals."""
    import html as _html
    import re

    lines = raw_text.split("\n")
    blocks: list[dict] = []
    current_topic: dict | None = None

    topic_icons = {
        "ML & AI": f"background:{MAUVE}25; color:{MAUVE}",
        "Security": f"background:{RED}25; color:{RED}",
        "Frontend": f"background:{MAUVE}25; color:{MAUVE}",
        "Backend": f"background:{MAUVE}25; color:{MAUVE}",
        "Cloud": f"background:{PEACH}25; color:{PEACH}",
        "CI/CD": f"background:{PEACH}25; color:{PEACH}",
        "Database": f"background:{MAUVE}25; color:{MAUVE}",
        "Performance": f"background:{PEACH}25; color:{PEACH}",
        "Monitoring": f"background:{PEACH}25; color:{PEACH}",
        "Code Review": f"background:{MAUVE}25; color:{MAUVE}",
        "Data Engineering": f"background:{MAUVE}25; color:{MAUVE}",
        "Emerging": f"background:{PEACH}25; color:{PEACH}",
    }

    def _icon_style(name: str) -> str:
        for key, style in topic_icons.items():
            if key.lower() in name.lower():
                return style
        return f"background:{MAUVE}25; color:{MAUVE}"

    section_colors = {
        "ROOT CAUSE": RED,
        "RECOMMENDED TOOL": MAUVE,
        "BEST PRACTICE": MAUVE,
        "QUICK WIN": PEACH,
        "WHAT": PEACH,
        "WHY NOW": PEACH,
        "RISK": RED,
        "QUICK START": PEACH,
    }

    def _section_color(label: str) -> str:
        for key, color in section_colors.items():
            if key in label.upper():
                return color
        return SUBTEXT

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        i += 1

        if not stripped:
            continue
        if re.match(r'^-{4,}$', stripped):
            continue
        if stripped.startswith("VALON AI") or stripped.startswith("Generated:") or stripped.startswith("Model:"):
            continue
        if stripped.startswith("TOPIC RESEARCH"):
            continue

        if re.match(r'^={4,}$', stripped):
            if i < len(lines):
                name_line = lines[i].strip()
                i += 1
                while i < len(lines) and not re.match(r'^={4,}$', lines[i].strip()):
                    i += 1
                if i < len(lines):
                    i += 1
                skip_words = ("advisor", "report", "valon", "generated", "model:", "curated resource", "appendix")
                if name_line and not any(w in name_line.lower() for w in skip_words):
                    if current_topic:
                        blocks.append(current_topic)
                    is_trend = "trend" in name_line.lower() or "emerging" in name_line.lower()
                    current_topic = {"name": name_line.strip(), "sections": [], "is_trend": is_trend}
            continue

        if not current_topic:
            continue

        section_match = re.match(r'^\*\*(.+?):?\*\*:?$', stripped)
        if section_match:
            label = section_match.group(1).strip(": ")
            current_topic["sections"].append({"label": label, "items": []})
            continue

        md_header_match = re.match(r'^#{1,4}\s+(.+?):?\s*$', stripped)
        if md_header_match:
            label = md_header_match.group(1).strip(": ")
            skip_headers = ("tier 1", "tier 2", "tier 3", "education", "tooling plan")
            if not any(s in label.lower() for s in skip_headers):
                current_topic["sections"].append({"label": label, "items": []})
            continue

        if stripped.startswith("**") and ":**" in stripped:
            parts = stripped.split(":**", 1)
            label = parts[0].strip("* ")
            rest = parts[1].strip().rstrip("*").strip() if len(parts) > 1 else ""
            if rest:
                current_topic["sections"].append({"label": label, "items": [rest]})
            else:
                current_topic["sections"].append({"label": label, "items": []})
            continue

        if re.match(r'^[\*\-•]\s', stripped) or re.match(r'^\d+\.\s', stripped):
            item = re.sub(r'^[\*\-•]\s*', '', stripped)
            item = re.sub(r'^\d+\.\s*', '', item)
            if current_topic["sections"]:
                current_topic["sections"][-1]["items"].append(item)
            continue

        if current_topic["sections"] and stripped:
            current_topic["sections"][-1]["items"].append(stripped)

    if current_topic:
        blocks.append(current_topic)

    out = []
    for block in blocks:
        is_trend = block.get("is_trend", False)
        css_class = "trend-block" if is_trend else "topic-block"
        icon_sym = "⚡" if is_trend else "◎"
        icon_s = _icon_style(block["name"])

        out.append(f'<div class="{css_class}">')
        out.append(f'<div class="topic-header">')
        out.append(f'<div class="topic-icon" style="{icon_s}">{icon_sym}</div>')
        out.append(f'<div class="topic-name">{_html.escape(block["name"])}</div>')
        out.append('</div>')

        quick_wins = []
        other_sections = []
        for sec in block["sections"]:
            if "QUICK WIN" in sec["label"].upper() or "QUICK START" in sec["label"].upper():
                quick_wins = sec["items"]
            else:
                other_sections.append(sec)

        def _linkify(text):
            """Convert escaped URLs back to clickable links."""
            return re.sub(
                r'(https?://[^\s<&]+)',
                rf'<a href="\1" target="_blank" style="color:{BLUE}; text-decoration:none">\1</a>',
                text)

        for sec in other_sections:
            color = _section_color(sec["label"])
            out.append(f'<div class="section-label"><span class="dot" style="background:{color}"></span>'
                       f'<span style="color:{color}">{_html.escape(sec["label"])}</span></div>')
            out.append("<ul>")
            for item in sec["items"]:
                safe = _html.escape(item)
                safe = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', safe)
                safe = _linkify(safe)
                out.append(f"<li>{safe}</li>")
            out.append("</ul>")

        if quick_wins:
            out.append(f'<div class="section-label" style="margin-top:16px">'
                       f'<span class="dot" style="background:{PEACH}"></span>'
                       f'<span style="color:{PEACH}">ACTION PIPELINE</span></div>')
            out.append('<div class="pipeline">')
            for i, item in enumerate(quick_wins):
                safe = _html.escape(item)
                safe = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', safe)
                safe = _linkify(safe)
                out.append(f'<div class="pipeline-step"><span class="step-num">STEP {i+1}</span>'
                           f'<div style="margin-top:6px; color:{SUBTEXT}; font-size:12px">{safe}</div></div>')
                if i < len(quick_wins) - 1:
                    out.append(f'<div class="pipeline-arrow">▶</div>')
            out.append('</div>')

        out.append('</div>')

    return "\n".join(out) if out else f'<pre style="color:{SUBTEXT}; white-space:pre-wrap">{_html.escape(raw_text)}</pre>'


def compute_ideal_team(records: list[dict], epic_topics: list[str],
                       team_size: int = 4) -> list[dict]:
    """Rank employees for an epic based on topic strength and current workload."""
    preset = get_active_preset()
    topic_kw = {t: set(cfg["keywords"]) for t, cfg in preset["topics"].items()}
    employees = preset["employees"]
    employee_models = preset.get("employee_models", {})

    emp_topic: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(
        lambda: {"count": 0, "total_errors": 0, "total_duration": 0, "total_norm_tokens": 0}
    ))
    emp_open_tickets: dict[str, int] = defaultdict(int)

    for r in records:
        emp = r.get("employee", "")
        if not emp:
            continue

        kw = set(r.get("keywords", []))
        best, best_s = "Unknown", 0
        for t, pool in topic_kw.items():
            s = len(kw & pool)
            if s > best_s:
                best, best_s = t, s

        s = emp_topic[emp][best]
        s["count"] += 1
        s["total_errors"] += r.get("error_count", 0)
        s["total_duration"] += r.get("duration_minutes", 0)
        s["total_norm_tokens"] += r.get("normalized_tokens", r.get("token_usage", 0))

        jira_status = r.get("jira_status", "").lower().replace(" ", "_")
        sprint = r.get("jira_sprint", "")
        if jira_status in ("in_progress", "to_do", "open", "in_review") and sprint:
            emp_open_tickets[emp] += 1

    results = []
    for emp in employees:
        topic_scores = []
        for topic in epic_topics:
            ts = emp_topic[emp][topic]
            if ts["count"] == 0:
                topic_scores.append({"topic": topic, "experience": 0,
                                     "avg_errors": 0, "score": 0})
                continue
            avg_err = ts["total_errors"] / ts["count"]
            avg_dur = ts["total_duration"] / ts["count"]
            error_score = max(0, 10 - avg_err * 2)
            speed_score = max(0, 10 - avg_dur / 30)
            exp_score = min(10, ts["count"] / 5 * 10)
            combined = exp_score * 0.4 + error_score * 0.35 + speed_score * 0.25
            topic_scores.append({
                "topic": topic, "experience": ts["count"],
                "avg_errors": round(avg_err, 1), "score": round(combined, 1),
            })

        avg_score = sum(t["score"] for t in topic_scores) / max(1, len(topic_scores))
        total_exp = sum(t["experience"] for t in topic_scores)
        open_tickets = emp_open_tickets.get(emp, 0)
        workload_penalty = min(3, open_tickets * 0.3)

        model_id = employee_models.get(emp, "unknown")
        quality = MODEL_BASELINES.get(model_id, {}).get("quality_factor", 0.8)
        quality_bonus = (quality - 0.8) * 10

        final_score = max(0, avg_score + quality_bonus - workload_penalty)

        if open_tickets > 8:
            availability = "Overloaded"
            avail_color = RED
        elif open_tickets > 4:
            availability = "Busy"
            avail_color = PEACH
        else:
            availability = "Available"
            avail_color = MAUVE

        results.append({
            "employee": emp,
            "score": round(final_score, 1),
            "topic_scores": topic_scores,
            "total_experience": total_exp,
            "open_tickets": open_tickets,
            "availability": availability,
            "avail_color": avail_color,
            "model": MODEL_BASELINES.get(model_id, {}).get("display_name", model_id),
            "quality": quality,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def get_blind_spots(records: list[dict]) -> list[dict]:
    """Quick blind spot detection from records."""
    import pandas as pd
    from analytics import classify_topic, build_benchmarks, compute_difficulty_scores

    df = pd.DataFrame(records)
    df["start_time"] = pd.to_datetime(df["start_time"], format="ISO8601")
    df["end_time"] = pd.to_datetime(df["end_time"], format="ISO8601")
    df["duration_minutes"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 60

    for col in ["error_count", "retry_count", "tool_call_count", "jira_reopen_count"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = df[col].fillna(0).astype(int)

    if "model" not in df.columns:
        df["model"] = "unknown"
    df["normalized_tokens"] = df.apply(
        lambda row: normalize_tokens(row.get("token_usage", 0), row.get("model", "unknown")),
        axis=1)

    topic_kw = {t: set(cfg["keywords"])
                for t, cfg in get_active_preset()["topics"].items()}
    df["topic"] = df["keywords"].apply(
        lambda kws: classify_topic(kws) if isinstance(kws, list) else "Unknown")

    bench = build_benchmarks(df)
    bench = compute_difficulty_scores(bench)
    spots = bench[bench["is_team_blind_spot"]].to_dict("records")
    return spots


# ─── UI Builder ───────────────────────────────────────────────────────────

def build_dashboard():
    data = load_all_data()
    records = data["records"]
    preset = data["preset"]
    metrics = compute_metrics(records)
    epic_data = compute_epic_data(records, data["epics"])
    blind_spots = get_blind_spots(records)
    curated = preset.get("curated_sources", {})
    slack_data = data.get("slack", {})

    ui.add_head_html(CUSTOM_CSS)

    NAV_ITEMS = [
        ("overview", "◎", "Overview"),
        ("efforts", "▤", "Efforts"),
        ("health", "♥", "Team Health"),
        ("slack", "⊞", "Slack"),
        ("insights", "⚑", "Code Insights"),
        ("predictions", "◈", "Predictions"),
    ]

    # ─── Sidebar ────────────────────────────
    with ui.element("div").props('id="sidebar"'):
        with ui.element("div").classes("brand"):
            ui.html(sanitize=False, content=
                f'<div class="brand-icon">V</div>'
                f'<span class="brand-text">{preset["company"]}</span>')

        for nav_id, icon, label in NAV_ITEMS:
            active = " active" if nav_id == "overview" else ""
            ui.html(sanitize=False, content=
                f'<div class="nav-item{active}" data-nav="{nav_id}" '
                f'onclick="switchSection(\'{nav_id}\')">'
                f'<div class="nav-icon">{icon}</div>'
                f'<span class="nav-label">{label}</span>'
                f'</div>')

    ui.add_head_html(f"""<script>
    function switchSection(id) {{
        document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        var sec = document.getElementById('section-' + id);
        if (sec) sec.classList.add('active');
        var nav = document.querySelector('.nav-item[data-nav="' + id + '"]');
        if (nav) nav.classList.add('active');
        window.scrollTo(0, 0);
    }}
    </script>""")

    # ─── Main Content ───────────────────────
    with ui.element("div").props('id="main-content"'):

        # ════════════════════════════════════════════════
        # SECTION 1: OVERVIEW
        # ════════════════════════════════════════════════
        with ui.element("div").props('id="section-overview"').classes("page-section active"):
            # Metric cards row
            with ui.element("div").style(
                    "display:flex; flex-direction:row; gap:16px; width:100%; margin-bottom:24px; flex-wrap:wrap"):
                _metric_card("Tasks Tracked", f"{metrics['total_tasks']:,}", BLUE)
                _metric_card("Team Members", str(metrics['employee_count']), GREEN)
                _metric_card("Total Hours", f"{metrics['total_duration_hrs']:,.0f}", PEACH)
                _metric_card("Avg Errors/Task", f"{metrics['avg_errors_per_task']:.1f}", RED)
                _metric_card("Blind Spots", str(len(blind_spots)), RED if blind_spots else GREEN)

            # Team ranking
            with ui.card().classes("w-full mb-6 p-4"):
                ui.label("Team Ranking").classes("section-title")
                ui.label(
                    "Ranked by overall performance vs team benchmarks. "
                    "Ticket count reflects current availability."
                ).style(f"color:{SUBTEXT}; font-size:14px; margin-bottom:14px")
                with ui.element("div").style(
                        "display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); "
                        "gap:14px; width:100%"):
                    for i, rk in enumerate(compute_team_ranking(records), 1):
                        _render_ranking_row(i, rk)

            # Model distribution
            with ui.card().classes("w-full p-4"):
                ui.label("AI Model Distribution").classes("section-title")
                with ui.element("div").style(
                        "display:flex; flex-wrap:wrap; gap:12px; width:100%"):
                    for model, count in sorted(metrics.get("model_counts", {}).items(),
                                               key=lambda x: -x[1]):
                        pct = count / metrics["total_tasks"] * 100
                        with ui.element("div").style(
                                f"background:{SURFACE2}; border-radius:8px; padding:12px 16px; "
                                f"min-width:120px; text-align:center"):
                            ui.label(f"{count}").style(
                                f"font-size:20px; font-weight:700; color:{BLUE}")
                            ui.label(model).style(
                                f"font-size:13px; color:{SUBTEXT}; text-align:center")
                            ui.label(f"{pct:.0f}%").style(
                                f"font-size:13px; color:{SUBTEXT}")

        # ════════════════════════════════════════════════
        # SECTION 2: EFFORTS
        # ════════════════════════════════════════════════
        with ui.element("div").props('id="section-efforts"').classes("page-section"):
            ui.label("Epic / Effort Tracking").classes("section-title mb-4")
            ui.label(
                "Aggregated cost and time estimates per epic, based on 60-day rolling averages."
            ).style(f"color:{SUBTEXT}; font-size:13px; margin-bottom:16px")

            for epic in epic_data:
                _render_epic_card(epic, blind_spots, records)

        # ════════════════════════════════════════════════
        # SECTION 3: TEAM HEALTH
        # ════════════════════════════════════════════════
        with ui.element("div").props('id="section-health"').classes("page-section"):
            # Blind spots summary
            ui.label("Team Blind Spots").classes("section-title mb-2")
            if blind_spots:
                ui.label(
                    f"{len(blind_spots)} topic(s) where the entire team underperforms. "
                    f"The 'best' person is just least bad."
                ).style(f"color:{SUBTEXT}; font-size:13px; margin-bottom:16px")

                for bs in blind_spots:
                    with ui.card().classes("w-full mb-3 p-4"):
                        with ui.row().classes("items-center gap-3 mb-2"):
                            ui.html(sanitize=False, content=f'<span class="blind-spot-tag">BLIND SPOT</span>')
                            ui.label(bs["topic"]).style(
                                f"font-size:15px; font-weight:600; color:{TEXT}")
                        with ui.row().classes("gap-6"):
                            _mini_stat("Difficulty Score", f"{bs['difficulty_score']:.1f}", RED)
                            _mini_stat("Avg Errors/Task", f"{bs['avg_errors']:.1f}", RED)
                            _mini_stat("Avg Duration", f"{bs['avg_duration']:.0f} min", PEACH)
                            _mini_stat("Avg Retries", f"{bs['avg_retries']:.1f}", PEACH)
            else:
                ui.label("No team-wide blind spots detected.").style(f"color:{MAUVE}")

            ui.separator().style(f"background:{BORDER}; margin:24px 0")

            # Action plan generator
            ui.label("AI Action Plan Generator").classes("section-title mb-2")
            ui.label(
                "Generates a fresh education and tooling plan using the local LLM (Ollama). "
                "Only targets team blind spots + one emerging trend."
            ).style(f"color:{SUBTEXT}; font-size:13px; margin-bottom:12px")

            plan_output = ui.html(sanitize=False, content="").classes("advisor-output").style("display:none")

            def generate_plan():
                import threading as _t

                btn.disable()
                spinner.set_visibility(True)
                plan_output.style("display:block")
                plan_output.set_content(f'<span style="color:{SUBTEXT}">Generating plan via Ollama... this may take 30-60 seconds.</span>')

                def _run():
                    import subprocess
                    try:
                        env = dict(os.environ, ADVISOR_NO_OPEN="1")
                        result = subprocess.run(
                            [sys.executable, os.path.join(os.path.dirname(__file__), "advisor.py")],
                            capture_output=True, text=True, timeout=180,
                            cwd=os.path.dirname(os.path.realpath(__file__)),
                            env=env,
                        )
                        output = result.stdout + result.stderr
                        report_path = os.path.join(OUTPUT_DIR, "advisor_report.txt")
                        if os.path.exists(report_path):
                            with open(report_path) as f:
                                report = f.read()
                            plan_output.set_content(_format_advisor_report(report))
                        else:
                            plan_output.set_content(
                                f'<pre style="color:{RED}">{output}</pre>')
                    except subprocess.TimeoutExpired:
                        plan_output.set_content(
                            f'<span style="color:{RED}">Timed out after 180s. Is Ollama running?</span>')
                    except Exception as e:
                        plan_output.set_content(
                            f'<span style="color:{RED}">Error: {e}</span>')
                    spinner.set_visibility(False)
                    btn.enable()

                _t.Thread(target=_run, daemon=True).start()

            with ui.row().classes("items-center gap-3 mb-4"):
                btn = ui.button("Generate Plan", on_click=generate_plan).style(
                    f"background:{MAUVE}; color:{DARK_BG}; font-weight:600")
                spinner = ui.spinner("dots", size="sm", color=MAUVE)
                spinner.set_visibility(False)

            plan_output  # render it

        # ════════════════════════════════════════════════
        # SECTION 4: PREDICTIONS
        # ════════════════════════════════════════════════
        with ui.element("div").props('id="section-predictions"').classes("page-section"):
            ui.label("Completion Forecasts").classes("section-title mb-2")
            ui.label(
                "Estimated completion for in-progress efforts, adjusted for "
                "temporal shifts in the codebase."
            ).style(f"color:{SUBTEXT}; font-size:14px; margin-bottom:20px")

            from code_insight import load_insights
            insight_data = load_insights()
            in_progress = [e for e in epic_data if e["status"] == "in_progress"]
            velocity_adj = _compute_velocity_adjustments(records, in_progress, insight_data)

            if not in_progress:
                ui.label("No in-progress efforts.").style(f"color:{SUBTEXT}")
            for epic in in_progress:
                _render_timing_card(epic, velocity_adj.get(epic["key"]))

        # ════════════════════════════════════════════════
        # SECTION 5: SLACK INSIGHTS
        # ════════════════════════════════════════════════
        with ui.element("div").props('id="section-slack"').classes("page-section"):
            _render_slack_section(slack_data, records, data["tickets"])

        # ════════════════════════════════════════════════
        # SECTION 6: CODE INSIGHTS
        # ════════════════════════════════════════════════
        with ui.element("div").props('id="section-insights"').classes("page-section"):
            _render_code_insights_section(records)


# ─── Incident Detector ───────────────────────────────────────────────────

# ─── Fix Prompt Formatter ────────────────────────────────────────────────

def _format_fix_prompts(raw_text: str) -> str:
    """Parse LLM output into styled fix-prompt cards with copy buttons."""
    import html as _html
    import re

    severity_colors = {
        "critical": RED,
        "high": PEACH,
        "medium": BLUE,
    }

    # Strip common markdown decoration the local model sometimes adds around
    # labels, e.g. "**PROMPT:**", "### Prompt:", "1. DIAGNOSIS:", "- Severity:".
    def _label(line):
        s = line.strip()
        s = re.sub(r'^[\s>#*`_\-]+', '', s)          # leading markdown / bullets
        s = re.sub(r'^\d+[.)]\s*', '', s)            # leading list numbers
        s = s.replace("*", "").replace("`", "")      # inline emphasis
        m = re.match(r'(?i)(DIAGNOSIS|SEVERITY|PROMPT)\s*:\s*(.*)', s)
        if m:
            return m.group(1).upper(), m.group(2).strip()
        return None, None

    blocks = re.split(r'\n[ \t]*[-=*]{3,}[ \t]*\n', raw_text.strip())
    if len(blocks) <= 1:
        blocks = re.split(r'(?im)(?=^[\s>#*`\-]*\d*[.)]?\s*DIAGNOSIS\s*:)',
                          raw_text.strip())
    cards_html = []
    prompt_idx = 0

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        diagnosis = ""
        severity = ""
        prompt_lines = []
        in_prompt = False

        for line in block.split("\n"):
            label, value = _label(line)

            if label == "DIAGNOSIS":
                diagnosis = value
                in_prompt = False
            elif label == "SEVERITY":
                severity = value.lower()
                in_prompt = False
            elif label == "PROMPT":
                if value:
                    prompt_lines.append(value)
                in_prompt = True
            elif in_prompt:
                if re.match(r'^[ \t]*[-=*]{3,}[ \t]*$', line):
                    break
                prompt_lines.append(line.rstrip())

        prompt_text = "\n".join(prompt_lines).strip()
        if not prompt_text:
            continue

        prompt_idx += 1
        sev_color = severity_colors.get(severity, SUBTEXT)
        sev_label = severity.title() if severity else "Info"
        safe_diag = _html.escape(diagnosis) if diagnosis else "Fix Prompt"
        safe_prompt = _html.escape(prompt_text)
        copy_id = f"fix-prompt-{prompt_idx}"

        cards_html.append(f'''
<div style="background:{SURFACE}; border:1px solid {BORDER}; border-left:3px solid {sev_color};
            border-radius:8px; padding:16px; margin-bottom:16px">
  <div style="display:flex; align-items:flex-start; gap:12px; margin-bottom:12px">
    <span style="flex:0 0 auto; width:26px; height:26px; border-radius:50%;
                 background:{sev_color}; color:{DARK_BG}; font-size:13px; font-weight:700;
                 display:flex; align-items:center; justify-content:center">{prompt_idx}</span>
    <div style="flex:1 1 auto">
      <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px">
        <span style="font-size:12px; font-weight:700; color:{DARK_BG}; background:{sev_color};
                     padding:2px 8px; border-radius:4px; text-transform:uppercase;
                     letter-spacing:0.5px">{sev_label}</span>
      </div>
      <div style="font-size:15px; color:{TEXT}; font-weight:600; line-height:1.4">{safe_diag}</div>
    </div>
  </div>
  <div id="{copy_id}" style="background:{DARK_BG}; border:1px solid {BORDER}; border-radius:6px;
              padding:12px 14px; margin-top:8px; position:relative; cursor:pointer"
       onclick="
         var el = document.getElementById('{copy_id}');
         var text = el.querySelector('pre').innerText;
         navigator.clipboard.writeText(text).then(function() {{
           var badge = el.querySelector('.copy-badge');
           badge.innerText = 'Copied!';
           badge.style.background = '{GREEN}';
           setTimeout(function() {{
             badge.innerText = 'Click to copy';
             badge.style.background = '{SURFACE2}';
           }}, 1500);
         }});
       ">
    <span class="copy-badge" style="position:absolute; top:8px; right:10px; font-size:12px;
                color:{SUBTEXT}; background:{SURFACE2}; padding:2px 8px;
                border-radius:3px; pointer-events:none">Click to copy</span>
    <pre style="color:{GREEN}; white-space:pre-wrap; font-size:12px; line-height:1.6;
                font-family:'SF Mono',Menlo,monospace; margin:0">{safe_prompt}</pre>
  </div>
</div>''')

    if not cards_html:
        safe_raw = _html.escape(raw_text)
        return (f'<pre style="color:{TEXT}; white-space:pre-wrap; font-size:12px; '
                f'line-height:1.6; font-family:-apple-system,system-ui,sans-serif">'
                f'{safe_raw}</pre>')

    return "\n".join(cards_html)


# ─── Code Insights Section Renderer ──────────────────────────────────────

def _render_code_insights_section(records: list[dict]):
    """Render the coding insights tab with failure pattern analysis."""
    if not records:
        ui.label("No Task Data").classes("section-title mb-2")
        with ui.card().classes("w-full p-4"):
            ui.label("No task data available for analysis.").style(f"color:{SUBTEXT}")
        return

    insight_data = load_insights()
    if not insight_data or not insight_data.get("keyword_hotspots"):
        insight_data = build_insight_data(records)
        save_insights(insight_data)

    summary = insight_data.get("summary", {})
    hotspots = insight_data.get("keyword_hotspots", [])
    toxic_pairs = insight_data.get("toxic_pairs", [])
    project_risk = insight_data.get("project_risk", [])
    drift = insight_data.get("temporal_drift", [])
    convergence = insight_data.get("convergence", [])

    # ── Summary Cards ──
    ui.label("Codebase Health Analysis").classes("section-title mb-2")
    ui.label(
        f"Pattern analysis across {summary.get('total_records', 0):,} tasks — "
        f"identifies which parts of the codebase keep causing problems."
    ).style(f"color:{SUBTEXT}; font-size:13px; margin-bottom:16px")

    with ui.element("div").style(
            "display:flex; flex-direction:row; gap:16px; width:100%; margin-bottom:24px; flex-wrap:wrap"):
        _metric_card("Risk Keywords", str(summary.get("high_risk_keywords", 0)), RED)
        _metric_card("Toxic Pairs", str(summary.get("toxic_pair_count", 0)), PEACH)
        _metric_card("Codebase Issues", str(summary.get("codebase_problems", 0)), RED)
        _metric_card("Worsening", str(summary.get("worsening_areas", 0)),
                     RED if summary.get("worsening_areas", 0) > 0 else MAUVE)

    # ── Keyword Failure Hotspots ──
    ui.label("Keyword Failure Hotspots").classes("section-title mb-2")
    ui.label(
        "Technical concepts with the highest error rates across tasks. "
        "High risk score = consistent failures."
    ).style(f"color:{SUBTEXT}; font-size:12px; margin-bottom:12px")

    with ui.element("div").style("overflow-x:auto; margin-bottom:20px"):
        header = ("Keyword", "Risk", "Avg Errors", "vs Avg", "Retries", "Occurrences", "Employees")
        rows = []
        for h in hotspots[:15]:
            risk_color = RED if h["risk_score"] > 1.5 else (PEACH if h["risk_score"] > 1.0 else SUBTEXT)
            rows.append((
                h["keyword"],
                f'<span style="color:{risk_color}; font-weight:700">{h["risk_score"]:.2f}</span>',
                f'{h["avg_errors"]:.1f}',
                f'{h["error_ratio"]:.1f}x',
                f'{h["avg_retries"]:.1f}',
                str(h["occurrences"]),
                str(h["employee_count"]),
            ))

        table_html = f'<table style="width:100%; border-collapse:collapse; font-size:12px">'
        table_html += '<thead><tr>'
        for col in header:
            table_html += (f'<th style="text-align:left; padding:8px 10px; '
                          f'border-bottom:1px solid {BORDER}; color:{MAUVE}; font-weight:600">{col}</th>')
        table_html += '</tr></thead><tbody>'
        for row in rows:
            table_html += '<tr>'
            for i, cell in enumerate(row):
                style = f"padding:6px 10px; border-bottom:1px solid {BORDER}; color:{TEXT}"
                if i == 0:
                    style += "; font-weight:600; font-family:monospace; font-size:13px"
                table_html += f'<td style="{style}">{cell}</td>'
            table_html += '</tr>'
        table_html += '</tbody></table>'
        ui.html(sanitize=False, content=table_html)

    # ── Toxic Pairs ──
    if toxic_pairs:
        ui.label("Toxic Keyword Combinations").classes("section-title mb-2")
        ui.label(
            "Keyword pairs that produce extra errors when they appear together — "
            "signals coupling or complexity hotspots."
        ).style(f"color:{SUBTEXT}; font-size:12px; margin-bottom:12px")

        with ui.element("div").style("display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px"):
            for p in toxic_pairs[:10]:
                pair_color = RED if p["error_ratio"] > 2.0 else PEACH
                with ui.card().classes("p-3").style(f"min-width:220px; flex:1; max-width:320px"):
                    with ui.row().classes("items-center gap-2 mb-1"):
                        ui.label(p["keywords"][0]).style(
                            f"font-family:monospace; font-size:13px; color:{TEXT}; "
                            f"background:{SURFACE2}; padding:2px 6px; border-radius:3px")
                        ui.label("+").style(f"color:{SUBTEXT}; font-size:13px")
                        ui.label(p["keywords"][1]).style(
                            f"font-family:monospace; font-size:13px; color:{TEXT}; "
                            f"background:{SURFACE2}; padding:2px 6px; border-radius:3px")
                    with ui.element("div").style("display:flex; gap:12px"):
                        _slack_mini_stat("errors", f"{p['avg_errors']:.1f}", pair_color)
                        _slack_mini_stat("vs avg", f"{p['error_ratio']:.1f}x", pair_color)
                        _slack_mini_stat("tasks", str(p["co_occurrences"]), SUBTEXT)

    # ── Cross-Employee Convergence ──
    codebase_issues = [c for c in convergence if c["convergence_ratio"] >= 0.5]
    if codebase_issues:
        ui.label("Cross-Employee Convergence").classes("section-title mb-2")
        ui.label(
            "Areas where most employees independently struggle — "
            "indicates a codebase problem, not individual skill gaps."
        ).style(f"color:{SUBTEXT}; font-size:12px; margin-bottom:12px")

        for c in codebase_issues[:10]:
            is_confirmed = c["verdict"] == "codebase_problem"
            bar_color = RED if is_confirmed else PEACH
            pct = c["convergence_ratio"] * 100

            with ui.element("div").style("margin-bottom:10px"):
                with ui.row().classes("items-center justify-between w-full"):
                    with ui.row().classes("items-center gap-3"):
                        ui.label(c["keyword"]).style(
                            f"font-family:monospace; font-size:12px; font-weight:600; "
                            f"color:{TEXT}; min-width:160px")
                        if is_confirmed:
                            ui.html(sanitize=False, content=
                                f'<span style="background:{RED}20; color:{RED}; '
                                f'padding:1px 8px; border-radius:10px; font-size:12px; '
                                f'font-weight:600">CODEBASE PROBLEM</span>')
                        else:
                            ui.html(sanitize=False, content=
                                f'<span style="background:{PEACH}20; color:{PEACH}; '
                                f'padding:1px 8px; border-radius:10px; font-size:12px; '
                                f'font-weight:600">LIKELY CODEBASE</span>')
                    ui.label(
                        f"{c['struggling_employees']}/{c['total_employees']} employees  "
                        f"({pct:.0f}%)"
                    ).style(f"color:{bar_color}; font-size:12px; font-weight:600")
                with ui.element("div").style(
                        f"height:6px; background:{SURFACE2}; border-radius:3px; margin-top:4px"):
                    ui.element("div").style(
                        f"height:100%; width:{pct:.0f}%; background:{bar_color}; border-radius:3px")

    # ── Temporal Drift ──
    worsening = [d for d in drift if d["direction"] == "worsening"]
    improving = [d for d in drift if d["direction"] == "improving"]

    if worsening or improving:
        ui.separator().style(f"background:{BORDER}; margin:20px 0")
        ui.label("Temporal Trends").classes("section-title mb-2")
        ui.label(
            "Keywords whose error rates are changing over time."
        ).style(f"color:{SUBTEXT}; font-size:12px; margin-bottom:12px")

        with ui.element("div").style("display:flex; gap:24px; flex-wrap:wrap; margin-bottom:20px"):
            if worsening:
                with ui.element("div").style("flex:1; min-width:280px"):
                    ui.label("Worsening").style(
                        f"color:{RED}; font-size:13px; font-weight:600; margin-bottom:8px")
                    for d in worsening[:8]:
                        with ui.element("div").style("margin-bottom:6px"):
                            with ui.row().classes("items-center justify-between w-full"):
                                ui.label(d["keyword"]).style(
                                    f"font-family:monospace; font-size:13px; color:{TEXT}")
                                ui.label(f"+{d['drift_pct']:.0f}%").style(
                                    f"color:{RED}; font-size:12px; font-weight:700")
                            ui.label(
                                f"{d['early_avg_errors']:.1f} → {d['late_avg_errors']:.1f} errors/task"
                            ).style(f"color:{SUBTEXT}; font-size:12px")

            if improving:
                with ui.element("div").style("flex:1; min-width:280px"):
                    ui.label("Improving").style(
                        f"color:{MAUVE}; font-size:13px; font-weight:600; margin-bottom:8px")
                    for d in improving[:8]:
                        with ui.element("div").style("margin-bottom:6px"):
                            with ui.row().classes("items-center justify-between w-full"):
                                ui.label(d["keyword"]).style(
                                    f"font-family:monospace; font-size:13px; color:{TEXT}")
                                ui.label(f"{d['drift_pct']:.0f}%").style(
                                    f"color:{MAUVE}; font-size:12px; font-weight:700")
                            ui.label(
                                f"{d['early_avg_errors']:.1f} → {d['late_avg_errors']:.1f} errors/task"
                            ).style(f"color:{SUBTEXT}; font-size:12px")

    # ── Project Risk ──
    ui.separator().style(f"background:{BORDER}; margin:20px 0")
    ui.label("Project Risk Profiles").classes("section-title mb-2")

    for p in project_risk[:6]:
        risk_color = RED if p["error_ratio"] > 1.3 else (PEACH if p["error_ratio"] > 1.0 else MAUVE)
        with ui.card().classes("w-full mb-3 p-4"):
            with ui.row().classes("items-center justify-between w-full mb-2"):
                ui.label(p["project"]).style(f"font-weight:600; color:{TEXT}; font-size:14px")
                ui.label(f"{p['error_ratio']:.1f}x avg errors").style(
                    f"color:{risk_color}; font-size:12px; font-weight:600")
            with ui.row().classes("gap-6 mb-2"):
                _slack_mini_stat("tasks", str(p["tasks"]), SUBTEXT)
                _slack_mini_stat("avg errors", f"{p['avg_errors']:.1f}", risk_color)
                _slack_mini_stat("total errors", str(p["total_errors"]), RED)
                _slack_mini_stat("employees", str(p["employees"]), SUBTEXT)
            if p.get("top_error_keywords"):
                with ui.row().classes("gap-2 flex-wrap"):
                    for kw_info in p["top_error_keywords"]:
                        ui.label(
                            f"{kw_info['keyword']} ({kw_info['high_error_tasks']})"
                        ).style(
                            f"font-family:monospace; font-size:12px; color:{RED}; "
                            f"background:{RED}15; padding:2px 6px; border-radius:3px")

    # ── LLM Analysis Button ──
    ui.separator().style(f"background:{BORDER}; margin:20px 0")
    ui.label("AI Fix Prompts").classes("section-title mb-2")
    ui.label(
        "Generates copy-paste prompts you can feed to an AI coding assistant "
        "(Claude, Cursor, Copilot) to fix the specific issues discovered above."
    ).style(f"color:{SUBTEXT}; font-size:12px; margin-bottom:12px")

    llm_output = ui.html(sanitize=False, content="").classes("advisor-output").style("display:none")

    existing_analysis = insight_data.get("llm_analysis", "")
    if existing_analysis:
        llm_output.style("display:block")
        llm_output.set_content(_format_fix_prompts(existing_analysis))

    def run_analysis():
        import threading as _t

        btn.disable()
        spinner.set_visibility(True)
        llm_output.style("display:block")
        llm_output.set_content(
            f'<span style="color:{SUBTEXT}">Generating fix prompts... '
            f'this may take 30-90 seconds.</span>')

        def _run():
            import subprocess as _sp
            try:
                result = _sp.run(
                    [sys.executable, "-c",
                     "import sys, os; sys.path.insert(0, os.path.dirname(os.path.realpath('code_insight.py'))); "
                     "import code_insight; "
                     "from code_insight import build_insight_data, generate_root_cause_analysis, save_insights; "
                     "import json; "
                     "tf=os.path.join(code_insight.DATA_DIR,'task_data.jsonl'); "
                     "records=[json.loads(l) for l in open(tf) if l.strip()]; "
                     "data=build_insight_data(records); "
                     "analysis=generate_root_cause_analysis(data); "
                     "data['llm_analysis']=analysis; "
                     "save_insights(data); "
                     "print(analysis)"],
                    capture_output=True, text=True, timeout=300,
                    cwd=os.path.dirname(os.path.realpath(__file__)),
                )
                output = result.stdout.strip()
                if output and not output.startswith("[Ollama error"):
                    llm_output.set_content(_format_fix_prompts(output))
                else:
                    err = result.stderr or output or "No output"
                    llm_output.set_content(
                        f'<span style="color:{RED}">Analysis failed: {err}</span>')
            except _sp.TimeoutExpired:
                llm_output.set_content(
                    f'<span style="color:{RED}">Timed out after 300s. Is Ollama running?</span>')
            except Exception as e:
                llm_output.set_content(
                    f'<span style="color:{RED}">Error: {e}</span>')
            spinner.set_visibility(False)
            btn.enable()

        _t.Thread(target=_run, daemon=True).start()

    with ui.row().classes("items-center gap-3 mb-4"):
        label = "Regenerate Prompts" if existing_analysis else "Generate Fix Prompts"
        btn = ui.button(label, on_click=run_analysis).style(
            f"background:{MAUVE}; color:{DARK_BG}; font-weight:600")
        spinner = ui.spinner("dots", size="sm", color=MAUVE)
        spinner.set_visibility(False)

    llm_output


# ─── Slack Section Renderer ───────────────────────────────────────────────

def _render_slack_section(slack_data: dict, records: list[dict], tickets: dict | None = None):
    """Render the full Slack insights tab."""
    tickets = tickets or {}
    if not slack_data or not slack_data.get("employee_signals"):
        ui.label("No Slack Data").classes("section-title mb-2")
        with ui.card().classes("w-full p-4"):
            ui.label("Slack signals not yet ingested.").style(f"color:{SUBTEXT}")
            ui.label("Run: python3 slack_connector.py --token xoxb-... --scan-all").style(
                f"color:{SUBTEXT}; font-family:monospace; font-size:12px; margin-top:8px")
            ui.label("Or generate demo data: python3 generate_fake_data.py").style(
                f"color:{SUBTEXT}; font-family:monospace; font-size:12px")
        return

    emp_signals = slack_data["employee_signals"]
    ch_signals = slack_data.get("channel_signals", [])
    workflow = slack_data.get("workflow_patterns", {})
    meta = slack_data.get("metadata", {})

    # ── Workflow Patterns ──
    ui.label("Workspace Patterns").classes("section-title mb-2")
    with ui.element("div").style(
            f"display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px"):
        _slack_pattern_chip("Task Flow", workflow.get("task_acquisition", "unknown"))
        _slack_pattern_chip("Completion", workflow.get("completion_tracking", "unknown"))
        _slack_pattern_chip("Reviews", workflow.get("review_culture", "unknown"))
        _slack_pattern_chip("Help-Seeking", workflow.get("help_seeking", "unknown"))
        _slack_pattern_chip("Workload", workflow.get("workload_distribution", "unknown"))

    observations = workflow.get("observations", [])
    if observations:
        with ui.card().classes("w-full p-3 mb-4"):
            for obs in observations:
                ui.label(f"→ {obs}").style(f"color:{TEXT}; font-size:12px; margin-bottom:4px")

    # ── Demand / Throughput / Collaboration Leaderboard ──
    ui.label("Employee Signals").classes("section-title mb-2")

    sorted_by_demand = sorted(emp_signals.items(), key=lambda x: -x[1]["demand_score"])
    sorted_by_throughput = sorted(emp_signals.items(), key=lambda x: -x[1]["throughput_score"])
    sorted_by_collab = sorted(emp_signals.items(), key=lambda x: -x[1]["collaboration_score"])

    with ui.element("div").style("display:flex; gap:16px; flex-wrap:wrap; margin-bottom:20px"):
        # Demand (who's overloaded)
        with ui.element("div").style(f"flex:1; min-width:280px"):
            ui.label("Highest Demand (overloaded)").style(
                f"color:{RED}; font-size:13px; font-weight:600; margin-bottom:8px")
            for name, sig in sorted_by_demand[:5]:
                _slack_employee_bar(name, sig["demand_score"],
                                    max(s["demand_score"] for _, s in sorted_by_demand[:5]),
                                    RED, f"{sig['mentions_received']} mentions, "
                                         f"{sig['blockers_raised']} blockers")

        # Throughput (who's shipping)
        with ui.element("div").style(f"flex:1; min-width:280px"):
            ui.label("Highest Throughput (shipping)").style(
                f"color:{MAUVE}; font-size:13px; font-weight:600; margin-bottom:8px")
            for name, sig in sorted_by_throughput[:5]:
                _slack_employee_bar(name, sig["throughput_score"],
                                    max(s["throughput_score"] for _, s in sorted_by_throughput[:5]),
                                    MAUVE, f"{sig['tasks_completed_announced']} done, "
                                           f"{sig['pr_reference_count']} PRs")

        # Collaboration (who's helping)
        with ui.element("div").style(f"flex:1; min-width:280px"):
            ui.label("Most Collaborative").style(
                f"color:{PEACH}; font-size:13px; font-weight:600; margin-bottom:8px")
            for name, sig in sorted_by_collab[:5]:
                _slack_employee_bar(name, sig["collaboration_score"],
                                    max(s["collaboration_score"] for _, s in sorted_by_collab[:5]),
                                    PEACH, f"{sig['thread_replies']} replies, "
                                           f"{sig['code_blocks_shared']} code shares")

    # ── Full Employee Table ──
    ui.label("All Employee Slack Metrics").classes("section-title mb-2")
    with ui.element("div").style("overflow-x:auto; margin-bottom:20px"):
        header = ("Employee", "Msgs", "Threads", "Tasks Done", "Blockers",
                  "Reviews", "PRs", "Demand", "Throughput", "Collab")
        rows = []
        for name, sig in sorted(emp_signals.items()):
            rows.append((
                name,
                str(sig["message_count"]),
                str(sig["thread_starts"] + sig["thread_replies"]),
                str(sig["tasks_completed_announced"]),
                str(sig["blockers_raised"]),
                str(sig["reviews_requested"]),
                str(sig["pr_reference_count"]),
                f'{sig["demand_score"]:.2f}',
                f'{sig["throughput_score"]:.2f}',
                f'{sig["collaboration_score"]:.2f}',
            ))

        table_html = f'<table style="width:100%; border-collapse:collapse; font-size:12px">'
        table_html += '<thead><tr>'
        for h in header:
            table_html += f'<th style="text-align:left; padding:8px 10px; border-bottom:1px solid {BORDER}; color:{MAUVE}; font-weight:600">{h}</th>'
        table_html += '</tr></thead><tbody>'
        for row in rows:
            table_html += '<tr>'
            for i, cell in enumerate(row):
                style = f"padding:6px 10px; border-bottom:1px solid {BORDER}; color:{TEXT}"
                if i == 0:
                    style += "; font-weight:600"
                table_html += f'<td style="{style}">{cell}</td>'
            table_html += '</tr>'
        table_html += '</tbody></table>'
        ui.html(sanitize=False, content=table_html)

    # ── Channel Activity ──
    ui.label("Channel Activity").classes("section-title mb-2")
    with ui.element("div").style("display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px"):
        for ch in sorted(ch_signals, key=lambda c: -c["total_messages"]):
            ch_color = MAUVE if ch["channel_type"] in ("engineering", "project") else (
                PEACH if ch["channel_type"] in ("review", "deploy") else (
                    RED if ch["channel_type"] == "incident" else SUBTEXT))
            with ui.card().classes("p-3").style(f"min-width:200px; flex:1; max-width:300px"):
                with ui.row().classes("items-center justify-between w-full mb-1"):
                    ui.label(f"#{ch['channel_name']}").style(
                        f"font-weight:600; color:{TEXT}; font-size:13px")
                    ui.label(ch["channel_type"]).style(
                        f"font-size:12px; color:{ch_color}; background:{SURFACE2}; "
                        f"padding:2px 6px; border-radius:4px")
                with ui.element("div").style("display:flex; gap:12px; flex-wrap:wrap"):
                    _slack_mini_stat("msgs/day", f"{ch['messages_per_day']:.0f}", TEXT)
                    _slack_mini_stat("tasks", str(ch["task_requests"]), MAUVE)
                    _slack_mini_stat("done", str(ch["completions"]), MAUVE)
                    _slack_mini_stat("blockers", str(ch["blockers"]), RED)
                    _slack_mini_stat("threads", f"{ch['thread_ratio']:.1f}x", PEACH)

    # ── Slack ↔ Ticket Cross-Reference ──
    if tickets:
        all_slack_refs = set()
        for sig in emp_signals.values():
            all_slack_refs.update(sig.get("jira_tickets_referenced", []))

        matched = {ref: tickets[ref] for ref in all_slack_refs if ref in tickets}
        if matched:
            ui.label("Ticket Cross-Reference").classes("section-title mb-2")
            ui.label(
                f"{len(matched)} of {len(all_slack_refs)} Slack-referenced tickets "
                f"matched to PM provider data"
            ).style(f"color:{SUBTEXT}; font-size:12px; margin-bottom:8px")

            status_counts: dict[str, int] = {}
            for t in matched.values():
                raw = t.get("status", "unknown").lower().replace(" ", "_")
                status_counts[raw] = status_counts.get(raw, 0) + 1

            with ui.element("div").style(
                    "display:flex; gap:10px; flex-wrap:wrap; margin-bottom:20px"):
                status_colors = {
                    "done": MAUVE, "in_progress": PEACH, "in_review": PEACH,
                    "to_do": SUBTEXT, "blocked": RED,
                }
                for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
                    sc = status_colors.get(status, SUBTEXT)
                    with ui.element("div").style(
                            f"background:{sc}15; border:1px solid {sc}40; "
                            f"border-radius:6px; padding:6px 12px; text-align:center"):
                        ui.label(str(count)).style(
                            f"font-size:16px; font-weight:700; color:{sc}")
                        ui.label(status.replace("_", " ").title()).style(
                            f"font-size:12px; color:{SUBTEXT}")

    # ── Metadata ──
    if meta:
        with ui.element("div").style(f"color:{SUBTEXT}; font-size:13px; margin-top:12px"):
            parts = []
            if meta.get("days_scanned"):
                parts.append(f"Last {meta['days_scanned']} days")
            if meta.get("channels_scanned"):
                parts.append(f"{meta['channels_scanned']} channels")
            if meta.get("total_messages_analyzed"):
                parts.append(f"{meta['total_messages_analyzed']} messages")
            if meta.get("simulated"):
                parts.append("simulated data")
            ui.label(" · ".join(parts))


def _slack_pattern_chip(label: str, value: str):
    color = MAUVE if value in ("ticket-driven", "pr-driven", "active-inline",
                               "dedicated-channel", "balanced") else (
            PEACH if value in ("mixed", "request-driven", "announcement-driven",
                              "distributed", "somewhat-uneven") else RED)
    with ui.element("div").style(
            f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px; "
            f"padding:8px 14px"):
        ui.label(label).style(f"color:{SUBTEXT}; font-size:12px; text-transform:uppercase")
        ui.label(value).style(f"color:{color}; font-size:13px; font-weight:600")


def _slack_employee_bar(name: str, score: float, max_score: float, color: str, detail: str):
    pct = (score / max(max_score, 0.01)) * 100
    with ui.element("div").style("margin-bottom:6px"):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label(name).style(f"color:{TEXT}; font-size:12px; font-weight:600; min-width:120px")
            ui.label(f"{score:.2f}").style(f"color:{color}; font-size:13px; font-weight:600")
        with ui.element("div").style(
                f"height:6px; background:{SURFACE2}; border-radius:3px; margin-top:2px"):
            ui.element("div").style(
                f"height:100%; width:{pct:.0f}%; background:{color}; border-radius:3px")
        ui.label(detail).style(f"color:{SUBTEXT}; font-size:12px")


def _slack_mini_stat(label: str, value: str, color: str):
    with ui.element("div"):
        ui.label(value).style(f"color:{color}; font-size:13px; font-weight:600")
        ui.label(label).style(f"color:{SUBTEXT}; font-size:12px")


# ─── Component Helpers ────────────────────────────────────────────────────

def _metric_card(label: str, value: str, color: str):
    with ui.element("div").style(
            f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px; "
            f"padding:16px 20px; flex:1; min-width:140px"):
        ui.label(value).classes("stat-value").style(f"color:{color}")
        ui.label(label).classes("stat-label")


def _mini_stat(label: str, value: str, color: str):
    with ui.column():
        ui.label(value).style(f"color:{color}; font-size:16px; font-weight:700")
        ui.label(label).style(f"color:{SUBTEXT}; font-size:13px")


def _render_ranking_row(rank: int, rk: dict):
    """One grid cell in the 3-column team ranking."""
    import html as _html
    name = _html.escape(rk["employee"])
    pct = rk["vs_team_pct"]
    pct_color = GREEN if pct >= 0 else RED
    pct_text = f"+{pct:.0f}%" if pct >= 0 else f"{pct:.0f}%"

    load_labels = {"light": ("Available", GREEN),
                   "normal": ("Balanced", SUBTEXT),
                   "heavy": ("Loaded", RED)}
    load_text, load_color = load_labels[rk["load"]]

    # Strength chips get a thin green outline; the worst niche gets red.
    chips = [
        f'<span style="background:{SURFACE2}; color:{TEXT}; padding:4px 10px; '
        f'border:1px solid {GREEN}; font-size:13px; font-weight:600; '
        f'white-space:nowrap">{_html.escape(t)}</span>'
        for t, _ in rk["strengths"][:2]
    ]
    if rk["weaknesses"]:
        worst = rk["weaknesses"][0][0]
        chips.append(
            f'<span style="background:{SURFACE2}; color:{TEXT}; padding:4px 10px; '
            f'border:1px solid {RED}; font-size:13px; font-weight:600; '
            f'white-space:nowrap">{_html.escape(worst)}</span>')
    chips_html = "".join(chips) or \
        f'<span style="color:{SUBTEXT}; font-size:13px">No standout topics yet</span>'

    eyebrow = (f'color:{SUBTEXT}; font-size:12px; font-weight:600; '
               f'text-transform:uppercase; letter-spacing:0.08em')

    ui.html(sanitize=False, content=f'''
<div style="display:flex; flex-direction:column; padding:16px 18px;
            border:1px solid {BORDER}; background:{SURFACE}; min-width:0">
  <div style="display:flex; align-items:baseline; gap:10px; min-width:0">
    <span style="font-size:22px; font-weight:800;
                 color:{BLUE if rank <= 3 else SUBTEXT}">{rank}</span>
    <span style="font-size:17px; font-weight:700; color:{TEXT}; overflow:hidden;
                 text-overflow:ellipsis; white-space:nowrap">{name}</span>
  </div>
  <div style="margin-top:10px">
    <div style="{eyebrow}">General Efficiency vs Team</div>
    <div style="font-size:20px; font-weight:700; color:{pct_color}; margin-top:2px">{pct_text}</div>
  </div>
  <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:12px">{chips_html}</div>
  <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:auto;
              padding-top:12px; margin-top:14px; border-top:1px solid {BORDER}">
    <div>
      <div style="{eyebrow}">Tickets</div>
      <div style="font-size:16px; font-weight:700; color:{TEXT}; margin-top:2px">{rk["tickets"]}</div>
    </div>
    <div>
      <div style="{eyebrow}">Availability</div>
      <div style="font-size:16px; font-weight:700; color:{load_color}; margin-top:2px">{load_text}</div>
    </div>
  </div>
</div>''')


def _render_epic_card(epic: dict, blind_spots: list[dict] | None = None,
                      records: list[dict] | None = None):
    status = epic["status"]
    status_colors = {"done": MAUVE, "in_progress": PEACH, "planning": PEACH}
    s_color = status_colors.get(status, SUBTEXT)
    pct = epic.get("pct_done", 0)
    show_team_btn = status == "planning" or pct == 0

    with ui.card().classes("w-full mb-4 p-5"):
        with ui.row().classes("items-center justify-between w-full mb-3"):
            with ui.row().classes("items-center gap-3"):
                ui.label(epic["key"]).style(
                    f"color:{SUBTEXT}; font-size:12px; font-family:monospace")
                ui.label(epic["name"]).style(
                    f"color:{TEXT}; font-size:15px; font-weight:600")
            ui.html(sanitize=False, content=
                f'<span class="status-chip status-{status}">'
                f'{status.replace("_", " ").title()}</span>')

        with ui.column().classes("w-full mb-3"):
            with ui.row().classes("justify-between w-full mb-1"):
                ui.label(f"{epic['done_count']}/{epic['ticket_count']} tickets").style(
                    f"font-size:12px; color:{SUBTEXT}")
                ui.label(f"{pct:.0f}%").style(
                    f"font-size:12px; color:{s_color}; font-weight:600")
            ui.html(sanitize=False, content=
                f'<div style="width:100%; height:6px; background:{SURFACE2}; border-radius:3px">'
                f'<div style="width:{pct}%; height:100%; background:{s_color}; border-radius:3px"></div>'
                f'</div>')

        with ui.row().classes("gap-6 mt-2 flex-wrap"):
            _mini_stat("Est. Total", f"{epic['est_duration_exp_hrs']}h", MAUVE)
            _mini_stat("Remaining", f"{epic['est_remaining_exp_hrs']}h", PEACH)
            _mini_stat("Est. Tokens", f"{epic['est_norm_tokens']:,} NT", SUBTEXT)
            _mini_stat("Est. Cost", f"${epic['est_cost']:.2f}", MAUVE)
            _mini_stat("Est. Errors", f"{epic['est_errors']:.0f}", RED)
            _mini_stat("Target", epic.get("target_date", "—"), SUBTEXT)

        with ui.row().classes("gap-2 mt-3 flex-wrap"):
            spots_set = {bs["topic"] for bs in (blind_spots or [])}
            for topic in epic.get("topics", []):
                is_spot = topic in spots_set
                bg = f"{RED}20" if is_spot else f"{SURFACE2}"
                tc = RED if is_spot else SUBTEXT
                suffix = " ⚠" if is_spot else ""
                ui.label(f"{topic}{suffix}").style(
                    f"background:{bg}; color:{tc}; padding:2px 8px; "
                    f"border-radius:4px; font-size:13px")

        if show_team_btn and records:
            team_output = ui.column().classes("w-full")

            def _gen_team(e=epic, container=team_output):
                container.clear()
                ranked = compute_ideal_team(records, e.get("topics", []))
                top4 = ranked[:4]
                rest = ranked[4:]
                growth_pick = min(rest, key=lambda r: r["score"]) if rest else None

                with container:
                    ui.separator().style(f"background:{BORDER}; margin:12px 0")
                    ui.label("Recommended Team").style(
                        f"color:{MAUVE}; font-size:13px; font-weight:700; margin-bottom:8px")
                    ui.label(
                        "Ranked by topic expertise, error rate, speed, model quality, and current workload."
                    ).style(f"color:{SUBTEXT}; font-size:13px; margin-bottom:10px")

                    show_list = [(r, "rec") for r in top4]
                    if growth_pick:
                        show_list.append((growth_pick, "growth"))

                    for idx, (r, role) in enumerate(show_list):
                        is_rec = role == "rec"
                        is_growth = role == "growth"
                        border_c = MAUVE if is_rec else (PEACH if is_growth else BORDER)
                        if is_rec:
                            badge = (f'<span style="background:{MAUVE}20; color:{MAUVE}; '
                                     f'padding:1px 8px; border-radius:10px; font-size:12px; '
                                     f'font-weight:700">RECOMMENDED</span>')
                        elif is_growth:
                            badge = (f'<span style="background:{PEACH}20; color:{PEACH}; '
                                     f'padding:1px 8px; border-radius:10px; font-size:12px; '
                                     f'font-weight:700">GROWTH OPPORTUNITY</span>')
                        else:
                            badge = ""

                        topic_chips = ""
                        for ts in r["topic_scores"]:
                            sc = ts["score"]
                            c = MAUVE if sc >= 7 else (PEACH if sc >= 4 else RED)
                            topic_chips += (
                                f'<span style="background:{c}15; color:{c}; '
                                f'padding:1px 6px; border-radius:3px; font-size:12px; '
                                f'margin-right:4px">{ts["topic"][:20]}: {sc}</span>'
                            )

                        avail_c = r["avail_color"]
                        quality_c = MAUVE if r["quality"] >= 0.85 else (
                            PEACH if r["quality"] >= 0.75 else RED)
                        display_idx = idx + 1 if is_rec else "+"

                        ui.html(sanitize=False, content=
                            f'<div style="background:{SURFACE2}; border:1px solid {border_c}; '
                            f'border-radius:8px; padding:10px 14px; margin-bottom:6px; '
                            f'display:flex; align-items:center; justify-content:space-between">'
                            f'<div style="display:flex; align-items:center; gap:12px; flex:1; min-width:0">'
                            f'<div style="background:{MAUVE if is_rec else PEACH}20; color:{MAUVE if is_rec else PEACH}; width:28px; height:28px; '
                            f'border-radius:50%; display:flex; align-items:center; justify-content:center; '
                            f'font-size:12px; font-weight:700; flex-shrink:0">{display_idx}</div>'
                            f'<div style="min-width:0">'
                            f'<div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap">'
                            f'<span style="color:{TEXT}; font-weight:600; font-size:13px">{r["employee"]}</span>'
                            f'{badge}</div>'
                            f'<div style="color:{SUBTEXT}; font-size:13px; margin-top:2px">'
                            f'{r["model"]} · {r["total_experience"]} tasks in these topics</div>'
                            f'<div style="margin-top:4px">{topic_chips}</div>'
                            f'</div></div>'
                            f'<div style="text-align:right; flex-shrink:0; margin-left:12px">'
                            f'<div style="font-size:18px; font-weight:700; color:{MAUVE if is_rec else PEACH}">{r["score"]}</div>'
                            f'<div style="font-size:12px; color:{SUBTEXT}; text-transform:uppercase">Score</div>'
                            f'<div style="font-size:13px; color:{avail_c}; margin-top:4px">'
                            f'{r["availability"]} ({r["open_tickets"]} tickets)</div>'
                            f'<div style="font-size:12px; color:{quality_c}">Quality: {r["quality"]:.0%}</div>'
                            f'</div></div>'
                        )

            with ui.row().classes("mt-3"):
                ui.button("Generate Ideal Team", on_click=_gen_team).style(
                    f"background:{MAUVE}; color:{DARK_BG}; font-weight:600; font-size:12px")


def _compute_velocity_adjustments(records, epic_data, insight_data):
    """Use temporal drift data to adjust velocity predictions for in-progress epics."""
    drift_items = insight_data.get("temporal_drift", [])
    if not drift_items:
        return {}

    topic_kw = {t: set(cfg["keywords"])
                for t, cfg in get_active_preset()["topics"].items()}

    # Index drift by keyword
    drift_by_kw = {d["keyword"]: d for d in drift_items}

    results = {}
    for epic in epic_data:
        if epic.get("status") != "in_progress":
            continue

        worsening_kws = []
        improving_kws = []
        for topic in epic.get("topics", []):
            kw_set = topic_kw.get(topic, set())
            for kw in kw_set:
                if kw in drift_by_kw:
                    d = drift_by_kw[kw]
                    entry = {"keyword": kw, "drift_pct": d["drift_pct"]}
                    if d["direction"] == "worsening":
                        worsening_kws.append(entry)
                    else:
                        improving_kws.append(entry)

        # Compute multiplier: worsening adds 1.1-1.3x, improving 0.85-0.95x
        multiplier = 1.0
        for w in worsening_kws:
            multiplier += min(0.3, max(0.1, abs(w["drift_pct"]) / 300))
        for i in improving_kws:
            multiplier -= min(0.15, max(0.05, abs(i["drift_pct"]) / 300))
        multiplier = max(0.7, min(1.5, multiplier))

        exp_hrs = epic.get("est_remaining_exp_hrs", epic.get("est_duration_exp_hrs", 0))
        adjusted_hrs = round(exp_hrs * multiplier, 1)

        # Completion date: 6 productive hrs/day, 5 days/week
        work_days = adjusted_hrs / 6.0 if adjusted_hrs > 0 else 0
        calendar_days = int(work_days * 7 / 5) + 1
        completion_date = (datetime.now() + timedelta(days=calendar_days)).strftime("%Y-%m-%d")

        results[epic["key"]] = {
            "multiplier": round(multiplier, 2),
            "worsening_keywords": sorted(worsening_kws, key=lambda x: -abs(x["drift_pct"]))[:3],
            "improving_keywords": sorted(improving_kws, key=lambda x: -abs(x["drift_pct"]))[:3],
            "adjusted_exp_hrs": adjusted_hrs,
            "original_exp_hrs": exp_hrs,
            "completion_date": completion_date,
        }

    return results


def _render_timing_card(epic: dict, vel: dict | None):
    """Minimal completion forecast: name, adjusted date, shift topics."""
    exp = epic.get("est_remaining_exp_hrs", epic.get("est_duration_exp_hrs", 0))
    if vel:
        hours = vel["adjusted_exp_hrs"]
        date = vel["completion_date"]
        m = vel["multiplier"]
    else:
        hours = exp
        work_days = hours / 6.0 if hours else 0
        date = (datetime.now() + timedelta(days=int(work_days * 7 / 5) + 1)).strftime("%Y-%m-%d")
        m = 1.0

    if m > 1.0:
        shift_text, shift_color = f"{(m - 1) * 100:.0f}% slower from shifts", RED
    elif m < 1.0:
        shift_text, shift_color = f"{(1 - m) * 100:.0f}% faster from shifts", GREEN
    else:
        shift_text, shift_color = "no temporal shift", SUBTEXT

    tags = []
    for w in (vel or {}).get("worsening_keywords", []):
        tags.append(
            f'<span style="background:{SURFACE2}; border:1px solid {BORDER}; color:{RED}; '
            f'padding:4px 12px; font-size:14px; font-weight:600">▲ {w["keyword"]}</span>')
    for i in (vel or {}).get("improving_keywords", []):
        tags.append(
            f'<span style="background:{SURFACE2}; border:1px solid {BORDER}; color:{GREEN}; '
            f'padding:4px 12px; font-size:14px; font-weight:600">▼ {i["keyword"]}</span>')

    # Drop the year: "2026-08-14" -> "Aug 14"
    try:
        date_display = datetime.strptime(date, "%Y-%m-%d").strftime("%b %d")
    except ValueError:
        date_display = date

    pct = epic.get("pct_done", 0)
    eyebrow = (f'color:{SUBTEXT}; font-size:12px; font-weight:600; '
               f'text-transform:uppercase; letter-spacing:0.08em')
    tags_html = ""
    if tags:
        tags_html = (f'<div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; '
                     f'padding-top:14px; border-top:1px solid {BORDER}">{"".join(tags)}</div>')

    with ui.card().classes("w-full mb-4 p-5"):
        ui.html(sanitize=False, content=f'''
<div style="font-size:19px; font-weight:700; color:{TEXT}; letter-spacing:-0.01em;
            margin-bottom:16px">{epic.get("name", "")}</div>
<div style="display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:16px">
  <div>
    <div style="{eyebrow}">Progress</div>
    <div style="font-size:26px; font-weight:700; color:{TEXT}; margin-top:4px">{pct:.0f}%</div>
  </div>
  <div>
    <div style="{eyebrow}">Hours Remaining</div>
    <div style="font-size:26px; font-weight:700; color:{BLUE}; margin-top:4px">{hours:.0f}h</div>
  </div>
  <div>
    <div style="{eyebrow}">Estimated End Date</div>
    <div style="font-size:26px; font-weight:700; color:{TEXT}; margin-top:4px">{date_display}</div>
    <div style="font-size:13px; font-weight:600; color:{shift_color}; margin-top:2px">{shift_text}</div>
  </div>
</div>
{tags_html}''')


# ─── Main ─────────────────────────────────────────────────────────────────

# Cache blind spots at module level to avoid recomputing in epic cards
_blind_spots_cache = None

def get_blind_spots_cached(records):
    global _blind_spots_cache
    if _blind_spots_cache is None:
        _blind_spots_cache = get_blind_spots(records)
    return _blind_spots_cache


build_dashboard()

# ─── Start Hub services (receiver + Bonjour) in background ────────────────
import threading as _threading

def _start_hub_services():
    """Start the data receiver (with TLS + auth) and Bonjour advertisement."""
    import importlib
    try:
        from hub_security import (
            init_hub_secrets, get_ssl_context, needs_dashboard_password,
            set_dashboard_password,
        )
        hub_secrets = init_hub_secrets()

        if needs_dashboard_password():
            import getpass
            print("\n[hub] First-time setup — set a dashboard password.")
            print("[hub] This password is used to view the analytics dashboard.")
            while True:
                pw = getpass.getpass("[hub] Dashboard password: ")
                if len(pw) < 4:
                    print("[hub] Password too short (min 4 characters).")
                    continue
                pw2 = getpass.getpass("[hub] Confirm password: ")
                if pw != pw2:
                    print("[hub] Passwords don't match. Try again.")
                    continue
                set_dashboard_password(pw)
                print("[hub] Dashboard password set.\n")
                break

        receiver = importlib.import_module("receiver")
        receiver._init_record_count()
        receiver._hub_secrets = hub_secrets
        server = receiver.ThreadingHTTPServer(("0.0.0.0", 8788), receiver.ReceiverHandler)
        ssl_ctx = get_ssl_context()
        if ssl_ctx:
            server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)
            print(f"[hub] Receiver listening on https://0.0.0.0:8788 (TLS enabled)")
        else:
            print(f"[hub] Receiver listening on http://0.0.0.0:8788 (TLS unavailable)")
        t = _threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        print(f"[hub] Pairing code for collectors: {hub_secrets.get('pairing_code', 'N/A')}")
    except Exception as e:
        print(f"[hub] Receiver failed to start: {e}")

    # Advertise via Bonjour
    try:
        from hub_discovery import start_advertisement
        start_advertisement(receiver_port=8788, dashboard_port=8790)
    except Exception as e:
        print(f"[hub] Bonjour advertisement failed: {e}")

_threading.Thread(target=_start_hub_services, daemon=True).start()

# ─── Launch UI ────────────────────────────────────────────────────────────
_use_native = False
if not os.environ.get("DASHBOARD_NO_NATIVE"):
    try:
        import webview  # noqa: F401
        _use_native = True
    except ImportError:
        pass

ui.run(
    title=f"{get_active_preset()['company']} — Dashboard",
    port=8790,
    dark=True,
    reload=False,
    native=_use_native,
    window_size=(1440, 900) if _use_native else None,
    reconnect_timeout=60,
)
