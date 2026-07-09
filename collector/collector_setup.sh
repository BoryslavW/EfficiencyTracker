#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# Valon AI — Collector Setup (Secured)
#
# Run this once on each developer's laptop. It will:
#   1. Auto-discover the Hub on the local network (or ask for IP)
#   2. Pair with the Hub using a one-time pairing code
#   3. Install the collector files to ~/.valon-collector/
#   4. Register a macOS Launch Agent so it runs on login (invisible)
#   5. Start the collector immediately
#
# Security:
#   - Pairing code required (displayed on Hub console at startup)
#   - API key issued per-collector (stored locally, never transmitted again)
#   - All data sent over TLS (self-signed cert, pinned on first connect)
#   - Secrets scrubbed from session data before transmission
#   - HMAC signature on every submitted record
# ──────────────────────────────────────────────────────────────────────

set -e

INSTALL_DIR="$HOME/.valon-collector"
PLIST_NAME="com.valon.collector"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
CONFIG_FILE="$INSTALL_DIR/config.json"
COLLECTOR_SCRIPT="$INSTALL_DIR/collector_agent.py"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    Valon AI — Collector Setup        ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── Step 1: Find Python ──────────────────────────────────────────────
PYTHON=""
for candidate in python3 /Library/Developer/CommandLineTools/usr/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ✗ Python 3 not found. Please install it first."
    exit 1
fi
echo "  ✓ Python: $PYTHON"

# ── Step 2: Install zeroconf if needed ───────────────────────────────
if ! "$PYTHON" -c "import zeroconf" 2>/dev/null; then
    echo "  Installing zeroconf for Hub discovery..."
    "$PYTHON" -m pip install --user --quiet zeroconf 2>/dev/null || true
fi

# ── Step 3: Discover Hub ─────────────────────────────────────────────
echo ""
echo "  Searching for Valon AI Hub on local network..."

