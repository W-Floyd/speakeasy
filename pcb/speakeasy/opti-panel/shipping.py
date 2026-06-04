#!/usr/bin/env python3
"""Shipping weight estimation and offline shipping cost lookup."""

# FR4 physical constants
FR4_DENSITY_G_CM3 = 1.85
COPPER_FACTOR     = 1.30   # +30% for copper layers, silkscreen, solder mask
PACKAGING_G       = 80.0   # flat packaging overhead per shipment

_PCB_THICKNESS_MM = 1.6    # default PCB thickness


def panel_weight_g(pcb_w: float, pcb_l: float,
                   qty_panels: int, cols: int, rows: int) -> float:
    """Estimate total shipment weight in grams for a panel order.

    Panel dimensions include 2 mm inter-board gaps and 5+6 mm rails
    (top+bottom) per JLCPCB panel_preset.json.  Single boards have no rails.
    """
    if cols == 1 and rows == 1:
        panel_w, panel_l = pcb_w, pcb_l
    else:
        panel_w = pcb_w * cols + 2.0 * (cols - 1)
        panel_l = pcb_l * rows + 2.0 * (rows - 1) + 2 * (5.0 + 6.0)
    volume_cm3 = (panel_w * panel_l * _PCB_THICKNESS_MM) / 1000.0
    board_g    = volume_cm3 * FR4_DENSITY_G_CM3 * COPPER_FACTOR
    return board_g * qty_panels + PACKAGING_G


def shipping_cost(methods: list[dict], weight_g: float,
                  preferred: str | None) -> list[dict]:
    """
    Look up shipping cost from an offline tier table for the given weight.

    methods: from quotes_data.json "shipping.methods"
      Each entry: {"name": str, "tiers": [{"max_weight_g": N, "cost": X}, ...]}

    Returns a list of {"display": str, "cost": float | None, "days": str}
    sorted cheapest-first.  Packages heavier than all tiers get the last tier's
    cost rather than None.
    """
    results = []
    for m in methods:
        cost = None
        for tier in sorted(m.get("tiers", []), key=lambda t: t["max_weight_g"]):
            if weight_g <= tier["max_weight_g"]:
                cost = tier["cost"]
                break
        if cost is None and m.get("tiers"):
            cost = max(m["tiers"], key=lambda t: t["max_weight_g"])["cost"]
        results.append({
            "display": m.get("name", ""),
            "cost":    cost,
            "days":    m.get("days", ""),
        })
    results.sort(key=lambda r: (r["cost"] is None, r["cost"] or 0))
    return results
