#!/usr/bin/env python3
"""
Model Baselines — public performance data for AI coding models.

Each model has:
  - tokens_per_task_baseline: median tokens a typical coding task consumes
    (derived from public benchmarks, pricing pages, and community reports)
  - output_verbosity: relative output length vs the reference model (1.0)
  - quality_factor: approximate SWE-bench / HumanEval pass rate normalized
    to [0, 1] — higher quality = fewer retries needed, so raw error counts
    from a weaker model shouldn't be compared 1:1 with a stronger one
  - cost_per_mtok: blended $/1M tokens (input+output avg) for cost context
  - context_window: max tokens the model can process

Normalization strategy:
  Raw tokens are converted to "normalized tokens" (NT) relative to a
  reference model. This lets us compare an engineer using GPT-4o (verbose,
  high quality) against one using Claude Haiku (terse, fast) fairly.

  NT = raw_tokens × (reference_verbosity / model_verbosity)
                   × (reference_quality / model_quality)

  This means:
  - A verbose model's tokens get scaled DOWN (they naturally use more)
  - A weaker model's tokens get scaled UP (they need more attempts)
  - The reference model's NT = raw tokens (identity transform)

The reference model is Claude Sonnet 4 (middle of the road in verbosity
and quality). All factors are relative to it.
"""

from __future__ import annotations

REFERENCE_MODEL = "claude-sonnet-4"

MODEL_BASELINES: dict[str, dict] = {
    # ── Anthropic ──
    "claude-opus-4": {
        "provider": "anthropic",
        "display_name": "Claude Opus 4",
        "tokens_per_task_baseline": 12000,
        "output_verbosity": 1.25,
        "quality_factor": 0.95,
        "cost_per_mtok": 37.50,
        "context_window": 200000,
    },
    "claude-sonnet-4": {
        "provider": "anthropic",
        "display_name": "Claude Sonnet 4",
        "tokens_per_task_baseline": 8500,
        "output_verbosity": 1.0,
        "quality_factor": 0.88,
        "cost_per_mtok": 9.00,
        "context_window": 200000,
    },
    "claude-haiku-4": {
        "provider": "anthropic",
        "display_name": "Claude Haiku 4",
        "tokens_per_task_baseline": 5000,
        "output_verbosity": 0.7,
        "quality_factor": 0.72,
        "cost_per_mtok": 2.00,
        "context_window": 200000,
    },

    # ── OpenAI ──
    "gpt-4o": {
        "provider": "openai",
        "display_name": "GPT-4o",
        "tokens_per_task_baseline": 9500,
        "output_verbosity": 1.15,
        "quality_factor": 0.86,
        "cost_per_mtok": 8.75,
        "context_window": 128000,
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "display_name": "GPT-4o Mini",
        "tokens_per_task_baseline": 5500,
        "output_verbosity": 0.75,
        "quality_factor": 0.68,
        "cost_per_mtok": 0.60,
        "context_window": 128000,
    },
    "o3": {
        "provider": "openai",
        "display_name": "o3",
        "tokens_per_task_baseline": 18000,
        "output_verbosity": 1.6,
        "quality_factor": 0.96,
        "cost_per_mtok": 30.00,
        "context_window": 200000,
    },
    "o4-mini": {
        "provider": "openai",
        "display_name": "o4-mini",
        "tokens_per_task_baseline": 10000,
        "output_verbosity": 1.1,
        "quality_factor": 0.90,
        "cost_per_mtok": 4.40,
        "context_window": 200000,
    },
    "codex-mini": {
        "provider": "openai",
        "display_name": "Codex Mini",
        "tokens_per_task_baseline": 7000,
        "output_verbosity": 0.85,
        "quality_factor": 0.82,
        "cost_per_mtok": 3.75,
        "context_window": 200000,
    },

    # ── Google ──
    "gemini-2.5-pro": {
        "provider": "google",
        "display_name": "Gemini 2.5 Pro",
        "tokens_per_task_baseline": 11000,
        "output_verbosity": 1.3,
        "quality_factor": 0.89,
        "cost_per_mtok": 7.50,
        "context_window": 1000000,
    },
    "gemini-2.5-flash": {
        "provider": "google",
        "display_name": "Gemini 2.5 Flash",
        "tokens_per_task_baseline": 6500,
        "output_verbosity": 0.8,
        "quality_factor": 0.78,
        "cost_per_mtok": 0.75,
        "context_window": 1000000,
    },

    # ── Open source / local ──
    "llama-3.3-70b": {
        "provider": "meta",
        "display_name": "Llama 3.3 70B",
        "tokens_per_task_baseline": 8000,
        "output_verbosity": 0.95,
        "quality_factor": 0.75,
        "cost_per_mtok": 0.80,
        "context_window": 128000,
    },
    "deepseek-v3": {
        "provider": "deepseek",
        "display_name": "DeepSeek V3",
        "tokens_per_task_baseline": 9000,
        "output_verbosity": 1.05,
        "quality_factor": 0.83,
        "cost_per_mtok": 1.10,
        "context_window": 128000,
    },
    "deepseek-r1": {
        "provider": "deepseek",
        "display_name": "DeepSeek R1",
        "tokens_per_task_baseline": 15000,
        "output_verbosity": 1.5,
        "quality_factor": 0.91,
        "cost_per_mtok": 4.40,
        "context_window": 128000,
    },
    "qwen-3-235b": {
        "provider": "alibaba",
        "display_name": "Qwen 3 235B",
        "tokens_per_task_baseline": 10000,
        "output_verbosity": 1.1,
        "quality_factor": 0.84,
        "cost_per_mtok": 1.60,
        "context_window": 128000,
    },

    # ── Coding assistants (composite — these use models internally) ──
    "github-copilot": {
        "provider": "github",
        "display_name": "GitHub Copilot",
        "tokens_per_task_baseline": 4000,
        "output_verbosity": 0.55,
        "quality_factor": 0.70,
        "cost_per_mtok": 3.00,
        "context_window": 64000,
    },
    "cursor-default": {
        "provider": "cursor",
        "display_name": "Cursor (default model)",
        "tokens_per_task_baseline": 8000,
        "output_verbosity": 1.0,
        "quality_factor": 0.85,
        "cost_per_mtok": 6.00,
        "context_window": 128000,
    },
    "windsurf-default": {
        "provider": "codeium",
        "display_name": "Windsurf (default)",
        "tokens_per_task_baseline": 7500,
        "output_verbosity": 0.9,
        "quality_factor": 0.80,
        "cost_per_mtok": 5.00,
        "context_window": 128000,
    },
    "aider-default": {
        "provider": "aider",
        "display_name": "Aider (default)",
        "tokens_per_task_baseline": 9000,
        "output_verbosity": 1.05,
        "quality_factor": 0.82,
        "cost_per_mtok": 5.00,
        "context_window": 128000,
    },
}

