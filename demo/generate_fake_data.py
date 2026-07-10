#!/usr/bin/env python3
"""Generate synthetic task records using the active company preset."""

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hub"))
from presets import get_active_preset, set_active_preset, ALL_PRESETS
from model_baselines import MODEL_BASELINES, REFERENCE_MODEL

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
DATA_FILE = os.path.join(DATA_DIR, "task_data.jsonl")

GENERIC_KEYWORDS = [
    "jira", "sprint", "review", "collaboration", "planning",
    "standup", "retro", "priority", "stakeholder", "deadline",
    "scrum", "kanban", "estimation", "blockers",
]

# Average tasks per employee — actual counts vary per person (see
# _tasks_for_employee) so workloads look realistic instead of uniform.
TASKS_PER_EMPLOYEE = 20
TASKS_SPREAD_STD = 12          # std-dev of per-employee task count
TASKS_MIN, TASKS_MAX = 0, 40


def _tasks_for_employee() -> int:
    n = int(random.gauss(TASKS_PER_EMPLOYEE, TASKS_SPREAD_STD))
    return max(TASKS_MIN, min(TASKS_MAX, n))
BASE_DATE = datetime(2025, 1, 6, 8, 0, 0, tzinfo=timezone.utc)


def pick_keywords(pool: list[str], count: int = 9) -> list[str]:
    n_topic = random.randint(6, min(count, len(pool)))
    chosen = random.sample(pool, n_topic)
    remaining = count - len(chosen)
    if remaining > 0:
        chosen += random.sample(GENERIC_KEYWORDS, min(remaining, len(GENERIC_KEYWORDS)))
    while len(chosen) < count:
        extra = random.choice(pool)
        if extra not in chosen:
            chosen.append(extra)
    return chosen


