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
import json
from pathlib import Path

from api import API_BASE, QUOTE_URI, auth_header, get_quote_live
from bom import (
    BomLine,
    assembly_summary,
    bom_cost_per_board,
    compute_assembly_cost,
    fetch_component_prices,
    load_bom,
    load_bom_from_csv,
    print_bom_breakdown,
)
from display import COL_W, fmt_cpu, fmt_price, print_table
from fab_model import estimate_fab, fit_fab_model, interpolate_variant_models
from pcb_cost import fit_pcb_model, parse_variant, read_pcb_dimensions
from shipping import panel_weight_g, shipping_cost

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"
DEFAULT_DATA = SCRIPT_DIR / "quotes_data.json"
PRICE_CACHE = SCRIPT_DIR / "component_prices_cache.json"
PCB_FILE = SCRIPT_DIR.parent / "speakeasy" / "Speakeasy.kicad_pcb"
JLCPCB_BOM_CSV = SCRIPT_DIR.parent / "speakeasy" / "speakeasy_jlcpcb_bom.csv"

DEFAULT_VARIANTS = ["1x1", "2x2", "2x3", "3x3"]
DEFAULT_QUANTITIES = [5, 10, 15, 20, 25]


def main():
    ap = argparse.ArgumentParser(description="JLCPCB panel price optimizer")
    ap.add_argument(
        "--offline",
        action="store_true",
        help="estimate from quotes_data.json instead of calling the API",
    )
    ap.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA,
        metavar="FILE",
        help="path to quotes/component data JSON (offline mode)",
    )
    ap.add_argument(
        "--qty",
        nargs="+",
        type=int,
        default=DEFAULT_QUANTITIES,
        metavar="N",
        help="panel quantities to evaluate",
    )
    ap.add_argument(
        "--variants",
        nargs="+",
        default=DEFAULT_VARIANTS,
        metavar="CxR",
        help="panel variants e.g. 1x1 2x2 2x3 3x3",
    )
    ap.add_argument("--pcb-width", type=float, default=None, metavar="MM")
    ap.add_argument("--pcb-length", type=float, default=None, metavar="MM")
    ap.add_argument(
        "--fetch-prices",
        action="store_true",
        help="hit the JLCPCB component API to refresh BOM prices",
    )
    ap.add_argument(
        "--bom", action="store_true", help="print BOM breakdown only (no panel table)"
    )
    ap.add_argument(
        "--residuals",
        action="store_true",
        help="show cost residuals for known PCBA quotes (offline mode)",
    )
    ap.add_argument(
        "--country",
        default=None,
        metavar="CC",
        help="destination country code for shipping estimate (e.g. US)",
    )
    ap.add_argument(
        "--postcode",
        default=None,
        metavar="ZIP",
        help="destination postcode for shipping estimate",
    )
    ap.add_argument(
        "--city",
        default=None,
        metavar="CITY",
        help="destination city for shipping estimate",
    )
    ap.add_argument(
        "--html",
        type=Path,
        default=None,
        metavar="FILE",
        help="write HTML report to FILE (e.g. report.html)",
    )
    args = ap.parse_args()

    variants = [(v, *parse_variant(v)) for v in args.variants]
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

        fab_quotes = data.get("fab_quotes", {})
        fab_is_pcba = data.get("fab_quotes_are_pcba", False)
        pcb_quotes = data.get("pcb_quotes", {})
        overrides = data.get("bom_overrides", {})
        asm_cfg = data.get("assembly", {})
        extended_part_fee = asm_cfg.get("extended_part_fee", 0.0)
        standard_base_fee = asm_cfg.get("standard_base_fee", 0.0) * asm_cfg.get(
            "assembly_sides", 1
        )
        import_duty_rate = data.get("import_duty_rate", 0.0)
        sales_tax_rate = data.get("sales_tax_rate", 0.0)
        payment_fee_rate = data.get("payment_fee_rate", 0.0)
        sale_rate = 1.0 + import_duty_rate + sales_tax_rate + payment_fee_rate
        cogs_rate = 1.0 + import_duty_rate + payment_fee_rate
        if import_duty_rate or sales_tax_rate:
            print(
                f"Taxes: {import_duty_rate * 100:.1f}% import duty"
                f" + {sales_tax_rate * 100:.1f}% sales tax"
                f" + {payment_fee_rate * 100:.2f}% payment fee"
                f"  →  ×{sale_rate:.3f} sale  /  ×{cogs_rate:.3f} COGS"
            )

        ship_cfg = data.get("shipping", {})
        ship_methods = ship_cfg.get("methods", [])
        preferred_ship = ship_cfg.get("preferred_method")

        def _fab_merch(entry: dict, cols: int, rows: int) -> float:
            """Return pure merch cost (pre-duty, pre-tax) from a fab_quotes entry.
            Uses breakdown.merch if present; otherwise back-calculates from grand
            total: merch = (grand − ship) / sale_rate if tax_free=False,
            or / cogs_rate if no tax was charged.
            """
            bp = entry.get("breakdown", {})
            if "merch" in bp:
                return bp["merch"]
            grand = entry["price"]
            if ship_methods and pcb_w and pcb_l:
                w_g = panel_weight_g(pcb_w, pcb_l, entry["qty"], cols, rows)
                opts = shipping_cost(ship_methods, w_g, preferred_ship)
                ship = (
                    next(
                        (
                            s["cost"]
                            for s in opts
                            if s["display"] == preferred_ship and s["cost"] is not None
                        ),
                        None,
                    )
                    or next((s["cost"] for s in opts if s["cost"] is not None), None)
                    or 0.0
                )
            else:
                ship = 0.0
            # tax_free=False → sales tax was charged; divide by sale_rate to recover
            # pure merch. Otherwise divide by cogs_rate (duty+fee but no sales tax).
            divisor = sale_rate if entry.get("tax_free") is False else cogs_rate
            return (grand - ship) / divisor if divisor > 1.0 else grand - ship

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
                app_id, access_key, secret_key = (
                    creds["AppID"],
                    creds["Accesskey"],
                    creds["SecretKey"],
                )

                def _auth(method, path, body):
                    return auth_header(
                        method, path, body, app_id, access_key, secret_key
                    )

                api_tiers = fetch_component_prices(
                    lcsc_codes, API_BASE, _auth, PRICE_CACHE
                )
            elif PRICE_CACHE.exists():
                import json as _j

                _cache = _j.loads(PRICE_CACHE.read_text())
                api_tiers = {
                    c: (_cache[c]["tiers"] if c in _cache else []) for c in lcsc_codes
                }
                print(
                    f"  Using cached component prices (run --fetch-prices to refresh)"
                )

        # ── Assembly summary ──────────────────────────────────────────────────
        if bom:
            asm = assembly_summary(bom)
            forced = asm_cfg.get("type", asm["forced_type"])
            ext_str = (
                f", {asm['n_extended']} Extended × ${extended_part_fee:.2f}/order"
                if asm["n_extended"] and extended_part_fee
                else ""
            )
            so_str = (
                f", Standard Only: {', '.join(l.lcsc for l in asm['standard_only'])}"
                if asm["standard_only"]
                else ""
            )
            std_str = (
                f", Standard base ${standard_base_fee:.2f}/side"
                if standard_base_fee
                else ""
            )
            print(f"Assembly: {forced} PCBA{ext_str}{so_str}{std_str}")

        # ── Fit bare-PCB pricing model ────────────────────────────────────────
        eng_fee, bm_per_board, n_bm = fit_pcb_model(pcb_quotes)
        print(
            f"  PCB model: eng_fee=${eng_fee:.2f} + ${bm_per_board:.4f}/board-in-panel × boards × qty"
            + (f"  (avg of {n_bm} data point(s))" if n_bm else "  (default)")
        )

        pcb_models: dict[str, tuple[float, float]] = {}
        for v, cols, rows in variants:
            pcb_models[v] = (eng_fee, bm_per_board * cols * rows)

        # ── Fit PCBA pricing model per variant ────────────────────────────────
        models: dict[str, tuple[float, float]] = {}
        for v, cols, rows in variants:
            known = [
                (e["qty"], _fab_merch(e, cols, rows)) for e in fab_quotes.get(v, [])
            ]
            models[v] = fit_fab_model(known)

        interpolate_variant_models(models, variants)

        for v, cols, rows in variants:
            a, b = models[v]
            n_pts = len(fab_quotes.get(v, []))
            src = (
                f"{n_pts} known point(s)" if n_pts else "~interpolated from neighbours"
            )
            print(f"  PCBA {v}: setup_fee=${a:.2f}  marginal=${b:.2f}/panel  ({src})")

        # ── BOM-only mode ─────────────────────────────────────────────────────
        if args.bom:
            for qty in sorted(quantities):
                for v, cols, rows in variants:
                    total_boards = qty * cols * rows
                    eng, mat = pcb_models[v]
                    pcb_total = estimate_fab(eng, mat, qty)

                    known_map = {
                        e["qty"]: _fab_merch(e, cols, rows)
                        for e in fab_quotes.get(v, [])
                    }
                    if qty in known_map:
                        pcba_total = known_map[qty]
                    else:
                        a, b = models[v]
                        pcba_total = estimate_fab(a, b, qty) if (a or b) else None

                    if ship_methods and pcb_w:
                        _opts = shipping_cost(
                            ship_methods,
                            panel_weight_g(pcb_w, pcb_l, qty, cols, rows),
                            preferred_ship,
                        )
                        ship_cost = next(
                            (
                                s["cost"]
                                for s in _opts
                                if s["display"] == preferred_ship
                                and s["cost"] is not None
                            ),
                            None,
                        ) or next(
                            (s["cost"] for s in _opts if s["cost"] is not None), None
                        )
                    else:
                        ship_cost = None

                    print(f"\n--- {v} × {qty} panels ({total_boards} boards) ---")
                    print_bom_breakdown(
                        bom,
                        total_boards,
                        api_tiers,
                        extended_part_fee,
                        standard_base_fee,
                        pcb_total,
                        pcba_total,
                        import_duty_rate,
                        ship_cost,
                        asm_cfg=asm_cfg,
                        pcb_w_mm=pcb_w,
                        pcb_l_mm=pcb_l,
                    )
            return

        # ── Residuals mode ────────────────────────────────────────────────────
        if args.residuals:
            col = 9
            hdr = (
                f"  {'Variant':>7}  {'Qty':>4}  {'Boards':>6}  "
                f"{'Comp/bd':>{col}}  {'PCB/bd':>{col}}  {'Asm/bd':>{col}}  "
                f"{'Bottom-up':>{col}}  {'Actual':>{col}}  Residual"
            )
            print(
                f"\n{'═' * len(hdr)}\n"
                f"RESIDUAL ANALYSIS — known PCBA quotes vs bottom-up (comp + PCB + assembly)\n"
                f"{'═' * len(hdr)}"
            )
            print(hdr)
            print("─" * len(hdr))
            for qty in quantities:
                for v, cols, rows in variants:
                    known_map = {
                        e["qty"]: _fab_merch(e, cols, rows)
                        for e in fab_quotes.get(v, [])
                    }
                    if qty not in known_map:
                        continue
                    actual_boards = qty * cols * rows
                    pcba_tot = known_map[qty]
                    pcba_pb = pcba_tot / actual_boards

                    eng, mat = pcb_models[v]
                    pcb_pb = estimate_fab(eng, mat, qty) / actual_boards

                    comp_cpu, _ = (
                        bom_cost_per_board(bom, actual_boards, api_tiers, asm_cfg)
                        if bom
                        else (None, [])
                    )

                    asm_detail = (
                        compute_assembly_cost(bom, actual_boards, pcb_w, pcb_l, asm_cfg)
                        if (bom and pcb_w and pcb_l)
                        else None
                    )
                    asm_pb = (
                        (asm_detail["total"] / actual_boards) if asm_detail else 0.0
                    )

                    if comp_cpu is None:
                        print(
                            f"  {v:>7}  {qty:>4}  {actual_boards:>6}  (missing component prices)"
                        )
                        continue

                    bottom_up = comp_cpu + pcb_pb + asm_pb
                    residual = pcba_pb - bottom_up
                    pct = residual / bottom_up * 100 if bottom_up else 0.0
                    sign = "+" if residual >= 0 else "-"
                    res_str = f"{sign}${abs(residual):.3f} ({sign}{abs(pct):.1f}%)"
                    print(
                        f"  {v:>7}  {qty:>4}  {actual_boards:>6}  "
                        f"${comp_cpu:{col - 1}.3f}  ${pcb_pb:{col - 1}.3f}  ${asm_pb:{col - 1}.3f}  "
                        f"${bottom_up:{col - 1}.3f}  ${pcba_pb:{col - 1}.3f}  "
                        f"{res_str}"
                    )
            print(
                f"\n  Positive residual = JLCPCB charges more than modeled (unaccounted fees/markup)."
            )
            print(
                f"  Negative residual = model overestimates (e.g. promotions applied to actual quote)."
            )
            if not pcb_w:
                print(
                    f"  (Assembly model unavailable — no PCB dimensions. Asm/bd = $0.)"
                )
            return

        # ── Shipping methods from data file ───────────────────────────────────
        if ship_methods:
            dest = ship_cfg.get("destination", "")
            pref_str = f", preferred: {preferred_ship}" if preferred_ship else ""
            print(
                f"Shipping: {len(ship_methods)} method(s) configured"
                + (f" → {dest}" if dest else "")
                + pref_str
            )
        else:
            print("Shipping: none configured in quotes_data.json")

        # ── Build fab + PCB + BOM + shipping results ──────────────────────────
        fab_results: dict = {}
        pcb_results: dict = {}
        bom_results: dict = {}
        ship_results: dict = {}
        for qty in quantities:
            fab_results[qty] = {}
            pcb_results[qty] = {}
            bom_results[qty] = {}
            ship_results[qty] = {}
            for v, cols, rows in variants:
                actual_boards = qty * cols * rows
                known_map = {
                    e["qty"]: _fab_merch(e, cols, rows) for e in fab_quotes.get(v, [])
                }
                if qty in known_map:
                    fab_price, est = known_map[qty], False
                else:
                    a, b = models[v]
                    fab_price = estimate_fab(a, b, qty) if (a or b) else None
                    est = True
                fab_results[qty][v] = (fab_price, actual_boards, est)

                pcb_known = {e["qty"]: e["price"] for e in pcb_quotes.get(v, [])}
                if qty in pcb_known:
                    pcb_results[qty][v] = (pcb_known[qty], False)
                else:
                    eng, mat = pcb_models[v]
                    pcb_price = estimate_fab(eng, mat, qty) if (eng or mat) else None
                    pcb_results[qty][v] = (pcb_price, True)

                bom_cpu, _ = (
                    bom_cost_per_board(bom, actual_boards, api_tiers, asm_cfg)
                    if bom
                    else (None, [])
                )
                bom_results[qty][v] = bom_cpu

                if ship_methods and pcb_w:
                    w_g = panel_weight_g(pcb_w, pcb_l, qty, cols, rows)
                    ship_results[qty][v] = shipping_cost(ship_methods, w_g, None)
                else:
                    ship_results[qty][v] = []

        # ── Table formatters ──────────────────────────────────────────────────
        def fab_total(qty, v):
            price, actual, est = fab_results[qty][v]
            return fmt_price(price, est)

        def fab_cpu(qty, v):
            price, actual, est = fab_results[qty][v]
            return fmt_cpu(price, actual, est)

        has_bom = (
            (not fab_is_pcba)
            and bool(bom)
            and any(bom_results[quantities[0]][v] is not None for v, *_ in variants)
        )

        def _total(qty, v):
            price, actual, est = fab_results[qty][v]
            comp_cpu = bom_results[qty][v] if has_bom else None
            if price is None or (has_bom and comp_cpu is None):
                return None, None, est
            return price + (comp_cpu or 0.0) * actual, actual, est

        def total_fmt(qty, v):
            total, actual, est = _total(qty, v)
            return fmt_price(total, est)

        def total_cpu_fmt(qty, v):
            total, actual, est = _total(qty, v)
            return fmt_cpu(total, actual or 1, est)

        def pcb_total_fmt(qty, v):
            price, est = pcb_results[qty][v]
            return fmt_price(price, est)

        def pcb_cpu_fmt(qty, v):
            price, est = pcb_results[qty][v]
            _, actual, _ = fab_results[qty][v]
            return fmt_cpu(price, actual, est)

        print_table(
            "PCB ONLY — total (bare board, no assembly)",
            variants,
            quantities,
            pcb_total_fmt,
        )
        print_table("PCB ONLY — per board", variants, quantities, pcb_cpu_fmt)

        fab_label = "PCBA COST" if fab_is_pcba else "FAB COST"
        print_table(
            f"{fab_label} — total (USD, excl. shipping)",
            variants,
            quantities,
            fab_total,
        )
        print_table(f"{fab_label} — per board", variants, quantities, fab_cpu)

        if has_bom:
            print_table(
                "TOTAL excl. shipping (fab + components)",
                variants,
                quantities,
                total_fmt,
            )
            print_table(
                "TOTAL excl. shipping — per board", variants, quantities, total_cpu_fmt
            )

        if fab_is_pcba and bom:
            bom_has_prices = any(
                bom_results[quantities[0]][v] is not None for v, *_ in variants
            )
            if bom_has_prices:
                print(
                    f"\n  (BOM component costs are included in PCBA quotes above — shown below for reference only)"
                )

        # ── Shipping table ────────────────────────────────────────────────────
        if ship_methods:
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
            ship_hdr = f"{'Qty':>5}  {'Variant':>7}{sep2}" + sep2.join(
                f"{m:>{ship_col}}" for m in all_methods
            )
            print(
                f"\n{'═' * len(ship_hdr)}\nSHIPPING COST (estimated by weight)\n{'═' * len(ship_hdr)}"
            )
            print(ship_hdr)
            print("─" * len(ship_hdr))
            for qty in quantities:
                for v, cols, rows in variants:
                    opts = {s["display"]: s for s in ship_results[qty][v]}
                    w_g = panel_weight_g(pcb_w, pcb_l, qty, cols, rows) if pcb_w else 0
                    row_pre = f"{qty:>5}  {v:>7}{sep2}"
                    row_d = sep2.join(
                        (
                            f"${opts[m]['cost']:>{ship_col - 1}.2f}"
                            if opts.get(m) and opts[m]["cost"] is not None
                            else f"{'—':>{ship_col}}"
                        )
                        for m in all_methods
                    )
                    print(f"{row_pre}{row_d}  ({w_g:.0f}g)")

        # ── Sale price table (merch × sale_rate + cheapest ship) ─────────────
        has_ship = bool(ship_methods)
        has_sale = sale_rate > 1.0 or has_ship

        def _pick_ship(qty, v) -> dict | None:
            opts = ship_results[qty][v]
            if not opts:
                return None
            if preferred_ship:
                for s in opts:
                    if s["display"] == preferred_ship and s["cost"] is not None:
                        return s
            valid = [s for s in opts if s["cost"] is not None]
            return valid[0] if valid else None

        def _cogs(qty, v):
            base, actual, est = _total(qty, v)
            if base is None:
                return None, actual, est
            ship = _pick_ship(qty, v)
            ship_cost = (ship["cost"] or 0.0) if ship else 0.0
            # base × cogs_rate + shipping (includes duty + payment, excludes sales_tax)
            return base * cogs_rate + ship_cost, actual, est

        def _sale(qty, v):
            base, actual, est = _total(qty, v)
            if base is None:
                return None, actual, est
            ship = _pick_ship(qty, v)
            ship_cost = (ship["cost"] or 0.0) if ship else 0.0
            # sale = merch × sale_rate + ship  (tax on merch only, not compounded on duty)
            return base * sale_rate + ship_cost, actual, est

        if has_sale:
            ship_label = " + cheapest shipping" if has_ship else ""
            if sales_tax_rate:
                WIDE = 22
                note = f" COGS (×{cogs_rate:.3f}), sale price in parens (×{sale_rate:.3f}){ship_label}"

                def _combined(cogs_tup, land_tup, boards):
                    ct, _, est = cogs_tup
                    lt, _, _ = land_tup
                    if ct is None:
                        return f"{'—':>{WIDE}}"
                    marker = "~" if est else " "
                    s = (
                        f"{marker}${ct / boards:.2f} (${lt / boards:.2f})"
                        if lt is not None
                        else f"{marker}${ct / boards:.2f}"
                    )
                    return s.rjust(WIDE)

                def combined_cpu_fmt(qty, v):
                    c = _cogs(qty, v)
                    l = _sale(qty, v)
                    return _combined(c, l, c[1] or 1)

                def combined_total_fmt(qty, v):
                    c = _cogs(qty, v)
                    l = _sale(qty, v)
                    ct, actual, est = c
                    lt, _, _ = l
                    if ct is None:
                        return f"{'—':>{WIDE}}"
                    marker = "~" if est else " "
                    s = (
                        f"{marker}${ct:.2f} (${lt:.2f})"
                        if lt is not None
                        else f"{marker}${ct:.2f}"
                    )
                    return s.rjust(WIDE)

                print_table(
                    f"COST — total{note}",
                    variants,
                    quantities,
                    combined_total_fmt,
                    WIDE,
                )
                print_table(
                    f"COST — per board{note}",
                    variants,
                    quantities,
                    combined_cpu_fmt,
                    WIDE,
                )
            else:
                tax_label = f" (×{sale_rate:.3f} duty/fee/tax{ship_label})"

                def sale_total_fmt(qty, v):
                    lt, actual, est = _sale(qty, v)
                    return fmt_price(lt, est)

                def sale_cpu_fmt(qty, v):
                    lt, actual, est = _sale(qty, v)
                    return fmt_cpu(lt, actual or 1, est)

                print_table(
                    f"SALE PRICE — total{tax_label}",
                    variants,
                    quantities,
                    sale_total_fmt,
                )
                print_table(
                    f"SALE PRICE — per board{tax_label}",
                    variants,
                    quantities,
                    sale_cpu_fmt,
                )

        # ── Best panel summary ────────────────────────────────────────────────
        sep = "  "
        hdr = f"{'Qty':>5}{sep}" + sep.join(f"{v:>{COL_W}}" for v, *_ in variants)
        label = (
            "BEST PANEL — lowest sale price per board"
            + (" (PCBA)" if fab_is_pcba else " incl. components" if has_bom else "")
            + (" + duty/tax" if sale_rate > 1.0 else "")
            + (
                f" via {preferred_ship}"
                if preferred_ship
                else " + cheapest shipping"
                if has_ship
                else ""
            )
        )
        print(f"\n{'═' * len(hdr)}\n{label}\n{'═' * len(hdr)}")
        for qty in quantities:
            best_v, best_cpu_val = None, float("inf")
            for v, cols, rows in variants:
                lt, actual, est = _sale(qty, v)
                if lt is None:
                    continue
                if lt / actual < best_cpu_val:
                    best_cpu_val, best_v = lt / actual, v
            if best_v:
                lt, actual, est = _sale(qty, best_v)
                total, _, _ = _total(qty, best_v)
                ship = _pick_ship(qty, best_v) if has_ship else None
                ship_cost = (ship["cost"] or 0.0) if ship else 0.0
                ship_name = ship["display"] if ship else ""
                marker = "~" if est else " "
                cogs_lt, _, _ = _cogs(qty, best_v)
                ship = _pick_ship(qty, best_v) if has_ship else None
                ship_cost = (ship["cost"] or 0.0) if ship else 0.0
                ship_name = ship["display"] if ship else ""
                ship_str = f" + ${ship_cost:.2f} {ship_name}" if has_ship else ""
                duty_str = f" ×{cogs_rate:.3f}" if cogs_rate > 1.0 else ""
                tax_str = f" ×{1 + sales_tax_rate:.3f} tax" if sales_tax_rate else ""
                cogs_str = (
                    f"  =  {marker}${cogs_lt:.2f} COGS" if cogs_lt is not None else ""
                )
                print(
                    f"  {qty:>3} panels  →  {best_v}  "
                    f"{marker}${total:.2f} merch{duty_str}{ship_str}"
                    f"{cogs_str}{tax_str}"
                    f"  =  {marker}${lt:.2f} sale"
                    f"  ({marker}${lt / actual:.2f}/board, {actual} boards)"
                )
        print(f"  ~ = estimated from model")

        # ── HTML report ───────────────────────────────────────────────────────
        if args.html:
            from report import generate_report

            bom_breakdown: dict = {}
            for qty in quantities:
                bom_breakdown[qty] = {}
                for v, cols, rows in variants:
                    total_boards = qty * cols * rows
                    eng, mat = pcb_models[v]
                    pcb_tot = estimate_fab(eng, mat, qty)
                    known_map = {
                        e["qty"]: _fab_merch(e, cols, rows)
                        for e in fab_quotes.get(v, [])
                    }
                    if qty in known_map:
                        pcba_tot, est_pcba = known_map[qty], False
                    else:
                        a, b = models[v]
                        pcba_tot = estimate_fab(a, b, qty) if (a or b) else None
                        est_pcba = True
                    if ship_methods and pcb_w:
                        _opts = shipping_cost(
                            ship_methods,
                            panel_weight_g(pcb_w, pcb_l, qty, cols, rows),
                            preferred_ship,
                        )
                        s_cost = next(
                            (
                                s["cost"]
                                for s in _opts
                                if s["display"] == preferred_ship
                                and s["cost"] is not None
                            ),
                            None,
                        ) or next(
                            (s["cost"] for s in _opts if s["cost"] is not None), None
                        )
                    else:
                        s_cost = None
                    comp_cpu, line_items_raw = (
                        bom_cost_per_board(bom, total_boards, api_tiers, asm_cfg)
                        if bom
                        else (None, [])
                    )
                    pcb_pb = pcb_tot / total_boards if total_boards else 0.0
                    asm_detail = (
                        compute_assembly_cost(bom, total_boards, pcb_w, pcb_l, asm_cfg)
                        if (bom and pcb_w and pcb_l)
                        else None
                    )
                    asm_pb = (asm_detail["total"] / total_boards) if asm_detail else 0.0
                    bottom_up = (comp_cpu or 0.0) + pcb_pb + asm_pb
                    asm_residual = (
                        (pcba_tot / total_boards - bottom_up) if pcba_tot else None
                    )
                    # pcba_tot = pure merch (duty/tax not yet applied)
                    # COGS     = merch × cogs_rate + shipping
                    # Landed   = merch × sale_rate + shipping
                    merch_pb = pcba_tot / total_boards if pcba_tot else None
                    ship_pb = (s_cost or 0.0) / total_boards
                    cogs_pb = (
                        merch_pb * cogs_rate + ship_pb if merch_pb is not None else None
                    )
                    sale_pb = (
                        merch_pb * sale_rate + ship_pb if merch_pb is not None else None
                    )
                    bom_breakdown[qty][v] = {
                        "total_boards": total_boards,
                        "pcb_cost_total": pcb_tot,
                        "pcba_price_total": pcba_tot,
                        "pcba_estimated": est_pcba,
                        "ship_cost": s_cost,
                        "component_cost_per_board": comp_cpu,
                        "pcb_per_board": pcb_pb,
                        "assembly_cost_detail": asm_detail,
                        "assembly_cost_per_board": asm_pb,
                        "assembly_residual_per_board": asm_residual,
                        "sale_per_board": sale_pb,
                        "cogs_per_board": cogs_pb,
                        "line_items": [
                            {
                                "lcsc": lcsc,
                                "desc": desc,
                                "qty_per_board": qpb,
                                "unit_price": up,
                                "line_total": lt,
                                "lib_type": next(
                                    (l.lib_type for l in bom if l.lcsc == lcsc), "Basic"
                                ),
                                "standard_only": next(
                                    (l.standard_only for l in bom if l.lcsc == lcsc),
                                    False,
                                ),
                            }
                            for lcsc, desc, qpb, up, lt, _ in line_items_raw
                        ],
                    }

            asm_meta = (
                assembly_summary(bom)
                if bom
                else {"forced_type": "Economy", "n_extended": 0, "standard_only": []}
            )
            report_data = {
                "meta": {
                    "pcb_w": pcb_w or 0,
                    "pcb_l": pcb_l or 0,
                    "assembly_type": asm_cfg.get("type", asm_meta["forced_type"]),
                    "n_extended": asm_meta["n_extended"],
                    "standard_only": [l.lcsc for l in asm_meta["standard_only"]],
                    "import_duty_rate": import_duty_rate,
                    "sales_tax_rate": sales_tax_rate,
                    "sale_rate": sale_rate,
                    "cogs_rate": cogs_rate,
                    "sales_tax_rate": sales_tax_rate,
                    "preferred_ship": data.get("shipping", {}).get(
                        "preferred_method", ""
                    ),
                    "bm_per_board": bm_per_board,
                    "eng_fee": eng_fee,
                },
                "variants": [v for v, *_ in variants],
                "quantities": quantities,
                "fab_results": {
                    qty: {v: fab_results[qty][v] for v, *_ in variants}
                    for qty in quantities
                },
                "pcb_results": {
                    qty: {v: pcb_results[qty][v] for v, *_ in variants}
                    for qty in quantities
                },
                "ship_results": {
                    qty: {v: ship_results[qty][v] for v, *_ in variants}
                    for qty in quantities
                },
                "bom_breakdown": bom_breakdown,
                "preferred_ship": data.get("shipping", {}).get("preferred_method", ""),
            }
            html_path = args.html if args.html.is_absolute() else SCRIPT_DIR / args.html
            generate_report(report_data, html_path)
            print(f"\nHTML report written: {html_path}")

        return

    # ── LIVE MODE ─────────────────────────────────────────────────────────────
    if not CREDENTIALS_FILE.exists():
        ap.error(f"credentials.json not found: {CREDENTIALS_FILE}")
    with open(CREDENTIALS_FILE) as f:
        creds = json.load(f)
    app_id, access_key, secret_key = (
        creds["AppID"],
        creds["Accesskey"],
        creds["SecretKey"],
    )

    live_results: dict = {}
    for qty in quantities:
        live_results[qty] = {}
        for v, cols, rows in variants:
            actual = qty * cols * rows
            print(f"  {v:>5}  qty={qty:>3}  → {actual} boards", end="  ")
            price, ship_opts = get_quote_live(
                cols,
                rows,
                qty,
                pcb_w,
                pcb_l,
                app_id,
                access_key,
                secret_key,
                country=args.country,
                postcode=args.postcode,
                city=args.city,
            )
            live_results[qty][v] = (price, actual, ship_opts)
            print(f"${price:.2f}" if price is not None else "—")

    def lv_total(qty, v):
        price, _, _s = live_results[qty][v]
        return fmt_price(price)

    def lv_cpu(qty, v):
        price, actual, _s = live_results[qty][v]
        return fmt_cpu(price, actual)

    print_table("FAB COST (USD, excl. shipping)", variants, quantities, lv_total)
    print_table("FAB COST — per board", variants, quantities, lv_cpu)

    all_ship_methods = []
    seen_s = set()
    for qty in quantities:
        for v, *_ in variants:
            for s in live_results[qty][v][2]:
                if s["display"] not in seen_s:
                    all_ship_methods.append(s)
                    seen_s.add(s["display"])

    if all_ship_methods:
        sep2 = "  "
        ship_col = 10
        m_names = [s["display"] for s in all_ship_methods]
        ship_hdr = f"{'Qty':>5}  {'Variant':>7}{sep2}" + sep2.join(
            f"{m:>{ship_col}}" for m in m_names
        )
        print(f"\n{'═' * len(ship_hdr)}\nSHIPPING OPTIONS\n{'═' * len(ship_hdr)}")
        print(ship_hdr)
        print("─" * len(ship_hdr))
        for qty in quantities:
            for v, *_ in variants:
                opts = {s["display"]: s for s in live_results[qty][v][2]}
                row_pre = f"{qty:>5}  {v:>7}{sep2}"
                row_d = sep2.join(
                    (
                        f"${opts[m]['cost']:>{ship_col - 1}.2f}"
                        if opts.get(m) and opts[m]["cost"] is not None
                        else f"{'—':>{ship_col}}"
                    )
                    for m in m_names
                )
                print(f"{row_pre}{row_d}")

    sep = "  "
    hdr = f"{'Qty':>5}{sep}" + sep.join(f"{v:>{COL_W}}" for v, *_ in variants)
    print(
        f"\n{'═' * len(hdr)}\nBEST PANEL — lowest fab cost per board\n{'═' * len(hdr)}"
    )
    for qty in quantities:
        best_v, best_cpu_val = None, float("inf")
        for v, *_ in variants:
            price, actual, _ = live_results[qty][v]
            if price is not None and price / actual < best_cpu_val:
                best_cpu_val, best_v = price / actual, v
        if best_v:
            price, actual, ship_opts = live_results[qty][best_v]
            cheapest_ship = min(
                (s for s in ship_opts if s["cost"] is not None),
                key=lambda s: s["cost"],
                default=None,
            )
            ship_str = (
                f" + ${cheapest_ship['cost']:.2f} {cheapest_ship['display']}"
                f" ({cheapest_ship['days']})"
                if cheapest_ship
                else ""
            )
            print(
                f"  {qty:>3} panels  →  {best_v}  "
                f"${price:.2f} fab{ship_str}  "
                f"${best_cpu_val:.2f}/board  ({actual} boards)"
            )


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
            "  Run with --fetch-prices to pull live tiers from the JLCPCB component API.",
        ],
        "fab_quotes": {
            "1x1": [{"qty": 10, "price": 279.51}],
            "2x2": [{"qty": 5, "price": 405.78}, {"qty": 10, "price": 653.24}],
            "2x3": [],
            "3x3": [{"qty": 5, "price": 714.92}, {"qty": 10, "price": 1296.49}],
        },
        "bom_overrides": {},
        "shipping": {
            "destination": "US",
            "methods": [
                {
                    "name": "DHL",
                    "days": "3-5",
                    "tiers": [
                        {"max_weight_g": 100, "cost": 15.90},
                        {"max_weight_g": 200, "cost": 16.90},
                        {"max_weight_g": 500, "cost": 19.90},
                        {"max_weight_g": 1000, "cost": 24.90},
                        {"max_weight_g": 2000, "cost": 34.90},
                    ],
                },
                {
                    "name": "Ordinary Mail",
                    "days": "25-35",
                    "tiers": [
                        {"max_weight_g": 100, "cost": 1.50},
                        {"max_weight_g": 200, "cost": 2.20},
                        {"max_weight_g": 500, "cost": 3.80},
                        {"max_weight_g": 1000, "cost": 5.50},
                        {"max_weight_g": 2000, "cost": 8.00},
                    ],
                },
            ],
        },
    }
    with open(path, "w") as f:
        json.dump(sample, f, indent=2)


if __name__ == "__main__":
    main()
