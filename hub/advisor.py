#!/usr/bin/env python3
"""
AI Advisor — uses a local Llama model (via Ollama) to research best practices
and generate education/tooling plans for topics where the team struggles.

Reads analytics output to find:
  - Team blind spots (high absolute difficulty)
  - High-error topics
  - Individual struggle areas

Then queries Llama 3.2 3B for:
  1. Current best practices and tools for each BLIND SPOT topic only
  2. One emerging tool/trend that may soon snowball
  3. A two-tier plan:
     - Strategic summary (for leadership)
     - Detailed action plan (for the team)

Uses curated source knowledge (not live scraping) — the model's training
data covers major tools, frameworks, and practices up to its cutoff.

Requires: Ollama running locally with llama3.2:3b pulled.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "output")
TASK_FILE = os.path.join(DATA_DIR, "task_data.jsonl")

from presets import get_active_preset
from pm_provider import load_all_tickets
from code_insight import sanitize_prompt_field

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")


def _get_curated_sources() -> dict:
    return get_active_preset().get("curated_sources", {})


# Legacy fallback — kept for reference but _get_curated_sources() is used at runtime.
_LEGACY_CURATED_SOURCES = {
    "Security & Auth": {
        "standards": ["OWASP Top 10 (2025)", "NIST Cybersecurity Framework", "CIS Benchmarks"],
        "tools": ["Snyk", "SonarQube", "Trivy", "HashiCorp Vault", "AWS IAM Access Analyzer",
                  "Checkov", "tfsec", "Semgrep", "Dependabot"],
        "training": ["SANS SEC540", "PortSwigger Web Security Academy (free)",
                     "OWASP WebGoat", "Hack The Box"],
        "practices": ["shift-left security scanning in CI", "secret rotation automation",
                      "RBAC with least-privilege", "automated dependency vulnerability scanning"],
    },
    "ML & AI Integration": {
        "standards": ["MLOps maturity model (Google)", "Responsible AI practices"],
        "tools": ["MLflow", "Weights & Biases", "DVC", "LangChain", "LlamaIndex",
                  "vLLM", "Hugging Face Transformers", "Ray Serve", "BentoML"],
        "training": ["fast.ai (free)", "Hugging Face NLP Course (free)",
                     "DeepLearning.AI short courses", "Made With ML (free)"],
        "practices": ["model versioning and experiment tracking", "prompt evaluation frameworks",
                      "RAG pipeline testing", "model serving with health checks",
                      "LLM output validation and guardrails"],
    },
    "Database & Schema Design": {
        "standards": ["Database reliability engineering principles"],
        "tools": ["Alembic", "Flyway", "pganalyze", "pg_stat_statements",
                  "SchemaHero", "Atlas (Ariga)", "Bytebase"],
        "training": ["Use The Index, Luke (free)", "PostgreSQL exercises",
                     "CMU Database Course (free videos)"],
        "practices": ["migration safety checks (no-lock migrations)", "query plan analysis",
                      "connection pooling (PgBouncer)", "schema review in PRs",
                      "automated index recommendations"],
    },
    "Frontend Development": {
        "standards": ["WCAG 2.2 accessibility", "Core Web Vitals"],
        "tools": ["Storybook", "Playwright", "Lighthouse CI", "Chromatic",
                  "React DevTools Profiler", "Bundle Analyzer"],
        "training": ["Epic React (Kent C. Dodds)", "Testing JavaScript",
                     "web.dev Learn (free)", "Frontend Masters"],
        "practices": ["component-driven development", "visual regression testing",
                      "bundle size budgets", "accessibility audits in CI"],
    },
    "Performance Optimization": {
        "standards": ["Google SRE workbook perf chapters"],
        "tools": ["py-spy", "cProfile", "flamegraph", "Locust", "k6",
                  "Grafana Tempo (tracing)", "Redis Insight"],
        "training": ["Systems Performance by Brendan Gregg",
                     "High Performance Python (book)"],
        "practices": ["continuous profiling in production", "load testing in CI",
                      "caching strategy documentation", "latency budgets per endpoint"],
    },
    "Data Engineering": {
        "standards": ["Data mesh principles", "Data quality dimensions (completeness, accuracy, timeliness)"],
        "tools": ["dbt", "Great Expectations", "Apache Airflow", "Dagster",
                  "Delta Lake", "Fivetran", "Monte Carlo (observability)"],
        "training": ["Data Engineering Zoomcamp (free)", "dbt Learn (free)"],
        "practices": ["data contracts between teams", "pipeline idempotency",
                      "schema evolution strategy", "data freshness SLAs"],
    },
    "CI/CD & DevOps": {
        "standards": ["DORA metrics", "12-factor app"],
        "tools": ["GitHub Actions", "ArgoCD", "Renovate", "Earthly",
                  "Dagger", "Trunk (CI optimization)"],
        "training": ["Google SRE Book (free)", "DevOps Handbook"],
        "practices": ["trunk-based development", "feature flags over long branches",
                      "deploy frequency tracking", "rollback automation"],
    },
    "Cloud Infrastructure": {
        "standards": ["AWS Well-Architected Framework", "Cloud cost optimization"],
        "tools": ["Terraform", "Pulumi", "Infracost", "Spacelift",
                  "AWS Trusted Advisor", "Spot.io"],
        "training": ["AWS Solutions Architect course", "Terraform Associate cert"],
        "practices": ["infrastructure as code review process", "cost tagging strategy",
                      "disaster recovery runbooks", "multi-region failover testing"],
    },
    "Testing & QA": {
        "standards": ["Testing pyramid", "Shift-left testing"],
        "tools": ["pytest", "Playwright", "Testcontainers", "Allure",
                  "Mutation testing (mutmut)", "Coverage.py"],
        "training": ["Test-Driven Development by Example (book)",
                     "Testing Python Applications (Real Python, free)"],
        "practices": ["contract testing between services", "flaky test quarantine",
                      "test impact analysis", "coverage gates in CI"],
    },
    "Monitoring & Observability": {
        "standards": ["OpenTelemetry specification", "SLO/SLI framework"],
        "tools": ["Grafana stack", "Datadog", "Honeycomb", "PagerDuty",
                  "OpenTelemetry Collector"],
        "training": ["Observability Engineering (book)", "Honeycomb sandbox (free)"],
        "practices": ["structured logging standard", "distributed tracing adoption",
                      "SLO-based alerting", "incident postmortem process"],
    },
    "Code Review & Refactoring": {
        "standards": ["Google Engineering Practices (code review guide)"],
        "tools": ["SonarQube", "CodeClimate", "Semgrep", "Sourcery",
                  "GitHub Copilot code review"],
        "training": ["Refactoring by Martin Fowler", "Working Effectively with Legacy Code"],
        "practices": ["PR size limits", "automated style enforcement",
                      "refactoring-only PRs separate from features"],
    },
    "Backend API Development": {
        "standards": ["OpenAPI 3.1", "REST API design guidelines", "gRPC best practices"],
        "tools": ["FastAPI", "Swagger/OpenAPI codegen", "Postman/Bruno",
                  "Pact (contract testing)", "APIdog"],
        "training": ["API Design Patterns (book)", "FastAPI docs tutorial (free)"],
        "practices": ["API versioning strategy", "request validation at boundaries",
                      "rate limiting", "comprehensive API documentation"],
    },
}


def ollama_generate(prompt: str, temperature: float = 0.3) -> str:
    """Call local Ollama API. Returns generated text."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 2048,
        },
    }
    try:
        req = Request(OLLAMA_URL, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=120)
        result = json.loads(resp.read().decode())
        return result.get("response", "").strip()
    except (URLError, OSError) as e:
        return f"[Ollama error: {e}]"