# Alias mapping: common variations → canonical model ID
MODEL_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4",
    "claude-opus": "claude-opus-4",
    "claude opus": "claude-opus-4",
    "sonnet": "claude-sonnet-4",
    "claude-sonnet": "claude-sonnet-4",
    "claude sonnet": "claude-sonnet-4",
    "haiku": "claude-haiku-4",
    "claude-haiku": "claude-haiku-4",
    "claude haiku": "claude-haiku-4",
    "gpt4o": "gpt-4o",
    "gpt-4-o": "gpt-4o",
    "4o": "gpt-4o",
    "4o-mini": "gpt-4o-mini",
    "gpt4o-mini": "gpt-4o-mini",
    "o3": "o3",
    "o4-mini": "o4-mini",
    "codex": "codex-mini",
    "gemini-pro": "gemini-2.5-pro",
    "gemini pro": "gemini-2.5-pro",
    "gemini-flash": "gemini-2.5-flash",
    "gemini flash": "gemini-2.5-flash",
    "llama": "llama-3.3-70b",
    "llama3": "llama-3.3-70b",
    "deepseek": "deepseek-v3",
    "deepseek-coder": "deepseek-v3",
    "deepseek-r1": "deepseek-r1",
    "r1": "deepseek-r1",
    "qwen": "qwen-3-235b",
    "copilot": "github-copilot",
    "gh-copilot": "github-copilot",
    "cursor": "cursor-default",
    "windsurf": "windsurf-default",
    "aider": "aider-default",
    "none": "unknown",
    "unknown": "unknown",
    "git-tracker": "unknown",
}

# Fallback for unrecognized models — uses reference model characteristics
MODEL_BASELINES["unknown"] = {
    "provider": "unknown",
    "display_name": "Unknown Model",
    "tokens_per_task_baseline": MODEL_BASELINES[REFERENCE_MODEL]["tokens_per_task_baseline"],
    "output_verbosity": 1.0,
    "quality_factor": 0.80,
    "cost_per_mtok": 5.00,
    "context_window": 128000,
}


