#!/usr/bin/env python3
"""BOM component cost estimator using the JLCPCB component API.

Fetches price tiers for LCSC part numbers and computes total component cost
at any board quantity.  Prices are cached locally to avoid repeated API calls.

Primary BOM source: the generated JLCPCB BOM CSV from circuit-synth:
  speakeasy/speakeasy_jlcpcb_bom.csv
  Columns: Comment, Designator, Footprint, LCSC Part #

Manual overrides in quotes_data.json (optional — use to seed price tiers
before API access is available, or to override a specific part):
  "bom_overrides": {
    "C2040": {"price_tiers": [{"min_qty": 1, "unit_price": 4.20}]},
    ...
  }
"""

import csv
import json
import time
from pathlib import Path

COMPONENT_URI = "/overseas/openapi/component/getComponentDetailByCode"
CACHE_TTL_HOURS = 24


# ── Price-tier helpers ─────────────────────────────────────────────────────────

def price_at_qty(tiers: list[dict], qty: int) -> float | None:
    """
    Return unit price for `qty` units given sorted price tiers.
    tiers: list of {"min_qty": N, "unit_price": X}
    Picks the highest tier whose min_qty ≤ qty.
    Returns None if no tiers provided.
    """
    if not tiers:
        return None
    best = None
    for t in sorted(tiers, key=lambda t: t["min_qty"]):
        if qty >= t["min_qty"]:
            best = t["unit_price"]
    return best


def tiers_from_api_ranges(price_ranges: list[dict]) -> list[dict]:
    """Convert API priceRanges → canonical {"min_qty", "unit_price"} list."""
    return [
        {"min_qty": int(r["startQuantity"]), "unit_price": float(r["unitPrice"])}
        for r in price_ranges
        if r.get("startQuantity") is not None and r.get("unitPrice") is not None
    ]


# ── Cache ──────────────────────────────────────────────────────────────────────

def load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            pass
    return {}


def save_cache(cache_path: Path, cache: dict):
    cache_path.write_text(json.dumps(cache, indent=2))


def cache_fresh(entry: dict) -> bool:
    fetched_at = entry.get("fetched_at", 0)
    return (time.time() - fetched_at) < CACHE_TTL_HOURS * 3600


# ── API fetch ──────────────────────────────────────────────────────────────────

