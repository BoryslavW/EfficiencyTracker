#!/usr/bin/env python3
"""Demo day preset switcher — restores pre-generated data instantly."""
import os
import shutil
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA_DIR = os.path.join(BASE, "data")
OUTPUT_DIR = os.path.join(BASE, "output")
DEMO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_data")

sys.path.insert(0, os.path.join(BASE, "hub"))

PRESETS = {
    "startup": "Valon AI — General SaaS startup",
    "fintech": "NovaPay — Payment infrastructure & lending",
    "medtech": "MedCore Systems — EHR integrations & clinical platforms",
}

def switch(name: str) -> None:
    if name not in PRESETS:
        print(f"Unknown preset: {name}")
        print(f"Available: {', '.join(PRESETS.keys())}")
        sys.exit(1)

    src = os.path.join(DEMO_DIR, name)
    if not os.path.exists(src):
        print(f"No saved demo data for '{name}' in {src}")
        sys.exit(1)

    from presets import set_active_preset
    set_active_preset(name)

    for fname in os.listdir(src):
        s = os.path.join(src, fname)
        if fname.endswith(".png"):
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            shutil.copy2(s, os.path.join(OUTPUT_DIR, fname))
        else:
            shutil.copy2(s, os.path.join(DATA_DIR, fname))

    insights_file = os.path.join(DATA_DIR, "code_insights.json")
    if os.path.exists(insights_file):
        os.remove(insights_file)

    print(f"Switched to: {name} — {PRESETS[name]}")
    print("Restart the dashboard to see the new data.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 demo/demo_switch.py <preset>")
        print()
        for k, v in PRESETS.items():
            print(f"  {k:10s}  {v}")
        sys.exit(0)
    switch(sys.argv[1])
