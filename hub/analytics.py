#!/usr/bin/env python3
"""
Analytics: classify tasks by topic, build per-topic benchmarks,
compare individuals against the general average, detect team-wide
blind spots, enrich with Jira data, visualise, and report.

Key concepts:
  - RELATIVE deviation: individual vs topic average (existing)
  - ABSOLUTE difficulty: per-topic error rate, retry rate, failure density
  - TEAM BLIND SPOTS: topics where the absolute difficulty is high for
    EVERYONE — the "best" person isn't skilled, just least bad
  - JIRA ENRICHMENT: reopen counts, time-in-status from Jira tickets
"""

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import subprocess
import numpy as np
import pandas as pd

from presets import get_active_preset
from model_baselines import normalize_tokens, resolve_model, get_baseline, MODEL_BASELINES
from pm_provider import load_all_tickets, normalize_status

DATA_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "data", "task_data.jsonl")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "output")


def _build_topic_keywords() -> dict[str, set[str]]:
    preset = get_active_preset()
    return {topic: set(cfg["keywords"]) for topic, cfg in preset["topics"].items()}


TOPIC_KEYWORDS: dict[str, set[str]] = _build_topic_keywords()

STRUGGLE_THRESHOLD = 1.35
TEAM_BLIND_SPOT_THRESHOLD = 1.3


