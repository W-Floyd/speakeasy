#!/usr/bin/env python3
"""Panelize the Speakeasy PCB using KiKit.

Reads:  speakeasy/Speakeasy.kicad_pcb  (hand-made, never overwritten)
Writes: speakeasy/Speakeasy_panel.kicad_pcb

Panel layout: 2 columns × 2 rows, mouse-bite tabs, top/bottom rails.
Edit panel_preset.json (same directory) to change layout parameters.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT   = Path(__file__).parent.parent / "speakeasy"
INPUT  = ROOT / "Speakeasy.kicad_pcb"
OUTPUT = ROOT / "Speakeasy_panel.kicad_pcb"
PRESET = Path(__file__).parent / "panel_preset.json"

# KiKit requires pcbnew, which is only available in KiCad's bundled Python.
KIKIT = Path(
    "/Applications/KiCad/KiCad.app/Contents/Frameworks"
    "/Python.framework/Versions/3.9/bin/kikit"
)


def ensure_net_settings(pro_path: Path):
    """Add net_settings.classes if missing — required by kikit for netclass transfer."""
    with open(pro_path) as f:
        pro = json.load(f)
    changed = False
    ns = pro.setdefault("net_settings", {})
    if "classes" not in ns:
        ns["classes"] = [{
            "bus_width": 12,
            "clearance": 0.2,
            "diff_pair_gap": 0.25,
            "diff_pair_via_gap": 0.25,
            "diff_pair_width": 0.2,
            "line_style": 0,
            "microvia_diameter": 0.3,
            "microvia_drill": 0.1,
            "name": "Default",
            "pcb_color": "rgba(0, 0, 0, 0.000)",
            "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": 0.25,
            "via_diameter": 0.8,
            "via_drill": 0.4,
            "wire_width": 6,
        }]
        changed = True
    if changed:
        with open(pro_path, "w") as f:
            json.dump(pro, f, indent=2)
        print(f"Patched net_settings.classes in {pro_path.name}")


def main():
    for path, label in [(INPUT, "source PCB"), (KIKIT, "kikit"), (PRESET, "preset")]:
        if not path.exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            sys.exit(1)

    pro_path = INPUT.with_suffix(".kicad_pro")
    if pro_path.exists():
        ensure_net_settings(pro_path)

    cmd = [str(KIKIT), "panelize", "-p", str(PRESET),
           "--debug", "deterministic: true",
           str(INPUT), str(OUTPUT)]

    print(f"Input:  {INPUT}")
    print(f"Output: {OUTPUT}")
    print(f"Preset: {PRESET}\n")
    print("Running kikit...")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\nkikit failed.", file=sys.stderr)
        sys.exit(result.returncode)

    print(f"\nPanel written to: {OUTPUT}")


if __name__ == "__main__":
    main()
