#!/usr/bin/env python3
"""Look up a part in the local EasyEDA KiCad symbol library by LCSC part number."""

import json
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
    raw_pins = re.findall(
        r'\(pin \w+ \w+.*?\(name "([^"]+)".*?\(number "([^"]+)"',
        block,
        re.DOTALL,
    )
    pins = [{"number": int(num), "name": name} for name, num in raw_pins]

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

    results = []
    for part in sys.argv[1:]:
        result = lookup(part)
        if result is None:
            results.append({"lcsc": part, "error": f"not found in {EASYEDA_LIB}"})
        else:
            results.append(result)

    print(json.dumps(results if len(results) > 1 else results[0], indent=2))


if __name__ == "__main__":
    main()
