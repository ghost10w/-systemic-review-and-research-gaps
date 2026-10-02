"""Matplotlib renderers for forest and funnel plots (PNG, embedded in reports)."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ureme.meta.bias import forest_data, funnel_data  # noqa: E402
from ureme.meta.effect_sizes import MEASURE_NAMES, null_value  # noqa: E402
from ureme.meta.models import MetaResult, p_text  # noqa: E402

INK = "#1f3864"


def _plain_log_axis(ax) -> None:
    """Log-scaled x axis labelled with plain numbers (0.5, 1, 2) rather than powers of ten."""
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

    ax.set_xscale("log")
    ax.xaxis.set_major_locator(LogLocator(base=10, subs=(0.1, 0.2, 0.25, 0.5, 1.0)))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(NullFormatter())


def render_forest(res: MetaResult, path: str | Path, title: str = "", favours: tuple[str, str] | None = None) -> Path:
    fd = forest_data(res)
    rows = fd["rows"]
    n = len(rows)
    fig_h = 0.38 * n + 2.6
    fig, ax = plt.subplots(figsize=(10, fig_h))
    ys = list(range(n, 0, -1))
    log = fd["log_scale"]
    for y, r in zip(ys, rows):
        ax.plot([r["ci_low"], r["ci_high"]], [y, y], color=INK, lw=1)
        size = 30 + 4 * r["weight_pct"]
        ax.scatter([r["effect"]], [y], marker="s", s=size, color=INK, zorder=3)
    p = fd["pooled"]
    yd = -0.2
    ax.fill([p["ci_low"], p["effect"], p["ci_high"], p["effect"]], [yd, yd + 0.35, yd, yd - 0.35], color="#c00000",
            zorder=3)
    if p["pred_low"] is not None:
        ax.plot([p["pred_low"], p["pred_high"]], [yd - 0.6, yd - 0.6], color="#c00000", lw=2, alpha=0.5)
    nv = null_value(res.measure)
    ax.axvline(nv, color="#555", lw=0.8, ls="-")
    ax.axvline(p["effect"], color="#c00000", lw=0.8, ls=":")
    if log:
        _plain_log_axis(ax)
    ax.set_yticks(ys + [yd])
    ax.set_yticklabels([r["label"] for r in rows] + [f"Pooled ({res.model} effects)"])
    ax.set_ylim(-1.3 if p["pred_low"] is not None else -1, n + 0.8)
    for y, r in zip(ys, rows):
        ax.annotate(f"{r['effect']:.2f} [{r['ci_low']:.2f}, {r['ci_high']:.2f}]  {r['weight_pct']:.1f}%",
                    xy=(1.01, y), xycoords=("axes fraction", "data"), va="center", fontsize=8)
    ax.annotate(f"{p['effect']:.2f} [{p['ci_low']:.2f}, {p['ci_high']:.2f}]  100%", xy=(1.01, yd),
                xycoords=("axes fraction", "data"), va="center", fontsize=8, weight="bold")
    ax.annotate("Effect [95% CI]  Weight", xy=(1.01, n + 0.6), xycoords=("axes fraction", "data"), fontsize=8,
                weight="bold")
    ax.set_xlabel(MEASURE_NAMES.get(res.measure, res.measure) + (" (log scale)" if log else ""))
    het = (f"Heterogeneity: τ² = {res.tau2:.3f}; Q({res.Q_df}) = {res.Q:.2f}, {p_text(res.Q_p)}; "
           f"I² = {res.I2:.0f}%\nTest for overall effect: {'t' if res.hksj else 'z'} = {res.z:.2f}, "
           f"{p_text(res.p)}")
    ax.text(0, -0.13, het, transform=ax.transAxes, fontsize=8, va="top")
    if favours:
        ax.text(0.25, 1.01, f"← Favours {favours[0]}", transform=ax.transAxes, ha="center", fontsize=8)
        ax.text(0.75, 1.01, f"Favours {favours[1]} →", transform=ax.transAxes, ha="center", fontsize=8)
    if title:
        ax.set_title(title, fontsize=11, pad=18)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def render_funnel(res: MetaResult, path: str | Path, title: str = "") -> Path:
    fd = funnel_data(res)
    fig, ax = plt.subplots(figsize=(6.5, 5))
    c = fd["contour"]
    tr = (lambda x: [math.exp(v) for v in x]) if res.is_ratio else (lambda x: list(x))
    ax.plot(tr(c["lower"]), c["se"], ls="--", color="#777", lw=0.8)
    ax.plot(tr(c["upper"]), c["se"], ls="--", color="#777", lw=0.8)
    ax.axvline(res.display(res.estimate), color="#c00000", lw=1)
    ax.scatter(tr([pt["effect"] for pt in fd["points"]]), [pt["se"] for pt in fd["points"]], color=INK, zorder=3)
    ax.invert_yaxis()
    if res.is_ratio:
        _plain_log_axis(ax)
    ax.set_ylabel("Standard error")
    ax.set_xlabel(MEASURE_NAMES.get(res.measure, res.measure))
    eg = fd["egger"]
    if eg:
        ax.text(0.02, 0.02, f"Egger's test: intercept = {eg['intercept']:.2f}, {p_text(eg['p'])}"
                + ("" if eg["adequately_powered"] else " (k < 10: low power)"), transform=ax.transAxes, fontsize=8)
    if title:
        ax.set_title(title, fontsize=11)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path
