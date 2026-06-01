#!/usr/bin/env python3
"""Look up a part in the local EasyEDA KiCad symbol library by LCSC part number."""

import re
import sys
from pathlib import Path

EASYEDA_LIB = Path.home() / "KiCad" / "EasyEDA.kicad_sym"


def lookup(lcsc: str) -> dict | None:
    content = EASYEDA_LIB.read_text()

    idx = content.find(lcsc)
    if idx == -1:
        return None

    sym_start = content.rfind("\n  (symbol ", 0, idx)
    sym_end = content.find("\n  (symbol ", idx)
    block = content[sym_start:sym_end if sym_end != -1 else len(content)]

    sym_name = re.search(r'\(symbol "([^"]+)"', block)
    props = dict(re.findall(r'"(Reference|Value|Footprint|MPN|Manufacturer|Datasheet)"\s+"([^"]+)"', block))
    pins = re.findall(r'\(pin \w+ \w+\s*\(at [^)]+\)\s*\(length [^)]+\)\s*\(name "([^"]+)"', block)

    return {
        "symbol": sym_name.group(1) if sym_name else None,
        "lcsc": lcsc,
        **props,
        "pins": pins,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: lookup_part.py <LCSC_part_number> [...]")
        sys.exit(1)

    for part in sys.argv[1:]:
        result = lookup(part)
        if result is None:
            print(f"{part}: not found in {EASYEDA_LIB}")
            continue
        print(f"\n{'─'*50}")
        print(f"LCSC:         {result['lcsc']}")
        print(f"Symbol:       {result['symbol']}")
        print(f"MPN:          {result.get('MPN', '—')}")
        print(f"Manufacturer: {result.get('Manufacturer', '—')}")
        print(f"Value:        {result.get('Value', '—')}")
        print(f"Footprint:    {result.get('Footprint', '—')}")
        print(f"Datasheet:    {result.get('Datasheet', '—')}")
        print(f"Pins:         {', '.join(result['pins'])}")


if __name__ == "__main__":
    main()
