#!/usr/bin/env python3
"""HTML report generator for the JLCPCB panel cost optimizer.

Called from price_calculator.py after all data is computed:

    from report import generate_report
    generate_report(report_data, output_path)

Writes a self-contained HTML file with Chart.js visualisations.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


# ── Palette ────────────────────────────────────────────────────────────────────

VARIANT_COLORS = {
    "1x1": "#60a5fa",
    "2x2": "#34d399",
    "2x3": "#fbbf24",
    "3x3": "#f87171",
}

SEGMENT_COLORS = [
    "#60a5fa",  # Components
    "#34d399",  # Assembly
    "#fbbf24",  # PCB bare board
    "#fb923c",  # Import duty
    "#38bdf8",  # Shipping
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _js(obj) -> str:
    """Serialize Python object to JavaScript literal (JSON-compatible)."""
    return json.dumps(obj, ensure_ascii=False)


def _fmt(v: float | None, prefix: str = "") -> str:
    if v is None:
        return "—"
    return f"{prefix}${v:.2f}"


def _safe(v: float | None) -> str:
    """Return a JS-safe number literal or null."""
    if v is None:
        return "null"
    return f"{v:.4f}"


def _truncate(s: str, n: int = 20) -> str:
    return s[:n] + "…" if len(s) > n else s


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_report(report_data: dict, output_path: Path) -> None:
    """Generate a self-contained HTML cost report and write it to output_path."""

    meta          = report_data["meta"]
    variants      = report_data["variants"]
    quantities    = report_data["quantities"]
    fab_results   = report_data["fab_results"]
    pcb_results   = report_data["pcb_results"]
    ship_results  = report_data["ship_results"]
    bom_breakdown = report_data["bom_breakdown"]
    preferred     = report_data.get("preferred_ship", "")

    pcb_w          = meta.get("pcb_w")
    pcb_l          = meta.get("pcb_l")
    assembly_type  = meta.get("assembly_type", "Economy")
    n_extended     = meta.get("n_extended", 0)
    standard_only  = meta.get("standard_only", [])
    duty_rate      = meta.get("import_duty_rate", 0.0)
    bm_per_board   = meta.get("bm_per_board")
    eng_fee        = meta.get("eng_fee")

    today = date.today().strftime("%B %d, %Y")

    # ── Pre-compute summary stats ──────────────────────────────────────────────

    best_landed_val  = None
    best_landed_cfg  = ""
    best_pcba_val    = None
    best_pcba_cfg    = ""
    dominant_label   = "N/A"
    dominant_cfg     = ""

    for qty in quantities:
        for v in variants:
            bb = bom_breakdown.get(qty, {}).get(v)
            if bb is None:
                continue
            lp = bb.get("landed_per_board")
            if lp is not None:
                if best_landed_val is None or lp < best_landed_val:
                    best_landed_val = lp
                    best_landed_cfg = f"{qty} panels × {v}"
            fa_price, actual, est = fab_results.get(qty, {}).get(v, (None, 1, False))
            if fa_price is not None and actual:
                pcba_pb = fa_price / actual
                if best_pcba_val is None or pcba_pb < best_pcba_val:
                    best_pcba_val = pcba_pb
                    best_pcba_cfg = f"{qty} panels × {v}"

    # Find dominant cost at best qty/variant
    if best_landed_cfg:
        best_qty_str, best_var_str = best_landed_cfg.split(" panels × ")
        best_qty = int(best_qty_str.strip())
        best_var = best_var_str.strip()
        bb = bom_breakdown.get(best_qty, {}).get(best_var, {})
        if bb:
            segments = {
                "Components":      bb.get("component_cost_per_board") or 0.0,
                "Assembly labor":  bb.get("assembly_labor_per_board") or 0.0,
                "PCB bare board":  bb.get("pcb_per_board") or 0.0,
                "Extended fees":   bb.get("ext_fee_per_board") or 0.0,
                "Standard base":   bb.get("std_base_per_board") or 0.0,
                "Import duty":     (bb.get("pcba_price_total") or 0.0) / (bb.get("total_boards") or 1) * duty_rate,
                "Shipping":        (bb.get("ship_cost") or 0.0) / (bb.get("total_boards") or 1),
            }
            if any(segments.values()):
                dominant_label = max(segments, key=segments.get)
                dominant_cfg   = best_landed_cfg

    # ── Build landed table data for JS ─────────────────────────────────────────

    landed_table_rows = []
    for qty in quantities:
        row = {"qty": qty, "cells": []}
        row_vals = []
        for v in variants:
            bb = bom_breakdown.get(qty, {}).get(v)
            if bb:
                lp  = bb.get("landed_per_board")
                est = fab_results.get(qty, {}).get(v, (None, 1, False))[2]
            else:
                lp, est = None, False
            row_vals.append(lp)
            row["cells"].append({"val": lp, "est": est})
        # find min (not None)
        valid = [v for v in row_vals if v is not None]
        row["min_val"] = min(valid) if valid else None
        landed_table_rows.append(row)

    # ── Build PCBA table data ──────────────────────────────────────────────────

    pcba_table_rows = []
    for qty in quantities:
        row = {"qty": qty, "cells": []}
        for v in variants:
            fa_price, actual, est = fab_results.get(qty, {}).get(v, (None, 1, False))
            if fa_price is not None and actual:
                val = fa_price / actual
            else:
                val = None
            row["cells"].append({"val": val, "est": est})
        pcba_table_rows.append(row)

    # ── Build PCB table data ───────────────────────────────────────────────────

    pcb_table_rows = []
    for qty in quantities:
        row = {"qty": qty, "cells": []}
        for v in variants:
            pr, est = pcb_results.get(qty, {}).get(v, (None, False))
            bb = bom_breakdown.get(qty, {}).get(v) or {}
            actual = bb.get("total_boards") or (qty * int(v.split("x")[0]) * int(v.split("x")[1]) if "x" in v else 1)
            val = (pr / actual) if (pr is not None and actual) else None
            row["cells"].append({"val": val, "est": est})
        pcb_table_rows.append(row)

    # ── Line chart dataset (landed $/board vs qty, one line per variant) ───────

    line_datasets = []
    for v in variants:
        color = VARIANT_COLORS.get(v, "#ffffff")
        points = []
        for qty in quantities:
            bb = bom_breakdown.get(qty, {}).get(v)
            lp = bb.get("landed_per_board") if bb else None
            points.append(lp)
        line_datasets.append({
            "label":           v,
            "data":            points,
            "borderColor":     color,
            "backgroundColor": color + "33",
            "tension":         0.3,
            "spanGaps":        True,
        })

    # ── Stacked bar and pie chart: data by qty selector ────────────────────────
    # We'll pass the full breakdown dict to JS and let it rebuild on selector change.

    # Serialize bom_breakdown for JS: convert keys to strings for JSON
    bom_breakdown_js: dict = {}
    for qty in quantities:
        bom_breakdown_js[str(qty)] = {}
        for v in variants:
            bb = bom_breakdown.get(qty, {}).get(v)
            if bb:
                bom_breakdown_js[str(qty)][v] = bb
            else:
                bom_breakdown_js[str(qty)][v] = None

    # Median qty as default selector
    median_qty = quantities[len(quantities) // 2]

    # ── BOM table: collect lines from first available qty+variant combo ────────
    # We take lines from median qty and best variant, or any available combo.
    bom_lines_display: list[dict] = []
    found_bom = False
    for qty in [median_qty] + quantities:
        for v in variants:
            bb = bom_breakdown.get(qty, {}).get(v)
            if bb and bb.get("line_items"):
                bom_lines_display = bb["line_items"]
                found_bom = True
                break
        if found_bom:
            break

    # ── Build HTML ─────────────────────────────────────────────────────────────
    html = _build_html(
        today=today,
        pcb_w=pcb_w,
        pcb_l=pcb_l,
        assembly_type=assembly_type,
        n_extended=n_extended,
        standard_only=standard_only,
        duty_rate=duty_rate,
        bm_per_board=bm_per_board,
        eng_fee=eng_fee,
        preferred=preferred,
        variants=variants,
        quantities=quantities,
        median_qty=median_qty,
        best_landed_val=best_landed_val,
        best_landed_cfg=best_landed_cfg,
        best_pcba_val=best_pcba_val,
        best_pcba_cfg=best_pcba_cfg,
        dominant_label=dominant_label,
        dominant_cfg=dominant_cfg,
        landed_table_rows=landed_table_rows,
        pcba_table_rows=pcba_table_rows,
        pcb_table_rows=pcb_table_rows,
        line_datasets=line_datasets,
        bom_breakdown_js=bom_breakdown_js,
        bom_lines_display=bom_lines_display,
    )

    output_path.write_text(html, encoding="utf-8")
    print(f"  Report written to {output_path}")


# ── HTML builder ───────────────────────────────────────────────────────────────

def _build_html(
    today, pcb_w, pcb_l, assembly_type, n_extended, standard_only,
    duty_rate, bm_per_board, eng_fee, preferred,
    variants, quantities, median_qty,
    best_landed_val, best_landed_cfg,
    best_pcba_val, best_pcba_cfg,
    dominant_label, dominant_cfg,
    landed_table_rows, pcba_table_rows, pcb_table_rows,
    line_datasets, bom_breakdown_js, bom_lines_display,
) -> str:

    dim_str  = f"{pcb_w} × {pcb_l} mm" if pcb_w and pcb_l else "unknown"
    duty_str = f"{duty_rate*100:.1f}%" if duty_rate else "0%"

    # Serialise all Python data to JS-safe JSON strings once
    js_variants        = _js(variants)
    js_quantities      = _js(quantities)
    js_median_qty      = _js(median_qty)
    js_line_datasets   = _js(line_datasets)
    js_bom_breakdown   = _js(bom_breakdown_js)
    js_bom_lines       = _js(bom_lines_display)
    js_duty_rate       = _js(duty_rate)
    js_preferred       = _js(preferred)

    # ── Landed table HTML ──────────────────────────────────────────────────────
    landed_thead_cells = "".join(f"<th>{v}</th>" for v in variants)
    landed_tbody = ""
    for row in landed_table_rows:
        cells_html = ""
        for i, cell in enumerate(row["cells"]):
            val = cell["val"]
            est = cell["est"]
            is_min = (val is not None and row["min_val"] is not None
                      and abs(val - row["min_val"]) < 1e-6)
            if val is None:
                cell_str = "—"
                cls = "cell-missing"
            else:
                prefix = "~" if est else ""
                cell_str = f"{prefix}${val:.2f}"
                cls = "cell-best" if is_min else ("cell-est" if est else "")
            cells_html += f'<td class="{cls}">{cell_str}</td>'
        landed_tbody += f"<tr><td class='col-qty'>{row['qty']}</td>{cells_html}</tr>\n"

    # ── PCBA table HTML ────────────────────────────────────────────────────────
    pcba_thead_cells = landed_thead_cells
    pcba_tbody = ""
    for row in pcba_table_rows:
        cells_html = ""
        for cell in row["cells"]:
            val = cell["val"]
            est = cell["est"]
            if val is None:
                cell_str, cls = "—", "cell-missing"
            else:
                prefix = "~" if est else ""
                cell_str = f"{prefix}${val:.2f}"
                cls = "cell-est" if est else ""
            cells_html += f'<td class="{cls}">{cell_str}</td>'
        pcba_tbody += f"<tr><td class='col-qty'>{row['qty']}</td>{cells_html}</tr>\n"

    # ── PCB table HTML ─────────────────────────────────────────────────────────
    pcb_tbody = ""
    for row in pcb_table_rows:
        cells_html = ""
        for cell in row["cells"]:
            val = cell["val"]
            est = cell["est"]
            if val is None:
                cell_str, cls = "—", "cell-missing"
            else:
                prefix = "~" if est else ""
                cell_str = f"{prefix}${val:.2f}"
                cls = "cell-est" if est else ""
            cells_html += f'<td class="{cls}">{cell_str}</td>'
        pcb_tbody += f"<tr><td class='col-qty'>{row['qty']}</td>{cells_html}</tr>\n"

    # ── BOM table HTML ─────────────────────────────────────────────────────────
    bom_tbody = ""
    for line in bom_lines_display:
        lcsc      = line.get("lcsc", "")
        desc      = line.get("desc", "")
        qty_pb    = line.get("qty_per_board", "")
        lib_type  = line.get("lib_type", "Basic")
        unit_p    = line.get("unit_price")
        line_tot  = line.get("line_total")
        so        = line.get("standard_only", False)

        unit_str  = f"${unit_p:.4f}" if unit_p is not None else "—"
        line_str  = f"${line_tot:.4f}" if line_tot is not None else "—"
        row_cls   = "bom-extended" if lib_type == "Extended" else ""
        so_badge  = " <span class='badge-warn'>⚠ Std Only</span>" if so else ""
        lib_badge = (f"<span class='badge-ext'>Extended</span>"
                     if lib_type == "Extended"
                     else f"<span class='badge-basic'>Basic</span>")

        bom_tbody += (
            f"<tr class='{row_cls}'>"
            f"<td class='mono'>{lcsc}</td>"
            f"<td>{desc}{so_badge}</td>"
            f"<td class='num'>{qty_pb}</td>"
            f"<td>{lib_badge}</td>"
            f"<td class='num mono'>{unit_str}</td>"
            f"<td class='num mono'>{line_str}</td>"
            f"</tr>\n"
        )

    # ── Qty selector options ───────────────────────────────────────────────────
    qty_options = "".join(
        f'<option value="{q}"{" selected" if q == median_qty else ""}>{q} panels</option>'
        for q in quantities
    )

    # ── Summary card values ────────────────────────────────────────────────────
    card_landed = _fmt(best_landed_val) if best_landed_val is not None else "N/A"
    card_pcba   = _fmt(best_pcba_val)   if best_pcba_val   is not None else "N/A"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Speakeasy PCB Cost Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  /* ── Reset & base ── */
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ font-size: 15px; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0d1117;
    color: #e2e8f0;
    line-height: 1.55;
    padding: 0 0 60px;
  }}

  /* ── Typography ── */
  h1, h2, h3 {{ font-weight: 600; letter-spacing: -0.01em; }}
  h2 {{ font-size: 1.1rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 14px; }}
  h3 {{ font-size: 0.95rem; color: #64748b; letter-spacing: 0.04em; }}
  a {{ color: #60a5fa; }}

  /* ── Layout ── */
  .page {{ max-width: 1100px; margin: 0 auto; padding: 0 24px; }}

  /* ── Header ── */
  .header {{
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border-bottom: 1px solid #1e3a5f;
    padding: 36px 24px 28px;
    margin-bottom: 36px;
  }}
  .header-inner {{ max-width: 1100px; margin: 0 auto; }}
  .header h1 {{
    font-size: 1.85rem;
    color: #f1f5f9;
    margin-bottom: 10px;
  }}
  .header h1 span {{ color: #60a5fa; }}
  .meta-row {{
    display: flex; flex-wrap: wrap; gap: 20px;
    margin-top: 12px;
    font-size: 0.85rem;
    color: #64748b;
  }}
  .meta-item {{ display: flex; gap: 6px; }}
  .meta-label {{ color: #94a3b8; }}
  .meta-value {{ color: #cbd5e1; font-weight: 500; }}

  /* ── Summary cards ── */
  .cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 36px; }}
  @media (max-width: 700px) {{ .cards {{ grid-template-columns: 1fr; }} }}
  .card {{
    background: #161f2e;
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 20px 22px;
  }}
  .card-label {{ font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 6px; }}
  .card-value {{ font-size: 2rem; font-weight: 700; color: #f1f5f9; font-variant-numeric: tabular-nums; }}
  .card-sub {{ font-size: 0.78rem; color: #475569; margin-top: 4px; }}
  .card-accent-green .card-value {{ color: #34d399; }}
  .card-accent-blue  .card-value {{ color: #60a5fa; }}
  .card-accent-amber .card-value {{ color: #fbbf24; }}

  /* ── Section wrapper ── */
  .section {{ margin-bottom: 40px; }}

  /* ── Tables ── */
  .table-wrap {{ overflow-x: auto; border-radius: 8px; border: 1px solid #1e293b; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  thead th {{
    background: #1e293b;
    color: #94a3b8;
    font-weight: 600;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 10px 14px;
    text-align: right;
    white-space: nowrap;
  }}
  thead th:first-child {{ text-align: left; }}
  tbody tr {{ border-bottom: 1px solid #1a2535; }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: #131c29; }}
  td {{
    padding: 9px 14px;
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }}
  td:first-child {{ text-align: left; }}
  .col-qty {{ color: #64748b; font-weight: 500; }}
  .cell-best {{ color: #34d399; font-weight: 700; }}
  .cell-est  {{ color: #94a3b8; }}
  .cell-missing {{ color: #374151; }}
  .num  {{ text-align: right; }}
  .mono {{ font-family: "SF Mono", "Fira Code", "Consolas", monospace; font-size: 0.83rem; }}

  /* ── BOM table variants ── */
  .bom-extended {{ background: #1a1400; }}
  .bom-extended:hover {{ background: #211900; }}
  .badge-ext  {{ background: #78350f; color: #fcd34d; border-radius: 4px; padding: 1px 6px; font-size: 0.72rem; font-weight: 600; }}
  .badge-basic{{ background: #1e293b; color: #64748b;  border-radius: 4px; padding: 1px 6px; font-size: 0.72rem; font-weight: 600; }}
  .badge-warn {{ background: #7c2d12; color: #fca5a5; border-radius: 4px; padding: 1px 6px; font-size: 0.72rem; font-weight: 600; }}

  /* ── Chart containers ── */
  .chart-wrap {{
    background: #0f1923;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 24px;
  }}
  .chart-canvas-wrap {{ position: relative; }}

  /* ── Controls ── */
  .chart-controls {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }}
  .qty-selector {{
    background: #1e293b;
    border: 1px solid #334155;
    color: #e2e8f0;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 0.85rem;
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%2394a3b8' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
    padding-right: 30px;
  }}
  .qty-selector:focus {{ outline: 2px solid #3b82f6; outline-offset: 2px; }}
  .control-label {{ font-size: 0.82rem; color: #64748b; }}

  /* ── Note / legend ── */
  .table-note {{ font-size: 0.75rem; color: #475569; margin-top: 8px; padding: 0 2px; }}
  .legend-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }}

  /* ── Collapsible details ── */
  details {{ border: 1px solid #1e293b; border-radius: 8px; overflow: hidden; margin-bottom: 16px; }}
  summary {{
    background: #161f2e;
    padding: 12px 18px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
    color: #94a3b8;
    list-style: none;
    user-select: none;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  summary::before {{ content: "▶"; font-size: 0.65rem; transition: transform 0.15s; }}
  details[open] summary::before {{ transform: rotate(90deg); }}
  summary::-webkit-details-marker {{ display: none; }}
  details .table-wrap {{ border-radius: 0; border: none; border-top: 1px solid #1e293b; }}

  /* ── Divider ── */
  .divider {{ height: 1px; background: #1e293b; margin: 32px 0; }}

  /* ── Pill/tag ── */
  .pill {{ display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; }}
  .pill-blue  {{ background: #1e3a5f; color: #60a5fa; }}
  .pill-green {{ background: #14432a; color: #34d399; }}
  .pill-amber {{ background: #422006; color: #fbbf24; }}

  /* ── Tooltip legend ── */
  .chart-legend {{ display: flex; flex-wrap: wrap; gap: 10px 18px; margin-top: 14px; font-size: 0.78rem; color: #94a3b8; }}
  .chart-legend-item {{ display: flex; align-items: center; gap: 5px; }}
</style>
</head>
<body>

<!-- ═══════════════════ HEADER ═══════════════════ -->
<div class="header">
  <div class="header-inner">
    <h1><span>Speakeasy</span> PCB Cost Report</h1>
    <div class="meta-row">
      <div class="meta-item"><span class="meta-label">PCB size</span><span class="meta-value">{dim_str}</span></div>
      <div class="meta-item"><span class="meta-label">Assembly</span><span class="meta-value">{assembly_type}</span></div>
      <div class="meta-item"><span class="meta-label">Extended parts</span><span class="meta-value">{n_extended}</span></div>
      <div class="meta-item"><span class="meta-label">Import duty</span><span class="meta-value">{duty_str}</span></div>
      {'<div class="meta-item"><span class="meta-label">Shipping</span><span class="meta-value">' + preferred + '</span></div>' if preferred else ''}
      {'<div class="meta-item"><span class="meta-label">Standard-only parts</span><span class="meta-value">' + ", ".join(standard_only) + '</span></div>' if standard_only else ''}
      <div class="meta-item"><span class="meta-label">Generated</span><span class="meta-value">{today}</span></div>
    </div>
  </div>
</div>

<div class="page">

<!-- ═══════════════════ SUMMARY CARDS ═══════════════════ -->
<div class="section">
  <h2>Summary</h2>
  <div class="cards">
    <div class="card card-accent-green">
      <div class="card-label">Best Landed Cost / Board</div>
      <div class="card-value">{card_landed}</div>
      <div class="card-sub">{best_landed_cfg or "—"}</div>
    </div>
    <div class="card card-accent-blue">
      <div class="card-label">Best PCBA Merch Cost / Board</div>
      <div class="card-value">{card_pcba}</div>
      <div class="card-sub">{best_pcba_cfg or "—"}</div>
    </div>
    <div class="card card-accent-amber">
      <div class="card-label">Dominant Cost Bucket</div>
      <div class="card-value" style="font-size:1.25rem; padding-top:8px">{dominant_label}</div>
      <div class="card-sub">{dominant_cfg or "at best config"}</div>
    </div>
  </div>
</div>

<!-- ═══════════════════ LANDED COST TABLE ═══════════════════ -->
<div class="section">
  <h2>Landed Cost per Board ($/board)</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Panels</th>{landed_thead_cells}</tr></thead>
      <tbody id="landed-tbody">
{landed_tbody}
      </tbody>
    </table>
  </div>
  <p class="table-note">
    <span style="color:#34d399">Green</span> = lowest in row &nbsp;|&nbsp;
    <span style="color:#94a3b8">Grey</span> = estimated from model &nbsp;|&nbsp;
    — = no data &nbsp;|&nbsp;
    ~ prefix = estimated
  </p>
</div>

<!-- ═══════════════════ LINE CHART ═══════════════════ -->
<div class="section">
  <h2>Landed Cost per Board vs Panels Ordered</h2>
  <div class="chart-wrap">
    <div class="chart-canvas-wrap" style="height:320px">
      <canvas id="lineChart"></canvas>
    </div>
    <div class="chart-legend" id="lineChartLegend"></div>
  </div>
</div>

<div class="divider"></div>

<!-- ═══════════════════ STACKED BAR + PIE (shared qty selector) ═══════════════════ -->
<div class="section">
  <div class="chart-controls">
    <span class="control-label">Quantity:</span>
    <select class="qty-selector" id="qtySelector">
      {qty_options}
    </select>
    <span class="control-label" style="color:#475569">Affects breakdown charts and BOM table below</span>
  </div>

  <h2>Cost Breakdown per Board (Stacked)</h2>
  <div class="chart-wrap" style="margin-bottom:24px">
    <div class="chart-canvas-wrap" style="height:360px">
      <canvas id="stackedBar"></canvas>
    </div>
  </div>

  <h2>Component Cost Breakdown (BOM Pie)</h2>
  <div class="chart-wrap">
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: center;">
      <div>
        <div class="chart-controls" style="margin-bottom:8px">
          <span class="control-label">Variant:</span>
          <select class="qty-selector" id="variantSelectorPie">
            <!-- populated by JS -->
          </select>
        </div>
        <div class="chart-canvas-wrap" style="height:300px">
          <canvas id="pieChart"></canvas>
        </div>
      </div>
      <div id="pieLegend" style="font-size:0.8rem; color:#94a3b8; line-height:1.8"></div>
    </div>
  </div>
</div>

<div class="divider"></div>

<!-- ═══════════════════ BOM TABLE ═══════════════════ -->
<div class="section">
  <h2>Bill of Materials</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th style="text-align:left">LCSC</th>
          <th style="text-align:left">Description</th>
          <th>Qty/bd</th>
          <th style="text-align:left">Lib Type</th>
          <th>Unit Price</th>
          <th>$/board</th>
        </tr>
      </thead>
      <tbody id="bom-tbody">
{bom_tbody}
      </tbody>
    </table>
  </div>
  <p class="table-note">
    <span class="badge-ext">Extended</span> parts incur an extra fee per order &nbsp;|&nbsp;
    <span class="badge-warn">⚠ Std Only</span> forces Standard PCBA type
  </p>
</div>

<div class="divider"></div>

<!-- ═══════════════════ PCBA COST TABLE (collapsible) ═══════════════════ -->
<div class="section">
  <details>
    <summary>PCBA Merch Cost per Board (excl. duty / shipping)</summary>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Panels</th>{pcba_thead_cells}</tr></thead>
        <tbody>
{pcba_tbody}
        </tbody>
      </table>
    </div>
    <p class="table-note" style="padding: 8px 14px">Bare PCBA price from JLCPCB. ~ = estimated from model.</p>
  </details>

<!-- ═══════════════════ PCB BARE BOARD TABLE (collapsible) ═══════════════════ -->
  <details>
    <summary>PCB Bare Board Cost per Board (no assembly)</summary>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Panels</th>{landed_thead_cells}</tr></thead>
        <tbody>
{pcb_tbody}
        </tbody>
      </table>
    </div>
    <p class="table-note" style="padding: 8px 14px">
      Engineering fee ${eng_fee:.2f} + ${bm_per_board:.4f}/board-in-panel × boards × panels.
      ~ = estimated from model.
    </p>
  </details>
</div>

</div><!-- .page -->

<!-- ═══════════════════ SCRIPTS ═══════════════════ -->
<script>
(function () {{
  "use strict";

  // ── Data ──────────────────────────────────────────────────────────────────
  const VARIANTS       = {js_variants};
  const QUANTITIES     = {js_quantities};
  const MEDIAN_QTY     = {js_median_qty};
  const LINE_DATASETS  = {js_line_datasets};
  const BOM_BREAKDOWN  = {js_bom_breakdown};
  const BOM_LINES_ALL  = {js_bom_lines};
  const DUTY_RATE      = {js_duty_rate};
  const PREFERRED_SHIP = {js_preferred};

  const VARIANT_COLORS = {{
    "1x1": "#60a5fa",
    "2x2": "#34d399",
    "2x3": "#fbbf24",
    "3x3": "#f87171",
  }};

  const SEG_COLORS = [
    "#60a5fa", // Components
    "#34d399", // Assembly
    "#fbbf24", // PCB bare board
    "#fb923c", // Import duty
    "#38bdf8", // Shipping
  ];

  const SEG_LABELS = [
    "Components",
    "Assembly",
    "PCB bare board",
    "Import duty",
    "Shipping",
  ];

  // ── Chart defaults ─────────────────────────────────────────────────────────
  Chart.defaults.color            = "#64748b";
  Chart.defaults.font.family      = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  Chart.defaults.font.size        = 12;
  Chart.defaults.plugins.legend.labels.color = "#94a3b8";

  const gridColor  = "#1e293b";
  const tickColor  = "#475569";
  const axisColor  = "#1e293b";

  function mkScale(title) {{
    return {{
      grid:  {{ color: gridColor, drawBorder: false }},
      border:{{ color: axisColor }},
      ticks: {{ color: tickColor, maxTicksLimit: 8 }},
      title: {{ display: !!title, text: title, color: "#64748b", font: {{ size: 11 }} }},
    }};
  }}

  // ── Line chart ─────────────────────────────────────────────────────────────
  const lineCtx = document.getElementById("lineChart").getContext("2d");
  const lineChart = new Chart(lineCtx, {{
    type: "line",
    data: {{
      labels:   QUANTITIES,
      datasets: LINE_DATASETS,
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: "index", intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: "#1e293b",
          borderColor: "#334155",
          borderWidth: 1,
          titleColor: "#e2e8f0",
          bodyColor: "#94a3b8",
          callbacks: {{
            label: ctx => {{
              const v = ctx.raw;
              return v == null ? `${{ctx.dataset.label}}: —` : `${{ctx.dataset.label}}: $${{v.toFixed(2)}}/board`;
            }},
          }},
        }},
      }},
      scales: {{
        x: {{ ...mkScale("Panels Ordered"), grid: {{ color: gridColor }} }},
        y: {{
          ...mkScale("Landed $/board"),
          ticks: {{
            color: tickColor,
            callback: v => `$${{v.toFixed(2)}}`,
          }},
        }},
      }},
    }},
  }});

  // Build custom legend for line chart
  const lineLegendEl = document.getElementById("lineChartLegend");
  VARIANTS.forEach(v => {{
    const color = VARIANT_COLORS[v] || "#ffffff";
    const item  = document.createElement("div");
    item.className = "chart-legend-item";
    item.innerHTML = `<span class="legend-dot" style="background:${{color}}"></span>${{v}}`;
    lineLegendEl.appendChild(item);
  }});

  // ── Stacked bar chart ──────────────────────────────────────────────────────
  const barCtx = document.getElementById("stackedBar").getContext("2d");

  function buildBarData(qty) {{
    const qtyKey = String(qty);
    // Each dataset = one cost segment, values for each variant
    const datasets = SEG_LABELS.map((label, i) => ({{
      label:           label,
      data:            VARIANTS.map(v => {{
        const bb = BOM_BREAKDOWN[qtyKey]?.[v];
        if (!bb) return null;
        const boards  = bb.total_boards || 1;
        const pcbaTotal = bb.pcba_price_total;
        switch (i) {{
          case 0: return bb.component_cost_per_board ?? 0;
          case 1: return bb.assembly_cost_per_board ?? 0;
          case 2: return bb.pcb_per_board ?? 0;
          case 3: return (pcbaTotal != null) ? (pcbaTotal / boards) * DUTY_RATE : 0;
          case 4: return (bb.ship_cost != null) ? bb.ship_cost / boards : 0;
          default: return 0;
        }}
      }}),
      backgroundColor: SEG_COLORS[i],
      stack:           "stack",
    }}));
    return {{ labels: VARIANTS, datasets }};
  }}

  const barChart = new Chart(barCtx, {{
    type: "bar",
    data: buildBarData(MEDIAN_QTY),
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: "index", intersect: false }},
      plugins: {{
        legend: {{
          display: true,
          position: "bottom",
          labels: {{
            color: "#94a3b8",
            boxWidth: 12,
            padding: 16,
          }},
        }},
        tooltip: {{
          backgroundColor: "#1e293b",
          borderColor: "#334155",
          borderWidth: 1,
          titleColor: "#e2e8f0",
          bodyColor: "#94a3b8",
          callbacks: {{
            label: ctx => {{
              const v = ctx.raw;
              return v == null || v === 0 ? null : `${{ctx.dataset.label}}: $${{v.toFixed(4)}}/board`;
            }},
          }},
        }},
      }},
      scales: {{
        x: mkScale("Panel Variant"),
        y: {{
          ...mkScale("$/board"),
          stacked: true,
          ticks: {{ color: tickColor, callback: v => `$${{v.toFixed(2)}}` }},
        }},
      }},
    }},
  }});

  // ── Pie chart ──────────────────────────────────────────────────────────────
  const pieCtx = document.getElementById("pieChart").getContext("2d");
  const PIE_PALETTE = [
    "#60a5fa","#34d399","#fbbf24","#f87171","#a78bfa",
    "#fb923c","#38bdf8","#4ade80","#e879f9","#f43f5e",
    "#22d3ee","#facc15","#86efac","#fda4af","#c4b5fd",
  ];

  // Build variant selector for pie
  const variantSelectorPie = document.getElementById("variantSelectorPie");
  VARIANTS.forEach((v, i) => {{
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    if (i === 0) opt.selected = true;
    variantSelectorPie.appendChild(opt);
  }});

  function buildPieData(qty, variant) {{
    const qtyKey = String(qty);
    const bb     = BOM_BREAKDOWN[qtyKey]?.[variant];
    if (!bb || !bb.line_items || bb.line_items.length === 0) {{
      return {{ labels: [], datasets: [{{ data: [], backgroundColor: [] }}] }};
    }}
    const items = bb.line_items.filter(li => li.line_total != null && li.line_total > 0);
    return {{
      labels:   items.map(li => `${{li.lcsc}} ${{li.desc ? li.desc.substring(0, 18) : ""}}`),
      datasets: [{{
        data:            items.map(li => li.line_total),
        backgroundColor: PIE_PALETTE.slice(0, items.length),
        borderColor:     "#0d1117",
        borderWidth:     2,
      }}],
    }};
  }}

  function buildPieLegend(qty, variant) {{
    const qtyKey = String(qty);
    const bb     = BOM_BREAKDOWN[qtyKey]?.[variant];
    const el     = document.getElementById("pieLegend");
    el.innerHTML = "";
    if (!bb || !bb.line_items) return;
    let total = 0;
    const items = bb.line_items.filter(li => li.line_total != null && li.line_total > 0);
    items.forEach(li => total += li.line_total);
    items.forEach((li, i) => {{
      const pct  = total > 0 ? (li.line_total / total * 100).toFixed(1) : "—";
      const color = PIE_PALETTE[i % PIE_PALETTE.length];
      el.innerHTML += `
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${{color}};flex-shrink:0"></span>
          <span style="color:#cbd5e1;font-weight:500">${{li.lcsc}}</span>
          <span style="color:#64748b">${{(li.desc || "").substring(0, 22)}}</span>
          <span style="margin-left:auto;color:#94a3b8">$${{li.line_total.toFixed(4)}}</span>
          <span style="color:#475569;width:44px;text-align:right">${{pct}}%</span>
        </div>`;
    }});
    if (items.length > 0) {{
      el.innerHTML += `<div style="border-top:1px solid #1e293b;margin-top:6px;padding-top:6px;color:#64748b;font-size:0.75rem">
        Total component cost/board: <strong style="color:#e2e8f0">$${{total.toFixed(4)}}</strong>
      </div>`;
    }}
  }}

  const pieChart = new Chart(pieCtx, {{
    type: "pie",
    data: buildPieData(MEDIAN_QTY, VARIANTS[0]),
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: "#1e293b",
          borderColor: "#334155",
          borderWidth: 1,
          titleColor: "#e2e8f0",
          bodyColor: "#94a3b8",
          callbacks: {{
            label: ctx => `$${{ctx.raw.toFixed(4)}}/board  (${{(ctx.raw / ctx.chart.data.datasets[0].data.reduce((a,b)=>a+b,0) * 100).toFixed(1)}}%)`,
          }},
        }},
      }},
    }},
  }});
  buildPieLegend(MEDIAN_QTY, VARIANTS[0]);

  // ── BOM table updater ──────────────────────────────────────────────────────
  function updateBomTable(qty, variant) {{
    const qtyKey = String(qty);
    const bb     = BOM_BREAKDOWN[qtyKey]?.[variant];
    const tbody  = document.getElementById("bom-tbody");
    if (!bb || !bb.line_items || bb.line_items.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="6" style="color:#475569;text-align:center;padding:20px">No BOM data for this configuration</td></tr>';
      return;
    }}
    let html = "";
    bb.line_items.forEach(li => {{
      const ext    = li.lib_type === "Extended";
      const so     = li.standard_only;
      const upStr  = li.unit_price  != null ? `$${{li.unit_price.toFixed(4)}}`  : "—";
      const ltStr  = li.line_total  != null ? `$${{li.line_total.toFixed(4)}}`  : "—";
      const rowCls = ext ? "bom-extended" : "";
      const libBadge = ext
        ? `<span class="badge-ext">Extended</span>`
        : `<span class="badge-basic">Basic</span>`;
      const soBadge = so ? ` <span class="badge-warn">⚠ Std Only</span>` : "";
      const descTrunc = (li.desc || "").substring(0, 40);
      html += `<tr class="${{rowCls}}">
        <td class="mono">${{li.lcsc}}</td>
        <td>${{descTrunc}}${{soBadge}}</td>
        <td class="num">${{li.qty_per_board}}</td>
        <td>${{libBadge}}</td>
        <td class="num mono">${{upStr}}</td>
        <td class="num mono">${{ltStr}}</td>
      </tr>`;
    }});
    tbody.innerHTML = html;
  }}

  // ── Shared qty selector handler ────────────────────────────────────────────
  const qtySelector = document.getElementById("qtySelector");

  function onQtyChange() {{
    const qty     = parseInt(qtySelector.value, 10);
    const variant = variantSelectorPie.value;

    // Update stacked bar
    barChart.data = buildBarData(qty);
    barChart.update();

    // Update pie
    pieChart.data = buildPieData(qty, variant);
    pieChart.update();
    buildPieLegend(qty, variant);

    // Update BOM table
    updateBomTable(qty, variant);
  }}

  qtySelector.addEventListener("change", onQtyChange);
  variantSelectorPie.addEventListener("change", () => {{
    const qty     = parseInt(qtySelector.value, 10);
    const variant = variantSelectorPie.value;
    pieChart.data = buildPieData(qty, variant);
    pieChart.update();
    buildPieLegend(qty, variant);
    updateBomTable(qty, variant);
  }});

  // Initial render
  updateBomTable(MEDIAN_QTY, VARIANTS[0]);

}})();
</script>
</body>
</html>"""