def fetch_component_prices(
    lcsc_codes: list[str],
    api_base: str,
    auth_fn,          # callable(method, path, body) → Authorization header str
    cache_path: Path,
) -> dict[str, list[dict]]:
    """
    Fetch price tiers for a list of LCSC codes.
    Returns {lcsc_code: [{"min_qty": N, "unit_price": X}, ...]}
    Merges with cache; only fetches codes that are missing or stale.
    """
    import urllib.error
    import urllib.request

    cache   = load_cache(cache_path)
    missing = [c for c in lcsc_codes if c not in cache or not cache_fresh(cache[c])]

    if missing:
        print(f"  Fetching prices for {len(missing)} component(s): {', '.join(missing)}")
        body   = json.dumps({"componentCodes": missing}, separators=(",", ":"))
        auth   = auth_fn("POST", COMPONENT_URI, body)
        req    = urllib.request.Request(
            f"{api_base}{COMPONENT_URI}",
            data=body.encode(),
            headers={"Content-Type": "application/json", "Authorization": auth},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            print(f"  Component API HTTP {e.code}: {e.read().decode()[:200]}")
            result = {}
        except Exception as e:
            print(f"  Component API error: {e}")
            result = {}

        for item in (result.get("data") or []):
            code   = item.get("componentCode", "")
            tiers  = tiers_from_api_ranges(item.get("priceRanges") or [])
            cache[code] = {
                "model":       item.get("componentModel", ""),
                "description": item.get("componentSpecification", ""),
                "stock":       item.get("stockCount"),
                "tiers":       tiers,
                "fetched_at":  time.time(),
            }

        save_cache(cache_path, cache)

    return {code: (cache[code]["tiers"] if code in cache else []) for code in lcsc_codes}


# ── BOM cost calculation ───────────────────────────────────────────────────────

class BomLine:
    def __init__(self, lcsc: str, qty_per_board: int, description: str = "",
                 price_tiers: list[dict] | None = None,
                 lib_type: str = "Basic", standard_only: bool = False,
                 solder_joints: int = 2, xray_required: bool = False,
                 min_assembly_qty: int = 0, attrition_qty: int = -1,
                 full_reel_qty: int = 0):
        self.lcsc             = lcsc
        self.qty_per_board    = qty_per_board
        self.description      = description
        self.price_tiers      = price_tiers or []
        self.lib_type         = lib_type
        self.standard_only    = standard_only
        self.solder_joints    = solder_joints
        self.xray_required    = xray_required
        self.min_assembly_qty = min_assembly_qty  # JLCPCB min order qty (0 = exact usage)
        self.attrition_qty    = attrition_qty     # basic attrition pcs (-1 = not set)
        self.full_reel_qty    = full_reel_qty     # reel size for extra attrition calc (0 = unknown)


def assembly_summary(bom: list[BomLine]) -> dict:
    """Return assembly metadata: forced type, extended part count, standard_only parts."""
    extended      = [l for l in bom if l.lib_type == "Extended"]
    standard_only = [l for l in bom if l.standard_only]
    forced        = "Standard" if standard_only else "Economy"
    return {
        "forced_type":    forced,
        "extended_parts": extended,
        "standard_only":  standard_only,
        "n_extended":     len(extended),
    }


def load_bom_from_csv(csv_path: Path,
                      overrides: dict[str, dict] | None = None) -> list[BomLine]:
    """
    Load BOM from a JLCPCB-format BOM CSV:
      Comment, Designator, Footprint, LCSC Part #

    Aggregates rows by LCSC part number (multiple designators → one line).
    `overrides` maps LCSC code → {"price_tiers": [...]} for manual tier seeding.
    """
    overrides = overrides or {}
    # lcsc → (description, total_qty)
    parts: dict[str, tuple[str, int]] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            lcsc = row.get("LCSC Part #", "").strip()
            if not lcsc:
                continue
            desc        = row.get("Comment", "").strip()
            designators = [d.strip() for d in row.get("Designator", "").split(",") if d.strip()]
            qty         = len(designators)
            if lcsc in parts:
                existing_desc, existing_qty = parts[lcsc]
                parts[lcsc] = (existing_desc or desc, existing_qty + qty)
            else:
                parts[lcsc] = (desc, qty)

    lines = []
    for lcsc, (desc, qty) in parts.items():
        ov = overrides.get(lcsc, {})
        lines.append(BomLine(
            lcsc          = lcsc,
            qty_per_board = qty,
            description   = desc,
            price_tiers   = ov.get("price_tiers", []),
            lib_type      = ov.get("lib_type", "Basic"),
            standard_only = ov.get("standard_only", False),
            solder_joints     = ov.get("solder_joints", 2),
            xray_required     = ov.get("xray_required", False),
            min_assembly_qty  = ov.get("min_assembly_qty", 0),
            attrition_qty     = ov.get("attrition_qty", -1),
            full_reel_qty     = ov.get("full_reel_qty", 0),
        ))
    return lines


def load_bom(bom_entries: list[dict]) -> list[BomLine]:
    """Load BOM from quotes_data.json 'bom' list (legacy / manual fallback)."""
    lines = []
    for e in bom_entries:
        lines.append(BomLine(
            lcsc          = e["lcsc"],
            qty_per_board = e.get("qty_per_board", e.get("qty", 1)),
            description   = e.get("description", ""),
            price_tiers   = e.get("price_tiers", []),
        ))
    return lines


def rec_order_qty(item: BomLine, total_boards: int, asm_cfg: dict | None = None) -> int:
    """
    JLCPCB recommended order qty:
      rec = max(usage + attrition, min_assembly_qty)

    attrition = basic_attrition + extra_attrition
    extra_attrition = floor((usage - full_reel_qty) × 0.002)  if usage > full_reel_qty, else 0

    attrition_qty, min_assembly_qty, full_reel_qty must be set per-component in bom_overrides.
    Components without values use exact usage (no attrition adjustment).
    """
    import math
    usage         = item.qty_per_board * total_boards
    basic_att     = item.attrition_qty if item.attrition_qty >= 0 else 0
    extra_att     = 0
    if item.full_reel_qty > 0 and usage > item.full_reel_qty:
        extra_att = math.floor((usage - item.full_reel_qty) * 0.002)
    attrition     = basic_att + extra_att
    min_asm       = item.min_assembly_qty if item.min_assembly_qty > 0 else usage
    return max(usage + attrition, min_asm)


def bom_cost_per_board(
    bom: list[BomLine],
    total_boards: int,
    api_tiers: dict[str, list[dict]],
    asm_cfg: dict | None = None,
) -> tuple[float | None, list[tuple]]:
    """
    Compute total component cost per board for `total_boards` units.
    Uses JLCPCB's rec_order_qty formula for accurate small-lot pricing.

    Returns (total_cost_per_board, line_items) where each line_item is:
        (lcsc, description, qty_per_board, unit_price, line_total_per_board, source)
    Returns (None, []) if any line is missing price data.
    """
    total = 0.0
    lines = []
    missing = []

    for item in bom:
        rec_qty = rec_order_qty(item, total_boards, asm_cfg)
        tiers   = api_tiers.get(item.lcsc) or item.price_tiers
        source  = "api" if api_tiers.get(item.lcsc) else ("manual" if item.price_tiers else "missing")
        up      = price_at_qty(tiers, rec_qty)

        if up is None:
            missing.append(item.lcsc)
            lines.append((item.lcsc, item.description, item.qty_per_board, None, None, source))
        else:
            # Total cost = unit_price × rec_qty; amortise over boards actually built
            line_total = (up * rec_qty) / total_boards
            total += line_total
            lines.append((item.lcsc, item.description, item.qty_per_board, up, line_total, source))

    if missing:
        return None, lines
    return total, lines


# ── Assembly cost model ────────────────────────────────────────────────────────

def _tiered_rate(tiers: list[dict], value: int, max_key: str, cost_key: str) -> float:
    """Pick the rate from a tiered list (first tier whose max_key >= value)."""
    for tier in sorted(tiers, key=lambda t: t[max_key]):
        if value <= tier[max_key]:
            return tier[cost_key]
    return tiers[-1][cost_key]  # beyond last tier, use highest-volume rate


def compute_assembly_cost(
    bom: list[BomLine],
    total_boards: int,
    pcb_w_mm: float,
    pcb_l_mm: float,
    asm_cfg: dict,
) -> dict:
    """
    Compute JLCPCB Standard PCBA assembly cost from published pricing.

    Returns dict with keys:
      total, setup_fee, stencil_fee, panel_fee, smt_fee,
      hand_solder_fee, feeder_fee, xray_fee, packing_fee,
      jlc_panels, total_joints
    """
    import math

    jlc_w, jlc_l   = asm_cfg.get("jlc_panel_size_mm", [300, 300])
    boards_per_jlc  = math.floor(jlc_w / pcb_w_mm) * math.floor(jlc_l / pcb_l_mm)
    jlc_panels      = math.ceil(total_boards / boards_per_jlc) if boards_per_jlc > 0 else 1

    total_joints = sum(
        line.solder_joints * line.qty_per_board for line in bom
    ) * total_boards

    setup_fee    = asm_cfg.get("setup_fee", 0.0) * asm_cfg.get("assembly_sides", 1)
    stencil_fee  = asm_cfg.get("stencil_fee", 0.0) * asm_cfg.get("assembly_sides", 1)
    panel_fee    = asm_cfg.get("panel_fee_per_jlc_panel", 0.0) * jlc_panels

    smt_rate     = _tiered_rate(
        asm_cfg.get("smt_assembly_per_joint_tiers", []),
        total_joints, "max_joints", "cost",
    ) if asm_cfg.get("smt_assembly_per_joint_tiers") else 0.0
    smt_fee      = smt_rate * total_joints

    hand_solder  = asm_cfg.get("hand_solder_fee", 0.0)

    feeder_fee   = asm_cfg.get("feeder_fee_per_unique_part", 0.0) * len(bom)

    needs_xray = any(line.xray_required for line in bom)
    xray_rate  = (
        _tiered_rate(asm_cfg.get("xray_tiers", []), total_boards, "max_pcs", "cost_per_pcs")
        if needs_xray and asm_cfg.get("xray_tiers") else 0.0
    )
    xray_fee   = xray_rate * total_boards

    # Packing: per cm² of PCB area × number of boards
    packing_rate = asm_cfg.get("packing_fee_per_cm2", 0.0)
    area_cm2     = (pcb_w_mm / 10.0) * (pcb_l_mm / 10.0)
    packing_fee  = packing_rate * area_cm2 * total_boards

    total = setup_fee + stencil_fee + panel_fee + smt_fee + hand_solder + feeder_fee + xray_fee + packing_fee

    return {
        "total":          total,
        "setup_fee":      setup_fee,
        "stencil_fee":    stencil_fee,
        "panel_fee":      panel_fee,
        "smt_fee":        smt_fee,
        "hand_solder_fee": hand_solder,
        "feeder_fee":     feeder_fee,
        "xray_fee":       xray_fee,
        "packing_fee":    packing_fee,
        "jlc_panels":     jlc_panels,
        "total_joints":   total_joints,
        "smt_rate":       smt_rate,
        "xray_rate":      xray_rate,
        "xray_required":  needs_xray,
        "boards_per_jlc": boards_per_jlc,
    }


# ── Pretty-print BOM breakdown ────────────────────────────────────────────────

def print_bom_breakdown(bom: list[BomLine], total_boards: int, api_tiers: dict,
                        extended_part_fee: float = 0.0,      # kept for compat, ignored when asm_cfg provided
                        standard_base_fee: float = 0.0,      # kept for compat, ignored when asm_cfg provided
                        pcb_cost_total: float | None = None,
                        pcba_price_total: float | None = None,
                        import_duty_rate: float = 0.0,
                        ship_cost: float | None = None,
                        asm_cfg: dict | None = None,          # full assembly config dict
                        pcb_w_mm: float | None = None,        # for JLC panel calculation
                        pcb_l_mm: float | None = None):
    asm    = assembly_summary(bom)
    cost, lines = bom_cost_per_board(bom, total_boards, api_tiers, asm_cfg)

    print(f"\nBOM breakdown @ {total_boards} boards  [{asm['forced_type']} PCBA]:")
    print(f"  {'LCSC':<10}  {'Qty/bd':>6}  {'Unit $':>8}  {'$/bd':>8}  {'Type':<8}  Description")
    print(f"  {'-'*10}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*28}")
    for lcsc, desc, qty, up, line, src in lines:
        bom_line = next((l for l in bom if l.lcsc == lcsc), None)
        ltype    = (bom_line.lib_type if bom_line else "?") + ("⚠" if bom_line and bom_line.standard_only else "")
        up_s     = f"${up:.4f}" if up is not None else "?"
        line_s   = f"${line:.4f}" if line is not None else "?"
        flag     = " *" if src == "manual" else ("  " if src == "api" else " !")
        print(f"  {lcsc:<10}  {qty:>6}  {up_s:>8}  {line_s:>8}  {ltype:<8}  {desc}{flag}")

    pcb_per_bd = (pcb_cost_total / total_boards) if pcb_cost_total is not None and total_boards else None
    if pcb_per_bd is not None:
        print(f"  {'[PCB]':<10}  {'':>6}  {'':>8}  ${pcb_per_bd:>7.4f}  {'':8}  Bare board (eng fee + material)")

    # ── Assembly cost breakdown ───────────────────────────────────────────────
    asm_detail: dict | None = None
    if asm_cfg and pcb_w_mm and pcb_l_mm and total_boards:
        asm_detail = compute_assembly_cost(bom, total_boards, pcb_w_mm, pcb_l_mm, asm_cfg)
        n_boards   = total_boards

        setup_stencil_total = asm_detail["setup_fee"] + asm_detail["stencil_fee"]
        print(f"  {'[Asm setup]':<12}  {'':>6}  {'':>8}  ${setup_stencil_total/n_boards:>7.4f}  {'':8}"
              f"  Setup+stencil (${setup_stencil_total:.2f} / {n_boards} boards)")
        print(f"  {'[Asm panel]':<12}  {'':>6}  {'':>8}  ${asm_detail['panel_fee']/n_boards:>7.4f}  {'':8}"
              f"  Panel fee ({asm_detail['jlc_panels']} JLC panel(s) × ${asm_cfg.get('panel_fee_per_jlc_panel',0):.2f} / {n_boards} boards)"
              f"  [{asm_detail['boards_per_jlc']} boards/JLC-panel]")
        print(f"  {'[Asm SMT]':<12}  {'':>6}  {'':>8}  ${asm_detail['smt_fee']/n_boards:>7.4f}  {'':8}"
              f"  {asm_detail['total_joints']//n_boards} joints/board × ${asm_detail['smt_rate']:.4f}/joint")
        print(f"  {'[Asm h-solder]':<14}{'':>6}  {'':>8}  ${asm_detail['hand_solder_fee']/n_boards:>7.4f}  {'':8}"
              f"  Hand-solder fee (${asm_detail['hand_solder_fee']:.2f} / {n_boards} boards)")
        print(f"  {'[Asm feeder]':<12}  {'':>6}  {'':>8}  ${asm_detail['feeder_fee']/n_boards:>7.4f}  {'':8}"
              f"  {len(bom)} parts × ${asm_cfg.get('feeder_fee_per_unique_part',0):.2f} feeder / {n_boards} boards")
        xray_parts = [l.lcsc for l in bom if l.xray_required]
        xray_note  = (f"X-ray @ ${asm_detail['xray_rate']:.2f}/pcs ({', '.join(xray_parts)})"
                      if asm_detail["xray_required"] else "X-ray: not required (no QFN/BGA)")
        print(f"  {'[Asm xray]':<12}  {'':>6}  {'':>8}  ${asm_detail['xray_fee']/n_boards:>7.4f}  {'':8}"
              f"  {xray_note}")
        print(f"  {'[Asm packing]':<12} {'':>6}  {'':>8}  ${asm_detail['packing_fee']/n_boards:>7.4f}  {'':8}"
              f"  Packing fee")
        print(f"  {'-'*10}  {'-'*6}  {'-'*8}  {'-'*8}")
        print(f"  {'[Assembly]':<10}  {'':>6}  {'':>8}  ${asm_detail['total']/n_boards:>7.4f}  {'':8}"
              f"  Assembly subtotal")

    comp_total  = cost if cost is not None else 0.0
    pcb_add     = (pcb_per_bd or 0.0)
    asm_per_bd  = (asm_detail["total"] / total_boards) if asm_detail else 0.0
    grand       = comp_total + pcb_add + asm_per_bd if cost is not None else None

    indent = f"  {'':10}  {'':>6}  {'':>8}  {'':>8}  {'':8}  "
    if grand is not None:
        print(f"  {'TOTAL/bd':<10}  {'':>6}  {'':>8}  ${grand:>7.4f}  {'':8}  components + PCB + assembly model")

        if pcba_price_total is not None and total_boards:
            pcba_per_bd = pcba_price_total / total_boards
            residual    = pcba_per_bd - grand
            print(f"{indent}  ${residual:+.4f}  JLCPCB markup / rounding residual")
            print(f"{indent}= ${pcba_per_bd:.4f}  PCBA merch/bd")

            landed = pcba_per_bd * (1 + import_duty_rate)
            if ship_cost is not None:
                ship_pb = ship_cost / total_boards
                landed += ship_pb
                print(f"{indent}+ ${pcba_per_bd * import_duty_rate:.4f}  import duty ({import_duty_rate*100:.0f}%)")
                print(f"{indent}+ ${ship_pb:.4f}  shipping/bd")
            else:
                print(f"{indent}+ ${pcba_per_bd * import_duty_rate:.4f}  import duty ({import_duty_rate*100:.0f}%)")
            print(f"{indent}= ${landed:.2f}  landed/bd")
    else:
        print(f"  TOTAL: incomplete (missing prices marked !)")
    if asm["standard_only"]:
        print(f"  ⚠ Standard Only: " + ", ".join(f"{l.lcsc} ({l.description})" for l in asm["standard_only"]))
    print(f"  * = manual price tiers (not from API)")