def resolve_model(model_str: str) -> str:
    """Resolve a model string to a canonical model ID."""
    if not model_str:
        return "unknown"
    lower = model_str.lower().strip()
    if lower in MODEL_BASELINES:
        return lower
    if lower in MODEL_ALIASES:
        return MODEL_ALIASES[lower]
    for alias, canonical in MODEL_ALIASES.items():
        if alias in lower:
            return canonical
    return "unknown"


def get_baseline(model_id: str) -> dict:
    """Get baseline data for a model, falling back to unknown."""
    canonical = resolve_model(model_id)
    return MODEL_BASELINES.get(canonical, MODEL_BASELINES["unknown"])


def normalize_tokens(raw_tokens: float, model_id: str) -> float:
    """Convert raw token count to normalized tokens (NT).

    NT adjusts for model verbosity and quality so cross-model
    comparisons are fair. The reference model (Claude Sonnet 4)
    maps 1:1 — its NT equals its raw tokens.

    Formula:
      NT = raw × (ref_verbosity / model_verbosity)
             × (ref_quality / model_quality)

    Verbose models get scaled down (they naturally produce more tokens).
    Weaker models get scaled up (more tokens spent on retries/mistakes).
    """
    ref = MODEL_BASELINES[REFERENCE_MODEL]
    model = get_baseline(model_id)

    verbosity_adjustment = ref["output_verbosity"] / model["output_verbosity"]
    quality_adjustment = ref["quality_factor"] / model["quality_factor"]

    return raw_tokens * verbosity_adjustment * quality_adjustment


def compute_efficiency_score(raw_tokens: float, duration_minutes: float,
                             error_count: int, model_id: str) -> float:
    """Compute a model-aware efficiency score (0-100).

    Higher = more efficient. Factors:
      - Normalized tokens per minute (lower is better)
      - Error rate adjusted for model quality (weaker models get slack)
      - Baseline comparison (how does this compare to the model's expected output)
    """
    model = get_baseline(model_id)
    nt = normalize_tokens(raw_tokens, model_id)
    baseline = model["tokens_per_task_baseline"]

    token_efficiency = min(2.0, baseline / max(1, nt))

    quality_adjusted_errors = error_count * (model["quality_factor"] / 0.88)
    error_penalty = max(0, 1 - (quality_adjusted_errors * 0.05))

    duration_factor = max(0.3, min(1.5, 30 / max(1, duration_minutes)))

    raw_score = (token_efficiency * 0.4 + error_penalty * 0.35 + duration_factor * 0.25) * 100
    return round(min(100, max(0, raw_score)), 1)


def get_model_summary() -> str:
    """Print a summary table of all registered models."""
    ref = MODEL_BASELINES[REFERENCE_MODEL]
    lines = [
        f"{'Model':<25} {'Provider':<12} {'Verbosity':>10} {'Quality':>8} "
        f"{'Baseline':>10} {'$/1M tok':>10} {'NT Factor':>10}",
        "-" * 95,
    ]
    for model_id, data in sorted(MODEL_BASELINES.items()):
        if model_id == "unknown":
            continue
        v_adj = ref["output_verbosity"] / data["output_verbosity"]
        q_adj = ref["quality_factor"] / data["quality_factor"]
        nt_factor = v_adj * q_adj
        lines.append(
            f"{data['display_name']:<25} {data['provider']:<12} "
            f"{data['output_verbosity']:>10.2f} {data['quality_factor']:>8.2f} "
            f"{data['tokens_per_task_baseline']:>10,} {data['cost_per_mtok']:>10.2f} "
            f"{nt_factor:>10.3f}"
        )
    lines.append("")
    lines.append(f"Reference model: {MODEL_BASELINES[REFERENCE_MODEL]['display_name']}")
    lines.append(f"NT Factor = how much raw tokens are scaled. "
                 f"<1 = model naturally uses more, >1 = model uses less")
    return "\n".join(lines)


if __name__ == "__main__":
    print(get_model_summary())
    print()
    print("Normalization examples:")
    test_cases = [
        ("claude-opus-4", 15000),
        ("claude-sonnet-4", 8500),
        ("claude-haiku-4", 4000),
        ("gpt-4o", 10000),
        ("o3", 20000),
        ("github-copilot", 3000),
        ("deepseek-r1", 16000),
    ]
    for model, raw in test_cases:
        nt = normalize_tokens(raw, model)
        display = MODEL_BASELINES[model]["display_name"]
        print(f"  {display:<25} {raw:>8,} raw → {nt:>10,.0f} NT")
