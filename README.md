# Valon AI — Task Analytics Dashboard

AI-powered team analytics platform that tracks coding sessions, benchmarks
performance by topic, detects team blind spots, and generates actionable
improvement plans. Built for LAN deployment with zero-config collector
auto-discovery.

## Quick Start

```bash
git clone https://github.com/BoryslavW/EfficiencyTracker.git
cd EfficiencyTracker
bash install.sh
```

The installer asks one question — your role — then handles everything else:

| Pick | What happens |
|------|-------------|
| **1 — Manager** | Installs the dashboard, AI model, desktop shortcut, and launches |
| **2 — Engineer** | Installs the background collector that sends metrics to the Hub |
| **3 — Demo** | Sets up the dashboard with pre-built sample data (no collectors needed) |

**Requirements:** macOS with Python 3.9+ (pre-installed on most Macs).
The installer checks for Python and tells you what to do if it's missing.

---

## Repo Structure

```
install.sh          ← Run this — picks your role, does the rest
hub/                ← Dashboard + analytics + AI (manager machine)
collector/          ← Background agent (engineer laptops)
demo/               ← Pre-built datasets for demos
```

---

## Hub (team lead / manager)

```bash
bash install.sh       # pick option 1
# — or directly —
bash hub/install.sh
```

What the installer does:
1. Checks Python 3.9+
2. Installs pip dependencies (`hub/requirements.txt`)
3. Downloads the Ollama AI model (`qwen2.5-coder:7b`) — optional, skipped gracefully if Ollama isn't installed
4. Creates a **desktop shortcut** (double-click to launch)
5. Loads demo data so the dashboard isn't empty on first run
6. Offers to launch the dashboard immediately

On first launch you'll set a dashboard password. The dashboard opens in a
native window or at http://127.0.0.1:8790.

A **pairing code** is printed to the terminal — share this with engineers
so they can connect their collectors.

### AI Features (optional)

Install [Ollama](https://ollama.ai) for AI-powered features:
- Code fix prompts (specific, copy-paste-ready fixes)
- Education plans and skill gap analysis
- Emerging trend detection

Without Ollama, every other feature works normally.

### Hub Files

| File | Purpose |
|------|---------|
| `dashboard.py` | NiceGUI dashboard (port 8790), native window |
| `analytics.py` | Topic classification, benchmarks, heatmaps |
| `advisor.py` | AI advisor — education plans, emerging trends |
| `code_insight.py` | Codebase health analysis + AI fix prompts |
| `receiver.py` | HTTPS data receiver (port 8788) with auth |
| `hub_security.py` | TLS, API keys, PBKDF2 auth, rate limiting, secret scrubbing |
| `hub_discovery.py` | Bonjour/mDNS LAN advertisement |
| `presets.py` | Company scenario presets |
| `slack_connector.py` | Slack workspace signal ingestion |
| `install.sh` | Automated hub installer |

---

## Collector (engineers)

```bash
bash install.sh       # pick option 2
# — or directly —
bash collector/collector_setup.sh
```

One command handles everything:
1. Installs `zeroconf` (for Hub discovery)
2. Auto-discovers the Hub on the LAN via Bonjour (falls back to manual IP entry)
3. Asks for your name and the pairing code (from the hub admin)
4. Registers with the Hub and receives a unique API key
5. Installs a background daemon that starts automatically on login

Once installed, the collector runs invisibly — no further action needed. It:
- Parses Claude Code session transcripts
- Scrubs secrets from all data before sending
- Signs records with HMAC-SHA256
- Queues locally if Hub is unreachable, flushes on reconnect

### Collector Files

| File | Purpose |
|------|---------|
| `collector_setup.sh` | One-time installer for dev laptops |
| `session_harvester.py` | Claude Code session parser + sender |
| `git_tracker.py` | Editor-agnostic git/filesystem session tracker |
| `hooks/on_session_end.sh` | Claude Code SessionEnd hook |

### Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.valon.collector.plist
rm -rf ~/.valon-collector ~/Library/LaunchAgents/com.valon.collector.plist
```

---

## Demo Mode (evaluation / demo day)

```bash
bash install.sh       # pick option 3
# — or directly —
bash demo/install.sh
```

Sets up the full dashboard with pre-built sample data. Three company
scenarios are included:

| Preset | Company | Industry |
|--------|---------|----------|
| `startup` | Valon AI | General SaaS platform |
| `fintech` | NovaPay | Payment infrastructure & lending |
| `medtech` | MedCore Systems | EHR integrations & clinical platforms |

Each has 2,000 task records, 20 employees, 12 topics, Slack signals, and
Jira tickets.

**Switch presets instantly** (no reinstall needed):

```bash
python3 demo/demo_switch.py fintech    # or startup, medtech
python3 hub/dashboard.py
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

| Layer | Detail |
|-------|--------|
| TLS encryption | Self-signed certs, auto-generated on first run |
| API key auth | Unique key per collector, issued via pairing code |
| PBKDF2 password | 600K iterations + random salt for dashboard login |
| HMAC-SHA256 | Record integrity verification on every submission |
| Rate limiting | 60 req/min per IP (sliding window) |
| Secret scrubbing | Strips API keys, passwords, JWTs, AWS creds from all data |
| LLM sanitization | Task fields sanitized before Ollama prompts |

### Dashboard Tabs

| Tab | What it shows |
|-----|---------------|
| **Overview** | Heatmap, key metrics, blind spots, model distribution |
| **Efforts** | Epic-level effort tracking with status badges |
| **Team Health** | Blind spot cards, AI action plans, curated resources |
| **Predictions** | In-progress completion estimates, velocity forecasting |
| **Slack** | Workspace patterns, employee signals, channel health |
| **Code Insights** | Keyword hotspots, toxic pairs, convergence, AI fix prompts |

---

## Dependencies

**Hub** — 6 pip packages (installed automatically):
matplotlib, numpy, pandas, nicegui, zeroconf, pywebview

**Collector** — zero packages at runtime. `zeroconf` is installed during
setup and can be removed after.