def load_analytics_context() -> dict:
    """Load the latest analytics output to understand what's struggling."""
    context = {
        "blind_spots": [],
        "high_error_topics": [],
        "individual_struggles": [],
        "active_projects": set(),
        "active_topics": set(),
    }

    report_path = os.path.join(OUTPUT_DIR, "summary_report.txt")
    if os.path.exists(report_path):
        with open(report_path) as f:
            context["report_text"] = f.read()

    if os.path.exists(TASK_FILE):
        records = []
        with open(TASK_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        from collections import defaultdict
        topic_errors = defaultdict(list)
        for r in records:
            context["active_projects"].add(r.get("project", "Unknown"))
            topic = r.get("task_name", "").split("-task-")[0].replace("-", " ").title()
            topic_errors[topic].append(r.get("error_count", 0))

    tickets = load_all_tickets()
    if tickets:
        from collections import Counter
        project_counts = Counter()
        component_counts = Counter()
        for ticket in tickets.values():
            status = ticket.get("status", "")
            if status.lower().replace(" ", "_") in ("in_progress", "in_review", "to_do"):
                for comp in ticket.get("components", []):
                    component_counts[comp] += 1

        context["active_components"] = component_counts.most_common(10)
        context["active_project_tickets"] = dict(project_counts.most_common())

    context["active_projects"] = sorted(context["active_projects"])
    return context


def generate_topic_research(topic: str, avg_errors: float, avg_retries: float,
                            avg_duration: float, avg_tokens: float) -> str:
    """Ask Llama to research best practices for a struggling topic."""
    sources = _get_curated_sources().get(topic, {})
    sources_text = ""
    if sources:
        sources_text = f"""
Known relevant resources for {topic}:
- Standards: {', '.join(sources.get('standards', []))}
- Tools: {', '.join(sources.get('tools', []))}
- Training: {', '.join(sources.get('training', []))}
- Best practices: {', '.join(sources.get('practices', []))}
"""

    preset = get_active_preset()
    company = preset["company"]
    prompt = f"""You are a senior engineering advisor at a software company called {company}.

The team is struggling with "{sanitize_prompt_field(topic)}". Here are the metrics:
- Average {avg_errors:.1f} errors per task (high)
- Average {avg_retries:.1f} retries per task
- Average task duration: {avg_duration:.0f} minutes
- Average token usage: {avg_tokens:.0f}
{sources_text}
Based on these known resources and current industry best practices, provide:

1. ROOT CAUSES: What typically causes high error rates in {sanitize_prompt_field(topic)}? (2-3 bullet points)
2. RECOMMENDED TOOLS: Which 3-4 specific tools should the team adopt? For each, explain why in one sentence.
3. BEST PRACTICES: What 3-4 practices would reduce errors? Be specific and actionable.
4. QUICK WINS: What can the team do THIS WEEK to start improving? (2-3 items)

Keep each section concise. Use bullet points. Focus on practical, implementable recommendations."""

    return ollama_generate(prompt)


def generate_education_plan(blind_spots: list[dict], struggles: list[dict],
                            active_projects: list[str],
                            active_components: list[tuple]) -> str:
    """Generate a two-tier education plan."""
    blind_spot_summary = "\n".join(
        f"  - {sanitize_prompt_field(b['topic'])}: avg {b['avg_errors']:.1f} errors/task, "
        f"{b['avg_duration']:.0f} min avg duration, difficulty score {b['difficulty_score']:.1f}"
        for b in blind_spots
    )

    struggle_summary = "\n".join(
        f"  - {sanitize_prompt_field(s['employee'], 'employee')} in {sanitize_prompt_field(s['topic'])}: {s['duration_ratio']:.1f}x duration, "
        f"{s['token_ratio']:.1f}x tokens"
        for s in struggles[:10]
    )

    project_text = ", ".join(sanitize_prompt_field(p, "project") for p in active_projects[:5])
    component_text = ", ".join(f"{sanitize_prompt_field(c[0])} ({c[1]} tickets)" for c in active_components[:8])

    preset = get_active_preset()
    company = preset["company"]
    desc = preset["description"]
    prompt = f"""You are a senior engineering advisor at {company}, a {desc}.

TEAM BLIND SPOTS (everyone struggles):
{blind_spot_summary}

INDIVIDUAL STRUGGLES:
{struggle_summary}

ACTIVE PROJECTS: {project_text}
ACTIVE WORK AREAS: {component_text}

Generate a TWO-TIER improvement plan. Be ruthless about brevity — no filler,
no restating the data, no generic advice. Every line must be a concrete action.

TIER 1 — STRATEGIC SUMMARY (for engineering leadership)
Exactly 3 bullet points, one line each: the core gap, the recommended
investment, the expected impact.

TIER 2 — ACTION PLAN (for the team)
For each blind spot topic (max 3 topics), exactly 3 bullets:
- Now: one quick win (a tool, config, or linting rule — name it)
- Next 30 days: one knowledge-sharing action (who pairs with whom, or who presents)
- Ongoing: one process change (a CI gate, checklist item, or automation)

Then ONE line per struggling individual: "Pair X with Y on <topic>."

Total response under 300 words. No introductions, no conclusions."""

    return ollama_generate(prompt, temperature=0.4)


def generate_emerging_trend(blind_spot_topics: list[str]) -> str:
    """Ask Llama for one emerging tool/trend that may soon snowball."""
    preset = get_active_preset()
    company = preset["company"]
    desc = preset["description"]
    topics_text = ", ".join(sanitize_prompt_field(t) for t in blind_spot_topics) if blind_spot_topics else "general engineering"

    prompt = f"""You are a senior engineering advisor at {company}, a {desc}.

The team currently has blind spots in: {topics_text}.

Identify ONE cutting-edge tool, framework, or industry trend that:
- Is rapidly gaining adoption RIGHT NOW
- Is likely to become critical/standard within 12 months
- Is relevant to this team's domain and their current weak areas
- Could snowball into a major gap if ignored

Provide:
1. WHAT: Name the specific tool or trend (one thing only)
2. WHY NOW: Why is this gaining momentum? (2-3 sentences)
3. RISK OF IGNORING: What happens if the team doesn't get ahead of this? (2-3 sentences)
4. GITHUB: Link to the main GitHub repository (e.g. https://github.com/org/repo). If it's a standard rather than a tool, link to the reference implementation or spec repo.
5. QUICK START: How can the team start exploring this in the next 2 weeks? (2-3 concrete steps)

Be specific — name the actual tool or standard, not a vague category. Keep the entire response under 250 words."""

    return ollama_generate(prompt, temperature=0.5)


def main() -> None:
    preset = get_active_preset()
    company = preset["company"]
    print("=" * 70)
    print(f"{company.upper()} — ADVISOR (powered by Llama 3.2 3B via Ollama)")
    print("=" * 70)
    print()

    # Verify Ollama is running
    try:
        urlopen("http://localhost:11434/api/tags", timeout=5)
    except (URLError, OSError):
        print("ERROR: Ollama is not running.")
        print("Start it with: brew services start ollama")
        sys.exit(1)

    print("Loading analytics context...")
    context = load_analytics_context()

    # Parse the report to find blind spots and struggles
    report = context.get("report_text", "")
    blind_spots = []
    struggles = []

    # Re-run analytics data loading for structured access
    import pandas as pd
    from analytics import (load_data, load_jira_tickets, enrich_with_jira,
                           classify_topic, build_benchmarks,
                           compute_difficulty_scores, compare_individuals)

    df = load_data()
    tickets = load_jira_tickets()
    df = enrich_with_jira(df, tickets)
    df["topic"] = df["keywords"].apply(classify_topic)
    bench = build_benchmarks(df)
    bench = compute_difficulty_scores(bench)
    ind = compare_individuals(df, bench)

    blind_spot_topics = bench[bench["is_team_blind_spot"]].to_dict("records")
    flagged = ind[ind["flagged"]].to_dict("records")

    if not blind_spot_topics and not flagged:
        print("No significant struggles detected. The team is performing well!")
        return

    print(f"Found {len(blind_spot_topics)} team blind spot(s) and "
          f"{len(flagged)} individual struggle(s).")
    print()

    # ── Research each blind spot topic ──
    all_research: list[dict] = []
    for bs in blind_spot_topics:
        topic = bs["topic"]
        print(f"Researching best practices for: {topic}...")
        research = generate_topic_research(
            topic, bs["avg_errors"], bs["avg_retries"],
            bs["avg_duration"], bs["avg_tokens"])
        all_research.append({"topic": topic, "research": research})
        print(f"  Done ({len(research)} chars)")

    covered = {bs["topic"] for bs in blind_spot_topics}

    # ── Research one emerging tool/trend ──
    print("Researching emerging tool/trend that may soon snowball...")
    trend_research = generate_emerging_trend(list(covered))
    all_research.append({"topic": "Emerging Trend", "research": trend_research})
    print(f"  Done ({len(trend_research)} chars)")

    # ── Generate education plan ──
    print()
    print("Generating education and tooling plan...")
    plan = generate_education_plan(
        blind_spot_topics, flagged,
        context["active_projects"],
        context.get("active_components", []))
    print("  Done")

    # ── Assemble final report ──
    output_lines = [
        "=" * 70,
        f"{company.upper()} — AI ADVISOR REPORT",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Model: {MODEL} (local via Ollama)",
        "=" * 70,
        "",
    ]

    output_lines.append("TOPIC RESEARCH — BEST PRACTICES & TOOLS")
    output_lines.append("-" * 70)
    for item in all_research:
        output_lines.append(f"\n{'='*40}")
        output_lines.append(f"  {item['topic']}")
        output_lines.append(f"{'='*40}")
        output_lines.append(item["research"])
        output_lines.append("")

    output_lines.append("")
    output_lines.append("EDUCATION & TOOLING PLAN")
    output_lines.append("-" * 70)
    output_lines.append(plan)

    output_lines.append("")
    output_lines.append("=" * 70)
    output_lines.append("CURATED RESOURCE APPENDIX")
    output_lines.append("-" * 70)
    for topic in covered:
        sources = _get_curated_sources().get(topic, {})
        if sources:
            output_lines.append(f"\n  {topic}:")
            for category, items in sources.items():
                output_lines.append(f"    {category}: {', '.join(items)}")

    output_lines.append("")
    output_lines.append("=" * 70)

    full_report = "\n".join(output_lines)

    # Save text
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_path = os.path.join(OUTPUT_DIR, "advisor_report.txt")
    with open(report_path, "w") as f:
        f.write(full_report)

    # Build and save HTML report, then open in browser
    html_path = os.path.join(OUTPUT_DIR, "advisor_report.html")
    html = build_html_report(company, all_research, plan, covered)
    with open(html_path, "w") as f:
        f.write(html)

    print()
    print(full_report)
    print(f"\nReport saved: {report_path}")
    if not os.environ.get("ADVISOR_NO_OPEN"):
        print(f"Opening action plan in browser...")
        subprocess.Popen(["open", html_path])


def build_html_report(company: str, research: list[dict],
                      plan: str, covered_topics: set[str]) -> str:
    """Build a dark-themed HTML report for the advisor output."""
    import html as html_mod

    def md_to_html(text: str) -> str:
        """Minimal markdown-ish to HTML: bold, bullets, headers."""
        lines = text.split("\n")
        out = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_list:
                    out.append("</ul>")
                    in_list = False
                out.append("<br>")
                continue
            # Bold markers
            escaped = html_mod.escape(stripped)
            escaped = escaped.replace("**", "<b>", 1)
            if "<b>" in escaped:
                escaped = escaped.replace("**", "</b>", 1)
            # Bullet points
            if stripped.startswith(("* ", "- ", "• ")):
                if not in_list:
                    out.append("<ul>")
                    in_list = True
                content = escaped[2:].strip()
                out.append(f"<li>{content}</li>")
            elif stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                if not in_list:
                    out.append("<ul>")
                    in_list = True
                content = escaped.split(".", 1)[1].strip() if "." in escaped else escaped
                out.append(f"<li>{content}</li>")
            elif stripped.startswith("###"):
                if in_list:
                    out.append("</ul>")
                    in_list = False
                out.append(f"<h4>{escaped.lstrip('#').strip()}</h4>")
            elif stripped.startswith("##"):
                if in_list:
                    out.append("</ul>")
                    in_list = False
                out.append(f"<h3>{escaped.lstrip('#').strip()}</h3>")
            elif stripped.startswith("#"):
                if in_list:
                    out.append("</ul>")
                    in_list = False
                out.append(f"<h2>{escaped.lstrip('#').strip()}</h2>")
            else:
                if in_list:
                    out.append("</ul>")
                    in_list = False
                out.append(f"<p>{escaped}</p>")
        if in_list:
            out.append("</ul>")
        return "\n".join(out)

    research_cards = ""
    for item in research:
        topic = html_mod.escape(item["topic"])
        body = md_to_html(item["research"])
        is_trend = item["topic"] == "Emerging Trend"
        card_class = "card trend-card" if is_trend else "card"
        title_class = "card-title trend-title" if is_trend else "card-title"
        research_cards += f"""
        <details class="{card_class}" open>
          <summary class="{title_class}">{"🚀 " if is_trend else ""}{topic}</summary>
          <div class="card-body">{body}</div>
        </details>"""

    plan_html = md_to_html(plan)

    appendix_html = ""
    curated = _get_curated_sources()
    for topic in sorted(covered_topics):
        sources = curated.get(topic, {})
        if sources:
            appendix_html += f"<h4>{html_mod.escape(topic)}</h4><ul>"
            for cat, items in sources.items():
                appendix_html += f"<li><b>{html_mod.escape(cat)}:</b> {html_mod.escape(', '.join(items))}</li>"
            appendix_html += "</ul>"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{company} — Action Plan</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, system-ui, 'Segoe UI', sans-serif;
    background: #1e1e2e; color: #cdd6f4;
    padding: 32px; line-height: 1.6;
    max-width: 900px; margin: 0 auto;
  }}
  h1 {{ color: #89b4fa; font-size: 22px; margin-bottom: 4px; }}
  .subtitle {{ color: #6c7086; font-size: 13px; margin-bottom: 24px; }}
  h2 {{ color: #89b4fa; font-size: 18px; margin: 28px 0 12px; border-bottom: 1px solid #45475a; padding-bottom: 6px; }}
  h3 {{ color: #a6e3a1; font-size: 16px; margin: 20px 0 8px; }}
  h4 {{ color: #f9e2af; font-size: 14px; margin: 16px 0 6px; }}
  p {{ margin: 6px 0; font-size: 14px; }}
  ul {{ margin: 6px 0 6px 20px; font-size: 14px; }}
  li {{ margin: 3px 0; }}
  b {{ color: #f5c2e7; }}
  .card {{
    background: #313244; border: 1px solid #45475a;
    border-radius: 8px; margin: 12px 0; overflow: hidden;
  }}
  .card-title {{
    padding: 12px 16px; cursor: pointer; font-size: 15px;
    font-weight: 600; color: #89b4fa; list-style: none;
  }}
  .card-title::-webkit-details-marker {{ display: none; }}
  .card-title::before {{ content: "▸ "; color: #6c7086; }}
  details[open] > .card-title::before {{ content: "▾ "; }}
  .card-body {{ padding: 0 16px 16px; }}
  .plan-section {{
    background: #313244; border: 1px solid #45475a;
    border-radius: 8px; padding: 20px; margin: 12px 0;
  }}
  .trend-card {{
    border: 1px solid #fab387;
    background: linear-gradient(135deg, #313244 0%, #2a2640 100%);
  }}
  .trend-title {{ color: #fab387 !important; }}
  .appendix {{
    background: #181825; border: 1px solid #313244;
    border-radius: 8px; padding: 16px; margin: 12px 0;
    font-size: 13px; color: #a6adc8;
  }}
  .appendix h4 {{ color: #89b4fa; margin: 12px 0 4px; }}
  .appendix ul {{ margin: 2px 0 8px 16px; }}
  .nav {{
    position: sticky; top: 0; background: #1e1e2e;
    padding: 10px 0; border-bottom: 1px solid #45475a;
    margin-bottom: 16px; z-index: 10;
    display: flex; gap: 12px;
  }}
  .nav a {{
    color: #89b4fa; text-decoration: none; font-size: 13px;
    padding: 4px 12px; border-radius: 4px; background: #313244;
  }}
  .nav a:hover {{ background: #45475a; }}
  br {{ display: block; margin: 4px 0; content: ""; }}
</style>
</head>
<body>
<h1>{html_mod.escape(company)} — Action Plan</h1>
<div class="subtitle">Generated {timestamp} · Llama 3.2 3B via Ollama</div>

<nav class="nav">
  <a href="#research">Topic Research</a>
  <a href="#plan">Education Plan</a>
  <a href="#appendix">Resources</a>
</nav>

<h2 id="research">Topic Research — Best Practices &amp; Tools</h2>
{research_cards}

<h2 id="plan">Education &amp; Tooling Plan</h2>
<div class="plan-section">
{plan_html}
</div>

<h2 id="appendix">Curated Resource Appendix</h2>
<div class="appendix">
{appendix_html}
</div>

</body>
</html>"""


if __name__ == "__main__":
    main()
