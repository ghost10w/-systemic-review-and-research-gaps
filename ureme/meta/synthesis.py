"""Run the full quantitative synthesis for every outcome in an extraction sheet."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ureme.meta.bias import egger_test, begg_test, forest_data, funnel_data
from ureme.meta.effect_sizes import CONTINUOUS_MEASURES, DICHOTOMOUS_MEASURES
from ureme.meta.models import meta_analyze
from ureme.meta.sensitivity import leave_one_out, restricted_analysis, subgroup_analysis
from ureme.review.extraction import StudyOutcome, default_measure
from ureme.review.grade import grade_outcome
from ureme.review.rob import normalize_judgement, normalize_tool, overall_judgement

log = logging.getLogger(__name__)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "outcome"


def synthesize(studies: list[StudyOutcome], measure: str | None = None, model: str = "random",
               tau2_method: str = "REML", hksj: bool = False, level: float = 0.95,
               figures_dir: str | Path | None = None) -> dict:
    """Returns ``{"outcomes": {name: {...}}, "excluded": [...]}`` ready for JSON and reporting."""
    from ureme.meta.plots import render_forest, render_funnel

    by_outcome: dict[str, list[StudyOutcome]] = {}
    for s in studies:
        if s.include:
            by_outcome.setdefault(s.outcome, []).append(s)
    out: dict = {"outcomes": {}, "excluded": [], "settings": {"model": model, "tau2_method": tau2_method,
                                                              "hksj": hksj, "level": level}}
    for outcome, rows in by_outcome.items():
        m = (measure or next((r.measure for r in rows if r.measure), None) or default_measure(rows[0].outcome_type)).upper()
        expected = DICHOTOMOUS_MEASURES if rows[0].outcome_type == "dichotomous" else (
            CONTINUOUS_MEASURES if rows[0].outcome_type == "continuous" else DICHOTOMOUS_MEASURES | CONTINUOUS_MEASURES)
        if m not in expected:
            m = default_measure(rows[0].outcome_type)
        yi, vi, labels, used = [], [], [], []
        for r in rows:
            if not r.has_data_for(m):
                out["excluded"].append({"study": r.study_label, "outcome": outcome, "reason": "Missing outcome data"})
                continue
            try:
                es = r.effect(m)
            except (ValueError, KeyError) as exc:
                out["excluded"].append({"study": r.study_label, "outcome": outcome, "reason": f"Invalid data: {exc}"})
                continue
            if es is None:
                out["excluded"].append({"study": r.study_label, "outcome": outcome,
                                        "reason": "Non-estimable (zero events in both arms)"})
                continue
            yi.append(es.yi)
            vi.append(es.vi)
            labels.append(r.study_label)
            used.append(r)
        if not yi:
            continue
        res = meta_analyze(yi, vi, labels, measure=m, model=model, tau2_method=tau2_method, hksj=hksj, level=level)
        fe = meta_analyze(yi, vi, labels, measure=m, model="fixed", level=level)
        kw = dict(model=model, tau2_method=tau2_method, hksj=hksj, level=level)
        rob_overall = []
        for r in used:
            tool = normalize_tool(r.rob_tool, r.design)
            rob_overall.append(normalize_judgement(r.rob_overall, tool) if r.rob_overall
                               else overall_judgement(tool, list(r.rob_domains.values())))
        egger = egger_test(yi, vi)
        sensitivity = []
        low_mask = [j not in {"High", "Serious", "Critical"} for j in rob_overall]
        ra = restricted_analysis(yi, vi, labels, low_mask, m, "Excluding studies at high/serious risk of bias", **kw)
        if ra:
            sensitivity.append(ra)
        alt = "fixed" if model == "random" else "random"
        alt_res = fe if alt == "fixed" else meta_analyze(yi, vi, labels, measure=m, model="random",
                                                          tau2_method=tau2_method, level=level)
        sensitivity.append({"analysis": f"{alt.title()}-effect model", "k": alt_res.k,
                            "estimate": alt_res.display(alt_res.estimate), "ci_low": alt_res.display(alt_res.ci_low),
                            "ci_high": alt_res.display(alt_res.ci_high), "p": alt_res.p, "I2": alt_res.I2})
        groups = [r.subgroup for r in used]
        sub = subgroup_analysis(yi, vi, labels, groups, m, **kw) if any(groups) else None
        entry = {
            "measure": m,
            "outcome_type": rows[0].outcome_type,
            "result": res.summary(),
            "text": res.text(),
            "fixed_effect": fe.summary(),
            "forest": forest_data(res),
            "funnel": funnel_data(res),
            "egger": egger,
            "begg": begg_test(yi, vi),
            "leave_one_out": leave_one_out(res),
            "sensitivity": sensitivity,
            "subgroups": sub,
            "rob_overall": dict(zip(labels, rob_overall)),
            "grade": grade_outcome(res, rob_overall, [r.design for r in used], egger),
            "total_participants": int(sum(_participants(r) for r in used)),
            "figures": {},
        }
        if figures_dir:
            fdir = Path(figures_dir)
            slug = _slug(outcome)
            entry["figures"]["forest"] = str(render_forest(res, fdir / f"forest_{slug}.png", title=outcome))
            if res.k >= 3:
                entry["figures"]["funnel"] = str(render_funnel(res, fdir / f"funnel_{slug}.png", title=outcome))
        out["outcomes"][outcome] = entry
    return out


def _participants(r: StudyOutcome) -> float:
    d = r.data
    if d.get("treat_total") is not None and d.get("ctrl_total") is not None:
        return d["treat_total"] + d["ctrl_total"]
    if d.get("treat_n") is not None and d.get("ctrl_n") is not None:
        return d["treat_n"] + d["ctrl_n"]
    return 0
