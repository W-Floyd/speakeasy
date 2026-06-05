#!/usr/bin/env python3
"""Bare-board PCB fabrication cost model.

Covers:
  - Parsing KiCad Edge.Cuts dimensions
  - Deriving per-board material cost from known JLCPCB breakdown quotes
  - Estimating PCB order cost for any (variant, qty) combination

Model: total_cost = eng_fee + board_material_per_panel_board × cols × rows × qty
  eng_fee = $4.00 fixed per order
  board_material_per_panel_board ≈ $0.170  (calibrated from 2x3 and 3x3 quotes)
"""

import re
from pathlib import Path

ENG_FEE_DEFAULT      = 4.00   # $ fixed per order
BM_PER_BOARD_DEFAULT = 0.170  # $ board material per board-in-panel


def parse_variant(v: str) -> tuple[int, int]:
    """Parse '2x3' → (cols=2, rows=3)."""
    parts = v.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"Invalid variant '{v}' — use COLSxROWS")
    return int(parts[0]), int(parts[1])


def _extract_blocks(text: str, tag: str) -> list[str]:
    """Extract all top-level S-expression blocks starting with `(tag`."""
    blocks = []
    i = 0
    pat = re.compile(r'\(' + re.escape(tag) + r'\b')
    while True:
        m = pat.search(text, i)
        if not m:
            break
        depth, start = 0, m.start()
        for j in range(start, len(text)):
            if text[j] == '(':
                depth += 1
            elif text[j] == ')':
                depth -= 1
                if depth == 0:
                    blocks.append(text[start:j+1])
                    i = j + 1
                    break
        else:
            break
    return blocks


def read_pcb_dimensions(pcb_path: Path) -> tuple[float, float]:
    """Return (width_mm, height_mm) from the Edge.Cuts bounding box."""
    text = pcb_path.read_text(errors="replace")
    xs, ys = [], []
    for tag in ("gr_line", "gr_arc", "gr_rect", "gr_poly", "gr_circle"):
        for block in _extract_blocks(text, tag):
            if '"Edge.Cuts"' not in block:
                continue
            if tag == "gr_circle":
                # bounding box = center ± radius
                cm = re.search(r'\(center\s+([\d.+-]+)\s+([\d.+-]+)', block)
                em = re.search(r'\(end\s+([\d.+-]+)\s+([\d.+-]+)', block)
                if cm and em:
                    cx, cy = float(cm.group(1)), float(cm.group(2))
                    r = ((float(em.group(1)) - cx) ** 2 + (float(em.group(2)) - cy) ** 2) ** 0.5
                    xs += [cx - r, cx + r]
                    ys += [cy - r, cy + r]
            else:
                for m in re.finditer(r'\((?:start|end|xy)\s+([\d.+-]+)\s+([\d.+-]+)', block):
                    xs.append(float(m.group(1)))
                    ys.append(float(m.group(2)))
    if not xs:
        raise ValueError(f"Could not parse Edge.Cuts from {pcb_path}")
    return round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)


def fit_pcb_model(pcb_quotes: dict) -> tuple[float, float, int]:
    """
    Derive board-material cost per board-in-panel from known quote breakdowns.

    Expects pcb_quotes[variant] entries with:
      {"qty": N, "price": X, "breakdown": {"engineering_fee": F, "board": B}}

    Returns (eng_fee, bm_per_board, n_samples).
    Falls back to (ENG_FEE_DEFAULT, BM_PER_BOARD_DEFAULT, 0) when no data.
    """
    bm_samples = []
    for v_key, entries in pcb_quotes.items():
        if v_key.startswith("_") or not isinstance(entries, list):
            continue
        cols, rows = parse_variant(v_key)
        boards_per_panel = cols * rows
        for e in entries:
            if "breakdown" in e and e["qty"] > 0:
                bm_per_panel = e["breakdown"]["board"] / e["qty"]
                bm_samples.append(bm_per_panel / boards_per_panel)
    bm = sum(bm_samples) / len(bm_samples) if bm_samples else BM_PER_BOARD_DEFAULT
    return ENG_FEE_DEFAULT, bm, len(bm_samples)


def pcb_cost(eng_fee: float, bm_per_board: float,
             cols: int, rows: int, qty: int) -> float:
    """Total bare-board PCB order cost for `qty` panels of a COLSxROWS variant."""
    return eng_fee + bm_per_board * cols * rows * qty