# ---------------------------------------------------------------------------
# 1. Load
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    records = []
    with open(DATA_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    df = pd.DataFrame(records)
    df["start_time"] = pd.to_datetime(df["start_time"], format="ISO8601")
    df["end_time"] = pd.to_datetime(df["end_time"], format="ISO8601")
    df["duration_minutes"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 60

    for col in ["error_count", "retry_count", "tool_call_count"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = df[col].fillna(0).astype(int)

    if "model" not in df.columns:
        df["model"] = "unknown"
    df["model"] = df["model"].fillna("unknown")

    df["normalized_tokens"] = df.apply(
        lambda row: normalize_tokens(row["token_usage"], row["model"]), axis=1)

    return df


def load_jira_tickets() -> dict:
    """Load tickets from all configured PM providers (Jira, Notion, etc.)."""
    return load_all_tickets()


def enrich_with_jira(df: pd.DataFrame, tickets: dict) -> pd.DataFrame:
    reopen_counts = []
    jira_statuses = []
    time_in_progress = []

    for _, row in df.iterrows():
        ticket = tickets.get(row.get("jira_id", ""), {})
        reopen_counts.append(ticket.get("reopen_count", 0))
        jira_statuses.append(ticket.get("status", ""))
        tip = ticket.get("time_in_status", {})
        ip_hours = tip.get("In Progress", 0) or tip.get("in_progress", 0)
        time_in_progress.append(ip_hours)

    df["jira_reopen_count"] = reopen_counts
    df["jira_status"] = jira_statuses
    df["jira_time_in_progress"] = time_in_progress
    return df


# ---------------------------------------------------------------------------
# 2. Classify by topic
# ---------------------------------------------------------------------------

def classify_topic(keywords: list[str]) -> str:
    kw_set = set(keywords)
    best_topic, best_score = "Unknown", 0
    for topic, pool in TOPIC_KEYWORDS.items():
        score = len(kw_set & pool)
        if score > best_score:
            best_topic, best_score = topic, score
    return best_topic


# ---------------------------------------------------------------------------
# 3. Build per-topic benchmark (with failure metrics)
# ---------------------------------------------------------------------------

def build_benchmarks(df: pd.DataFrame) -> pd.DataFrame:
    bench = df.groupby("topic").agg(
        avg_duration=("duration_minutes", "mean"),
        med_duration=("duration_minutes", "median"),
        std_duration=("duration_minutes", "std"),
        avg_tokens=("token_usage", "mean"),
        med_tokens=("token_usage", "median"),
        std_tokens=("token_usage", "std"),
        avg_norm_tokens=("normalized_tokens", "mean"),
        med_norm_tokens=("normalized_tokens", "median"),
        std_norm_tokens=("normalized_tokens", "std"),
        avg_errors=("error_count", "mean"),
        avg_retries=("retry_count", "mean"),
        avg_reopens=("jira_reopen_count", "mean"),
        count=("topic", "size"),
    ).reset_index()
    return bench


# ---------------------------------------------------------------------------
# 4. Absolute difficulty scoring (team-wide blind spot detection)
# ---------------------------------------------------------------------------

def compute_difficulty_scores(bench: pd.DataFrame) -> pd.DataFrame:
    """Compute a normalized difficulty score per topic.

    Combines: avg duration, avg tokens, avg errors, avg retries, avg reopens.
    Each metric is z-scored across topics, then summed into a composite.
    Topics with high composite = hard for EVERYONE.
    """
    metrics = ["avg_duration", "avg_norm_tokens", "avg_errors", "avg_retries", "avg_reopens"]
    for m in metrics:
        mean = bench[m].mean()
        std = bench[m].std()
        bench[f"{m}_z"] = (bench[m] - mean) / std if std > 0 else 0

    z_cols = [f"{m}_z" for m in metrics]
    bench["difficulty_score"] = bench[z_cols].sum(axis=1)

    global_mean = bench["difficulty_score"].mean()
    global_std = bench["difficulty_score"].std()
    if global_std > 0:
        bench["is_team_blind_spot"] = bench["difficulty_score"] > (global_mean + global_std * 0.5)
    else:
        bench["is_team_blind_spot"] = False

    return bench


# ---------------------------------------------------------------------------
# 5. Individual vs benchmark (enhanced)
# ---------------------------------------------------------------------------

def compare_individuals(df: pd.DataFrame, bench: pd.DataFrame) -> pd.DataFrame:
    ind = df.groupby(["employee", "topic"]).agg(
        ind_avg_duration=("duration_minutes", "mean"),
        ind_avg_tokens=("token_usage", "mean"),
        ind_avg_norm_tokens=("normalized_tokens", "mean"),
        ind_avg_errors=("error_count", "mean"),
        ind_avg_retries=("retry_count", "mean"),
        ind_avg_reopens=("jira_reopen_count", "mean"),
        task_count=("topic", "size"),
    ).reset_index()

    ind = ind.merge(bench[["topic", "avg_duration", "avg_tokens", "avg_norm_tokens",
                            "avg_errors", "avg_retries", "avg_reopens",
                            "difficulty_score", "is_team_blind_spot"]], on="topic")
    ind["duration_ratio"] = ind["ind_avg_duration"] / ind["avg_duration"]
    ind["token_ratio"] = ind["ind_avg_norm_tokens"] / ind["avg_norm_tokens"]
    ind["error_ratio"] = ind["ind_avg_errors"] / ind["avg_errors"].replace(0, 1)
    ind["flagged"] = (ind["duration_ratio"] >= STRUGGLE_THRESHOLD) | (ind["token_ratio"] >= STRUGGLE_THRESHOLD)

    ind["assessment"] = "Normal"
    for idx, row in ind.iterrows():
        if row["is_team_blind_spot"]:
            if row["flagged"]:
                ind.at[idx, "assessment"] = "Struggling (team-wide weak topic)"
            elif row["duration_ratio"] <= 1.1 and row["token_ratio"] <= 1.1:
                ind.at[idx, "assessment"] = "Least bad (NOT skilled — team-wide gap)"
            else:
                ind.at[idx, "assessment"] = "Average (team-wide weak topic)"
        else:
            if row["flagged"]:
                ind.at[idx, "assessment"] = "Individual struggle"
            elif row["duration_ratio"] <= 0.85 and row["token_ratio"] <= 0.85:
                ind.at[idx, "assessment"] = "Genuinely skilled"

    return ind


# ---------------------------------------------------------------------------
# 6. Visualise
# ---------------------------------------------------------------------------

def plot_topic_distributions(df: pd.DataFrame) -> list[str]:
    files = []
    topics = sorted(df["topic"].unique())

    fig, axes = plt.subplots(2, 1, figsize=(16, 10))
    data_dur = [df[df["topic"] == t]["duration_minutes"].values for t in topics]
    data_tok = [df[df["topic"] == t]["token_usage"].values for t in topics]
    axes[0].boxplot(data_dur, tick_labels=topics, vert=True)
    axes[0].set_title("Duration (minutes) by Topic", fontsize=13)
    axes[0].set_ylabel("Minutes")
    axes[0].tick_params(axis="x", rotation=35, labelsize=8)
    axes[1].boxplot(data_tok, tick_labels=topics, vert=True)
    axes[1].set_title("Token Usage by Topic", fontsize=13)
    axes[1].set_ylabel("Tokens")
    axes[1].tick_params(axis="x", rotation=35, labelsize=8)
    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, "topic_distributions.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    files.append(path)
    return files


def plot_employee_vs_benchmark(ind: pd.DataFrame, bench: pd.DataFrame) -> list[str]:
    files = []
    topics = sorted(ind["topic"].unique())
    employees = sorted(ind["employee"].unique())

    for topic in topics:
        t_bench = bench[bench["topic"] == topic].iloc[0]
        t_ind = ind[ind["topic"] == topic].set_index("employee")

        present = [e for e in employees if e in t_ind.index]
        if not present:
            continue

        x = np.arange(len(present))
        width = 0.35

        fig, axes = plt.subplots(1, 2, figsize=(max(14, len(present) * 0.8), 6))
        for ax, metric, bench_val, ind_col, label in [
            (axes[0], "Duration (min)", t_bench["avg_duration"], "ind_avg_duration", "Avg Duration"),
            (axes[1], "Tokens", t_bench["avg_tokens"], "ind_avg_tokens", "Avg Tokens"),
        ]:
            vals = [t_ind.loc[e, ind_col] for e in present]
            ax.bar(x - width / 2, vals, width, label="Individual", color="#5b9bd5")
            ax.bar(x + width / 2, [bench_val] * len(present), width,
                   label="Topic Avg", alpha=0.6, color="#a0a0a0")
            ax.set_xticks(x)
            ax.set_xticklabels([n.split()[-1] for n in present], rotation=35, ha="right", fontsize=8)
            ax.set_ylabel(metric)
            ax.set_title(f"{topic} — {label}", fontsize=11)
            ax.legend(fontsize=7)

            for i, v in enumerate(vals):
                if v > bench_val * STRUGGLE_THRESHOLD:
                    ax.annotate("!", (i - width / 2, v), ha="center",
                                fontsize=13, color="red", fontweight="bold")

        fig.tight_layout()
        safe = topic.replace("/", "-").replace(" & ", "-").replace(" ", "-")
        path = os.path.join(OUTPUT_DIR, f"employee_vs_avg_{safe}.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        files.append(path)

    return files


def plot_heatmap(ind: pd.DataFrame, bench: pd.DataFrame) -> str:
    topics = sorted(ind["topic"].unique())
    employees = sorted(ind["employee"].unique())

    matrix = np.ones((len(employees), len(topics)))
    for _, row in ind.iterrows():
        ei = employees.index(row["employee"])
        ti = topics.index(row["topic"])
        matrix[ei, ti] = max(row["duration_ratio"], row["token_ratio"])

    blind_spot_cols = []
    for ti, topic in enumerate(topics):
        row = bench[bench["topic"] == topic]
        if not row.empty and row.iloc[0].get("is_team_blind_spot", False):
            blind_spot_cols.append(ti)

    fig, ax = plt.subplots(figsize=(18, 10))
    im = ax.imshow(matrix, cmap="RdYlGn_r", aspect="auto", vmin=0.5, vmax=2.5)
    ax.set_xticks(range(len(topics)))
    xlabels = []
    for ti, topic in enumerate(topics):
        label = topic
        if ti in blind_spot_cols:
            label = f"** {topic} **"
        xlabels.append(label)
    ax.set_xticklabels(xlabels, rotation=40, ha="right", fontsize=11, fontweight="bold")
    ax.set_yticks(range(len(employees)))
    ax.set_yticklabels(employees, fontsize=11, fontweight="bold")
    company = get_active_preset()["company"]
    ax.set_title(f"{company} — Employee x Topic Deviation  (** = Team Blind Spot)", fontsize=13, pad=12)

    for ei in range(len(employees)):
        for ti in range(len(topics)):
            val = matrix[ei, ti]
            ax.text(ti, ei, f"{val:.1f}x", ha="center", va="center", fontsize=7,
                    color="white" if val > 1.8 else "black")

    for ti in blind_spot_cols:
        ax.axvline(x=ti - 0.5, color="#ff6b6b", linewidth=2, linestyle="--", alpha=0.7)
        ax.axvline(x=ti + 0.5, color="#ff6b6b", linewidth=2, linestyle="--", alpha=0.7)

    fig.colorbar(im, ax=ax, label="Max(duration ratio, token ratio)", shrink=0.7)
    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, "heatmap_employee_topic.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_difficulty_scores(bench: pd.DataFrame) -> str:
    bench_sorted = bench.sort_values("difficulty_score", ascending=True)
    topics = bench_sorted["topic"].tolist()
    scores = bench_sorted["difficulty_score"].tolist()
    is_blind = bench_sorted["is_team_blind_spot"].tolist()

    colors = ["#d9534f" if b else "#5bc0de" for b in is_blind]

    fig, ax = plt.subplots(figsize=(12, max(4, len(topics) * 0.45)))
    bars = ax.barh(topics, scores, color=colors)
    ax.axvline(x=0, color="gray", linewidth=0.5)
    ax.set_xlabel("Difficulty Score (composite z-score)")
    ax.set_title("Absolute Topic Difficulty — Red = Team Blind Spot", fontsize=13)

    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor="#d9534f", label="Team blind spot"),
                       Patch(facecolor="#5bc0de", label="Normal difficulty")]
    ax.legend(handles=legend_elements, fontsize=8)

    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, "topic_difficulty.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_error_heatmap(df: pd.DataFrame) -> str:
    topics = sorted(df["topic"].unique())
    employees = sorted(df["employee"].unique())

    matrix = np.zeros((len(employees), len(topics)))
    for _, row in df.groupby(["employee", "topic"]).agg(
        avg_errors=("error_count", "mean")).reset_index().iterrows():
        ei = employees.index(row["employee"])
        ti = topics.index(row["topic"])
        matrix[ei, ti] = row["avg_errors"]

    fig, ax = plt.subplots(figsize=(18, 10))
    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto", vmin=0)
    ax.set_xticks(range(len(topics)))
    ax.set_xticklabels(topics, rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(employees)))
    ax.set_yticklabels(employees, fontsize=8)
    company = get_active_preset()["company"]
    ax.set_title(f"{company} — Avg Errors per Task (Employee x Topic)", fontsize=13, pad=12)

    for ei in range(len(employees)):
        for ti in range(len(topics)):
            val = matrix[ei, ti]
            if val > 0:
                ax.text(ti, ei, f"{val:.1f}", ha="center", va="center", fontsize=7,
                        color="white" if val > 5 else "black")

    fig.colorbar(im, ax=ax, label="Avg errors per task", shrink=0.7)
    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, "error_heatmap.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_flagged_summary(ind: pd.DataFrame) -> str:
    flagged = ind[ind["flagged"]].copy()
    if flagged.empty:
        return ""
    flagged["max_ratio"] = flagged[["duration_ratio", "token_ratio"]].max(axis=1)
    flagged = flagged.sort_values("max_ratio", ascending=True)
    flagged["label"] = flagged["employee"] + " / " + flagged["topic"]

    fig, ax = plt.subplots(figsize=(12, max(4, len(flagged) * 0.4)))
    colors = []
    for _, row in flagged.iterrows():
        if row["is_team_blind_spot"]:
            colors.append("#9b59b6")
        elif row["max_ratio"] >= 2.0:
            colors.append("#d9534f")
        elif row["max_ratio"] >= 1.5:
            colors.append("#f0ad4e")
        else:
            colors.append("#5bc0de")
    ax.barh(flagged["label"], flagged["max_ratio"], color=colors)
    ax.axvline(x=1.0, color="green", linestyle="--", linewidth=1, label="General avg (1.0x)")
    ax.axvline(x=STRUGGLE_THRESHOLD, color="orange", linestyle="--", linewidth=1,
               label=f"Flag threshold ({STRUGGLE_THRESHOLD}x)")
    ax.set_xlabel("Ratio to General Topic Average")
    ax.set_title("Flagged Employee / Topic Combinations", fontsize=13)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#d9534f", label="Notable outlier (>=2.0x)"),
        Patch(facecolor="#f0ad4e", label="Moderate (1.5-2.0x)"),
        Patch(facecolor="#5bc0de", label="Emerging (1.35-1.5x)"),
        Patch(facecolor="#9b59b6", label="Team blind spot topic"),
    ]
    ax.legend(handles=legend_elements, fontsize=8)
    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, "flagged_summary.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# 7. Report