def generate_records(preset: dict) -> list[dict]:
    records = []
    task_counter = 0
    topics = preset["topics"]
    topic_names = list(topics.keys())
    employees = preset["employees"]
    projects = list(preset["projects"].keys())
    jira_prefixes = [p["key"] for p in preset["projects"].values()]
    struggle_signals = preset.get("struggle_signals", {})
    team_wide = preset.get("team_wide_struggles", {})
    employee_models = preset.get("employee_models", {})
    ref_baseline = MODEL_BASELINES[REFERENCE_MODEL]

    for emp in employees:
        model_id = employee_models.get(emp, "claude-sonnet-4")
        model_data = MODEL_BASELINES.get(model_id, ref_baseline)
        verbosity = model_data["output_verbosity"]

        for _ in range(_tasks_for_employee()):
            topic = random.choice(topic_names)
            cfg = topics[topic]

            dur_lo, dur_hi = cfg["duration_range"]
            tok_lo, tok_hi = cfg["token_range"]

            duration_minutes = random.gauss((dur_lo + dur_hi) / 2, (dur_hi - dur_lo) / 4)
            tokens = random.gauss((tok_lo + tok_hi) / 2, (tok_hi - tok_lo) / 4)

            tokens *= verbosity

            team_signal = team_wide.get(topic)
            if team_signal:
                duration_minutes *= team_signal["duration_mult"]
                tokens *= team_signal["token_mult"]

            signal = struggle_signals.get((emp, topic))
            if signal:
                duration_minutes *= signal["duration_mult"]
                tokens *= signal["token_mult"]

            duration_minutes = max(5, duration_minutes)
            tokens = max(50, int(tokens))

            start = BASE_DATE + timedelta(
                days=random.randint(0, 180),
                hours=random.randint(0, 8),
                minutes=random.randint(0, 59),
            )
            end = start + timedelta(minutes=duration_minutes)

            task_counter += 1
            prefix = random.choice(jira_prefixes)
            jira_id = f"{prefix}-{task_counter}"
            safe_topic = topic.lower().replace(" & ", "-").replace(" ", "-").replace("/", "-")

            kw_count = random.randint(9, 12)
            keywords = pick_keywords(cfg["keywords"], kw_count)

            struggle_level = 1.0
            if signal:
                struggle_level = max(signal["duration_mult"], signal["token_mult"])

            base_errors = random.randint(0, 3)
            base_retries = random.randint(0, 2)
            if team_signal:
                base_errors += random.randint(1, team_signal["error_boost"])
                base_retries += random.randint(0, 2)
            if struggle_level >= 1.5:
                base_errors = max(base_errors, random.randint(2, 8))
                base_retries = max(base_retries, random.randint(1, 5))
            if struggle_level >= 2.0:
                base_errors = max(base_errors, random.randint(5, 15))
                base_retries = max(base_retries, random.randint(3, 10))

            records.append({
                "employee": emp,
                "jira_id": jira_id,
                "task_name": f"{safe_topic}-task-{task_counter}",
                "project": random.choice(projects),
                "token_usage": tokens,
                "model": model_id,
                "keywords": keywords,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "error_count": base_errors,
                "retry_count": base_retries,
                "tool_call_count": random.randint(10, 50) + base_retries,
            })

    random.shuffle(records)
    return records


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ALL_PRESETS:
        set_active_preset(sys.argv[1])

    preset = get_active_preset()
    print(f"Preset: {preset['name']} — {preset['company']} ({preset['description']})")

    os.makedirs(DATA_DIR, exist_ok=True)
    records = generate_records(preset)
    with open(DATA_FILE, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"Generated {len(records)} records -> {DATA_FILE}")

    topics = preset["topics"]
    topic_counts: dict[str, int] = {}
    for r in records:
        best, best_score = "Unknown", 0
        for t, cfg in topics.items():
            overlap = len(set(r["keywords"]) & set(cfg["keywords"]))
            if overlap > best_score:
                best, best_score = t, overlap
        topic_counts[best] = topic_counts.get(best, 0) + 1

    print(f"\nRecords per topic:")
    for t, c in sorted(topic_counts.items()):
        print(f"  {t}: {c}")

    from collections import Counter
    model_counts = Counter(r["model"] for r in records)
    print(f"\nModel distribution:")
    for model, count in model_counts.most_common():
        display = MODEL_BASELINES.get(model, {}).get("display_name", model)
        print(f"  {display}: {count} records ({count * 100 // len(records)}%)")

    print(f"\nBuilt-in struggle signals:")
    for (emp, topic), mult in preset.get("struggle_signals", {}).items():
        label = "OBVIOUS" if mult["duration_mult"] >= 2.0 else "subtle"
        print(f"  [{label}] {emp} in {topic}: "
              f"~{mult['duration_mult']}x duration, ~{mult['token_mult']}x tokens")

    tw = preset.get("team_wide_struggles", {})
    if tw:
        print(f"\nTeam-wide struggles:")
        for topic, signal in tw.items():
            print(f"  {topic}: {signal['duration_mult']}x duration, "
                  f"{signal['token_mult']}x tokens, +{signal['error_boost']} errors")

    # Generate simulated Slack signals
    slack_signals = generate_slack_signals(preset, records)
    slack_file = os.path.join(DATA_DIR, "slack_signals.json")
    with open(slack_file, "w") as f:
        json.dump(slack_signals, f, indent=2)
    print(f"\nSlack signals generated -> {slack_file}")
    print(f"  Employees: {len(slack_signals['employee_signals'])}")
    print(f"  Channels: {len(slack_signals['channel_signals'])}")
    print(f"  Workflow: {slack_signals['workflow_patterns']['task_acquisition']}")


# ─── Simulated Slack Signals ──────────────────────────────────────────────

