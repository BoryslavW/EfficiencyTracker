#!/usr/bin/env python3
"""
Hub discovery — Bonjour/mDNS advertisement and discovery for LAN deployment.

The Hub (leader machine) advertises itself as _valonhub._tcp.local. on the
local network.  Collector machines discover it automatically — no IP entry
needed.

Uses the `zeroconf` library (pip install zeroconf).
"""

from __future__ import annotations

import socket
import threading
import time


SERVICE_TYPE = "_valonhub._tcp.local."
SERVICE_NAME = "Valon AI Hub._valonhub._tcp.local."


def get_local_ip() -> str:
    """Get the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Hub side — advertise
# ---------------------------------------------------------------------------

_zc_instance = None
_service_info = None


def start_advertisement(receiver_port: int = 8788, dashboard_port: int = 8790) -> str | None:
    """Start advertising this machine as the Valon AI Hub on the LAN.
    Returns the local IP if successful, None on failure."""
    global _zc_instance, _service_info

    try:
        from zeroconf import Zeroconf, ServiceInfo
    except ImportError:
        print("[hub] zeroconf not installed — skipping Bonjour advertisement")
        print("[hub] install with: pip3 install zeroconf")
        return None

    local_ip = get_local_ip()
    ip_bytes = socket.inet_aton(local_ip)

    _service_info = ServiceInfo(
        SERVICE_TYPE,
        SERVICE_NAME,
        addresses=[ip_bytes],
        port=receiver_port,
        properties={
            "dashboard_port": str(dashboard_port),
            "receiver_port": str(receiver_port),
            "version": "1.0",
        },
    )

    _zc_instance = Zeroconf()
    _zc_instance.register_service(_service_info)
    print(f"[hub] Advertising on LAN: {local_ip}  (receiver:{receiver_port}, dashboard:{dashboard_port})")
    print(f"[hub] Bonjour will auto-stop after 10 minutes (re-enable from dashboard if needed)")

    def _auto_stop():
        time.sleep(600)
        stop_advertisement()
        print("[hub] Bonjour advertisement auto-stopped (10 min limit)")

    t = threading.Thread(target=_auto_stop, daemon=True)
    t.start()

    return local_ip


def stop_advertisement():
    """Stop advertising."""
    global _zc_instance, _service_info
    if _zc_instance and _service_info:
        _zc_instance.unregister_service(_service_info)
        _zc_instance.close()
        _zc_instance = None
        _service_info = None


# ---------------------------------------------------------------------------
# Collector side — discover
# ---------------------------------------------------------------------------

def discover_hub(timeout: float = 8.0) -> dict | None:
    """Discover the Hub on the LAN via Bonjour.
    Returns {"ip": ..., "receiver_port": ..., "dashboard_port": ...} or None."""
    try:
        from zeroconf import Zeroconf, ServiceBrowser
    except ImportError:
        print("[discovery] zeroconf not installed — cannot auto-discover")
        return None

    result = {}
    found = threading.Event()

    class Listener:
        def add_service(self, zc, stype, name):
            info = zc.get_service_info(stype, name)
            if info and info.addresses:
                result["ip"] = socket.inet_ntoa(info.addresses[0])
                result["receiver_port"] = int(info.properties.get(b"receiver_port", b"8788").decode())
                result["dashboard_port"] = int(info.properties.get(b"dashboard_port", b"8790").decode())
                found.set()

        def remove_service(self, zc, stype, name):
            pass

        def update_service(self, zc, stype, name):
            pass

    zc = Zeroconf()
    browser = ServiceBrowser(zc, SERVICE_TYPE, Listener())

    found.wait(timeout=timeout)
    zc.close()

    return result if result else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "discover":
        print("Searching for Valon AI Hub on local network...")
        hub = discover_hub()
        if hub:
            print(f"Found Hub: {hub['ip']}")
            print(f"  Receiver: http://{hub['ip']}:{hub['receiver_port']}/submit")
            print(f"  Dashboard: http://{hub['ip']}:{hub['dashboard_port']}")
        else:
            print("No Hub found on this network.")
    else:
        print("Starting Hub advertisement (Ctrl+C to stop)...")
        ip = start_advertisement()
        if ip:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                stop_advertisement()
                print("\nStopped.")
        else:
            print("Failed to start advertisement.")
