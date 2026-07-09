# Valon AI — Task Analytics Dashboard

AI-powered team analytics platform that tracks coding sessions, benchmarks
performance by topic, detects team blind spots, and generates actionable
improvement plans. Built for LAN deployment with zero-config collector
auto-discovery.

## Repo Structure

```
hub/            ← Leader/manager installs this on their machine
collector/      ← Engineers install this on their laptops
demo/           ← Demo-only: fake data generators + preset switcher
```

### Who downloads what

| Role | What to install | Directory |
|------|----------------|-----------|
| **Team lead / manager** | Dashboard, analytics, receiver, AI advisor | `hub/` |
| **Engineers / developers** | Collector agent (runs silently in background) | `collector/` |
| **Demo / evaluation only** | Fake data generator + 3 pre-built datasets | `demo/` |

---

## Hub Setup (team lead / manager)

### Prerequisites

- Python 3.9+
- [Ollama](https://ollama.ai) with `qwen2.5-coder:7b` (for AI features)
- pip3

### Install

```bash
git clone https://github.com/BoryslavW/task-analytics-poc.git
cd task-analytics-poc
pip3 install -r hub/requirements.txt
```

### Run

```bash
python3 hub/dashboard.py
```

On first run you'll set a dashboard password. The dashboard opens in a native
window (if pywebview is installed) or at http://127.0.0.1:8790.

A **pairing code** is printed to the terminal — share this with engineers
running the collector setup.

### What the Hub includes

| File | Purpose |
|------|---------|
| `dashboard.py` | NiceGUI dashboard (port 8790), native window |
| `analytics.py` | Topic classification, benchmarks, heatmaps |
| `advisor.py` | AI advisor — education plans, emerging trends (Ollama) |
| `code_insight.py` | Codebase health analysis + AI fix prompts |
| `receiver.py` | HTTPS data receiver (port 8788) with auth |
| `hub_security.py` | TLS, API keys, PBKDF2 auth, rate limiting, secret scrubbing |
| `hub_discovery.py` | Bonjour/mDNS LAN advertisement |
| `presets.py` | Company scenario presets |
| `model_baselines.py` | AI model token normalization (19 models) |
| `pm_provider.py` | Abstract PM provider + Jira/Notion integrations |
| `slack_connector.py` | Slack workspace signal ingestion |
| `requirements.txt` | Hub Python dependencies |

### macOS Desktop Shortcut

```bash
cd task-analytics-poc
osacompile -o ~/Desktop/"Valon AI Dashboard.app" -e '
on run
    set appDir to "'$(pwd)'"
    try
        do shell script "pgrep -f \"python3.*dashboard.py\" > /dev/null 2>&1"
    on error
        do shell script "cd " & quoted form of appDir & " && python3 hub/dashboard.py > /dev/null 2>&1 &"
    end try
end run'
```

---

## Collector Setup (engineers)

### Prerequisites

- Python 3.9+ (no pip packages needed at runtime)
- `zeroconf` for initial setup only: `pip3 install zeroconf`

### Install

On each developer's machine, run the one-time setup:

```bash
bash collector/collector_setup.sh
```

This will:
1. Auto-discover the Hub on the LAN via Bonjour (falls back to manual IP)
2. Ask for the engineer's name and the pairing code (from the hub admin)
3. Register with the Hub and receive a unique API key
4. Install a background daemon (macOS Launch Agent)

Once installed, the collector runs invisibly. It:
- Parses Claude Code session transcripts
- Scrubs secrets from all data before sending
- Signs records with HMAC-SHA256
- Queues locally if Hub is unreachable, flushes on reconnect
- Starts automatically on login

### What the Collector includes

| File | Purpose |
|------|---------|
| `collector_setup.sh` | One-time installer for dev laptops |
| `session_harvester.py` | Claude Code session parser + sender |
| `git_tracker.py` | Editor-agnostic git/filesystem session tracker |
| `hooks/on_session_end.sh` | Claude Code SessionEnd hook |

### Session Harvester (Claude Code hook)

```bash
python3 collector/session_harvester.py              # Batch harvest all
python3 collector/session_harvester.py --auto-harvest <session_id>  # Single
```

### Git Tracker (all editors)

For VS Code, Cursor, Copilot, Windsurf, Aider, etc.:

```bash
python3 collector/git_tracker.py
```

Detects sessions from file save patterns and git operations, extracts
keywords from diffs, and auto-submits to the Hub.

---

## Demo Mode (evaluation / demo day)

### Quick Start with Pre-built Data

Three datasets ship pre-generated in `demo/demo_data/`:

| Preset | Company | Industry |
|--------|---------|----------|
| `startup` | Valon AI | General SaaS platform |
| `fintech` | NovaPay | Payment infrastructure & lending |
| `medtech` | MedCore Systems | EHR integrations & clinical platforms |

Each has 2,000 task records, 20 employees, 12 topics, Slack signals, and Jira tickets.

**Switch presets instantly:**

```bash
python3 demo/demo_switch.py startup    # or fintech, medtech
python3 hub/dashboard.py
```

### Generate Fresh Data

```bash
python3 demo/generate_fake_data.py     # Uses the active preset
python3 hub/analytics.py               # Regenerate heatmaps + charts
```

---

## Architecture

```
Developer laptops (collectors)              Hub machine (leader)
┌─────────────────────────┐                ┌──────────────────────────┐
│ collector_agent          │  ── HTTPS ──>  │ hub/receiver.py          │
│ (auto-installed daemon)  │    /submit     │ (TLS + API key auth)     │
│                          │                │                          │
│ session_harvester.py     │                │ data/task_data.jsonl     │
│ git_tracker.py           │                │                          │
└─────────────────────────┘                │ hub/dashboard.py (:8790) │
       ▲                                   │ hub/analytics.py         │
       │ Auto-discovers hub                │ hub/advisor.py (Ollama)  │
       │ via Bonjour/mDNS                  └──────────────────────────┘
       └── collector_setup.sh                     ▲ Bonjour advertise
```

### Security

1. **TLS encryption** — self-signed certs, auto-generated on first run
2. **API key auth** — unique key per collector, issued via pairing code
3. **PBKDF2 password hashing** — 600K iterations with random salt
4. **HMAC-SHA256** — record integrity verification
5. **Rate limiting** — 60 req/min per IP (sliding window)
6. **Secret scrubbing** — strips API keys, passwords, JWTs, AWS creds from all data
7. **LLM prompt sanitization** — task data fields sanitized before Ollama prompts

### Dashboard Tabs

| Tab | What it shows |
|-----|---------------|
| **Overview** | Heatmap, key metrics, blind spots, model distribution |
| **Efforts** | Epic-level effort tracking with status badges |
| **Team Health** | Blind spot cards, AI action plans, curated resources |
| **Predictions** | In-progress completion estimates, velocity forecasting, effort estimator |
| **Slack** | Workspace patterns, employee signals, channel health |
| **Code Insights** | Keyword hotspots, toxic pairs, convergence, AI fix prompts |

---

## Dependencies

### Hub (6 packages)

| Package | Purpose |
|---------|---------|
| matplotlib | Charts and heatmaps |
| numpy | Numerical computation |
| pandas | Data analysis |
| nicegui | Dashboard web UI |
| zeroconf | Bonjour/mDNS LAN discovery |
| pywebview | Native window (optional) |

### Collector (0 packages at runtime)

Pure Python stdlib. `zeroconf` is only needed during the one-time setup
and can be uninstalled after.
