#!/usr/bin/env python3
"""Fuzzy search across all KiCad symbol libraries."""

import re
import sys
from pathlib import Path

SEARCH_DIRS = [
    Path.home() / "KiCad",
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
]


def iter_symbols(lib_file: Path):
    """Yield (lib_name, symbol_name, props_dict) for every symbol in a .kicad_sym file."""
    try:
        text = lib_file.read_text(errors="replace")
    except OSError:
        return

    lib_name = lib_file.stem

    # Top-level symbol blocks (not sub-symbols like Foo_0_1)
    for m in re.finditer(r'\(symbol "([^"_][^"]*(?<!_\d))"', text):
        name = m.group(1)
        # Skip internal sub-symbols (name contains _0_ or _1_ pattern at end)
        if re.search(r'_\d+_\d+$', name):
            continue

        start = m.start()
        # Grab a window of text for property extraction (next top-level symbol or EOF)
        next_sym = text.find('\n  (symbol "', start + 1)
        block = text[start: next_sym if next_sym != -1 else start + 4000]

        props = dict(re.findall(r'"(Value|Footprint|MPN|Manufacturer|Description|LCSC Part)"\s+"([^"]+)"', block))
        yield lib_name, name, props


def score(query: str, lib: str, sym: str, props: dict) -> int:
    """Return a relevance score; higher = better match. 0 = no match."""
    tokens = query.lower().split()
    haystack = " ".join([
        sym,
        props.get("MPN", ""),
        props.get("Value", ""),
        props.get("Description", ""),
        props.get("LCSC Part", ""),
        lib,
    ]).lower()

    # All tokens must appear somewhere
    if not all(t in haystack for t in tokens):
        return 0

    # Score based on how well the full query matches a single field
    q = query.lower()
    fields = [
        sym.lower(),
        props.get("MPN", "").lower(),
        props.get("Value", "").lower(),
        props.get("LCSC Part", "").lower(),
        props.get("Description", "").lower(),
        lib.lower(),
    ]
    best = 10  # base: all tokens matched
    for f in fields:
        if not f:
            continue
        if q == f:
            best = max(best, 100)
        elif f.startswith(q):
            best = max(best, 80)
        elif q in f:
            best = max(best, 60)
    return best


def search(query: str, limit: int = 20) -> list[tuple[int, str, str, dict]]:
    results = []
    for search_dir in SEARCH_DIRS:
        if not search_dir.exists():
            continue
        for lib_file in sorted(search_dir.glob("*.kicad_sym")):
            for lib_name, sym_name, props in iter_symbols(lib_file):
                s = score(query, lib_name, sym_name, props)
                if s > 0:
                    results.append((s, lib_name, sym_name, props))

    results.sort(key=lambda x: -x[0])
    return results[:limit]


def main():
    if len(sys.argv) < 2:
        print("Usage: find_part.py <search term>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"Searching for: {query!r}\n")
    results = search(query)

    if not results:
        print("No matches found.")
        return

    for s, lib, sym, props in results:
        lcsc = props.get("LCSC Part", "")
        fp   = props.get("Footprint", "")
        desc = props.get("Description", props.get("MPN", ""))
        lcsc_str = f"  LCSC: {lcsc}" if lcsc else ""
        print(f"[{s:3d}] {lib}:{sym}")
        if desc:
            print(f"       {desc}")
        if fp:
            print(f"       Footprint: {fp}")
        if lcsc_str:
            print(f"      {lcsc_str}")
        print()


if __name__ == "__main__":
    main()
