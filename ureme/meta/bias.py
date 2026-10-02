"""Small-study effects / publication bias: Egger's regression, Begg's rank test, funnel data."""

from __future__ import annotations

import math

import numpy as np
import statsmodels.api as sm
from scipy import stats

from ureme.meta.models import MetaResult


def egger_test(yi, vi) -> dict | None:
    """Egger's regression test (standard normal deviate on precision). Needs k >= 3."""
    y, v = np.asarray(yi, float), np.asarray(vi, float)
    if len(y) < 3:
        return None
    se = np.sqrt(v)
    X = sm.add_constant(1 / se)
    fit = sm.OLS(y / se, X).fit()
    return {
        "intercept": float(fit.params[0]),
        "se": float(fit.bse[0]),
        "t": float(fit.tvalues[0]),
        "p": float(fit.pvalues[0]),
        "slope": float(fit.params[1]),
        "k": len(y),
        "adequately_powered": len(y) >= 10,
    }


def begg_test(yi, vi) -> dict | None:
    """Begg & Mazumdar rank correlation (Kendall's tau)."""
    y, v = np.asarray(yi, float), np.asarray(vi, float)
    if len(y) < 3:
        return None
    w = 1 / v
    mu = np.sum(w * y) / np.sum(w)
    v_star = v - 1 / np.sum(w)
    z = (y - mu) / np.sqrt(np.clip(v_star, 1e-12, None))
    tau, p = stats.kendalltau(z, v)
    return {"kendall_tau": float(tau), "p": float(p), "k": len(y)}


def funnel_data(res: MetaResult, level: float = 0.95) -> dict:
    """Points plus pseudo-confidence contour for a funnel plot (analysis scale)."""
    se = [math.sqrt(x) for x in res.vi]
    max_se = max(se) * 1.1 if se else 1
    z = stats.norm.ppf(1 - (1 - level) / 2)
    grid = np.linspace(0, max_se, 50)
    return {
        "measure": res.measure,
        "scale": "log" if res.is_ratio else "identity",
        "points": [{"label": l, "effect": y, "se": s} for l, y, s in zip(res.labels, res.yi, se)],
        "pooled": res.estimate,
        "contour": {"se": grid.tolist(), "lower": (res.estimate - z * grid).tolist(),
                    "upper": (res.estimate + z * grid).tolist()},
        "egger": egger_test(res.yi, res.vi),
        "begg": begg_test(res.yi, res.vi),
    }


def forest_data(res: MetaResult) -> dict:
    """Rows for a forest plot, on the display scale."""
    z = stats.norm.ppf(1 - (1 - res.level) / 2)
    rows = []
    for label, y, v, w in zip(res.labels, res.yi, res.vi, res.weights):
        s = math.sqrt(v)
        rows.append({"label": label, "effect": res.display(y), "ci_low": res.display(y - z * s),
                     "ci_high": res.display(y + z * s), "weight_pct": w})
    return {
        "measure": res.measure, "model": res.model, "rows": rows,
        "pooled": {"effect": res.display(res.estimate), "ci_low": res.display(res.ci_low),
                   "ci_high": res.display(res.ci_high), "pred_low": res.display(res.pred_low),
                   "pred_high": res.display(res.pred_high)},
        "heterogeneity": {"I2": res.I2, "tau2": res.tau2, "Q": res.Q, "df": res.Q_df, "p": res.Q_p},
        "log_scale": res.is_ratio,
    }
