"""Provisional GRADE certainty ratings for the Summary of Findings table.

Automated domains: risk of bias, inconsistency, imprecision, publication bias.
Indirectness cannot be judged automatically and is flagged for reviewer input.
"""

from __future__ import annotations

from ureme.meta.effect_sizes import null_value

LEVELS = ["Very low", "Low", "Moderate", "High"]


def grade_outcome(result, rob_overall: list[str], designs: list[str], egger: dict | None = None) -> dict:
    start = 3 if not designs or sum(d.upper() == "RCT" for d in designs) >= len(designs) / 2 else 1
    reasons, down = [], 0

    high = sum(j in {"High", "Serious", "Critical"} for j in rob_overall)
    concerns = sum(j in {"Some concerns", "Moderate", "No information", ""} for j in rob_overall)
    n = max(len(rob_overall), 1)
    if high / n > 0.5:
        down += 2
        reasons.append("Risk of bias: very serious (-2) - most studies at high/serious risk")
    elif high / n > 0.25 or (high + concerns) / n > 0.5:
        down += 1
        reasons.append("Risk of bias: serious (-1) - substantial proportion of studies with concerns")

    if result.k > 1:
        if result.I2 >= 75:
            down += 2 if result.Q_p < 0.10 else 1
            reasons.append(f"Inconsistency: I² = {result.I2:.0f}% (-{2 if result.Q_p < 0.10 else 1})")
        elif result.I2 >= 50:
            down += 1
            reasons.append(f"Inconsistency: I² = {result.I2:.0f}% (-1)")

    nv = null_value(result.measure)
    lo, hi = result.display(result.ci_low), result.display(result.ci_high)
    total_n = None
    if lo <= nv <= hi:
        down += 1
        reasons.append("Imprecision: confidence interval includes the null effect (-1)")
    elif result.k < 3:
        down += 1
        reasons.append("Imprecision: fewer than three studies (-1)")

    if egger and egger.get("k", 0) >= 10 and egger.get("p", 1) < 0.10:
        down += 1
        reasons.append(f"Publication bias: Egger p = {egger['p']:.3f} (-1)")

    level = LEVELS[max(0, start - down)]
    return {
        "start": LEVELS[start],
        "certainty": level,
        "downgrades": reasons,
        "indirectness": "Not assessed automatically - reviewer judgement required",
        "provisional": True,
        "total_n": total_n,
    }