# ---------------------------------------------------------------------------

def write_report(bench: pd.DataFrame, ind: pd.DataFrame) -> str:
    lines = [
        "=" * 70,
        f"{get_active_preset()['company'].upper()} — TASK ANALYTICS SUMMARY REPORT",
        "=" * 70, "",
    ]

    # ── Team blind spots ──
    blind_spots = bench[bench["is_team_blind_spot"]].sort_values("difficulty_score", ascending=False)
    if not blind_spots.empty:
        lines.append("TEAM-WIDE BLIND SPOTS")
        lines.append("-" * 70)
        lines.append("  Topics where the ENTIRE team underperforms. The 'best' person")
        lines.append("  in these areas is NOT necessarily skilled — they're just least bad.")
        lines.append("  These require org-level investment (training, hiring, tooling).")
        lines.append("")
        for _, row in blind_spots.iterrows():
            lines.append(f"  !! {row['topic']}  (difficulty score: {row['difficulty_score']:.2f})")
            lines.append(f"     Avg duration: {row['avg_duration']:.1f} min | "
                          f"Avg tokens: {row['avg_tokens']:.0f} | "
                          f"Avg errors/task: {row['avg_errors']:.1f} | "
                          f"Avg retries: {row['avg_retries']:.1f} | "
                          f"Avg Jira reopens: {row['avg_reopens']:.1f}")
            least_bad = ind[(ind["topic"] == row["topic"]) &
                            (ind["assessment"] == "Least bad (NOT skilled — team-wide gap)")]
            if not least_bad.empty:
                names = ", ".join(least_bad["employee"].tolist()[:5])
                lines.append(f"     'Least bad' (NOT ideal collaborators): {names}")
            lines.append("")

    # ── General benchmarks ──
    lines.append("GENERAL BENCHMARKS (per topic, all employees)")
    lines.append("-" * 70)
    for _, row in bench.sort_values("topic").iterrows():
        blind_tag = " [BLIND SPOT]" if row.get("is_team_blind_spot", False) else ""
        lines.append(f"\n  {row['topic']}{blind_tag}  ({int(row['count'])} tasks)")
        lines.append(f"    Duration  — avg: {row['avg_duration']:.1f} min, "
                      f"median: {row['med_duration']:.1f} min, std: {row['std_duration']:.1f}")
        lines.append(f"    Tokens    — avg: {row['avg_tokens']:.0f}, "
                      f"median: {row['med_tokens']:.0f}, std: {row['std_tokens']:.0f}")
        lines.append(f"    Norm. Tok — avg: {row['avg_norm_tokens']:.0f}, "
                      f"median: {row['med_norm_tokens']:.0f} (model-adjusted)")
        lines.append(f"    Errors    — avg: {row['avg_errors']:.1f}/task | "
                      f"Retries: {row['avg_retries']:.1f}/task | "
                      f"Jira reopens: {row['avg_reopens']:.1f}/ticket")

    # ── Individual flags ──
    flagged = ind[ind["flagged"]].copy()
    flagged["max_ratio"] = flagged[["duration_ratio", "token_ratio"]].max(axis=1)
    flagged = flagged.sort_values("max_ratio", ascending=False)

    lines += ["", "", "CANDIDATE AREAS FOR SUPPORT / KNOWLEDGE-SHARING", "-" * 70]

    if flagged.empty:
        lines.append("  No employee/topic combinations exceed the flagging threshold.")
    else:
        lines.append(f"  (Flagged when individual avg >= {STRUGGLE_THRESHOLD}x the topic avg)")
        lines.append("")

        obvious = flagged[flagged["max_ratio"] >= 1.8]
        subtle = flagged[flagged["max_ratio"] < 1.8]

        if not obvious.empty:
            lines.append("  NOTABLE OUTLIERS:")
            for _, row in obvious.iterrows():
                blind_tag = " [TEAM BLIND SPOT]" if row["is_team_blind_spot"] else ""
                lines.append(f"    {row['employee']} — {row['topic']}{blind_tag}")
                lines.append(f"      Assessment: {row['assessment']}")
                lines.append(f"      Duration: {row['ind_avg_duration']:.1f} min vs avg {row['avg_duration']:.1f} min "
                              f"({row['duration_ratio']:.2f}x)")
                lines.append(f"      Tokens (normalized): {row['ind_avg_norm_tokens']:.0f} vs avg {row['avg_norm_tokens']:.0f} "
                              f"({row['token_ratio']:.2f}x)")
                lines.append(f"      Errors:   {row['ind_avg_errors']:.1f}/task vs avg {row['avg_errors']:.1f} "
                              f"({row['error_ratio']:.2f}x)")
                lines.append("")

        if not subtle.empty:
            lines.append("  MODERATE / EMERGING PATTERNS:")
            for _, row in subtle.iterrows():
                blind_tag = " [TEAM BLIND SPOT]" if row["is_team_blind_spot"] else ""
                lines.append(f"    {row['employee']} — {row['topic']}{blind_tag}")
                lines.append(f"      Assessment: {row['assessment']}")
                lines.append(f"      Duration: {row['ind_avg_duration']:.1f} min vs avg {row['avg_duration']:.1f} min "
                              f"({row['duration_ratio']:.2f}x)")
                lines.append(f"      Tokens (normalized): {row['ind_avg_norm_tokens']:.0f} vs avg {row['avg_norm_tokens']:.0f} "
                              f"({row['token_ratio']:.2f}x)")
                lines.append("")

    # ── Genuinely skilled ──
    skilled = ind[ind["assessment"] == "Genuinely skilled"].copy()
    if not skilled.empty:
        lines += ["", "GENUINELY SKILLED (ideal collaborators / mentors)", "-" * 70]
        lines.append("  These individuals are measurably efficient in topics that are")
        lines.append("  NOT team-wide blind spots — their skill is real, not relative.")
        lines.append("")
        for _, row in skilled.sort_values(["topic", "employee"]).iterrows():
            lines.append(f"    {row['employee']} — {row['topic']}")
            lines.append(f"      Duration: {row['duration_ratio']:.2f}x avg | "
                          f"Tokens: {row['token_ratio']:.2f}x avg | "
                          f"Tasks: {row['task_count']}")

    lines.append("")
    lines.append("=" * 70)
    report = "\n".join(lines)

    path = os.path.join(OUTPUT_DIR, "summary_report.txt")
    with open(path, "w") as f:
        f.write(report)
    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Loading data...")
    df = load_data()
    print(f"  {len(df)} records loaded.")

    print("Loading Jira tickets...")
    tickets = load_jira_tickets()
    print(f"  {len(tickets)} tickets loaded.")
    df = enrich_with_jira(df, tickets)

    print("Classifying topics...")
    df["topic"] = df["keywords"].apply(classify_topic)

    print("Building benchmarks...")
    bench = build_benchmarks(df)

    print("Computing absolute difficulty scores...")
    bench = compute_difficulty_scores(bench)
    blind_spots = bench[bench["is_team_blind_spot"]]["topic"].tolist()
    if blind_spots:
        print(f"  Team blind spots detected: {', '.join(blind_spots)}")

    print("Comparing individuals to benchmarks...")
    ind = compare_individuals(df, bench)

    print("Generating charts...")
    chart_files = []
    chart_files += plot_topic_distributions(df)
    chart_files += plot_employee_vs_benchmark(ind, bench)
    chart_files.append(plot_heatmap(ind, bench))
    chart_files.append(plot_difficulty_scores(bench))
    chart_files.append(plot_error_heatmap(df))
    flagged_path = plot_flagged_summary(ind)
    if flagged_path:
        chart_files.append(flagged_path)

    print("Writing report...")
    report = write_report(bench, ind)

    print("\n" + report)
    print(f"\nCharts saved ({len(chart_files)} files):")
    for f in chart_files:
        print(f"  {os.path.basename(f)}")
    print(f"\nFull report: {os.path.join(OUTPUT_DIR, 'summary_report.txt')}")

    heatmap_path = os.path.join(OUTPUT_DIR, "heatmap_employee_topic.png")
    print("\nOpening heatmap...")
    subprocess.Popen(["open", heatmap_path])


if __name__ == "__main__":
    main()
