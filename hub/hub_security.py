#!/usr/bin/env python3
"""
Hub security layer — API key auth, TLS certs, rate limiting, secret scrubbing,
and dashboard access control.

All secrets are stored in data/.hub_secrets.json (auto-generated on first run).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import ssl
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "data")
SECRETS_FILE = os.path.join(DATA_DIR, "hub_secrets.json")
CERTS_DIR = os.path.join(DATA_DIR, "certs")
CERT_FILE = os.path.join(CERTS_DIR, "hub.crt")
KEY_FILE = os.path.join(CERTS_DIR, "hub.key")


# ─── API Key Management ──────────────────────────────────────────────────

def _load_secrets() -> dict:
    if os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE) as f:
            return json.load(f)
    return {}


def _save_secrets(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SECRETS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(SECRETS_FILE, 0o600)


def init_hub_secrets() -> dict:
    """Initialize or load Hub secrets. Returns the secrets dict."""
    data = _load_secrets()
    changed = False

    if "hub_api_key" not in data:
        data["hub_api_key"] = secrets.token_urlsafe(32)
        changed = True

    if "pairing_code" not in data:
        data["pairing_code"] = secrets.token_hex(4).upper()
        changed = True

    if "dashboard_password_hash" not in data:
        data["_needs_dashboard_password"] = True
        changed = True

    if "registered_collectors" not in data:
        data["registered_collectors"] = {}
        changed = True

    if changed:
        _save_secrets(data)
        print(f"[security] Hub secrets saved to {SECRETS_FILE}")

    return data


def validate_api_key(provided_key: str) -> bool:
    """Check if an API key matches the Hub key or any registered collector key."""
    data = _load_secrets()
    hub_key = data.get("hub_api_key", "")
    if hmac.compare_digest(provided_key, hub_key):
        return True
    for collector_info in data.get("registered_collectors", {}).values():
        if hmac.compare_digest(provided_key, collector_info.get("api_key", "")):
            return True
    return False


def register_collector(employee_name: str, pairing_code: str) -> str | None:
    """Register a new collector. Returns an API key if pairing code matches."""
    data = _load_secrets()
    if not hmac.compare_digest(pairing_code.upper(), data.get("pairing_code", "")):
        return None

    collector_key = secrets.token_urlsafe(32)
    collector_id = hashlib.sha256(f"{employee_name}-{time.time()}".encode()).hexdigest()[:12]

    data.setdefault("registered_collectors", {})[collector_id] = {
        "employee": employee_name,
        "api_key": collector_key,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_secrets(data)
    return collector_key


def set_dashboard_password(password: str) -> None:
    """Set (or change) the dashboard login password."""
    data = _load_secrets()
    salt = os.urandom(32)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    data["dashboard_password_salt"] = salt.hex()
    data["dashboard_password_hash"] = pw_hash.hex()
    data.pop("_needs_dashboard_password", None)
    _save_secrets(data)


def needs_dashboard_password() -> bool:
    """True if no dashboard password has been set yet."""
    data = _load_secrets()
    return not data.get("dashboard_password_hash")


def validate_dashboard_password(password: str) -> bool:
    """Check dashboard login password."""
    data = _load_secrets()
    expected_hash = data.get("dashboard_password_hash", "")
    salt_hex = data.get("dashboard_password_salt", "")
    if not expected_hash or not salt_hex:
        return False
    salt = bytes.fromhex(salt_hex)
    provided_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return hmac.compare_digest(provided_hash.hex(), expected_hash)


def get_dashboard_sessions() -> dict:
    """Simple session store for dashboard auth. Returns {token: expiry_ts}."""
    data = _load_secrets()
    return data.get("dashboard_sessions", {})


def create_dashboard_session() -> str:
    """Create a new dashboard session token (valid 24h)."""
    data = _load_secrets()
    token = secrets.token_urlsafe(32)
    sessions = data.setdefault("dashboard_sessions", {})
    # Clean expired
    now = time.time()
    sessions = {t: exp for t, exp in sessions.items() if exp > now}
    sessions[token] = now + 86400  # 24 hours
    data["dashboard_sessions"] = sessions
    _save_secrets(data)
    return token


def validate_dashboard_session(token: str) -> bool:
    """Check if a dashboard session token is valid."""
    data = _load_secrets()
    sessions = data.get("dashboard_sessions", {})
    expiry = sessions.get(token, 0)
    return expiry > time.time()


# ─── TLS Certificate Generation ──────────────────────────────────────────

def ensure_tls_certs() -> tuple[str, str] | None:
    """Generate self-signed TLS certs if they don't exist. Returns (cert, key) paths."""
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return CERT_FILE, KEY_FILE

    os.makedirs(CERTS_DIR, exist_ok=True)

    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", KEY_FILE, "-out", CERT_FILE,
            "-days", "365", "-nodes",
            "-subj", "/CN=Valon AI Hub/O=Valon/C=US",
        ], capture_output=True, check=True)
        os.chmod(KEY_FILE, 0o600)
        print(f"[security] TLS certs generated: {CERTS_DIR}")
        return CERT_FILE, KEY_FILE
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[security] openssl not available — TLS disabled")
        return None


