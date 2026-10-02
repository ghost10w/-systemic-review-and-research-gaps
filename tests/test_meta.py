import math

import numpy as np
import pytest
from statsmodels.stats.meta_analysis import combine_effects

from ureme.meta.bias import begg_test, egger_test, forest_data, funnel_data
from ureme.meta.effect_sizes import (compute_effect, log_odds_ratio, log_risk_ratio, mean_difference,
                                     risk_difference, smd_hedges_g)
from ureme.meta.models import meta_analyze, p_text
from ureme.meta.sensitivity import leave_one_out, subgroup_analysis

# metafor::dat.bcg (tpos, tneg+tpos, cpos, cneg+cpos)
BCG = [(4, 123, 11, 139), (6, 306, 29, 303), (3, 231, 11, 220), (62, 13598, 248, 12867), (33, 5069, 47, 5808),
       (180, 1541, 372, 1451), (8, 2545, 10, 629), (505, 88391, 499, 88391), (29, 7499, 45, 7277),
       (17, 1716, 65, 1665), (186, 50634, 141, 27338), (5, 2498, 3, 2341), (27, 16913, 29, 17854)]


@pytest.fixture(scope="module")
def bcg():
    es = [log_risk_ratio(*r) for r in BCG]
    return [e.yi for e in es], [e.vi for e in es]


def test_effect_sizes():
    e = log_odds_ratio(10, 50, 20, 50)
    assert math.isclose(math.exp(e.yi), (10 * 30) / (40 * 20))
    assert math.isclose(e.vi, 1 / 10 + 1 / 40 + 1 / 20 + 1 / 30)
    rr = log_risk_ratio(10, 50, 20, 50)
    assert math.isclose(math.exp(rr.yi), 0.5)
    z = log_odds_ratio(0, 20, 5, 20)
    assert z.corrected and math.isclose(math.exp(z.yi), (0.5 * 15.5) / (20.5 * 5.5))
    assert log_odds_ratio(0, 20, 0, 20) is None
    g = smd_hedges_g(10, 2, 20, 8, 2, 20)
    assert math.isclose(g.yi, (1 - 3 / (4 * 40 - 9)) * 1.0)
    assert math.isclose(mean_difference(10, 2, 20, 8, 2, 20).vi, 0.4)
    assert math.isclose(risk_difference(10, 50, 20, 50).yi, -0.2)
    assert compute_effect("smd", treat_mean=10, treat_sd=2, treat_n=20, ctrl_mean=8, ctrl_sd=2, ctrl_n=20).measure == "SMD"
    with pytest.raises(ValueError):
        log_odds_ratio(60, 50, 1, 50)


def test_bcg_matches_metafor(bcg):
    y, v = bcg
    fe = meta_analyze(y, v, measure="RR", model="fixed")
    assert fe.estimate == pytest.approx(-0.4303, abs=1e-4) and fe.se == pytest.approx(0.0405, abs=1e-4)
    assert fe.Q == pytest.approx(152.2330, abs=1e-3) and fe.Q_df == 12
    reml = meta_analyze(y, v, measure="RR", tau2_method="REML")
    assert reml.estimate == pytest.approx(-0.7145, abs=1e-4)
    assert reml.se == pytest.approx(0.1798, abs=1e-4)
    assert reml.tau2 == pytest.approx(0.3132, abs=1e-4)
    assert reml.tau2_ci[0] == pytest.approx(0.1197, abs=1e-3) and reml.tau2_ci[1] == pytest.approx(1.1115, abs=1e-3)
    dl = meta_analyze(y, v, measure="RR", tau2_method="DL")
    assert dl.estimate == pytest.approx(-0.7141, abs=1e-4) and dl.tau2 == pytest.approx(0.3088, abs=1e-4)
    pm = meta_analyze(y, v, measure="RR", tau2_method="PM")
    assert pm.tau2 == pytest.approx(0.3181, abs=1e-3)
    assert reml.display(reml.estimate) == pytest.approx(math.exp(-0.7145), abs=1e-3)


def test_dl_matches_statsmodels(bcg):
    y, v = bcg
    ref = combine_effects(np.array(y), np.array(v), method_re="dl")
    ours = meta_analyze(y, v, measure="RR", tau2_method="DL")
    assert ours.estimate == pytest.approx(ref.mean_effect_re, rel=1e-8)
    assert ours.tau2 == pytest.approx(ref.tau2, rel=1e-8)
    assert ours.I2 == pytest.approx(ref.i2 * 100, rel=1e-6)


def test_hksj_and_prediction(bcg):
    y, v = bcg
    r = meta_analyze(y, v, measure="RR", hksj=True)
    plain = meta_analyze(y, v, measure="RR")
    assert r.hksj and (r.ci_high - r.ci_low) >= (plain.ci_high - plain.ci_low)
    assert r.pred_low < r.ci_low and r.pred_high > r.ci_high


def test_homogeneous_and_single_study():
    r = meta_analyze([0.2, 0.2, 0.2], [0.01, 0.02, 0.03])
    assert r.tau2 == 0 and r.I2 == 0
    one = meta_analyze([0.5], [0.04])
    assert one.k == 1 and one.estimate == 0.5 and math.isnan(one.Q_p)
    with pytest.raises(ValueError):
        meta_analyze([0.1], [0.0])


def test_bias_and_plot_data(bcg):
    y, v = bcg
    eg = egger_test(y, v)
    assert eg["k"] == 13 and 0 <= eg["p"] <= 1 and eg["adequately_powered"]
    assert begg_test(y, v)["k"] == 13
    assert egger_test([0.1, 0.2], [0.1, 0.1]) is None
    res = meta_analyze(y, v, [f"S{i}" for i in range(13)], measure="RR")
    fd = forest_data(res)
    assert len(fd["rows"]) == 13 and sum(r["weight_pct"] for r in fd["rows"]) == pytest.approx(100)
    assert fd["log_scale"] and fd["pooled"]["effect"] == pytest.approx(math.exp(res.estimate))
    fu = funnel_data(res)
    assert len(fu["points"]) == 13 and len(fu["contour"]["se"]) == 50


def test_sensitivity_and_subgroups(bcg):
    y, v = bcg
    res = meta_analyze(y, v, [f"S{i}" for i in range(13)], measure="RR")
    loo = leave_one_out(res)
    assert len(loo) == 13 and all(r["omitted"].startswith("S") for r in loo)
    groups = ["A"] * 6 + ["B"] * 7
    sg = subgroup_analysis(y, v, res.labels, groups, "RR")
    assert set(sg["subgroups"]) == {"A", "B"} and sg["df"] == 1 and 0 <= sg["p_between"] <= 1
    assert subgroup_analysis(y, v, res.labels, ["A"] * 13, "RR") is None


def test_p_text():
    assert p_text(0.0001) == "p < 0.001" and p_text(0.0345) == "p = 0.035"
