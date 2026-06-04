#!/usr/bin/env python3
"""Table formatting helpers for price output."""

COL_W = 13   # column width for price cells


def fmt_price(price: float | None, estimated: bool = False) -> str:
    if price is None:
        return f"{'—':>{COL_W}}"
    marker = "~" if estimated else " "
    return f"{marker}${price:>{COL_W-2}.2f}"


def fmt_cpu(price: float | None, boards: int, estimated: bool = False) -> str:
    if price is None or boards == 0:
        return f"{'—':>{COL_W}}"
    marker = "~" if estimated else " "
    return f"{marker}${price/boards:>{COL_W-2}.2f}"


def print_table(title: str, variants, quantities, fmt_fn, col_w: int = COL_W):
    """Print a qty × variant price table using fmt_fn(qty, variant_str)."""
    sep = "  "
    hdr = f"{'Qty':>5}{sep}" + sep.join(f"{v:>{col_w}}" for v, *_ in variants)
    bar = "═" * len(hdr)
    print(f"\n{bar}\n{title}\n{bar}")
    print(hdr)
    print("─" * len(hdr))
    for qty in quantities:
        cells = sep.join(fmt_fn(qty, v) for v, *_ in variants)
        print(f"{qty:>5}{sep}{cells}")
    print(f"  ~ = estimated from model")
