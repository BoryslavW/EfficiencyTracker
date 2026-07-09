#!/usr/bin/env python3
"""
Central data receiver — accepts task submissions via HTTPS POST with
API key authentication, rate limiting, and secret scrubbing.

Security layers:
  1. TLS encryption (self-signed cert, auto-generated)
  2. API key auth (X-API-Key header required on all POST requests)
  3. Per-IP rate limiting (60 requests/minute)
  4. Secret scrubbing (strips credentials from incoming data)
  5. HMAC signature verification (optional, X-Signature header)
  6. Collector registration via pairing code

Usage:
    python3 receiver.py                  # default: 0.0.0.0:8788
    python3 receiver.py --no-tls         # disable TLS (not recommended)
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from hub_security import (
    init_hub_secrets,
    validate_api_key,
    register_collector,
    scrub_record,
    RateLimiter,
    get_ssl_context,
    verify_signature,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "data")
DATA_FILE = os.path.join(DATA_DIR, "task_data.jsonl")

_write_lock = threading.Lock()
_record_count = 0
_count_lock = threading.Lock()
_rate_limiter = RateLimiter(max_requests=60, window_seconds=60)
_hub_secrets = {}


def _init_record_count() -> None:
    global _record_count
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            _record_count = sum(1 for line in f if line.strip())


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class ReceiverHandler(BaseHTTPRequestHandler):

    def _get_client_ip(self) -> str:
        return self.client_address[0]

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, X-Signature")

    def _json_response(self, status: int, body: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def _check_rate_limit(self) -> bool:
        ip = self._get_client_ip()
        if not _rate_limiter.allow(ip):
            self._json_response(429, {"error": "Rate limit exceeded. Try again later."})
            return False
        return True

    def _check_api_key(self) -> bool:
        key = self.headers.get("X-API-Key", "")
        if not key or not validate_api_key(key):
            self._json_response(401, {"error": "Invalid or missing API key"})
            return False
        return True

    def do_POST(self):
        global _record_count

        if not self._check_rate_limit():
            return

        # ── Collector registration (pairing) ──
        if self.path == "/register":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            try:
                req = json.loads(body)
            except json.JSONDecodeError:
                self._json_response(400, {"error": "Invalid JSON"})
                return

            employee = req.get("employee", "")
            code = req.get("pairing_code", "")
            if not employee or not code:
                self._json_response(400, {"error": "Missing employee or pairing_code"})
                return

            api_key = register_collector(employee, code)
            if api_key:
                self._json_response(200, {"status": "registered", "api_key": api_key})
                print(f"  [registered] {employee} from {self._get_client_ip()}")
            else:
                self._json_response(403, {"error": "Invalid pairing code"})
            return

        # ── Task submission ──
        if self.path == "/submit":
            if not self._check_api_key():
                return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()

            try:
                record = json.loads(body)
            except json.JSONDecodeError:
                self._json_response(400, {"error": "Invalid JSON"})
                return

            required = ["employee", "jira_id", "task_name", "project",
                        "token_usage", "keywords", "start_time", "end_time"]
            missing = [f for f in required if f not in record]
            if missing:
                self._json_response(400, {"error": f"Missing fields: {missing}"})
                return

            # Verify HMAC signature if provided
            sig = self.headers.get("X-Signature", "")
            if sig:
                api_key = self.headers.get("X-API-Key", "")
                if not verify_signature(record, sig, api_key):
                    self._json_response(400, {"error": "Invalid signature"})
                    return

            # Scrub any secrets from the record
            record = scrub_record(record)
            record["received_at"] = datetime.now(timezone.utc).isoformat()
            record["source_ip"] = self._get_client_ip()

            os.makedirs(DATA_DIR, exist_ok=True)
            with _write_lock:
                with open(DATA_FILE, "a") as f:
                    f.write(json.dumps(record) + "\n")

            with _count_lock:
                _record_count += 1

            print(f"  [{record['received_at'][:19]}] {record['employee']} — {record['jira_id']}")
            self._json_response(200, {"status": "ok", "jira_id": record["jira_id"]})
            return

        # ── Health check ──
        if self.path == "/health":
            self._json_response(200, {"status": "ok", "records": _record_count})
            return

        self._json_response(404, {"error": "Not found"})

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._json_response(200, {"status": "ok", "records": _record_count})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(f"Valon AI Hub — {_record_count} records stored.\n".encode())

    def log_message(self, format, *args):
        pass


def main():
    global _hub_secrets

    parser = argparse.ArgumentParser(description="Central task data receiver")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--no-tls", action="store_true",
                        help="Disable TLS (not recommended)")
    args = parser.parse_args()

    _hub_secrets = init_hub_secrets()
    _init_record_count()

    server = ThreadingHTTPServer((args.host, args.port), ReceiverHandler)

    protocol = "http"
    if not args.no_tls:
        ssl_ctx = get_ssl_context()
        if ssl_ctx:
            server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)
            protocol = "https"

    print(f"Receiver listening on {protocol}://{args.host}:{args.port}")
    print(f"Data file: {DATA_FILE}")
    print(f"Pairing code: {_hub_secrets.get('pairing_code', 'N/A')}")
    print(f"Registered collectors: {len(_hub_secrets.get('registered_collectors', {}))}")
    print("Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