SLACK_CHANNEL_TEMPLATES = {
    "engineering": {"msgs_per_day": (15, 40), "task_ratio": 0.2, "blocker_ratio": 0.08},
    "project":     {"msgs_per_day": (8, 25),  "task_ratio": 0.3, "blocker_ratio": 0.1},
    "deploy":      {"msgs_per_day": (5, 15),  "task_ratio": 0.1, "blocker_ratio": 0.15},
    "review":      {"msgs_per_day": (10, 30), "task_ratio": 0.15, "blocker_ratio": 0.05},
    "support":     {"msgs_per_day": (5, 20),  "task_ratio": 0.05, "blocker_ratio": 0.2},
    "incident":    {"msgs_per_day": (2, 8),   "task_ratio": 0.1, "blocker_ratio": 0.3},
    "standup":     {"msgs_per_day": (8, 15),  "task_ratio": 0.1, "blocker_ratio": 0.05},
    "general":     {"msgs_per_day": (10, 25), "task_ratio": 0.05, "blocker_ratio": 0.03},
}

SLACK_CHANNELS_PER_PRESET = {
    "startup": [
        ("engineering", "engineering"), ("frontend-dev", "engineering"),
        ("backend-dev", "engineering"), ("proj-onboarding", "project"),
        ("proj-migration", "project"), ("deploys", "deploy"),
        ("code-review", "review"), ("help-eng", "support"),
        ("incidents", "incident"), ("daily-standup", "standup"),
        ("general", "general"), ("random", "general"),
    ],
    "fintech": [
        ("engineering", "engineering"), ("payments-eng", "engineering"),
        ("compliance-eng", "engineering"), ("proj-settlement", "project"),
        ("proj-aml", "project"), ("releases", "deploy"),
        ("pr-reviews", "review"), ("ask-engineering", "support"),
        ("incidents", "incident"), ("standup", "standup"),
        ("general", "general"), ("risk-alerts", "incident"),
    ],
    "medtech": [
        ("engineering", "engineering"), ("ehr-team", "engineering"),
        ("clinical-dev", "engineering"), ("proj-fhir", "project"),
        ("proj-telehealth", "project"), ("deploys", "deploy"),
        ("code-review", "review"), ("help-eng", "support"),
        ("incidents", "incident"), ("daily-sync", "standup"),
        ("general", "general"), ("hipaa-alerts", "incident"),
    ],
}


