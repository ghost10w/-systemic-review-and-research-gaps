"""Fixed- and random-effects meta-analysis with heterogeneity statistics.

tau^2 estimators: DerSimonian-Laird (DL), restricted maximum likelihood
(REML; Fisher scoring as in Viechtbauer 2005, matching metafor's default) and
Paule-Mandel (PM).  Optional Hartung-Knapp-Sidik-Jonkman (HKSJ) adjustment.
Confidence interval for tau^2 uses the Q-profile method.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy import optimize, stats

from ureme.meta.effect_sizes import RATIO_MEASURES, to_display


@dataclass
class MetaResult:
    measure: str
    model: str                     # "fixed" | "random"
    tau2_method: str | None
    k: int
    estimate: float                # analysis scale
    se: float
    ci_low: float
    ci_high: float
    z: float                       # z (or t under HKSJ)
    p: float
    Q: float
    Q_df: int
    Q_p: float
    I2: float                      # percent
    H2: float
    tau2: float
    tau: float
    tau2_ci: tuple[float, float] | None = None
    I2_ci: tuple[float, float] | None = None
    pred_low: float | None = None
    pred_high: float | None = None
    hksj: bool = False
    labels: list[str] = field(default_factory=list)
    yi: list[float] = field(default_factory=list)
    vi: list[float] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)  # percent
    level: float = 0.95

    @property
    def is_ratio(self) -> bool:
        return self.measure.upper() in RATIO_MEASURES

    def display(self, value: float | None) -> float | None:
        return None if value is None else to_display(value, self.measure)

    def summary(self) -> dict:
        d = asdict(self)
        d.update(
            estimate_display=self.display(self.estimate),
            ci_low_display=self.display(self.ci_low),
            ci_high_display=self.display(self.ci_high),
            pred_low_display=self.display(self.pred_low),
            pred_high_display=self.display(self.pred_high),
            scale="log" if self.is_ratio else "identity",
        )
        return d

    def text(self) -> str:
        est, lo, hi = self.display(self.estimate), self.display(self.ci_low), self.display(self.ci_high)
        stat = "t" if self.hksj else "z"
        return (f"{self.measure} {est:.2f} ({int(self.level * 100)}% CI {lo:.2f} to {hi:.2f}); "
                f"{stat} = {self.z:.2f}, {p_text(self.p)}; k = {self.k}; "
                f"I² = {self.I2:.0f}%, τ² = {self.tau2:.3f}, Q({self.Q_df}) = {self.Q:.2f}, {p_text(self.Q_p)}")


def p_text(p: float) -> str:
    """'p < 0.001' or 'p = 0.034' for running text."""
    f = format_p(p)
    return f"p {f[0]} {f[1:]}" if f.startswith("<") else f"p = {f}"


def format_p(p: float) -> str:
    if p is None or math.isnan(p):
        return "NA"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _q_stat(y: np.ndarray, v: np.ndarray, tau2: float = 0.0) -> float:
    w = 1 / (v + tau2)
    mu = np.sum(w * y) / np.sum(w)
    return float(np.sum(w * (y - mu) ** 2))


def tau2_dl(y: np.ndarray, v: np.ndarray) -> float:
    w = 1 / v
    q = _q_stat(y, v)
    c = np.sum(w) - np.sum(w**2) / np.sum(w)
    return max(0.0, (q - (len(y) - 1)) / c) if c > 0 else 0.0


def tau2_reml(y: np.ndarray, v: np.ndarray, tol: float = 1e-10, max_iter: int = 200) -> float:
    tau2 = tau2_dl(y, v)
    for _ in range(max_iter):
        w = 1 / (v + tau2)
        mu = np.sum(w * y) / np.sum(w)
        new = float(np.sum(w**2 * ((y - mu) ** 2 - v)) / np.sum(w**2) + 1 / np.sum(w))
        new = max(0.0, new)
        if abs(new - tau2) < tol:
            return new
        # step halving for stability
        tau2 = new if new >= 0 else tau2 / 2
    # fall back to direct maximisation of the restricted log-likelihood
    def neg_ll(t2: float) -> float:
        w = 1 / (v + t2)
        mu = np.sum(w * y) / np.sum(w)
        return 0.5 * (np.sum(np.log(v + t2)) + math.log(np.sum(w)) + np.sum(w * (y - mu) ** 2))
    hi = max(10 * float(np.var(y)), 10 * float(np.max(v)), 1.0)
    return float(optimize.minimize_scalar(neg_ll, bounds=(0, hi), method="bounded").x)


def tau2_pm(y: np.ndarray, v: np.ndarray) -> float:
    k = len(y)
    if _q_stat(y, v, 0.0) <= k - 1:
        return 0.0
    f = lambda t2: _q_stat(y, v, t2) - (k - 1)
    hi = 1.0
    while f(hi) > 0:
        hi *= 2
    return float(optimize.brentq(f, 0.0, hi))


def tau2_ci_qprofile(y: np.ndarray, v: np.ndarray, level: float = 0.95) -> tuple[float, float] | None:
    k = len(y)
    if k < 2:
        return None
    df = k - 1
    a = (1 - level) / 2
    q_hi, q_lo = stats.chi2.ppf(1 - a, df), stats.chi2.ppf(a, df)

    def solve(target: float) -> float:
        f = lambda t2: _q_stat(y, v, t2) - target
        if f(0.0) < 0:
            return 0.0
        hi = 1.0
        while f(hi) > 0 and hi < 1e8:
            hi *= 2
        return float(optimize.brentq(f, 0.0, hi))

    return solve(q_hi), solve(q_lo)


def meta_analyze(yi, vi, labels=None, measure: str = "SMD", model: str = "random", tau2_method: str = "REML",
                 hksj: bool = False, level: float = 0.95) -> MetaResult:
    y = np.asarray(yi, dtype=float)
    v = np.asarray(vi, dtype=float)
    if y.shape != v.shape or len(y) == 0:
        raise ValueError("yi and vi must be non-empty and of equal length")
    if np.any(v <= 0):
        raise ValueError("All sampling variances must be positive")
    k = len(y)
    labels = list(labels) if labels is not None else [f"Study {i + 1}" for i in range(k)]
    model = model.lower()
    method = tau2_method.upper()

    # Heterogeneity (always from the fixed-effect fit)
    w_fe = 1 / v
    Q = _q_stat(y, v)
    df = k - 1
    Q_p = float(stats.chi2.sf(Q, df)) if df > 0 else float("nan")
    I2 = max(0.0, (Q - df) / Q) * 100 if Q > 0 and df > 0 else 0.0
    H2 = Q / df if df > 0 else float("nan")

    if model == "fixed":
        tau2, method_used = 0.0, None
    elif model == "random":
        method_used = method
        if k == 1:
            tau2 = 0.0
        elif method == "DL":
            tau2 = tau2_dl(y, v)
        elif method == "REML":
            tau2 = tau2_reml(y, v)
        elif method == "PM":
            tau2 = tau2_pm(y, v)
        else:
            raise ValueError(f"Unknown tau^2 estimator {tau2_method}; use DL, REML or PM")
    else:
        raise ValueError("model must be 'fixed' or 'random'")

    w = 1 / (v + tau2)
    mu = float(np.sum(w * y) / np.sum(w))
    se = math.sqrt(1 / np.sum(w))
    alpha = 1 - level
    use_hksj = hksj and model == "random" and k > 1
    if use_hksj:
        q_w = float(np.sum(w * (y - mu) ** 2) / df)
        se = se * math.sqrt(max(q_w, 1.0))  # ad hoc variance correction (never narrower than standard)
        crit = stats.t.ppf(1 - alpha / 2, df)
        z = mu / se
        p = float(2 * stats.t.sf(abs(z), df))
    else:
        crit = stats.norm.ppf(1 - alpha / 2)
        z = mu / se
        p = float(2 * stats.norm.sf(abs(z)))

    pred_low = pred_high = None
    tau2_ci = I2_ci = None
    if model == "random" and k >= 3:
        t_crit = stats.t.ppf(1 - alpha / 2, k - 2)
        half = t_crit * math.sqrt(tau2 + se**2)
        pred_low, pred_high = mu - half, mu + half
        tau2_ci = tau2_ci_qprofile(y, v, level)
        if tau2_ci:
            # I^2 bounds implied by tau^2 bounds and the "typical" within-study variance
            s2 = df * np.sum(w_fe) / (np.sum(w_fe) ** 2 - np.sum(w_fe**2))
            I2_ci = tuple(100 * t / (t + s2) for t in tau2_ci)

    return MetaResult(
        measure=measure.upper(), model=model, tau2_method=method_used, k=k, estimate=mu, se=se,
        ci_low=mu - crit * se, ci_high=mu + crit * se, z=float(z), p=p, Q=Q, Q_df=df, Q_p=Q_p,
        I2=I2, H2=H2, tau2=tau2, tau=math.sqrt(tau2), tau2_ci=tau2_ci, I2_ci=I2_ci,
        pred_low=pred_low, pred_high=pred_high, hksj=use_hksj, labels=labels,
        yi=y.tolist(), vi=v.tolist(), weights=(100 * w / np.sum(w)).tolist(), level=level,
    )
