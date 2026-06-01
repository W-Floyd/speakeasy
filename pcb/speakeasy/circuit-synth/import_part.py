#!/usr/bin/env python3
"""Import an EasyEDA/LCSC part into the local KiCad library via KiCadImport CLI."""

import subprocess
import sys
from pathlib import Path

PLUGIN_DIR = Path.home() / "Documents/KiCad/10.0/3rdparty/plugins/com_github_Steffen-W_impartGUI"
LIB_FOLDER = Path.home() / "KiCad"
LIB_NAME   = "EasyEDA"


def import_part(lcsc: str, overwrite: bool = False) -> bool:
    cmd = [
        sys.executable, "-m", "KiCadImport",
        "--easyeda", lcsc,
        "--lib-folder", str(LIB_FOLDER),
        "--lib-name", LIB_NAME,
    ]
    if overwrite:
        cmd.append("--overwrite-if-exists")

    result = subprocess.run(cmd, cwd=PLUGIN_DIR, capture_output=True, text=True)
    output = result.stdout + result.stderr
    print(output.strip())
    return result.returncode == 0


def main():
    if len(sys.argv) < 2:
        print("Usage: import_part.py <LCSC_part_number> [...] [--overwrite]")
        sys.exit(1)

    parts   = [a for a in sys.argv[1:] if not a.startswith("--")]
    overwrite = "--overwrite" in sys.argv

    ok, failed = 0, []
    for part in parts:
        print(f"\nImporting {part}...")
        if import_part(part, overwrite=overwrite):
            ok += 1
        else:
            failed.append(part)

    print(f"\n{ok}/{len(parts)} imported successfully.")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
