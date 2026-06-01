#!/usr/bin/env python3
"""JLCPCB panel price optimizer for the Speakeasy PCB.

Two modes:
  live    — queries the JLCPCB Online Quote API (requires API access)
  offline — estimates from known quotes + component costs in a data file

Usage:
    python price_calculator.py                         # live API
    python price_calculator.py --offline               # estimate from quotes_data.json
    python price_calculator.py --offline --data my.json
    python price_calculator.py --offline --fetch-prices  # hit component API for BOM prices
    python price_calculator.py --qty 5 10 25 --variants 1x1 2x2 3x3
    python price_calculator.py --bom                   # show BOM breakdown only
"""

import argparse
import base64
import hashlib
import hmac
import json
import math
import random
import re
import string
import time
import urllib.error
import urllib.request
from pathlib import Path

from bom import (
    BomLine, assembly_summary, bom_cost_per_board, fetch_component_prices,
    load_bom, load_bom_from_csv, print_bom_breakdown,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR       = Path(__file__).parent
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"
DEFAULT_DATA     = SCRIPT_DIR / "quotes_data.json"
PRICE_CACHE      = SCRIPT_DIR / "component_prices_cache.json"
PCB_FILE         = SCRIPT_DIR.parent / "speakeasy" / "Speakeasy.kicad_pcb"
JLCPCB_BOM_CSV   = SCRIPT_DIR.parent / "speakeasy" / "speakeasy_jlcpcb_bom.csv"

# ── JLCPCB API ─────────────────────────────────────────────────────────────────
API_BASE  = "https://open.jlcpcb.com"
QUOTE_URI = "/overseas/openapi/pcb/calculate"

# ── PCB defaults (standard 2-layer green HASL board) ──────────────────────────
DEFAULT_LAYERS         = 2
DEFAULT_THICKNESS      = 1.6
DEFAULT_COLOR          = 1      # green
DEFAULT_SURFACE_FINISH = 1      # HASL
DEFAULT_COPPER_WEIGHT  = 1.0    # oz

DEFAULT_VARIANTS   = ["1x1", "2x2", "2x3", "3x3"]
DEFAULT_QUANTITIES = [5, 10, 15, 20, 25]


# ── KiCad dimension parser ─────────────────────────────────────────────────────

def read_pcb_dimensions(pcb_path: Path) -> tuple[float, float]:
    """Return (width_mm, height_mm) from the Edge.Cuts bounding box."""
    text = pcb_path.read_text(errors="replace")
    xs, ys = [], []
    for block in re.findall(
        r'\((?:gr_line|gr_arc|gr_rect|gr_poly)\b[^()]*(?:\([^()]*\)[^()]*)*\)',
        text, re.DOTALL
    ):
        if '"Edge.Cuts"' not in block:
            continue
        for m in re.finditer(r'\((?:start|end|xy)\s+([\d.+-]+)\s+([\d.+-]+)', block):
            xs.append(float(m.group(1)))
            ys.append(float(m.group(2)))
    if not xs:
        # Wider fallback: grab any coordinate near an Edge.Cuts keyword
        for m in re.finditer(r'\((?:start|end)\s+([\d.+-]+)\s+([\d.+-]+)', text):
            ctx = text[max(0, m.start()-120):m.start()+120]
            if "Edge.Cuts" in ctx:
                xs.append(float(m.group(1)))
                ys.append(float(m.group(2)))
    if not xs:
        raise ValueError(f"Could not parse Edge.Cuts from {pcb_path}")
    return round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)


# ── Auth / signing ─────────────────────────────────────────────────────────────

