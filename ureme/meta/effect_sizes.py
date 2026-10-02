"""Study-level effect sizes on the analysis scale.

Ratio measures (OR, RR) are analysed on the natural-log scale and
back-transformed for display.  Formulas follow the Cochrane Handbook
(chapter 10) and Borenstein et al., *Introduction to Meta-Analysis* (2009).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

RATIO_MEASURES = {"OR", "RR"}
DICHOTOMOUS_MEASURES = {"OR", "RR", "RD"}
CONTINUOUS_MEASURES = {"SMD", "MD"}
MEASURE_NAMES = {
    "OR": "Odds ratio", "RR": "Risk ratio", "RD": "Risk difference",
    "SMD": "Standardised mean difference (Hedges' g)", "MD": "Mean difference",
}


@dataclass
class EffectSize:
    yi: float          # effect on analysis scale (log for OR/RR)
    vi: float          # sampling variance
    measure: str
    corrected: bool = False  # continuity correction applied

    @property
    def sei(self) -> float:
        return math.sqrt(self.vi)


def _check_2x2(a: float, n1: float, c: float, n2: float) -> None:
    if n1 <= 0 or n2 <= 0 or a < 0 or c < 0 or a > n1 or c > n2:
        raise ValueError(f"Invalid 2x2 data: events {a}/{n1} vs {c}/{n2}")


def _cells(a: float, n1: float, c: float, n2: float, cc: float) -> tuple[float, float, float, float, bool]:
    b, d = n1 - a, n2 - c
    if min(a, b, c, d) == 0:
        return a + cc, b + cc, c + cc, d + cc, True
    return a, b, c, d, False


def log_odds_ratio(a: float, n1: float, c: float, n2: float, cc: float = 0.5) -> EffectSize | None:
    """a/n1 = events/total in experimental arm; c/n2 in control arm."""
    _check_2x2(a, n1, c, n2)
    if (a == 0 and c == 0) or (a == n1 and c == n2):
        return None  # non-estimable: no information on the relative effect
    a2, b2, c2, d2, corr = _cells(a, n1, c, n2, cc)
    return EffectSize(math.log((a2 * d2) / (b2 * c2)), 1 / a2 + 1 / b2 + 1 / c2 + 1 / d2, "OR", corr)


def log_risk_ratio(a: float, n1: float, c: float, n2: float, cc: float = 0.5) -> EffectSize | None:
    _check_2x2(a, n1, c, n2)
    if (a == 0 and c == 0) or (a == n1 and c == n2):
        return None
    a2, b2, c2, d2, corr = _cells(a, n1, c, n2, cc)
    m1, m2 = a2 + b2, c2 + d2
    return EffectSize(math.log((a2 / m1) / (c2 / m2)), 1 / a2 - 1 / m1 + 1 / c2 - 1 / m2, "RR", corr)


def risk_difference(a: float, n1: float, c: float, n2: float) -> EffectSize:
    _check_2x2(a, n1, c, n2)
    p1, p2 = a / n1, c / n2
    v = p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2
    if v == 0:
        v = 0.25 / n1 + 0.25 / n2  # degenerate case: fall back to max-variance bound
    return EffectSize(p1 - p2, v, "RD")


def _check_cont(sd1: float, n1: float, sd2: float, n2: float) -> None:
    if n1 < 2 or n2 < 2 or sd1 <= 0 or sd2 <= 0:
        raise ValueError(f"Invalid continuous data: SD {sd1}/{sd2}, N {n1}/{n2}")


def smd_hedges_g(m1: float, sd1: float, n1: float, m2: float, sd2: float, n2: float) -> EffectSize:
    _check_cont(sd1, n1, sd2, n2)
    sp = math.sqrt(((n1 - 1) * sd1**2 + (n2 - 1) * sd2**2) / (n1 + n2 - 2))
    d = (m1 - m2) / sp
    j = 1 - 3 / (4 * (n1 + n2) - 9)
    g = j * d
    v = (n1 + n2) / (n1 * n2) + g**2 / (2 * (n1 + n2))
    return EffectSize(g, v, "SMD")


def mean_difference(m1: float, sd1: float, n1: float, m2: float, sd2: float, n2: float) -> EffectSize:
    _check_cont(sd1, n1, sd2, n2)
    return EffectSize(m1 - m2, sd1**2 / n1 + sd2**2 / n2, "MD")


def compute_effect(measure: str, **data: float) -> EffectSize | None:
    """Dispatch on measure. Dichotomous keys: treat_events, treat_total, ctrl_events, ctrl_total.
    Continuous keys: treat_mean, treat_sd, treat_n, ctrl_mean, ctrl_sd, ctrl_n."""
    m = measure.upper()
    if m in DICHOTOMOUS_MEASURES:
        args = (data["treat_events"], data["treat_total"], data["ctrl_events"], data["ctrl_total"])
        return {"OR": log_odds_ratio, "RR": log_risk_ratio, "RD": risk_difference}[m](*args)
    if m in CONTINUOUS_MEASURES:
        args = (data["treat_mean"], data["treat_sd"], data["treat_n"], data["ctrl_mean"], data["ctrl_sd"], data["ctrl_n"])
        return {"SMD": smd_hedges_g, "MD": mean_difference}[m](*args)
    raise ValueError(f"Unknown effect measure: {measure}")


def to_display(value: float, measure: str) -> float:
    return math.exp(value) if measure.upper() in RATIO_MEASURES else value


def null_value(measure: str) -> float:
    """Null effect on the display scale."""
    return 1.0 if measure.upper() in RATIO_MEASURES else 0.0