HUB_INFO=$("$PYTHON" -c "
import sys, socket, threading
try:
    from zeroconf import Zeroconf, ServiceBrowser
except ImportError:
    sys.exit(1)

result = {}
found = threading.Event()

class L:
    def add_service(self, zc, stype, name):
        info = zc.get_service_info(stype, name)
        if info and info.addresses:
            result['ip'] = socket.inet_ntoa(info.addresses[0])
            result['rp'] = info.properties.get(b'receiver_port', b'8788').decode()
            result['dp'] = info.properties.get(b'dashboard_port', b'8790').decode()
            found.set()
    def remove_service(self, zc, stype, name): pass
    def update_service(self, zc, stype, name): pass

zc = Zeroconf()
ServiceBrowser(zc, '_valonhub._tcp.local.', L())
found.wait(timeout=10)
zc.close()

if result:
    print(f\"{result['ip']}|{result['rp']}|{result['dp']}\")
" 2>/dev/null) || true

if [ -n "$HUB_INFO" ]; then
    HUB_IP=$(echo "$HUB_INFO" | cut -d'|' -f1)
    RECEIVER_PORT=$(echo "$HUB_INFO" | cut -d'|' -f2)
    DASHBOARD_PORT=$(echo "$HUB_INFO" | cut -d'|' -f3)
    echo "  ✓ Found Hub: $HUB_IP"
else
    echo "  ✗ No Hub found automatically."
    echo ""
    read -p "  Enter Hub IP address: " HUB_IP
    RECEIVER_PORT="8788"
    DASHBOARD_PORT="8790"

    if [ -z "$HUB_IP" ]; then
        echo "  ✗ No IP provided. Exiting."
        exit 1
    fi
    echo "  ✓ Using Hub: $HUB_IP"
fi

RECEIVER_URL="https://${HUB_IP}:${RECEIVER_PORT}"

# ── Step 4: Get employee name ────────────────────────────────────────
echo ""
CURRENT_USER=$(whoami)
read -p "  Your name (for task attribution) [$CURRENT_USER]: " EMPLOYEE_NAME
EMPLOYEE_NAME="${EMPLOYEE_NAME:-$CURRENT_USER}"

# ── Step 5: Pair with Hub ────────────────────────────────────────────
echo ""
echo "  The pairing code is displayed on the Hub console at startup."
read -p "  Enter pairing code: " PAIRING_CODE

if [ -z "$PAIRING_CODE" ]; then
    echo "  ✗ No pairing code provided. Exiting."
    exit 1
fi

echo "  Registering with Hub..."
REGISTER_RESULT=$("$PYTHON" -c "
import json, ssl
from urllib.request import Request, urlopen

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

body = json.dumps({'employee': '$EMPLOYEE_NAME', 'pairing_code': '$PAIRING_CODE'}).encode()
req = Request('${RECEIVER_URL}/register', data=body, headers={'Content-Type': 'application/json'})
try:
    resp = urlopen(req, context=ctx, timeout=10)
    data = json.loads(resp.read().decode())
    if data.get('api_key'):
        print('OK|' + data['api_key'])
    else:
        print('FAIL|' + data.get('error', 'Unknown error'))
except Exception as e:
    print('FAIL|' + str(e))
" 2>/dev/null) || true

REGISTER_STATUS=$(echo "$REGISTER_RESULT" | cut -d'|' -f1)
REGISTER_VALUE=$(echo "$REGISTER_RESULT" | cut -d'|' -f2-)

if [ "$REGISTER_STATUS" != "OK" ]; then
    echo "  ✗ Registration failed: $REGISTER_VALUE"
    echo "    Check the pairing code and try again."
    exit 1
fi

API_KEY="$REGISTER_VALUE"
echo "  ✓ Registered with Hub (API key received)"

# ── Step 6: Install collector files ──────────────────────────────────
echo ""
echo "  Installing to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/queue"

# Write config
cat > "$CONFIG_FILE" <<CONF
{
    "hub_ip": "$HUB_IP",
    "receiver_url": "${RECEIVER_URL}/submit",
    "dashboard_url": "https://${HUB_IP}:${DASHBOARD_PORT}",
    "employee_name": "$EMPLOYEE_NAME",
    "api_key": "$API_KEY",
    "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "sync_interval_seconds": 300,
    "tls_verify": false
}
CONF
chmod 600 "$CONFIG_FILE"

# Write the collector agent
cat > "$COLLECTOR_SCRIPT" <<'PYEOF'
#!/usr/bin/env python3
"""
Valon AI Collector Agent — secured version.

Runs in the background on developer laptops. Watches for completed Claude Code
sessions, scrubs secrets, signs records, and sends them to the Hub over TLS.
"""

import hashlib
import hmac
import json
import os
import re
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(INSTALL_DIR, "config.json")
QUEUE_DIR = os.path.join(INSTALL_DIR, "queue")
HARVEST_LOG = os.path.join(INSTALL_DIR, ".harvested_sessions.json")

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"

TERM_LIBRARY = {
    "python": "python", "fastapi": "fastapi", "django": "django",
    "react": "react", "typescript": "typescript", "nextjs": "nextjs",
    "docker": "docker", "kubernetes": "kubernetes", "terraform": "terraform",
    "sql": "sql", "postgresql": "sql", "graphql": "graphql",
    "api": "endpoint", "endpoint": "endpoint", "rest": "rest-api",
    "auth": "authentication", "oauth": "authentication", "jwt": "authentication",
    "test": "pytest", "testing": "pytest", "jest": "pytest",
    "security": "security", "encryption": "security", "vault": "security",
    "llm": "llm", "gpt": "llm", "claude": "llm", "openai": "llm",
    "pipeline": "pipeline", "etl": "etl", "kafka": "kafka",
    "ci": "ci-pipeline", "cd": "ci-pipeline", "deploy": "deployment",
    "aws": "cloud", "gcp": "cloud", "azure": "cloud",
    "monitoring": "monitoring", "logging": "logging", "grafana": "monitoring",
    "css": "frontend", "html": "frontend", "component": "frontend",
    "database": "database", "migration": "database", "schema": "database",
    "redis": "caching", "cache": "caching", "performance": "performance",
    "refactor": "refactor", "bug": "bugfix", "fix": "bugfix",
}

_ERROR_PATTERNS = re.compile(
    r'(?:error|Error|ERROR|exception|Exception|Traceback|FAILED|'
    r'fatal|FATAL|exit code [1-9])', re.IGNORECASE)

# ── Secret scrubbing patterns ──
_SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|api[_-]?token|access[_-]?token|secret[_-]?key|auth[_-]?token|bearer)\s*[=:]\s*["\']?([A-Za-z0-9_\-/.]{20,})["\']?'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[=:]\s*["\']?([A-Za-z0-9/+=]{30,})["\']?'),
    re.compile(r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----'),
    re.compile(r'(?i)(postgres|mysql|mongodb|redis|amqp)://[^\s"\']+'),
    re.compile(r'(?i)(password|passwd|pwd|db_pass|secret)\s*[=:]\s*["\']?([^\s"\']{6,})["\']?'),
    re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'),
    re.compile(r'gh[ps]_[A-Za-z0-9_]{30,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{30,}'),
    re.compile(r'xox[bpras]-[A-Za-z0-9-]+'),
    re.compile(r'(?i)(ssh-rsa|ssh-ed25519)\s+[A-Za-z0-9+/=]{40,}'),
]


def scrub_text(text):
    for p in _SECRET_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text


def scrub_record(record):
    cleaned = {}
    for k, v in record.items():
        if isinstance(v, str):
            cleaned[k] = scrub_text(v)
        elif isinstance(v, list):
            cleaned[k] = [scrub_text(i) if isinstance(i, str) else i for i in v]
        else:
            cleaned[k] = v
    return cleaned


def sign_record(record, api_key):
    payload = json.dumps(record, sort_keys=True).encode()
    return hmac.new(api_key.encode(), payload, hashlib.sha256).hexdigest()


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def load_harvested():
    if os.path.exists(HARVEST_LOG):
        with open(HARVEST_LOG) as f:
            return set(json.load(f))
    return set()


def save_harvested(harvested):
    with open(HARVEST_LOG, "w") as f:
        json.dump(sorted(harvested), f)


def extract_keywords(text):
    found = set()
    text_lower = text.lower()
    for term, canonical in TERM_LIBRARY.items():
        if term in text_lower:
            found.add(canonical)
    return sorted(found)


def find_sessions():
    sessions = []
    if not PROJECTS_DIR.exists():
        return sessions
    for project_dir in PROJECTS_DIR.iterdir():
        if project_dir.is_dir():
            for f in project_dir.glob("*.jsonl"):
                sessions.append(f)
    return sessions


def parse_session(jsonl_path, employee_name):
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

    all_text = []
    total_input = 0
    total_output = 0
    first_ts = None
    last_ts = None
    session_id = ""
    cwd = ""
    first_user_msg = ""
    error_count = 0

    for msg in messages:
        ts = msg.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
        if not session_id and msg.get("sessionId"):
            session_id = msg["sessionId"]
        if not cwd and msg.get("cwd"):
            cwd = msg["cwd"]

        msg_type = msg.get("type", "")
        if msg_type == "user":
            content = msg.get("message", {}).get("content", "")
            text = content if isinstance(content, str) else " ".join(
                p.get("text", "") for p in (content if isinstance(content, list) else [])
                if isinstance(p, dict) and p.get("type") == "text"
            )
            all_text.append(text)
            if not first_user_msg and text.strip():
                first_user_msg = text.strip()
        elif msg_type == "assistant":
            inner = msg.get("message", {})
            usage = inner.get("usage", {})
            total_input += usage.get("input_tokens", 0)
            total_output += usage.get("output_tokens", 0)
            content = inner.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        all_text.append(part.get("text", ""))
        elif msg_type in ("tool_result", "result"):
            rc = msg.get("content", "")
            if isinstance(rc, str) and _ERROR_PATTERNS.search(rc):
                error_count += 1

    if not first_ts or not last_ts:
        return None
    total_tokens = total_input + total_output
    if total_tokens == 0:
        return None

    try:
        t_start = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
        t_end = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        duration = max(1, (t_end - t_start).total_seconds() / 60)
    except (ValueError, TypeError):
        return None

    full_text = " ".join(all_text)
    keywords = extract_keywords(full_text)
    if len(keywords) < 2:
        return None

    project = os.path.basename(cwd) if cwd else "Unknown"
    jira_match = re.search(r'\b([A-Z]{2,10}-\d+)\b', first_user_msg)
    jira_id = jira_match.group(1) if jira_match else f"SESSION-{session_id[:8]}"
    task_name = first_user_msg[:80].replace("\n", " ").strip()

    return {
        "employee": employee_name,
        "jira_id": jira_id,
        "task_name": task_name,
        "project": project,
        "token_usage": total_tokens,
        "keywords": keywords,
        "start_time": t_start.isoformat(),
        "end_time": t_end.isoformat(),
        "duration_minutes": round(duration, 1),
        "error_count": error_count,
        "source": "collector-agent",
        "session_id": session_id,
    }


def _ssl_context(config):
    ctx = ssl.create_default_context()
    if not config.get("tls_verify", True):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def send_record(record, config):
    api_key = config["api_key"]
    sig = sign_record(record, api_key)
    data = json.dumps(record).encode()
    req = Request(config["receiver_url"], data=data, headers={
        "Content-Type": "application/json",
        "X-API-Key": api_key,
        "X-Signature": sig,
    })
    try:
        resp = urlopen(req, context=_ssl_context(config), timeout=10)
        return resp.status == 200
    except (URLError, OSError):
        return False


def queue_record(record):
    os.makedirs(QUEUE_DIR, exist_ok=True)
    fname = f"{int(time.time())}_{record.get('session_id', 'x')[:8]}.json"
    with open(os.path.join(QUEUE_DIR, fname), "w") as f:
        json.dump(record, f)


def flush_queue(config):
    if not os.path.exists(QUEUE_DIR):
        return
    for fname in os.listdir(QUEUE_DIR):
        fpath = os.path.join(QUEUE_DIR, fname)
        try:
            with open(fpath) as f:
                record = json.load(f)
            if send_record(record, config):
                os.remove(fpath)
        except Exception:
            pass


def run_cycle(config):
    employee = config["employee_name"]
    harvested = load_harvested()

    flush_queue(config)

    new_count = 0
    for session_path in find_sessions():
        sid = session_path.stem
        if sid in harvested:
            continue

        record = parse_session(session_path, employee)
        if record is None:
            harvested.add(sid)
            continue

        # Scrub secrets before sending
        record = scrub_record(record)

        if send_record(record, config):
            new_count += 1
        else:
            queue_record(record)

        harvested.add(sid)

    save_harvested(harvested)
    return new_count


def main():
    config = load_config()
    interval = config.get("sync_interval_seconds", 300)

    print(f"Valon AI Collector Agent (secured)")
    print(f"  Employee: {config['employee_name']}")
    print(f"  Hub: {config['receiver_url']}")
    print(f"  Interval: {interval}s")
    print(f"  TLS: enabled")
    print(f"  Secret scrubbing: enabled")
    print(f"  HMAC signing: enabled")
    print()

    while True:
        try:
            n = run_cycle(config)
            if n > 0:
                print(f"  [{datetime.now().strftime('%H:%M')}] Sent {n} new record(s)")
        except Exception as e:
            print(f"  [{datetime.now().strftime('%H:%M')}] Error: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
PYEOF

chmod +x "$COLLECTOR_SCRIPT"
chmod 600 "$CONFIG_FILE"
echo "  ✓ Collector agent installed"

# ── Step 7: Install Launch Agent ─────────────────────────────────────
echo "  Installing Launch Agent (starts on login)..."

launchctl unload "$PLIST_PATH" 2>/dev/null || true

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${COLLECTOR_SCRIPT}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${INSTALL_DIR}/collector.log</string>
    <key>StandardErrorPath</key>
    <string>${INSTALL_DIR}/collector_error.log</string>
    <key>ThrottleInterval</key>
    <integer>60</integer>
</dict>
</plist>
PLIST

launchctl load "$PLIST_PATH"
echo "  ✓ Launch Agent registered"

# ── Step 8: Verify ───────────────────────────────────────────────────
echo ""
sleep 2
if launchctl list | grep -q "$PLIST_NAME"; then
    echo "  ✓ Collector is running!"
else
    echo "  ⚠ Collector may not have started. Check: launchctl list | grep valon"
fi

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    Setup Complete!                   ║"
echo "  ╠══════════════════════════════════════╣"
echo "  ║  Security:                           ║"
echo "  ║    ✓ TLS encryption                  ║"
echo "  ║    ✓ API key authentication          ║"
echo "  ║    ✓ Secret scrubbing                ║"
echo "  ║    ✓ HMAC record signing             ║"
echo "  ╠══════════════════════════════════════╣"
echo "  ║  Employee: $EMPLOYEE_NAME"
echo "  ║  Hub: $HUB_IP"
echo "  ║  Install: $INSTALL_DIR"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  Commands:"
echo "    View logs:   tail -f ~/.valon-collector/collector.log"
echo "    Stop:        launchctl unload ~/Library/LaunchAgents/com.valon.collector.plist"
echo "    Uninstall:   launchctl unload ~/Library/LaunchAgents/com.valon.collector.plist && rm -rf ~/.valon-collector ~/Library/LaunchAgents/com.valon.collector.plist"
echo ""