def _nonce(length: int = 32) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def _sign(s: str, secret_key: str) -> str:
    mac = hmac.new(secret_key.encode(), s.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


def _auth_header(method, path, body, app_id, access_key, secret_key) -> str:
    nonce = _nonce()
    ts    = int(time.time())
    sig   = _sign(f"{method}\n{path}\n{ts}\n{nonce}\n{body}\n", secret_key)
    return (f'JOP appid="{app_id}",accesskey="{access_key}",'
            f'nonce="{nonce}",timestamp="{ts}",signature="{sig}"')


# ── Live API quote ─────────────────────────────────────────────────────────────

def get_quote_live(cols, rows, qty, pcb_w, pcb_l, app_id, access_key, secret_key,
                   country=None, postcode=None, city=None
                   ) -> tuple[float | None, list[dict]]:
    """
    Returns (fab_price, ship_options) where ship_options is a list of:
      {"method": str, "display": str, "cost": float, "days": str}
    Ship options are only populated when country/postcode are provided.
    """
    panel_flag = 0 if (cols == 1 and rows == 1) else 1
    pcb_param  = {
        "layer": DEFAULT_LAYERS, "width": pcb_w, "length": pcb_l,
        "qty": qty, "thickness": DEFAULT_THICKNESS,
        "pcbColor": DEFAULT_COLOR, "surfaceFinish": DEFAULT_SURFACE_FINISH,
        "copperWeight": DEFAULT_COPPER_WEIGHT, "panelFlag": panel_flag,
    }
    if panel_flag == 1:
        pcb_param["panelByJLCPCB_X"] = cols
        pcb_param["panelByJLCPCB_Y"] = rows
    payload: dict = {"orderType": 1, "pcbParam": pcb_param}
    if country:
        payload["country"] = country
    if postcode:
        payload["postCode"] = postcode
    if city:
        payload["city"] = city
    body = json.dumps(payload, separators=(",", ":"))
    auth = _auth_header("POST", QUOTE_URI, body, app_id, access_key, secret_key)
    req  = urllib.request.Request(
        f"{API_BASE}{QUOTE_URI}", data=body.encode(),
        headers={"Content-Type": "application/json", "Authorization": auth},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.read().decode()[:200]}")
        return None, []
    except Exception as e:
        print(f"    Request failed: {e}")
        return None, []
    if result.get("code") != 0:
        print(f"    API error {result.get('code')}: {result.get('message')}")
        return None, []
    data      = result.get("data") or {}
    price_str = data.get("priceWithoutFreight")
    fab_price = float(price_str) if price_str is not None else None
    ship_opts = [
        {
            "method":  s.get("options", ""),
            "display": s.get("showOptions", s.get("options", "")),
            "cost":    float(s["cost"]) if s.get("cost") not in (None, "") else None,
            "days":    s.get("day", ""),
        }
        for s in (data.get("shipList") or [])
    ]
    return fab_price, ship_opts


# ── Offline estimation ─────────────────────────────────────────────────────────
#
# Pricing model per variant:  price = setup_fee + marginal_cost * qty
#
# With 1 known point (qty0, p0):
#   We solve for marginal_cost by assuming setup_fee is proportional to the
#   per-panel cost at qty0:  setup_fee ≈ marginal_cost * SETUP_PANELS_EQUIV
#   (i.e. the setup fee is equivalent to ~N free panels worth of material)
#   This gives: p0 = m*(SETUP_PANELS_EQUIV + qty0)  →  m = p0 / (SETUP_PANELS_EQUIV + qty0)
#
# With 2+ known points: ordinary least-squares fit.
#
SETUP_PANELS_EQUIV = 3   # tunable; JLCPCB setup fee ≈ cost of ~3 panels of material

# ── Shipping estimation ────────────────────────────────────────────────────────
#
# PCB weight: FR4 density ~1.85 g/cm³, plus ~30% for copper/silkscreen/mask.
# Packaging adds a flat ~80g.
FR4_DENSITY_G_CM3 = 1.85
COPPER_FACTOR     = 1.30
PACKAGING_G       = 80.0

def _panel_weight_g(pcb_w: float, pcb_l: float, qty_panels: int,
                    cols: int, rows: int) -> float:
    """Estimate total shipment weight in grams."""
    # Panel dimensions: boards + 2mm gaps + 6mm rails (top+bottom) per panel_preset.json
    panel_w = pcb_w * cols + 2.0 * (cols - 1)
    panel_l = pcb_l * rows + 2.0 * (rows - 1) + 2 * (5.0 + 6.0)  # vspace + rail width
    if cols == 1 and rows == 1:
        panel_w, panel_l = pcb_w, pcb_l   # no rails for single boards
    volume_cm3 = (panel_w * panel_l * DEFAULT_THICKNESS) / 1000.0
    board_g    = volume_cm3 * FR4_DENSITY_G_CM3 * COPPER_FACTOR
    return board_g * qty_panels + PACKAGING_G


def _shipping_cost(methods: list[dict], weight_g: float, preferred: str | None
                   ) -> list[dict]:
    """
    Look up shipping cost from offline tier table for a given weight.
    methods: from quotes_data.json "shipping.methods"
      Each method: {"name": str, "tiers": [{"max_weight_g": N, "cost": X}, ...]}
    Returns list of {"display": str, "cost": float | None, "days": str}
    sorted cheapest-first.
    """
    results = []
    for m in methods:
        cost = None
        for tier in sorted(m.get("tiers", []), key=lambda t: t["max_weight_g"]):
            if weight_g <= tier["max_weight_g"]:
                cost = tier["cost"]
                break
        if cost is None and m.get("tiers"):
            # Heavier than all tiers — use the last (heaviest) tier
            cost = max(m["tiers"], key=lambda t: t["max_weight_g"])["cost"]
        results.append({
            "display": m.get("name", ""),
            "cost":    cost,
            "days":    m.get("days", ""),
        })
    results.sort(key=lambda r: (r["cost"] is None, r["cost"] or 0))
    return results

def _fit_fab_model(known: list[tuple[int, float]]) -> tuple[float, float]:
    """Return (setup_fee, marginal_cost) from known [(qty, price)] pairs."""
    if len(known) == 0:
        return 0.0, 0.0
    if len(known) == 1:
        qty0, p0 = known[0]
        m = p0 / (SETUP_PANELS_EQUIV + qty0)
        return m * SETUP_PANELS_EQUIV, m
    # OLS: price = a + b*qty  →  minimise sum of (a + b*qi - pi)^2
    n     = len(known)
    sum_q = sum(q for q, _ in known)
    sum_p = sum(p for _, p in known)
    sum_qq= sum(q*q for q, _ in known)
    sum_qp= sum(q*p for q, p in known)
    denom = n * sum_qq - sum_q * sum_q
    if abs(denom) < 1e-9:          # all same qty — just average
        return 0.0, sum_p / sum_q
    b = (n * sum_qp - sum_q * sum_p) / denom
    a = (sum_p - b * sum_q) / n
    return max(a, 0.0), max(b, 0.0)   # clamp negatives from noisy fits


def _estimate_fab(setup_fee: float, marginal: float, qty: int) -> float:
    return setup_fee + marginal * qty



# ── Output helpers ─────────────────────────────────────────────────────────────

COL_W = 13

def _fmt_price(price: float | None, estimated: bool = False) -> str:
    if price is None:
        return f"{'—':>{COL_W}}"
    marker = "~" if estimated else " "
    return f"{marker}${price:>{COL_W-2}.2f}"

def _fmt_cpu(price: float | None, boards: int, estimated: bool = False) -> str:
    if price is None or boards == 0:
        return f"{'—':>{COL_W}}"
    marker = "~" if estimated else " "
    return f"{marker}${price/boards:>{COL_W-2}.2f}"


def _print_table(title: str, variants, quantities, fmt_fn):
    sep = "  "
    hdr = f"{'Qty':>5}{sep}" + sep.join(f"{v:>{COL_W}}" for v, *_ in variants)
    bar = "═" * len(hdr)
    print(f"\n{bar}\n{title}\n{bar}")
    print(hdr)
    print("─" * len(hdr))
    for qty in quantities:
        cells = sep.join(fmt_fn(qty, v) for v, *_ in variants)
        print(f"{qty:>5}{sep}{cells}")
    print(f"  ~ = estimated from model")


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_variant(v: str) -> tuple[int, int]:
    parts = v.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"Invalid variant '{v}' — use COLSxROWS")
    return int(parts[0]), int(parts[1])


