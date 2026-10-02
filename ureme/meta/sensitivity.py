"""Sensitivity (leave-one-out, restriction) and subgroup analyses."""

from __future__ import annotations

import numpy as np
from scipy import stats

from ureme.meta.models import MetaResult, meta_analyze


def leave_one_out(res: MetaResult, **kw) -> list[dict]:
    if res.k < 3:
        return []
    out = []
    opts = dict(measure=res.measure, model=res.model, tau2_method=res.tau2_method or "REML", hksj=res.hksj,
                level=res.level)
    opts.update(kw)
    for i, label in enumerate(res.labels):
        y = res.yi[:i] + res.yi[i + 1:]
        v = res.vi[:i] + res.vi[i + 1:]
        r = meta_analyze(y, v, res.labels[:i] + res.labels[i + 1:], **opts)
        out.append({"omitted": label, "estimate": r.display(r.estimate), "ci_low": r.display(r.ci_low),
                    "ci_high": r.display(r.ci_high), "p": r.p, "I2": r.I2, "tau2": r.tau2})
    return out


def subgroup_analysis(yi, vi, labels, groups, measure: str, model: str = "random", tau2_method: str = "REML",
                      hksj: bool = False, level: float = 0.95) -> dict | None:
    """Separate syntheses per subgroup + test for subgroup differences (Q_between)."""
    groups = [g if g not in (None, "") else "Unspecified" for g in groups]
    names = list(dict.fromkeys(groups))
    if len(names) < 2:
        return None
    results = {}
    for g in names:
        idx = [i for i, x in enumerate(groups) if x == g]
        results[g] = meta_analyze([yi[i] for i in idx], [vi[i] for i in idx], [labels[i] for i in idx],
                                  measure=measure, model=model, tau2_method=tau2_method, hksj=hksj, level=level)
    est = np.array([r.estimate for r in results.values()])
    var = np.array([r.se**2 for r in results.values()])
    w = 1 / var
    pooled = np.sum(w * est) / np.sum(w)
    q_b = float(np.sum(w * (est - pooled) ** 2))
    df = len(names) - 1
    return {
        "subgroups": {g: r.summary() for g, r in results.items()},
        "Q_between": q_b, "df": df, "p_between": float(stats.chi2.sf(q_b, df)),
    }


def restricted_analysis(yi, vi, labels, keep_mask, measure: str, reason: str, **kw) -> dict | None:
    idx = [i for i, keep in enumerate(keep_mask) if keep]
    if len(idx) < 2 or len(idx) == len(yi):
        return None
    r = meta_analyze([yi[i] for i in idx], [vi[i] for i in idx], [labels[i] for i in idx], measure=measure, **kw)
    return {"analysis": reason, "k": r.k, "estimate": r.display(r.estimate), "ci_low": r.display(r.ci_low),
            "ci_high": r.display(r.ci_high), "p": r.p, "I2": r.I2}
