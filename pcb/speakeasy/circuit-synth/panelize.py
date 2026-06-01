#!/usr/bin/env python3
"""Panelize the Speakeasy PCB using KiKit.

Reads:  speakeasy/Speakeasy.kicad_pcb  (hand-made, never overwritten)
Writes: speakeasy/Speakeasy_panel_<cols>x<rows>.kicad_pcb

Usage:
    python panelize.py           # generate all variants: 2x2, 2x3, 3x3
    python panelize.py 2x2       # generate a single variant
    python panelize.py 2x3 3x3   # generate specific variants

Edit panel_preset.json to change layout parameters (rows/cols are overridden per variant).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT   = Path(__file__).parent.parent / "speakeasy"
INPUT  = ROOT / "Speakeasy.kicad_pcb"
PRESET = Path(__file__).parent / "panel_preset.json"

KIKIT = Path(
    "/Applications/KiCad/KiCad.app/Contents/Frameworks"
    "/Python.framework/Versions/3.9/bin/kikit"
)

ALL_VARIANTS = ["2x2", "2x3", "3x3"]


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


def parse_variant(variant: str) -> tuple[int, int]:
    parts = variant.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"Invalid variant '{variant}' — expected COLSxROWS (e.g. 2x3)")
    cols, rows = int(parts[0]), int(parts[1])
    return cols, rows


def panelize(cols: int, rows: int) -> bool:
    output = ROOT / f"Speakeasy_panel_{cols}x{rows}.kicad_pcb"

    with open(PRESET) as f:
        preset = json.load(f)

    preset.setdefault("layout", {})
    preset["layout"]["cols"] = cols
    preset["layout"]["rows"] = rows

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=Path(__file__).parent
    ) as tf:
        json.dump(preset, tf, indent=2)
        tmp_preset = Path(tf.name)

    try:
        cmd = [
            str(KIKIT), "panelize",
            "-p", str(tmp_preset),
            "--debug", "deterministic: true",
            str(INPUT), str(output),
        ]
        print(f"\n--- {cols}x{rows} panel ---")
        print(f"Output: {output}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"kikit failed for {cols}x{rows}.", file=sys.stderr)
            return False
        print(f"Written: {output}")
        return True
    finally:
        tmp_preset.unlink(missing_ok=True)


def main():
    args = sys.argv[1:]
    variants = args if args else ALL_VARIANTS

    for path, label in [(INPUT, "source PCB"), (KIKIT, "kikit"), (PRESET, "preset")]:
        if not path.exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            sys.exit(1)

    pro_path = INPUT.with_suffix(".kicad_pro")
    if pro_path.exists():
        ensure_net_settings(pro_path)

    failed = []
    for v in variants:
        try:
            cols, rows = parse_variant(v)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            failed.append(v)
            continue
        if not panelize(cols, rows):
            failed.append(v)

    if failed:
        print(f"\nFailed variants: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)
    print(f"\nDone — {len(variants)} panel(s) generated.")


if __name__ == "__main__":
    main()