def main():
    ap = argparse.ArgumentParser(description="JLCPCB panel price optimizer")
    ap.add_argument("--offline",    action="store_true",
                    help="estimate from quotes_data.json instead of calling the API")
    ap.add_argument("--data",       type=Path, default=DEFAULT_DATA,
                    metavar="FILE", help="path to quotes/component data JSON (offline mode)")
    ap.add_argument("--qty",          nargs="+", type=int, default=DEFAULT_QUANTITIES,
                    metavar="N",      help="panel quantities to evaluate")
    ap.add_argument("--variants",     nargs="+",           default=DEFAULT_VARIANTS,
                    metavar="CxR",    help="panel variants e.g. 1x1 2x2 2x3 3x3")
    ap.add_argument("--pcb-width",    type=float, default=None, metavar="MM")
    ap.add_argument("--pcb-length",   type=float, default=None, metavar="MM")
    ap.add_argument("--fetch-prices", action="store_true",
                    help="hit the JLCPCB component API to refresh BOM prices")
    ap.add_argument("--bom",          action="store_true",
                    help="print BOM breakdown only (no panel table)")
    ap.add_argument("--country",  default=None, metavar="CC",
                    help="destination country code for shipping estimate (e.g. US)")
    ap.add_argument("--postcode", default=None, metavar="ZIP",
                    help="destination postcode for shipping estimate")
    ap.add_argument("--city",     default=None, metavar="CITY",
                    help="destination city for shipping estimate")
    args = ap.parse_args()

    variants   = [(v, *parse_variant(v)) for v in args.variants]
    quantities = sorted(args.qty)

    # PCB dimensions (needed for live mode; shown in offline too)
    if args.pcb_width and args.pcb_length:
        pcb_w, pcb_l = args.pcb_width, args.pcb_length
        print(f"PCB: {pcb_w} × {pcb_l} mm (manual)")
    elif PCB_FILE.exists():
        pcb_w, pcb_l = read_pcb_dimensions(PCB_FILE)
        print(f"PCB: {pcb_w} × {pcb_l} mm (from KiCad)")
    elif args.offline:
        pcb_w = pcb_l = None
    else:
        ap.error("KiCad PCB not found and --pcb-width/--pcb-length not set")

    # ── OFFLINE MODE ──────────────────────────────────────────────────────────
    if args.offline:
        if not args.data.exists():
            _write_sample_data(args.data)
            print(f"Created sample data file: {args.data}")
            print("Edit it with your known quotes and re-run.")
            return

        with open(args.data) as f:
            data = json.load(f)

        fab_quotes         = data.get("fab_quotes", {})
        fab_is_pcba        = data.get("fab_quotes_are_pcba", False)
        pcb_quotes         = data.get("pcb_quotes", {})
        overrides          = data.get("bom_overrides", {})
        asm_cfg            = data.get("assembly", {})
        extended_part_fee  = asm_cfg.get("extended_part_fee", 0.0)
        standard_base_fee  = asm_cfg.get("standard_base_fee", 0.0) * asm_cfg.get("assembly_sides", 1)
        import_duty_rate = data.get("import_duty_rate", 0.0)
        sales_tax_rate   = data.get("sales_tax_rate",   0.0)
        payment_fee_rate = data.get("payment_fee_rate", 0.0)
        landed_rate      = 1.0 + import_duty_rate + sales_tax_rate + payment_fee_rate
        if import_duty_rate or sales_tax_rate:
            print(f"Taxes: {import_duty_rate*100:.1f}% import duty"
                  f" + {sales_tax_rate*100:.1f}% sales tax"
                  f" + {payment_fee_rate*100:.2f}% payment fee"
                  f"  →  ×{landed_rate:.3f} landed multiplier")

        # Prefer generated JLCPCB BOM CSV; fall back to manual list in data file
        if JLCPCB_BOM_CSV.exists():
            bom = load_bom_from_csv(JLCPCB_BOM_CSV, overrides)
            print(f"BOM: {len(bom)} parts from {JLCPCB_BOM_CSV.name}")
        elif data.get("bom"):
            bom = load_bom(data["bom"])
            print(f"BOM: {len(bom)} parts from quotes_data.json (manual)")
        else:
            bom = []
            print("BOM: none found — run circuit-synth/generate.py first")

        # ── Load component prices ─────────────────────────────────────────────
        api_tiers: dict[str, list[dict]] = {}
        if bom:
            lcsc_codes = [line.lcsc for line in bom]
            if args.fetch_prices:
                if not CREDENTIALS_FILE.exists():
                    ap.error(f"credentials.json not found (needed for --fetch-prices)")
                with open(CREDENTIALS_FILE) as f:
                    creds = json.load(f)
                app_id, access_key, secret_key = creds["AppID"], creds["Accesskey"], creds["SecretKey"]
                def _auth(method, path, body):
                    return _auth_header(method, path, body, app_id, access_key, secret_key)
                api_tiers = fetch_component_prices(lcsc_codes, API_BASE, _auth, PRICE_CACHE)
            elif PRICE_CACHE.exists():
                # Use stale cache without re-fetching
                import json as _j
                _cache = _j.loads(PRICE_CACHE.read_text())
                api_tiers = {c: (_cache[c]["tiers"] if c in _cache else []) for c in lcsc_codes}
                print(f"  Using cached component prices (run --fetch-prices to refresh)")

        # ── Assembly summary ──────────────────────────────────────────────────
        if bom:
            asm = assembly_summary(bom)
            forced = asm_cfg.get("type", asm["forced_type"])
            ext_str = (f", {asm['n_extended']} Extended × ${extended_part_fee:.2f}/order"
                       if asm["n_extended"] and extended_part_fee else "")
            so_str  = (f", Standard Only: {', '.join(l.lcsc for l in asm['standard_only'])}"
                       if asm["standard_only"] else "")
            std_str = (f", Standard base ${standard_base_fee:.2f}/side"
                       if standard_base_fee else "")
            print(f"Assembly: {forced} PCBA{ext_str}{so_str}{std_str}")

        # ── Fit PCB-only pricing model ─────────────────────────────────────────
        # Model: price = eng_fee + board_material_per_board_in_panel × boards_per_panel × qty
        # eng_fee = $4.00 fixed per order (confirmed from all breakdowns)
        # board_material_per_board_in_panel ≈ $0.170 (confirmed: 2x3=$0.170, 3x3=$0.169)
        ENG_FEE = 4.00
        # Derive board_material_per_board from all available breakdowns
        bm_samples = []
        for v_key, entries in pcb_quotes.items():
            if v_key.startswith("_") or not isinstance(entries, list):
                continue
            v_cols, v_rows = parse_variant(v_key)
            boards_per_panel = v_cols * v_rows
            for e in entries:
                if "breakdown" in e and e["qty"] > 0:
                    bm_per_panel = e["breakdown"]["board"] / e["qty"]
                    bm_samples.append(bm_per_panel / boards_per_panel)
        BM_PER_BOARD = sum(bm_samples) / len(bm_samples) if bm_samples else 0.170
        print(f"  PCB model: eng_fee=${ENG_FEE:.2f} + ${BM_PER_BOARD:.4f}/board-in-panel × boards × qty"
              + (f"  (avg of {len(bm_samples)} data point(s))" if bm_samples else "  (default)"))

        pcb_models: dict[str, tuple[float, float]] = {}
        for v, cols, rows in variants:
            mat = BM_PER_BOARD * cols * rows   # board_material cost per panel
            pcb_models[v] = (ENG_FEE, mat)

        # ── Fit PCBA pricing model per variant ────────────────────────────────
        models: dict[str, tuple[float, float]] = {}
        for v, cols, rows in variants:
            known = [(e["qty"], e["price"]) for e in fab_quotes.get(v, [])]
            models[v] = _fit_fab_model(known)
            a, b = models[v]
            src  = f"{len(known)} known point(s)" if known else "no data — model only"
            print(f"  PCBA {v}: setup_fee=${a:.2f}  marginal=${b:.2f}/panel  ({src})")

        # ── BOM-only mode ─────────────────────────────────────────────────────
        if args.bom:
            for qty in sorted(quantities):
                for v, cols, rows in variants:
                    total_boards = qty * cols * rows
                    eng, mat     = pcb_models[v]
                    pcb_total    = eng + mat * qty

                    # PCBA price for this config
                    known_map  = {e["qty"]: e["price"] for e in fab_quotes.get(v, [])}
                    if qty in known_map:
                        pcba_total = known_map[qty]
                    else:
                        a, b = models[v]
                        pcba_total = _estimate_fab(a, b, qty) if (a or b) else None

                    # Cheapest preferred shipping for this config
                    _ship_cfg      = data.get("shipping", {})
                    _ship_methods  = _ship_cfg.get("methods", [])
                    _preferred     = _ship_cfg.get("preferred_method")
                    if _ship_methods and pcb_w:
                        _opts     = _shipping_cost(_ship_methods, _panel_weight_g(pcb_w, pcb_l, qty, cols, rows), _preferred)
                        ship_cost = next((s["cost"] for s in _opts if s["display"] == _preferred and s["cost"] is not None), None) \
                                    or next((s["cost"] for s in _opts if s["cost"] is not None), None)
                    else:
                        ship_cost = None

                    print(f"\n--- {v} × {qty} panels ({total_boards} boards) ---")
                    print_bom_breakdown(bom, total_boards, api_tiers,
                                        extended_part_fee, standard_base_fee, pcb_total,
                                        pcba_total, import_duty_rate, ship_cost)
            return

        # ── Shipping methods from data file ───────────────────────────────────
        ship_cfg = data.get("shipping", {})
        ship_methods   = ship_cfg.get("methods", [])
        preferred_ship = ship_cfg.get("preferred_method")
        if ship_methods:
            dest = ship_cfg.get("destination", "")
            pref_str = f", preferred: {preferred_ship}" if preferred_ship else ""
            print(f"Shipping: {len(ship_methods)} method(s) configured"
                  + (f" → {dest}" if dest else "") + pref_str)
        else:
            print("Shipping: none configured in quotes_data.json")

        # ── Build fab + PCB + BOM + shipping results ──────────────────────────
        # fab_results[qty][v]  = (fab_price | None, actual_boards, estimated)
        # pcb_results[qty][v]  = (pcb_price | None, estimated)
        # bom_results[qty][v]  = bom_cost_per_board | None
        # ship_results[qty][v] = [{"display", "cost", "days"}, ...]
        fab_results:  dict = {}
        pcb_results:  dict = {}
        bom_results:  dict = {}
        ship_results: dict = {}
        for qty in quantities:
            fab_results[qty]  = {}
            pcb_results[qty]  = {}
            bom_results[qty]  = {}
            ship_results[qty] = {}
            for v, cols, rows in variants:
                actual_boards = qty * cols * rows
                known_map     = {e["qty"]: e["price"] for e in fab_quotes.get(v, [])}
                if qty in known_map:
                    fab_price, est = known_map[qty], False
                else:
                    a, b = models[v]
                    fab_price = _estimate_fab(a, b, qty) if (a or b) else None
                    est = True
                fab_results[qty][v] = (fab_price, actual_boards, est)

                pcb_known = {e["qty"]: e["price"] for e in pcb_quotes.get(v, [])}
                if qty in pcb_known:
                    pcb_results[qty][v] = (pcb_known[qty], False)
                else:
                    eng, mat = pcb_models[v]
                    pcb_price = (eng + mat * qty) if (eng or mat) else None
                    pcb_results[qty][v] = (pcb_price, True)

                bom_cpu, _ = bom_cost_per_board(bom, actual_boards, api_tiers) if bom else (None, [])
                bom_results[qty][v] = bom_cpu

                if ship_methods and pcb_w:
                    w_g = _panel_weight_g(pcb_w, pcb_l, qty, cols, rows)
                    ship_results[qty][v] = _shipping_cost(ship_methods, w_g, None)
                else:
                    ship_results[qty][v] = []

        # ── Table formatters ──────────────────────────────────────────────────
        def fab_total(qty, v):
            price, actual, est = fab_results[qty][v]
            return _fmt_price(price, est)

        def fab_cpu(qty, v):
            price, actual, est = fab_results[qty][v]
            return _fmt_cpu(price, actual, est)

        has_bom = (not fab_is_pcba) and bool(bom) and any(
            bom_results[quantities[0]][v] is not None for v, *_ in variants
        )

        def _total(qty, v):
            price, actual, est = fab_results[qty][v]
            comp_cpu = bom_results[qty][v] if has_bom else None
            if price is None or (has_bom and comp_cpu is None):
                return None, None, est
            return price + (comp_cpu or 0.0) * actual, actual, est

        def total_fmt(qty, v):
            total, actual, est = _total(qty, v)
            return _fmt_price(total, est)

        def total_cpu_fmt(qty, v):
            total, actual, est = _total(qty, v)
            return _fmt_cpu(total, actual or 1, est)

        def pcb_total_fmt(qty, v):
            price, est = pcb_results[qty][v]
            return _fmt_price(price, est)

        def pcb_cpu_fmt(qty, v):
            price, est = pcb_results[qty][v]
            _, actual, _ = fab_results[qty][v]
            return _fmt_cpu(price, actual, est)

        _print_table("PCB ONLY — total (bare board, no assembly)", variants, quantities, pcb_total_fmt)
        _print_table("PCB ONLY — per board",                       variants, quantities, pcb_cpu_fmt)

        fab_label = "PCBA COST" if fab_is_pcba else "FAB COST"
        _print_table(f"{fab_label} — total (USD, excl. shipping)", variants, quantities, fab_total)
        _print_table(f"{fab_label} — per board",                   variants, quantities, fab_cpu)

        if has_bom:
            _print_table("TOTAL excl. shipping (fab + components)",         variants, quantities, total_fmt)
            _print_table("TOTAL excl. shipping — per board",                variants, quantities, total_cpu_fmt)

        if fab_is_pcba and bom:
            bom_has_prices = any(
                bom_results[quantities[0]][v] is not None for v, *_ in variants
            )
            if bom_has_prices:
                print(f"\n  (BOM component costs are included in PCBA quotes above — shown below for reference only)")

        # ── Shipping table ────────────────────────────────────────────────────
        if ship_methods:
            # Collect all method names seen across results
            all_methods = []
            seen = set()
            for qty in quantities:
                for v, *_ in variants:
                    for s in ship_results[qty][v]:
                        if s["display"] not in seen:
                            all_methods.append(s["display"])
                            seen.add(s["display"])

            sep2 = "  "
            ship_col = 10
            ship_hdr = (f"{'Qty':>5}  {'Variant':>7}{sep2}"
                        + sep2.join(f"{m:>{ship_col}}" for m in all_methods))
            print(f"\n{'═'*len(ship_hdr)}\nSHIPPING COST (estimated by weight)\n{'═'*len(ship_hdr)}")
            print(ship_hdr)
            print("─" * len(ship_hdr))
            for qty in quantities:
                for v, cols, rows in variants:
                    opts     = {s["display"]: s for s in ship_results[qty][v]}
                    w_g      = _panel_weight_g(pcb_w, pcb_l, qty, cols, rows) if pcb_w else 0
                    row_pre  = f"{qty:>5}  {v:>7}{sep2}"
                    row_data = sep2.join(
                        (f"${opts[m]['cost']:>{ship_col-1}.2f}" if opts.get(m) and opts[m]['cost'] is not None
                         else f"{'—':>{ship_col}}")
                        for m in all_methods
                    )
                    print(f"{row_pre}{row_data}  ({w_g:.0f}g)")

        # ── Landed cost table (merch × tax multiplier + cheapest ship) ──────
        has_ship   = bool(ship_methods)
        has_landed = landed_rate > 1.0 or has_ship

        def _pick_ship(qty, v) -> dict | None:
            """Return the preferred shipping option, or cheapest if not found."""
            opts = ship_results[qty][v]
            if not opts:
                return None
            if preferred_ship:
                for s in opts:
                    if s["display"] == preferred_ship and s["cost"] is not None:
                        return s
            # Fall back to cheapest with a known cost
            valid = [s for s in opts if s["cost"] is not None]
            return valid[0] if valid else None

        def _landed(qty, v):
            """(landed_total, actual, est) including duty/tax/ship."""
            total, actual, est = _total(qty, v)
            if total is None:
                return None, actual, est
            ship = _pick_ship(qty, v)
            ship_cost = (ship["cost"] or 0.0) if ship else 0.0
            return total * landed_rate + ship_cost, actual, est

        if has_landed:
            ship_label = " + cheapest shipping" if has_ship else ""
            tax_label  = f" (×{landed_rate:.3f} tax/duty/fee{ship_label})"

            def landed_total_fmt(qty, v):
                lt, actual, est = _landed(qty, v)
                return _fmt_price(lt, est)

            def landed_cpu_fmt(qty, v):
                lt, actual, est = _landed(qty, v)
                return _fmt_cpu(lt, actual or 1, est)

            _print_table(f"LANDED COST — total{tax_label}",    variants, quantities, landed_total_fmt)
            _print_table(f"LANDED COST — per board{tax_label}", variants, quantities, landed_cpu_fmt)

        # ── Best panel summary ────────────────────────────────────────────────
        sep = "  "
        hdr = f"{'Qty':>5}{sep}" + sep.join(f"{v:>{COL_W}}" for v, *_ in variants)
        label = ("BEST PANEL — lowest landed cost per board"
                 + (" (PCBA)" if fab_is_pcba else " incl. components" if has_bom else "")
                 + (" + duty/tax" if landed_rate > 1.0 else "")
                 + (f" via {preferred_ship}" if preferred_ship else " + cheapest shipping" if has_ship else ""))
        print(f"\n{'═'*len(hdr)}\n{label}\n{'═'*len(hdr)}")
        for qty in quantities:
            best_v, best_cpu_val = None, float("inf")
            for v, cols, rows in variants:
                lt, actual, est = _landed(qty, v)
                if lt is None:
                    continue
                if lt / actual < best_cpu_val:
                    best_cpu_val, best_v = lt / actual, v
            if best_v:
                lt, actual, est = _landed(qty, best_v)
                total, _, _    = _total(qty, best_v)
                ship           = _pick_ship(qty, best_v) if has_ship else None
                ship_cost      = (ship["cost"] or 0.0) if ship else 0.0
                ship_name      = ship["display"] if ship else ""
                marker    = "~" if est else " "
                duty_str  = f" ×{landed_rate:.3f}" if landed_rate > 1.0 else ""
                ship_str  = f" + ${ship_cost:.2f} {ship_name}" if has_ship else ""
                print(f"  {qty:>3} panels  →  {best_v}  "
                      f"{marker}${total:.2f} merch{duty_str}{ship_str}"
                      f"  =  {marker}${lt:.2f} landed"
                      f"  ({marker}${lt/actual:.2f}/board, {actual} boards)")
        print(f"  ~ = estimated from model")
        return

    # ── LIVE MODE ─────────────────────────────────────────────────────────────
    if not CREDENTIALS_FILE.exists():
        ap.error(f"credentials.json not found: {CREDENTIALS_FILE}")
    with open(CREDENTIALS_FILE) as f:
        creds = json.load(f)
    app_id, access_key, secret_key = creds["AppID"], creds["Accesskey"], creds["SecretKey"]

    # live_results[qty][v] = (fab_price | None, actual_boards, ship_opts)
    live_results: dict = {}
    for qty in quantities:
        live_results[qty] = {}
        for v, cols, rows in variants:
            actual = qty * cols * rows
            print(f"  {v:>5}  qty={qty:>3}  → {actual} boards", end="  ")
            price, ship_opts = get_quote_live(
                cols, rows, qty, pcb_w, pcb_l, app_id, access_key, secret_key,
                country=args.country, postcode=args.postcode, city=args.city,
            )
            live_results[qty][v] = (price, actual, ship_opts)
            print(f"${price:.2f}" if price is not None else "—")

    def lv_total(qty, v):
        price, _, _s = live_results[qty][v]
        return _fmt_price(price)

    def lv_cpu(qty, v):
        price, actual, _s = live_results[qty][v]
        return _fmt_cpu(price, actual)

    _print_table("FAB COST (USD, excl. shipping)", variants, quantities, lv_total)
    _print_table("FAB COST — per board",           variants, quantities, lv_cpu)

    # Shipping table (only if destination was provided and API returned options)
    all_ship_methods = []
    seen_s = set()
    for qty in quantities:
        for v, *_ in variants:
            for s in live_results[qty][v][2]:
                if s["display"] not in seen_s:
                    all_ship_methods.append(s)
                    seen_s.add(s["display"])

    if all_ship_methods:
        sep2     = "  "
        ship_col = 10
        m_names  = [s["display"] for s in all_ship_methods]
        ship_hdr = (f"{'Qty':>5}  {'Variant':>7}{sep2}"
                    + sep2.join(f"{m:>{ship_col}}" for m in m_names))
        print(f"\n{'═'*len(ship_hdr)}\nSHIPPING OPTIONS\n{'═'*len(ship_hdr)}")
        print(ship_hdr)
        print("─" * len(ship_hdr))
        for qty in quantities:
            for v, *_ in variants:
                opts    = {s["display"]: s for s in live_results[qty][v][2]}
                row_pre = f"{qty:>5}  {v:>7}{sep2}"
                row_d   = sep2.join(
                    (f"${opts[m]['cost']:>{ship_col-1}.2f}" if opts.get(m) and opts[m]['cost'] is not None
                     else f"{'—':>{ship_col}}")
                    for m in m_names
                )
                print(f"{row_pre}{row_d}")

    sep = "  "
    hdr = f"{'Qty':>5}{sep}" + sep.join(f"{v:>{COL_W}}" for v, *_ in variants)
    print(f"\n{'═'*len(hdr)}\nBEST PANEL — lowest fab cost per board\n{'═'*len(hdr)}")
    for qty in quantities:
        best_v, best_cpu_val = None, float("inf")
        for v, *_ in variants:
            price, actual, _ = live_results[qty][v]
            if price is not None and price / actual < best_cpu_val:
                best_cpu_val, best_v = price / actual, v
        if best_v:
            price, actual, ship_opts = live_results[qty][best_v]
            cheapest_ship = min((s for s in ship_opts if s["cost"] is not None),
                                key=lambda s: s["cost"], default=None)
            ship_str = (f" + ${cheapest_ship['cost']:.2f} {cheapest_ship['display']}"
                        f" ({cheapest_ship['days']})" if cheapest_ship else "")
            print(f"  {qty:>3} panels  →  {best_v}  "
                  f"${price:.2f} fab{ship_str}  "
                  f"${best_cpu_val:.2f}/board  ({actual} boards)")


