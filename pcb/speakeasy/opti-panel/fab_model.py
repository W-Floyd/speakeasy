#!/usr/bin/env python3
"""Offline PCBA/fab pricing model.

Fits a linear price model from known JLCPCB quotes and interpolates
estimates for variants or quantities without data.

Model:  price = setup_fee + marginal × qty
"""

SETUP_PANELS_EQUIV = 3  # JLCPCB setup fee ≈ cost of ~3 panels of material


def fit_fab_model(known: list[tuple[int, float]]) -> tuple[float, float]:
    """
    Fit (setup_fee, marginal_cost) from a list of (qty, price) pairs.

    1 point  → single-point heuristic: setup_fee = SETUP_PANELS_EQUIV × marginal
    2+ points → ordinary least-squares
    0 points  → (0.0, 0.0) sentinel meaning "no data"
    """
    if len(known) == 0:
        return 0.0, 0.0
    if len(known) == 1:
        qty0, p0 = known[0]
        m = p0 / (SETUP_PANELS_EQUIV + qty0)
        return m * SETUP_PANELS_EQUIV, m
    n      = len(known)
    sum_q  = sum(q for q, _ in known)
    sum_p  = sum(p for _, p in known)
    sum_qq = sum(q * q for q, _ in known)
    sum_qp = sum(q * p for q, p in known)
    denom  = n * sum_qq - sum_q * sum_q
    if abs(denom) < 1e-9:          # all same qty — just average
        return 0.0, sum_p / sum_q
    b = (n * sum_qp - sum_q * sum_p) / denom
    a = (sum_p - b * sum_q) / n
    return max(a, 0.0), max(b, 0.0)   # clamp negatives from noisy fits


def estimate_fab(setup_fee: float, marginal: float, qty: int) -> float:
    return setup_fee + marginal * qty


def interpolate_variant_models(
    models: dict[str, tuple[float, float]],
    variants: list[tuple[str, int, int]],
) -> dict[str, tuple[float, float]]:
    """
    Fill in (0, 0) models for variants with no data by interpolating
    (or extrapolating) from fitted neighbours ordered by boards-per-panel.

    Mutates `models` in-place and returns it.
    """
    fitted_bpp: dict[int, tuple[float, float]] = {
        cols * rows: models[v]
        for v, cols, rows in variants
        if models[v] != (0.0, 0.0)
    }
    if not fitted_bpp:
        return models

    sorted_bpps = sorted(fitted_bpp.keys())

    for v, cols, rows in variants:
        if models[v] != (0.0, 0.0):
            continue
        bpp   = cols * rows
        below = [(b, *fitted_bpp[b]) for b in sorted_bpps if b <= bpp]
        above = [(b, *fitted_bpp[b]) for b in sorted_bpps if b >= bpp]

        if below and above:
            lo_bpp, lo_a, lo_b = below[-1]
            hi_bpp, hi_a, hi_b = above[0]
            if lo_bpp == hi_bpp:
                models[v] = (lo_a, lo_b)
            else:
                t = (bpp - lo_bpp) / (hi_bpp - lo_bpp)
                models[v] = (lo_a + t * (hi_a - lo_a), lo_b + t * (hi_b - lo_b))
        elif below:
            lo_bpp, lo_a, lo_b = below[-1]
            ratio = bpp / lo_bpp if lo_bpp else 1
            models[v] = (lo_a, lo_b * ratio)
        elif above:
            hi_bpp, hi_a, hi_b = above[0]
            ratio = bpp / hi_bpp if hi_bpp else 1
            models[v] = (hi_a, hi_b * ratio)

    return models