def generate_slack_signals(preset: dict, task_records: list[dict]) -> dict:
    """Generate realistic simulated Slack signals that correlate with task data."""
    employees = preset["employees"]
    struggles = preset.get("struggle_signals", {})
    team_struggles = preset.get("team_wide_struggles", {})
    preset_name = preset["name"]
    channels = SLACK_CHANNELS_PER_PRESET.get(preset_name, SLACK_CHANNELS_PER_PRESET["startup"])

    # Build per-employee task stats for correlation
    emp_task_counts = {}
    emp_jira_ids = {}
    emp_error_rates = {}
    for r in task_records:
        emp = r["employee"]
        emp_task_counts[emp] = emp_task_counts.get(emp, 0) + 1
        emp_jira_ids.setdefault(emp, []).append(r["jira_id"])
        emp_error_rates.setdefault(emp, []).append(r.get("error_count", 0))

    emp_avg_errors = {e: sum(errs)/len(errs) for e, errs in emp_error_rates.items()}

    # Determine employee "personality" for Slack behavior
    emp_profiles = {}
    for emp in employees:
        is_struggler = any(struggles.get((emp, t)) for t in preset["topics"])
        avg_err = emp_avg_errors.get(emp, 1)

        emp_profiles[emp] = {
            "chattiness": random.uniform(0.5, 2.0),
            "help_seeker": 1.5 if is_struggler else random.uniform(0.3, 1.0),
            "task_completer": random.uniform(0.6, 1.5) * (0.7 if is_struggler else 1.0),
            "reviewer": random.uniform(0.3, 1.5),
            "error_rate": avg_err,
            "thread_tendency": random.uniform(0.3, 0.9),
            "code_sharer": random.uniform(0.1, 0.6),
            "reaction_tendency": random.uniform(0.3, 1.5),
        }

    # Generate employee signals
    employee_signals = {}
    for emp in employees:
        prof = emp_profiles[emp]
        base_msgs = int(random.gauss(80, 25) * prof["chattiness"])
        base_msgs = max(20, min(300, base_msgs))

        thread_starts = int(base_msgs * random.uniform(0.15, 0.35))
        thread_replies = int(base_msgs * prof["thread_tendency"] * random.uniform(0.3, 0.6))
        threads_engaged = int(thread_starts * random.uniform(0.5, 0.9))

        tasks_requested = int(base_msgs * random.uniform(0.05, 0.15))
        tasks_completed = int(tasks_requested * prof["task_completer"] * random.uniform(0.6, 1.2))
        blockers = int(base_msgs * prof["help_seeker"] * random.uniform(0.03, 0.1))
        reviews = int(base_msgs * prof["reviewer"] * random.uniform(0.05, 0.12))
        escalations = int(blockers * random.uniform(0.1, 0.4))
        help_seeking = blockers + int(random.uniform(0, 3) * prof["help_seeker"])

        mentions_sent = int(base_msgs * random.uniform(0.1, 0.3))
        mentions_received = int(base_msgs * random.uniform(0.08, 0.25))
        ack_reactions = int(base_msgs * prof["reaction_tendency"] * random.uniform(0.05, 0.2))
        completion_reactions = int(tasks_completed * random.uniform(0.3, 0.8))

        jira_refs = random.sample(emp_jira_ids.get(emp, []),
                                  min(int(base_msgs * 0.15), len(emp_jira_ids.get(emp, []))))
        pr_refs = [str(random.randint(100, 999)) for _ in range(int(reviews * random.uniform(0.5, 1.5)))]

        peak_hours = random.sample(range(9, 18), 3)
        peak_hours.sort()

        ch_dist = {}
        for ch_name, ch_type in channels:
            if random.random() < 0.7:
                ch_dist[ch_type] = ch_dist.get(ch_type, 0) + random.randint(3, 20)

        demand = round((mentions_received * 2.0 + blockers * 3.0 +
                        escalations * 4.0 + help_seeking * 1.5) / max(base_msgs, 1), 2)
        throughput = round((tasks_completed * 3.0 + completion_reactions * 2.0 +
                           len(pr_refs) * 2.5 + len(jira_refs) * 1.5) / max(base_msgs, 1), 2)
        collaboration = round((thread_replies * 1.0 + mentions_sent * 0.5 +
                               int(base_msgs * prof["code_sharer"]) * 2.0 +
                               reviews * 1.5 + threads_engaged * 1.0 +
                               len(ch_dist) * 0.5) / max(base_msgs, 1), 2)

        employee_signals[emp] = {
            "slack_user_id": f"U{random.randint(10000000, 99999999)}",
            "message_count": base_msgs,
            "thread_starts": thread_starts,
            "thread_replies": thread_replies,
            "threads_with_engagement": threads_engaged,
            "avg_message_length": int(random.gauss(120, 40)),
            "code_blocks_shared": int(base_msgs * prof["code_sharer"]),
            "attachments_shared": random.randint(1, 10),
            "tasks_requested_of_others": tasks_requested,
            "tasks_completed_announced": tasks_completed,
            "blockers_raised": blockers,
            "reviews_requested": reviews,
            "escalations": escalations,
            "help_seeking_count": help_seeking,
            "mentions_sent": mentions_sent,
            "mentions_received": mentions_received,
            "mention_ratio": round(mentions_received / max(mentions_sent, 1), 2),
            "ack_reactions_received": ack_reactions,
            "completion_reactions_received": completion_reactions,
            "jira_tickets_referenced": jira_refs,
            "jira_reference_count": len(jira_refs),
            "pr_references": pr_refs,
            "pr_reference_count": len(pr_refs),
            "avg_thread_depth": round(random.uniform(1.5, 5.0), 1),
            "peak_hours": [{"hour": h, "count": random.randint(8, 25)} for h in peak_hours],
            "channel_type_distribution": ch_dist,
            "demand_score": demand,
            "throughput_score": throughput,
            "collaboration_score": collaboration,
        }

    # Generate channel signals
    channel_signals = []
    for ch_name, ch_type in channels:
        tmpl = SLACK_CHANNEL_TEMPLATES.get(ch_type, SLACK_CHANNEL_TEMPLATES["general"])
        mpd_lo, mpd_hi = tmpl["msgs_per_day"]
        msgs_per_day = random.uniform(mpd_lo, mpd_hi)
        total_msgs = int(msgs_per_day * 14)
        unique_users = min(len(employees), max(3, int(total_msgs * random.uniform(0.03, 0.08))))
        task_requests = int(total_msgs * tmpl["task_ratio"] * random.uniform(0.7, 1.3))
        completions = int(task_requests * random.uniform(0.5, 1.1))
        blockers = int(total_msgs * tmpl["blocker_ratio"] * random.uniform(0.7, 1.3))
        reviews = int(total_msgs * random.uniform(0.05, 0.15))
        escalations = int(blockers * random.uniform(0.1, 0.3))
        threads = int(total_msgs * random.uniform(0.2, 0.5))
        thread_replies = int(threads * random.uniform(1.5, 4.0))
        code_ratio = random.uniform(0.05, 0.25) if ch_type in ("engineering", "review") else random.uniform(0.01, 0.08)

        channel_signals.append({
            "channel_name": ch_name,
            "channel_type": ch_type,
            "total_messages": total_msgs,
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
            "code_message_ratio": round(code_ratio, 2),
            "task_completion_ratio": round(completions / max(task_requests, 1), 2),
            "blocker_rate": round(blockers / max(total_msgs, 1), 3),
            "escalation_rate": round(escalations / max(total_msgs, 1), 3),
        })

    # Detect workflow patterns from the generated data
    total_task_req = sum(e["tasks_requested_of_others"] for e in employee_signals.values())
    total_jira_ref = sum(e["jira_reference_count"] for e in employee_signals.values())
    total_mentions = sum(e["mentions_sent"] for e in employee_signals.values())
    total_completions = sum(e["tasks_completed_announced"] for e in employee_signals.values())
    total_pr_ref = sum(e["pr_reference_count"] for e in employee_signals.values())

    if total_jira_ref > total_task_req * 2:
        task_acq = "ticket-driven"
    elif total_task_req > total_mentions * 0.3:
        task_acq = "request-driven"
    else:
        task_acq = "mixed"

    if total_pr_ref > total_completions:
        comp_track = "pr-driven"
    else:
        comp_track = "announcement-driven"

    demand_scores = [e["demand_score"] for e in employee_signals.values()]
    avg_demand = sum(demand_scores) / len(demand_scores)
    max_demand = max(demand_scores)
    if max_demand > avg_demand * 3:
        wl_dist = "highly-uneven"
    elif max_demand > avg_demand * 1.8:
        wl_dist = "somewhat-uneven"
    else:
        wl_dist = "balanced"

    overloaded = sorted(employee_signals.items(), key=lambda x: -x[1]["demand_score"])[:3]

    workflow_patterns = {
        "task_acquisition": task_acq,
        "completion_tracking": comp_track,
        "review_culture": "active-inline",
        "help_seeking": "distributed",
        "workload_distribution": wl_dist,
        "observations": [
            f"Team primarily uses {task_acq} task acquisition pattern",
            f"Completions tracked via {comp_track} approach",
            f"Workload distribution is {wl_dist}",
            f"Highest demand: {overloaded[0][0]} (score: {overloaded[0][1]['demand_score']})",
        ],
    }

    return {
        "metadata": {
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "days_scanned": 14,
            "channels_scanned": len(channels),
            "total_messages_analyzed": sum(c["total_messages"] for c in channel_signals),
            "employees_detected": len(employee_signals),
            "simulated": True,
        },
        "employee_signals": employee_signals,
        "channel_signals": channel_signals,
        "workflow_patterns": workflow_patterns,
    }


if __name__ == "__main__":
    main()
