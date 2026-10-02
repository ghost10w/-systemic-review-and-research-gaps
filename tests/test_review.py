import csv

from ureme.demo import DEMO_CRITERIA, demo_bundle
from ureme.models import Record
from ureme.review.dedup import deduplicate, normalize_title
from ureme.review.extraction import build_extraction_template, infer_design, load_extraction, suggest_outcome_data
from ureme.review.prisma import build_flow
from ureme.review.rob import ROB2_DOMAINS, overall_judgement, rob_matrix, suggest_rob
from ureme.review.screening import (Criteria, apply_overrides, assess_eligibility, detect_sample_size, find_terms,
                                    screen_title_abstract)


def R(title, **kw):
    return Record(title=title, abstract=kw.pop("abstract", "Adults with depression were randomized to exercise."),
                  **kw)


def test_dedup_rules():
    recs = [
        R("Exercise for depression: a randomized trial", doi="https://doi.org/10.1/ABC", year=2020,
          authors=["Smith J"], sources=["PubMed"]),
        R("Exercise for depression: a randomized trial.", doi="10.1/abc", year=2020, sources=["Europe PMC"],
          citation_count=5),
        R("Exercise for depression - a randomised trial", year=2021, authors=["Smith J"], s2_id="x",
          sources=["Semantic Scholar"]),
        R("Exercise for anxiety: a randomized trial in older adults", year=2020, authors=["Smith J"]),
        R("Exercise for depression: a randomized trial", year=2015, authors=["Jones K"], pmid="9"),
    ]
    dd = deduplicate(recs)
    assert len(dd.unique) == 3 and dd.n_removed == 2
    kept = dd.unique[0]
    assert set(kept.sources) == {"PubMed", "Europe PMC", "Semantic Scholar"} and kept.citation_count == 5
    reasons = {d["reason"].split(" ")[0] for d in dd.duplicates}
    assert "identical" in reasons and "title" in reasons
    assert normalize_title("Café: <i>Test</i>!") == "cafe test"


def test_screening_reasons_and_wildcards():
    c = Criteria.from_dict(DEMO_CRITERIA)
    assert find_terms("participants were randomised", ["randomi*"]) == ["randomi*"]
    assert find_terms("heart-failure", ["heart failure"]) and not find_terms("rate", ["rat"])
    recs = [
        R("Exercise and depression RCT", year=2020, publication_types=["Randomized Controlled Trial"]),
        R("Old trial of exercise for depression", year=2010),
        R("Review of exercise for depression", year=2020, publication_types=["Review"]),
        R("Running in mice", year=2020, abstract="Mice with depressive-like behaviour were randomized to exercise."),
        R("Exercise in adults", year=2020, abstract="Adults were randomized to exercise; anxiety outcomes."),
        R("Cohort of exercise and depression", year=2020, abstract="Exercise was associated with less depression."),
        R("No abstract trial of exercise and depression", year=2020, abstract=""),
    ]
    ds = screen_title_abstract(recs, c)
    got = [d.reason for d in ds]
    assert got == [None, "Outside publication date range", "Ineligible publication type", "Animal study",
                   "Population criterion not met", "Not a randomised controlled trial", "No abstract available"]
    s2 = screen_title_abstract([R("S2 meta-analysis of exercise for depression", year=2020,
                                  publication_types=["MetaAnalysis"]),
                                R("Trial comment", year=2020, publication_types=["Comment", "Randomized Controlled Trial"])], c)
    assert s2[0].reason == "Ineligible publication type" and s2[1].included
    ov = apply_overrides(ds, {recs[5].record_id: {"decision": "include"}}, "title_abstract")
    assert ov[5].included and ov[5].source == "override"


def test_eligibility_sample_size_and_strict_policy():
    c = Criteria.from_dict({**DEMO_CRITERIA, "full_text_policy": "strict"})
    small = R("Pilot", abstract="In this pilot, n = 18 adults with depression were randomized to yoga.")
    ft = R("Full", abstract="x", full_text="A total of 120 adults with depression were randomized to exercise.")
    decisions, not_retrieved = assess_eligibility([small, ft], c)
    assert not_retrieved == [small.record_id]
    assert decisions[0].included and "full text" in decisions[0].detail
    c2 = Criteria.from_dict(DEMO_CRITERIA)
    d2, nr2 = assess_eligibility([small], c2)
    assert nr2 == [] and d2[0].reason == "Sample size below 30"
    assert detect_sample_size("120 participants were randomized; n = 60 per arm") == 120


def test_prisma_flow_is_consistent():
    b = demo_bundle()
    recs = b.all_records
    dd = deduplicate(recs)
    c = Criteria.from_dict(DEMO_CRITERIA)
    ta = screen_title_abstract(dd.unique, c)
    passed = [r for r, d in zip(dd.unique, ta) if d.included]
    el, nr = assess_eligibility(passed, c)
    flow = build_flow({k: len(v) for k, v in b.records_by_db.items()}, dd.n_removed, ta, nr, el)
    assert flow.check() == []
    assert flow.identified == 35 and flow.duplicates_removed == 14 and flow.included_studies == 14


def test_rob_algorithms():
    assert overall_judgement("RoB2", ["Low"] * 5) == "Low"
    assert overall_judgement("RoB2", ["Low", "Some concerns", "Low", "Low", "Low"]) == "Some concerns"
    assert overall_judgement("RoB2", ["Some concerns"] * 3 + ["Low"] * 2) == "High"
    assert overall_judgement("RoB2", ["Low", "high"]) == "High"
    assert overall_judgement("ROBINS-I", ["Low", "Moderate", "Serious"]) == "Serious"
    assert overall_judgement("ROBINS-I", ["low", "critical"]) == "Critical"
    rec = R("t", abstract="Participants were randomized using computer-generated sequence with allocation concealment "
                         "by sealed opaque envelopes. Double-blind, placebo-controlled; intention-to-treat. NCT01234567.")
    s = suggest_rob(rec, "RCT")
    assert s["tool"] == "RoB2" and s["overall"] == "Low" and s["provisional"]
    assert s["domains"][ROB2_DOMAINS[0]]["support"]
    obs = suggest_rob(R("c", abstract="A retrospective cohort without adjustment."), "NRSI")
    assert obs["tool"] == "ROBINS-I" and obs["overall"] == "Serious"


def test_extraction_roundtrip(tmp_path):
    s = suggest_outcome_data("Response occurred in 30/60 (50.0%) vs 18/58 (31.0%) participants. "
                             "Scores were 12.1 ± 4.2 and 15.3 ± 4.0 (n = 60 and n = 58).")
    assert s["prefill"] == {"treat_events": 30, "treat_total": 60, "ctrl_events": 18, "ctrl_total": 58}
    assert s["continuous"][0]["mean_sd"] == [(12.1, 4.2), (15.3, 4.0)]
    recs = [R("Exercise RCT", abstract="Adults were randomized. Response 30/60 (50%) vs 18/58 (31%).", year=2021,
              authors=["Lee A"])]
    assert infer_design(recs[0]) == "RCT"
    path = build_extraction_template(recs, tmp_path / "x.csv", ["Response"], measure="OR")
    rows = list(csv.DictReader(path.open()))
    assert rows[0]["treat_events"] == "30" and rows[0]["outcome_type"] == "dichotomous"
    rows[0]["rob_tool"], rows[0]["rob_d1"] = "RoB2", "High"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    st = load_extraction(path)
    assert st[0].has_data_for("OR") and not st[0].has_data_for("SMD")
    assert st[0].effect("OR").measure == "OR"
    m = rob_matrix(st)
    assert m["RoB2"]["rows"][0]["overall"] == "High"
