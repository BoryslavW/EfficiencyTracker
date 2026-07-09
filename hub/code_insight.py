#!/usr/bin/env python3
"""
Coding Insight Engine — identifies codebase problem areas by analyzing
failure patterns across tasks, keywords, projects, and employees.

Unlike the advisor (which recommends learning resources), this module
answers: "Which parts of the codebase keep causing problems, and why?"

Analysis layers:
  1. Keyword failure hotspots — technical concepts that correlate with errors
  2. Keyword co-occurrence clusters — combos that are toxic together
  3. Project risk profiles — which projects accumulate the most trouble
  4. Temporal drift — areas getting worse over time
  5. Cross-employee convergence — when everyone struggles on the same thing,
     it's a codebase problem, not a people problem
  6. LLM root cause analysis — explains the patterns and suggests fixes

Uses the same Ollama model as the advisor (configurable via OLLAMA_MODEL env).
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "output")

import re as _re

from presets import get_active_preset
from model_baselines import normalize_tokens

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")

# ─── Prompt-injection sanitization ──────────────────────────────────────

_SAFE_CHARS_RE = _re.compile(r"[^a-zA-Z0-9 \-_./]")

FIELD_MAX_LENGTHS = {
    "keyword": 50,
    "project": 100,
    "employee": 80,
}


def sanitize_prompt_field(value: str, field_type: str = "keyword") -> str:
    """Strip non-safe characters and truncate to the limit for *field_type*.

    Accepted field_type values: "keyword", "project", "employee".
    """
    cleaned = _SAFE_CHARS_RE.sub("", str(value))
    max_len = FIELD_MAX_LENGTHS.get(field_type, 50)
    return cleaned[:max_len]


GENERIC_KEYWORDS = {
    "jira", "sprint", "review", "collaboration", "planning",
    "standup", "retro", "priority", "stakeholder", "deadline",
    "scrum", "kanban", "estimation", "blockers",
}


def ollama_generate(prompt: str, temperature: float = 0.3,
                    max_tokens: int = 2048) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    try:
        req = Request(OLLAMA_URL, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=180)
        result = json.loads(resp.read().decode())
        return result.get("response", "").strip()
    except (URLError, OSError) as e:
        return f"[Ollama error: {e}]"


# ---------------------------------------------------------------------------
# 1. Keyword failure hotspots
# ---------------------------------------------------------------------------

def compute_keyword_failure_rates(records: list[dict]) -> list[dict]:
    """For each technical keyword, compute error/retry rates and flag outliers."""
    kw_stats: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "total_errors": 0, "total_retries": 0,
        "total_duration": 0, "total_tokens": 0, "employees": set(),
        "projects": set(),
    })

    for r in records:
        errors = r.get("error_count", 0)
        retries = r.get("retry_count", 0)
        duration = r.get("duration_minutes", 0)
        tokens = r.get("normalized_tokens", r.get("token_usage", 0))

        for kw in r.get("keywords", []):
            if kw in GENERIC_KEYWORDS:
                continue
            s = kw_stats[kw]
            s["count"] += 1
            s["total_errors"] += errors
            s["total_retries"] += retries
            s["total_duration"] += duration
            s["total_tokens"] += tokens
            s["employees"].add(r.get("employee", ""))
            s["projects"].add(r.get("project", ""))

    global_avg_errors = sum(r.get("error_count", 0) for r in records) / max(len(records), 1)
    global_avg_retries = sum(r.get("retry_count", 0) for r in records) / max(len(records), 1)

    results = []
    for kw, s in kw_stats.items():
        if s["count"] < 5:
            continue
        avg_err = s["total_errors"] / s["count"]
        avg_ret = s["total_retries"] / s["count"]
        avg_dur = s["total_duration"] / s["count"]
        err_ratio = avg_err / max(global_avg_errors, 0.1)
        ret_ratio = avg_ret / max(global_avg_retries, 0.1)
        risk_score = err_ratio * 0.6 + ret_ratio * 0.4

        results.append({
            "keyword": kw,
            "occurrences": s["count"],
            "avg_errors": round(avg_err, 2),
            "avg_retries": round(avg_ret, 2),
            "avg_duration_min": round(avg_dur, 1),
            "error_ratio": round(err_ratio, 2),
            "retry_ratio": round(ret_ratio, 2),
            "risk_score": round(risk_score, 2),
            "employee_count": len(s["employees"]),
            "projects": sorted(s["projects"]),
        })

    results.sort(key=lambda x: -x["risk_score"])
    return results


# ---------------------------------------------------------------------------
# 2. Keyword co-occurrence clusters
# ---------------------------------------------------------------------------

def compute_toxic_pairs(records: list[dict], top_n: int = 15) -> list[dict]:
    """Find keyword pairs that co-occur with unusually high error rates."""
    pair_stats: dict[tuple, dict] = defaultdict(lambda: {
        "count": 0, "total_errors": 0, "total_retries": 0,
    })

    global_avg_errors = sum(r.get("error_count", 0) for r in records) / max(len(records), 1)

    for r in records:
        technical_kw = sorted(k for k in r.get("keywords", []) if k not in GENERIC_KEYWORDS)
        errors = r.get("error_count", 0)
        retries = r.get("retry_count", 0)

        for i in range(len(technical_kw)):
            for j in range(i + 1, len(technical_kw)):
                pair = (technical_kw[i], technical_kw[j])
                s = pair_stats[pair]
                s["count"] += 1
                s["total_errors"] += errors
                s["total_retries"] += retries

    results = []
    for (kw1, kw2), s in pair_stats.items():
        if s["count"] < 5:
            continue
        avg_err = s["total_errors"] / s["count"]
        pair_ratio = avg_err / max(global_avg_errors, 0.1)
        if pair_ratio < 1.3:
            continue
        results.append({
            "keywords": [kw1, kw2],
            "co_occurrences": s["count"],
            "avg_errors": round(avg_err, 2),
            "error_ratio": round(pair_ratio, 2),
        })

    results.sort(key=lambda x: -x["error_ratio"])
    return results[:top_n]


# ---------------------------------------------------------------------------
# 3. Project risk profiles
# ---------------------------------------------------------------------------

def compute_project_risk(records: list[dict]) -> list[dict]:
    """Per-project error concentration and keyword-level breakdown."""
    proj: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "total_errors": 0, "total_retries": 0,
        "employees": set(), "keyword_errors": Counter(),
    })

    for r in records:
        p = proj[r.get("project", "Unknown")]
        p["count"] += 1
        p["total_errors"] += r.get("error_count", 0)
        p["total_retries"] += r.get("retry_count", 0)
        p["employees"].add(r.get("employee", ""))
        if r.get("error_count", 0) >= 3:
            for kw in r.get("keywords", []):
                if kw not in GENERIC_KEYWORDS:
                    p["keyword_errors"][kw] += 1

    global_avg = sum(r.get("error_count", 0) for r in records) / max(len(records), 1)

    results = []
    for name, p in proj.items():
        avg_err = p["total_errors"] / max(p["count"], 1)
        top_error_kw = p["keyword_errors"].most_common(5)
        results.append({
            "project": name,
            "tasks": p["count"],
            "avg_errors": round(avg_err, 2),
            "error_ratio": round(avg_err / max(global_avg, 0.1), 2),
            "total_errors": p["total_errors"],
            "employees": len(p["employees"]),
            "top_error_keywords": [{"keyword": k, "high_error_tasks": c}
                                   for k, c in top_error_kw],
        })

    results.sort(key=lambda x: -x["error_ratio"])
    return results


# ---------------------------------------------------------------------------
# 4. Temporal drift
# ---------------------------------------------------------------------------

def compute_temporal_drift(records: list[dict]) -> list[dict]:
    """Detect topics/keywords whose error rates are trending upward."""
    kw_monthly: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for r in records:
        try:
            ts = datetime.fromisoformat(r["start_time"])
            month_key = ts.strftime("%Y-%m")
        except (ValueError, KeyError):
            continue
        for kw in r.get("keywords", []):
            if kw in GENERIC_KEYWORDS:
                continue
            kw_monthly[kw][month_key].append(r.get("error_count", 0))

    results = []
    for kw, months in kw_monthly.items():
        sorted_months = sorted(months.keys())
        if len(sorted_months) < 2:
            continue

        monthly_avgs = []
        for m in sorted_months:
            errs = months[m]
            monthly_avgs.append({
                "month": m,
                "avg_errors": round(sum(errs) / len(errs), 2),
                "count": len(errs),
            })

        if len(monthly_avgs) >= 2:
            first_half = monthly_avgs[:len(monthly_avgs)//2]
            second_half = monthly_avgs[len(monthly_avgs)//2:]
            early_avg = sum(m["avg_errors"] for m in first_half) / len(first_half)
            late_avg = sum(m["avg_errors"] for m in second_half) / len(second_half)

            if early_avg > 0:
                drift = (late_avg - early_avg) / early_avg
            else:
                drift = late_avg

            if abs(drift) > 0.15:
                total_tasks = sum(m["count"] for m in monthly_avgs)
                if total_tasks < 10:
                    continue
                results.append({
                    "keyword": kw,
                    "direction": "worsening" if drift > 0 else "improving",
                    "drift_pct": round(drift * 100, 1),
                    "early_avg_errors": round(early_avg, 2),
                    "late_avg_errors": round(late_avg, 2),
                    "months": monthly_avgs,
                })

    results.sort(key=lambda x: -abs(x["drift_pct"]))
    return results


# ---------------------------------------------------------------------------
# 5. Cross-employee convergence
# ---------------------------------------------------------------------------

def compute_convergence_signals(records: list[dict]) -> list[dict]:
    """Find keywords where multiple employees independently struggle.

    When 60%+ of employees who touch a keyword have above-average errors,
    it's likely a codebase problem, not an individual skill gap.
    """
    kw_emp: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(
        lambda: {"count": 0, "total_errors": 0}))

    for r in records:
        emp = r.get("employee", "")
        errors = r.get("error_count", 0)
        for kw in r.get("keywords", []):
            if kw in GENERIC_KEYWORDS:
                continue
            s = kw_emp[kw][emp]
            s["count"] += 1
            s["total_errors"] += errors

    global_avg = sum(r.get("error_count", 0) for r in records) / max(len(records), 1)

    results = []
    for kw, employees in kw_emp.items():
        if len(employees) < 3:
            continue

        struggling_emps = []
        normal_emps = []
        for emp, s in employees.items():
            if s["count"] < 2:
                continue
            avg = s["total_errors"] / s["count"]
            if avg > global_avg * 1.3:
                struggling_emps.append(emp)
            else:
                normal_emps.append(emp)

        total_qualified = len(struggling_emps) + len(normal_emps)
        if total_qualified < 3:
            continue

        convergence = len(struggling_emps) / total_qualified
        if convergence >= 0.5:
            results.append({
                "keyword": kw,
                "convergence_ratio": round(convergence, 2),
                "struggling_employees": len(struggling_emps),
                "total_employees": total_qualified,
                "verdict": "codebase_problem" if convergence >= 0.7 else "likely_codebase",
            })

    results.sort(key=lambda x: -x["convergence_ratio"])
    return results


# ---------------------------------------------------------------------------
# 6. Assemble full insight report
# ---------------------------------------------------------------------------

def build_insight_data(records: list[dict]) -> dict:
    """Run all analyses and return the structured insight data."""
    from model_baselines import normalize_tokens as _nt

    for r in records:
        if "normalized_tokens" not in r:
            r["normalized_tokens"] = _nt(r.get("token_usage", 0),
                                         r.get("model", "unknown"))
        if "duration_minutes" not in r:
            try:
                start = datetime.fromisoformat(r["start_time"])
                end = datetime.fromisoformat(r["end_time"])
                r["duration_minutes"] = max(1, (end - start).total_seconds() / 60)
            except (ValueError, KeyError):
                r["duration_minutes"] = 0

    hotspots = compute_keyword_failure_rates(records)
    toxic_pairs = compute_toxic_pairs(records)
    project_risk = compute_project_risk(records)
    drift = compute_temporal_drift(records)
    convergence = compute_convergence_signals(records)

    codebase_problems = [c for c in convergence if c["verdict"] == "codebase_problem"]
    worsening = [d for d in drift if d["direction"] == "worsening"]

    return {
        "keyword_hotspots": hotspots[:20],
        "toxic_pairs": toxic_pairs,
        "project_risk": project_risk,
        "temporal_drift": drift[:15],
        "convergence": convergence[:15],
        "summary": {
            "total_records": len(records),
            "high_risk_keywords": len([h for h in hotspots if h["risk_score"] > 1.5]),
            "toxic_pair_count": len(toxic_pairs),
            "codebase_problems": len(codebase_problems),
            "worsening_areas": len(worsening),
            "top_risk_keyword": hotspots[0]["keyword"] if hotspots else None,
            "top_risk_project": project_risk[0]["project"] if project_risk else None,
        },
    }


# ---------------------------------------------------------------------------
# 7. LLM root cause analysis
# ---------------------------------------------------------------------------

def generate_root_cause_analysis(insight_data: dict) -> str:
    """Generate copy-paste fix prompts from the statistical patterns."""
    preset = get_active_preset()
    company = preset["company"]
    desc = preset["description"]

    hotspots = insight_data["keyword_hotspots"][:10]
    hotspot_text = "\n".join(
        f"  - {sanitize_prompt_field(h['keyword'])}: {h['avg_errors']:.1f} errors/task ({h['error_ratio']:.1f}x avg), "
        f"seen by {h['employee_count']} employees in {', '.join(sanitize_prompt_field(p, 'project') for p in h['projects'][:2])}"
        for h in hotspots
    )

    toxic = insight_data["toxic_pairs"][:5]
    toxic_text = "\n".join(
        f"  - {sanitize_prompt_field(p['keywords'][0])} + {sanitize_prompt_field(p['keywords'][1])}: {p['avg_errors']:.1f} errors ({p['error_ratio']:.1f}x avg)"
        for p in toxic
    )

    convergence = [c for c in insight_data["convergence"][:5]]
    conv_text = "\n".join(
        f"  - {sanitize_prompt_field(c['keyword'])}: {c['struggling_employees']}/{c['total_employees']} employees struggle "
        f"({c['convergence_ratio']:.0%}) → {c['verdict'].replace('_', ' ')}"
        for c in convergence
    )

    worsening = [d for d in insight_data["temporal_drift"] if d["direction"] == "worsening"][:5]
    drift_text = "\n".join(
        f"  - {sanitize_prompt_field(d['keyword'])}: errors up {d['drift_pct']:.0f}% "
        f"({d['early_avg_errors']:.1f} → {d['late_avg_errors']:.1f})"
        for d in worsening
    )

    projects = insight_data["project_risk"][:3]
    proj_text = "\n".join(
        f"  - {sanitize_prompt_field(p['project'], 'project')}: {p['avg_errors']:.1f} errors/task ({p['error_ratio']:.1f}x avg), "
        f"top error areas: {', '.join(sanitize_prompt_field(k['keyword']) for k in p['top_error_keywords'][:3])}"
        for p in projects
    )

    prompt = f"""You are a senior software engineer at {company}, a {desc}. You are generating ready-to-use AI coding prompts that engineers can paste into Claude, Cursor, or Copilot to fix specific codebase issues.