def get_ssl_context() -> ssl.SSLContext | None:
    """Get an SSL context for the receiver, or None if certs unavailable."""
    paths = ensure_tls_certs()
    if not paths:
        return None
    cert, key = paths
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    return ctx


# ─── Rate Limiter ────────────────────────────────────────────────────────

class RateLimiter:
    """Per-IP sliding window rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, ip: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        hits = self._hits[ip]
        # Prune old entries
        self._hits[ip] = [t for t in hits if t > cutoff]
        if len(self._hits[ip]) >= self.max_requests:
            return False
        self._hits[ip].append(now)
        return True


# ─── Secret Scrubber ─────────────────────────────────────────────────────

_SECRET_PATTERNS = [
    # API keys / tokens (generic long alphanumeric strings after key-like words)
    re.compile(r'(?i)(api[_-]?key|api[_-]?token|access[_-]?token|secret[_-]?key|auth[_-]?token|bearer)\s*[=:]\s*["\']?([A-Za-z0-9_\-/.]{20,})["\']?'),
    # AWS keys
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[=:]\s*["\']?([A-Za-z0-9/+=]{30,})["\']?'),
    # Private keys
    re.compile(r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----'),
    # Connection strings
    re.compile(r'(?i)(postgres|mysql|mongodb|redis|amqp)://[^\s"\']+'),
    # Generic password patterns
    re.compile(r'(?i)(password|passwd|pwd|db_pass|secret)\s*[=:]\s*["\']?([^\s"\']{6,})["\']?'),
    # JWT tokens
    re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'),
    # GitHub tokens
    re.compile(r'gh[ps]_[A-Za-z0-9_]{30,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{30,}'),
    # Slack tokens
    re.compile(r'xox[bpras]-[A-Za-z0-9-]+'),
    # .env file patterns
    re.compile(r'(?i)^[A-Z_]{3,50}=\S{10,}$', re.MULTILINE),
    # SSH private key content
    re.compile(r'(?i)(ssh-rsa|ssh-ed25519)\s+[A-Za-z0-9+/=]{40,}'),
]

SCRUB_PLACEHOLDER = "[REDACTED]"


def scrub_secrets(text: str) -> str:
    """Remove anything that looks like a secret/credential from text."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(SCRUB_PLACEHOLDER, text)
    return text


def scrub_record(record: dict) -> dict:
    """Scrub secrets from all string fields in a task record."""
    cleaned = {}
    for key, value in record.items():
        if isinstance(value, str):
            cleaned[key] = scrub_secrets(value)
        elif isinstance(value, list):
            cleaned[key] = [scrub_secrets(v) if isinstance(v, str) else v for v in value]
        else:
            cleaned[key] = value
    return cleaned


# ─── Data Integrity ──────────────────────────────────────────────────────

def sign_record(record: dict, api_key: str) -> str:
    """Create an HMAC signature for a record."""
    payload = json.dumps(record, sort_keys=True).encode()
    return hmac.new(api_key.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(record: dict, signature: str, api_key: str) -> bool:
    """Verify a record's HMAC signature."""
    expected = sign_record(record, api_key)
    return hmac.compare_digest(signature, expected)