# ── Sample data file ───────────────────────────────────────────────────────────

def _write_sample_data(path: Path):
    sample = {
        "_comment": [
            "fab_quotes: known JLCPCB board quotes. qty = number of panels ordered.",
            "  Populate from the JLCPCB website quote tool.",
            "bom: bill of materials — one entry per unique LCSC part number.",
            "  qty_per_board: how many of this part per board.",
            "  price_tiers: optional manual tiers used when API prices are unavailable.",
            "    Each tier: {min_qty: N, unit_price: X} — N = total parts ordered.",
            "  Run with --fetch-prices to pull live tiers from the JLCPCB component API."
        ],
        "fab_quotes": {
            "1x1": [
                {"qty": 10, "price": 279.51}
            ],
            "2x2": [
                {"qty": 5,  "price": 405.78},
                {"qty": 10, "price": 653.24}
            ],
            "2x3": [],
            "3x3": [
                {"qty": 5,  "price": 714.92},
                {"qty": 10, "price": 1296.49}
            ]
        },
        "bom_overrides": {},
        "shipping": {
            "destination": "US",
            "methods": [
                {
                    "name": "DHL",
                    "days": "3-5",
                    "tiers": [
                        {"max_weight_g": 100,  "cost": 15.90},
                        {"max_weight_g": 200,  "cost": 16.90},
                        {"max_weight_g": 500,  "cost": 19.90},
                        {"max_weight_g": 1000, "cost": 24.90},
                        {"max_weight_g": 2000, "cost": 34.90}
                    ]
                },
                {
                    "name": "Ordinary Mail",
                    "days": "25-35",
                    "tiers": [
                        {"max_weight_g": 100,  "cost": 1.50},
                        {"max_weight_g": 200,  "cost": 2.20},
                        {"max_weight_g": 500,  "cost": 3.80},
                        {"max_weight_g": 1000, "cost": 5.50},
                        {"max_weight_g": 2000, "cost": 8.00}
                    ]
                }
            ]
        }
    }
    with open(path, "w") as f:
        json.dump(sample, f, indent=2)


if __name__ == "__main__":
    main()
