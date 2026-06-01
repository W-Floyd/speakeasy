#!/usr/bin/env python3
"""Generate JLCPCB fabrication outputs from the hand-placed PCB.

Outputs written to speakeasy/jlcpcb/:
  - Gerbers + drill files (zipped)
  - CPL CSV  (component placement list for SMT assembly)

The JLCPCB BOM is written separately by generate.py → speakeasy_jlcpcb_bom.csv.

Run with:
  uv run python circuit-synth/fab_jlcpcb.py
"""

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import deterministic_zip

ROOT   = Path(__file__).parent.parent / "speakeasy"
PCB       = ROOT / "Speakeasy.kicad_pcb"
PANEL_PCB = ROOT / "Speakeasy_panel.kicad_pcb"
OUTDIR = ROOT / "jlcpcb"

KICAD_CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")

# JLCPCB-required Gerber layers
GERBER_LAYERS = ",".join([
    "F.Cu", "B.Cu",
    "F.Paste", "B.Paste",
    "F.Silkscreen", "B.Silkscreen",
    "F.Mask", "B.Mask",
    "Edge.Cuts",
    "F.Courtyard", "B.Courtyard",
])


_DATE_RE = re.compile(
    rb'^(G04 (#@! TF\.CreationDate,|Created by KiCad.*date )|; (#@! TF\.CreationDate,|DRILL file KiCad.*date )).*\r?\n',
    re.MULTILINE
)
_JSON_DATE_RE = re.compile(rb'"CreationDate"\s*:\s*"[^"]*"')


def run(cmd, label):
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n{label} failed.", file=sys.stderr)
        sys.exit(result.returncode)


def export_gerbers(pcb: Path, gerber_dir: Path, zip_path: Path):
    """Export Gerbers + drill for a PCB and zip them deterministically."""
    gerber_dir.mkdir(parents=True, exist_ok=True)

    run([
        str(KICAD_CLI), "pcb", "export", "gerbers",
        "--output", str(gerber_dir),
        "--layers", GERBER_LAYERS,
        "--no-x2", "--no-netlist",
        str(pcb),
    ], "Gerber export")

    run([
        str(KICAD_CLI), "pcb", "export", "drill",
        "--output", str(gerber_dir) + "/",
        "--format", "excellon",
        "--excellon-units", "mm",
        str(pcb),
    ], "Drill export")

    for f in gerber_dir.iterdir():
        data = _DATE_RE.sub(b'', f.read_bytes())
        data = _JSON_DATE_RE.sub(b'"CreationDate": ""', data)
        f.write_bytes(data)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(gerber_dir.iterdir()):
            deterministic_zip.add_file(zf, f, f.name)
    print(f"Gerbers zipped: {zip_path.name}  ({len(list(gerber_dir.iterdir()))} files)")


def main():
    for path, label in [(PCB, "PCB"), (KICAD_CLI, "kicad-cli")]:
        if not path.exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            sys.exit(1)

    # ── Single board Gerbers ──────────────────────────────────────────────────
    print("Exporting Gerbers (single board)...")
    export_gerbers(PCB, OUTDIR / "gerbers", OUTDIR / "Speakeasy_gerbers.zip")

    # ── Panel Gerbers ─────────────────────────────────────────────────────────
    if PANEL_PCB.exists():
        print("Exporting Gerbers (panel)...")
        export_gerbers(PANEL_PCB, OUTDIR / "gerbers_panel", OUTDIR / "Speakeasy_panel_gerbers.zip")
    else:
        print(f"Panel PCB not found, skipping: {PANEL_PCB.name}")

    # ── CPL (component placement list) ────────────────────────────────────────
    print("Exporting CPL...")
    cpl_path = OUTDIR / "Speakeasy_cpl.csv"
    run([
        str(KICAD_CLI), "pcb", "export", "pos",
        "--output", str(cpl_path),
        "--format", "csv",
        "--units", "mm",
        "--side", "both",
        "--smd-only",
        "--exclude-dnp",
        str(PCB),
    ], "CPL export")

    # Remap headers and normalize for JLCPCB
    import csv, io
    rows = list(csv.reader(cpl_path.read_text().splitlines()))
    header = rows[0]
    header = ["Designator" if h == "Ref" else
              "Mid X"      if h == "PosX" else
              "Mid Y"      if h == "PosY" else
              "Rotation"   if h == "Rot" else
              "Layer"      if h == "Side" else h
              for h in header]
    rot_idx   = header.index("Rotation")
    layer_idx = header.index("Layer")
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows[1:]:
        row[rot_idx]   = str(float(row[rot_idx]) % 360)
        row[layer_idx] = row[layer_idx].capitalize()
        writer.writerow(row)
    cpl_path.write_text(out.getvalue())

    print(f"\nOutputs written to: {OUTDIR}")
    for f in sorted(OUTDIR.iterdir()):
        if f.is_file():
            print(f"  {f.name}")
    print(f"\nUpload to JLCPCB:")
    print(f"  Single board:  Speakeasy_gerbers.zip + speakeasy_jlcpcb_bom.csv + Speakeasy_cpl.csv")
    print(f"  Panel:         Speakeasy_panel_gerbers.zip")


if __name__ == "__main__":
    main()
