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
                 lib_type: str = "Basic", standard_only: bool = False):
        self.lcsc          = lcsc
        self.qty_per_board = qty_per_board
        self.description   = description
        self.price_tiers   = price_tiers or []
        self.lib_type      = lib_type        # "Basic" or "Extended"
        self.standard_only = standard_only   # True → forces Standard PCBA


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


def bom_cost_per_board(
    bom: list[BomLine],
    total_boards: int,
    api_tiers: dict[str, list[dict]],   # fetched or empty
) -> tuple[float | None, list[tuple]]:
    """
    Compute total component cost per board for `total_boards` units.

    Returns (total_cost_per_board, line_items) where each line_item is:
        (lcsc, description, qty_per_board, unit_price, line_total_per_board, source)
    Returns (None, []) if any line is missing price data.
    """
    total = 0.0
    lines = []
    missing = []

    for item in bom:
        total_qty = item.qty_per_board * total_boards
        # Priority: API/cache tiers → manual tiers in data file
        tiers  = api_tiers.get(item.lcsc) or item.price_tiers
        source = "api" if api_tiers.get(item.lcsc) else ("manual" if item.price_tiers else "missing")
        up     = price_at_qty(tiers, total_qty)

        if up is None:
            missing.append(item.lcsc)
            lines.append((item.lcsc, item.description, item.qty_per_board, None, None, source))
        else:
            line_total = (up * total_qty) / total_boards
            total += line_total
            lines.append((item.lcsc, item.description, item.qty_per_board, up, line_total, source))

    if missing:
        return None, lines
    return total, lines


# ── Pretty-print BOM breakdown ────────────────────────────────────────────────

def print_bom_breakdown(bom: list[BomLine], total_boards: int, api_tiers: dict,
                        extended_part_fee: float = 0.0,
                        standard_base_fee: float = 0.0,
                        pcb_cost_total: float | None = None,
                        pcba_price_total: float | None = None,
                        import_duty_rate: float = 0.0,
                        ship_cost: float | None = None):
    asm    = assembly_summary(bom)
    cost, lines = bom_cost_per_board(bom, total_boards, api_tiers)

    # One-time fees for this order
    ext_fee_total  = asm["n_extended"] * extended_part_fee
    ext_fee_per_bd = ext_fee_total / total_boards if total_boards else 0.0
    base_per_bd    = standard_base_fee / total_boards if total_boards else 0.0

    print(f"\nBOM breakdown @ {total_boards} boards  "
          f"[{asm['forced_type']} PCBA"
          + (f", {asm['n_extended']} Extended × ${extended_part_fee:.2f} = ${ext_fee_total:.2f} one-time" if asm["n_extended"] else "")
          + (f", Standard base ${standard_base_fee:.2f}" if standard_base_fee else "")
          + "]:")
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
        print(f"  {'[PCB]':<10}  {'':>6}  {'':>8}  ${pcb_per_bd:>7.4f}  {'Basic':8}  Bare board (eng fee + material)")
    if extended_part_fee and asm["n_extended"]:
        print(f"  {'[Ext fee]':<10}  {'':>6}  {'':>8}  ${ext_fee_per_bd:>7.4f}  {'':8}  {asm['n_extended']} extended parts × ${extended_part_fee:.2f} / {total_boards} boards")
    if standard_base_fee:
        print(f"  {'[Std base]':<10}  {'':>6}  {'':>8}  ${base_per_bd:>7.4f}  {'':8}  Standard base fee / {total_boards} boards")

    comp_total = cost if cost is not None else 0.0
    pcb_add    = (pcb_per_bd or 0.0) if pcb_per_bd is not None else 0.0
    grand = comp_total + ext_fee_per_bd + base_per_bd + pcb_add if cost is not None else None

    if grand is not None:
        parts = [f"${grand:.4f}/bd (est. components+PCB+fees)"]

        # Assembly labor = PCBA merch price - our estimated bottom-up cost
        if pcba_price_total is not None and total_boards:
            pcba_per_bd   = pcba_price_total / total_boards
            assembly_labor = pcba_per_bd - grand
            parts.append(f"+ ~${assembly_labor:.4f} assembly labor")
            parts.append(f"= ${pcba_per_bd:.4f} PCBA merch")

            # Landed = PCBA × (1 + duty) + ship/board
            landed = pcba_per_bd * (1 + import_duty_rate)
            if ship_cost is not None:
                landed += ship_cost / total_boards
                parts.append(f"+ ${import_duty_rate*100:.0f}% duty + ${ship_cost/total_boards:.4f} ship")
            else:
                parts.append(f"+ ${import_duty_rate*100:.0f}% duty")
            parts.append(f"= ${landed:.2f} landed/bd")

        print(f"  {'TOTAL/bd':<10}  {'':>6}  {'':>8}  {'':>8}  {'':8}  " + "  ".join(parts))
    else:
        print(f"  TOTAL: incomplete (missing prices marked !)")
    if asm["standard_only"]:
        print(f"  ⚠ Standard Only: " + ", ".join(f"{l.lcsc} ({l.description})" for l in asm["standard_only"]))
    print(f"  * = manual price tiers (not from API)")