Below is data from {insight_data['summary']['total_records']} coding tasks showing where the codebase is broken.

KEYWORD FAILURE HOTSPOTS (highest error rates):
{hotspot_text}

TOXIC COMBINATIONS (pairs that multiply errors):
{toxic_text}

CROSS-EMPLOYEE CONVERGENCE (everyone struggles = codebase problem):
{conv_text}

WORSENING TRENDS:
{drift_text}

PROJECT RISK PROFILES:
{proj_text}

Generate exactly 5 FIX PROMPTS. Each prompt is something an engineer can copy-paste into an AI coding assistant to fix a real problem found in the data above.

Use this exact format for each (do not deviate):

---
DIAGNOSIS: [one line — what the data shows is broken and where]
SEVERITY: [Critical / High / Medium]
PROMPT:
[The actual multi-line prompt an engineer would paste into an AI assistant. It must:
- Reference specific technical areas from the data (e.g. "our authentication middleware", "the database migration layer")
- Describe the concrete symptom (e.g. "engineers hit ~4.2 errors per task when touching X")
- Ask for a specific deliverable (refactored code, a wrapper, a test suite, a migration script, etc.)
- Include enough context that the AI assistant can act without further questions
- Be 3-6 sentences long]
---

Rules:
- Each prompt targets a DIFFERENT problem from the data. Cover hotspots, toxic pairs, convergence issues, and worsening trends.
- Prompts must be specific to {company}'s data — not generic advice. Reference actual keywords, projects, and error rates.
- The prompt text should read as a direct instruction to a coding AI, starting with an action verb (Refactor, Audit, Create, Extract, Write, etc.)
- Order from most critical to least critical."""

    return ollama_generate(prompt, temperature=0.3, max_tokens=3000)


def generate_keyword_deep_dive(keyword: str, stats: dict,
                               related_pairs: list[dict]) -> str:
    """Deep analysis of a single problematic keyword/area."""
    preset = get_active_preset()
    company = preset["company"]
    safe_keyword = sanitize_prompt_field(keyword)

    pairs_text = "\n".join(
        f"  - Combined with {sanitize_prompt_field(p['keywords'][0] if p['keywords'][1] == keyword else p['keywords'][1])}: "
        f"{p['avg_errors']:.1f} errors ({p['error_ratio']:.1f}x)"
        for p in related_pairs[:5]
    )

    prompt = f"""You are debugging codebase issues at {company}.

The keyword "{safe_keyword}" appears in coding tasks and correlates with high error rates:
- Average {stats['avg_errors']:.1f} errors per task ({stats['error_ratio']:.1f}x the team average)
- Average {stats['avg_retries']:.1f} retries per task
- Average task duration: {stats['avg_duration_min']:.0f} minutes
- Seen by {stats['employee_count']} different employees
- In projects: {', '.join(sanitize_prompt_field(p, 'project') for p in stats['projects'][:3])}

When combined with other keywords, errors spike further:
{pairs_text}

This is a technical analysis. Based on what "{safe_keyword}" typically represents in software engineering:

1. What types of code issues typically cause high error rates in this area?
2. What specific code patterns or anti-patterns are likely present?
3. What's the most impactful single change the team could make to reduce errors here?

Keep it under 150 words. Be specific and technical."""

    return ollama_generate(prompt, temperature=0.25, max_tokens=500)


# ---------------------------------------------------------------------------
# 8. Save / load insight cache
# ---------------------------------------------------------------------------

INSIGHT_FILE = os.path.join(DATA_DIR, "code_insights.json")


def save_insights(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(INSIGHT_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_insights() -> dict:
    if os.path.exists(INSIGHT_FILE):
        with open(INSIGHT_FILE) as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    preset = get_active_preset()
    company = preset["company"]

    task_file = os.path.join(DATA_DIR, "task_data.jsonl")
    if not os.path.exists(task_file):
        print("No task_data.jsonl found. Run generate_fake_data.py first.")
        return

    records = []
    with open(task_file) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    print(f"{'='*60}")
    print(f"{company.upper()} — CODING INSIGHT ENGINE")
    print(f"{'='*60}")
    print(f"Analyzing {len(records)} task records...\n")

    insight_data = build_insight_data(records)
    summary = insight_data["summary"]

    print(f"High-risk keywords: {summary['high_risk_keywords']}")
    print(f"Toxic keyword pairs: {summary['toxic_pair_count']}")
    print(f"Codebase-level problems: {summary['codebase_problems']}")
    print(f"Worsening areas: {summary['worsening_areas']}")

    print("\nTOP 10 KEYWORD HOTSPOTS")
    print("-" * 60)
    for h in insight_data["keyword_hotspots"][:10]:
        print(f"  {h['keyword']:30s}  risk={h['risk_score']:.2f}  "
              f"err={h['avg_errors']:.1f} ({h['error_ratio']:.1f}x)  "
              f"n={h['occurrences']}  employees={h['employee_count']}")

    print("\nTOXIC PAIRS")
    print("-" * 60)
    for p in insight_data["toxic_pairs"][:8]:
        print(f"  {p['keywords'][0]} + {p['keywords'][1]}:  "
              f"err={p['avg_errors']:.1f} ({p['error_ratio']:.1f}x)  "
              f"n={p['co_occurrences']}")

    print("\nCROSS-EMPLOYEE CONVERGENCE (codebase problems)")
    print("-" * 60)
    for c in insight_data["convergence"][:8]:
        print(f"  {c['keyword']:30s}  "
              f"{c['struggling_employees']}/{c['total_employees']} struggle  "
              f"({c['convergence_ratio']:.0%})  → {c['verdict']}")

    print("\nWORSENING TRENDS")
    print("-" * 60)
    for d in insight_data["temporal_drift"][:8]:
        arrow = "↑" if d["direction"] == "worsening" else "↓"
        print(f"  {arrow} {d['keyword']:30s}  {d['drift_pct']:+.0f}%  "
              f"({d['early_avg_errors']:.1f} → {d['late_avg_errors']:.1f})")

    # LLM analysis
    use_llm = "--no-llm" not in sys.argv
    if use_llm:
        try:
            urlopen("http://localhost:11434/api/tags", timeout=5)
        except (URLError, OSError):
            print("\nOllama not running — skipping LLM analysis.")
            print("Start with: brew services start ollama")
            use_llm = False

    if use_llm:
        print(f"\nGenerating root cause analysis via {MODEL}...")
        analysis = generate_root_cause_analysis(insight_data)
        insight_data["llm_analysis"] = analysis
        print("\n" + analysis)

    save_insights(insight_data)
    print(f"\nInsight data saved to {INSIGHT_FILE}")


if __name__ == "__main__":
    main()
