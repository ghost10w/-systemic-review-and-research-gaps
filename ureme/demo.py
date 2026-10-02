"""Offline, fully synthetic demonstration data.

Used by ``ureme demo`` and the test-suite to exercise every stage without
network access.  All records are fictitious (DOI prefix 10.0000/ureme-demo)
and every generated document is stamped as synthetic.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import random
from pathlib import Path

from ureme.models import Record, SearchBundle, SearchLogEntry

DEMO_QUERY = '("exercise" OR "physical activity") AND ("depression" OR "depressive symptoms") AND randomized'

DEMO_CRITERIA = {
    "title": "Exercise interventions for depressive symptoms in adults (SYNTHETIC DEMO)",
    "question": "In adults with depressive symptoms, does structured exercise compared with usual care or "
                "control reduce depressive symptom severity and increase treatment response?",
    "pico": {"population": "Adults (18+) with depressive symptoms or major depressive disorder",
             "intervention": "Structured exercise or physical-activity programme",
             "comparison": "Usual care, waiting list, attention control or stretching",
             "outcome": "Depressive symptom severity; treatment response"},
    "year_min": 2015,
    "languages": ["eng"],
    "require_abstract": True,
    "include_concepts": {"Population": ["depress*"], "Intervention": ["exercise", "physical activity", "aerobic",
                                                                      "resistance training", "yoga"]},
    "exclude_terms": {"Animal study": ["mice", "rats", "murine", "rodent*"],
                      "Paediatric population": ["children", "adolescents"]},
    "study_design_terms": ["randomi*", "randomly assigned"],
    "study_design_label": "Not a randomised controlled trial",
    "min_sample_size": 30,
    "outcomes": ["Depressive symptoms (SMD)", "Treatment response (OR)"],
}

_LIMITATIONS = [
    "A limitation of this study is the small sample size, and larger adequately powered trials are needed.",
    "The mechanisms underlying the antidepressant effect of exercise remain unclear, particularly the role of "
    "inflammatory pathways and BDNF signalling.",
    "Little is known about the effects of exercise in older adults with comorbid chronic disease.",
    "Generalizability is limited because participants were predominantly women from high-income countries.",
    "The short follow-up period precludes conclusions about long-term effects of exercise on depressive symptoms.",
    "Future studies should examine whether inflammatory biomarkers mediate the effect of aerobic exercise.",
    "Evidence on the cost-effectiveness of supervised exercise programmes remains limited.",
    "Self-report measures and the lack of blinded outcome assessment may have introduced bias.",
    "Ethnic minority and low-income populations were underrepresented, and further research is needed in these groups.",
    "Adherence measurement was not standardized, and future trials should use objective accelerometry.",
]
_POS = "Conclusions: Exercise significantly reduced depressive symptoms compared with control."
_NULL = "Conclusions: Exercise did not significantly reduce depressive symptoms compared with control."


def _rec(i: int, year: int, title: str, abstract: str, pts: list[str], **kw) -> Record:
    return Record(
        title=title, abstract=abstract, authors=[f"Demo{i:02d} A", "Synth B", "Example C"], year=year,
        journal="Journal of Synthetic Evidence", doi=f"10.0000/ureme-demo.{i:03d}", pmid=f"9{i:07d}",
        publication_types=pts, language="eng", citation_count=random.Random(i).randint(0, 120), **kw)


def demo_records() -> list[Record]:
    rng = random.Random(42)
    this_year = dt.date.today().year
    recs = []
    for i in range(1, 15):
        n = rng.randint(40, 220)
        kind = ["aerobic exercise", "resistance training", "yoga", "supervised physical activity"][i % 4]
        concl = _POS if i % 3 else _NULL
        abstract = (
            f"Background: Depression is a leading cause of disability. Methods: In this randomized controlled trial, "
            f"{n} adults with depressive symptoms were randomly assigned using computer-generated block randomization "
            f"with allocation concealment by sealed opaque envelopes to {kind} or usual care for 12 weeks. Outcome "
            f"assessors were blinded. Analysis followed the intention-to-treat principle (registered NCT0{i:07d}). "
            f"Results: The primary outcome was depressive symptom severity. "
            f"{_LIMITATIONS[i % len(_LIMITATIONS)]} {_LIMITATIONS[(i + 3) % len(_LIMITATIONS)]} {concl}")
        recs.append(_rec(i, this_year - (i % 5), f"{kind.capitalize()} for depressive symptoms in adults: a randomized "
                                                 f"controlled trial (synthetic study {i})", abstract,
                         ["Journal Article", "Randomized Controlled Trial"], pmcid=f"PMC9{i:06d}" if i % 2 else None,
                         keywords=["exercise", "depression", kind]))
    # ineligible records exercising each screening rule
    recs.append(_rec(20, this_year - 1, "Exercise for depression: a systematic review (synthetic)",
                     "We reviewed randomized trials of exercise for depression. Evidence remains limited.",
                     ["Review", "Systematic Review"]))
    recs.append(_rec(21, this_year - 2, "Treadmill running reduces depressive-like behaviour in mice (synthetic)",
                     "Randomized allocation of mice to running wheels. The mechanism remains unclear.",
                     ["Journal Article"]))
    recs.append(_rec(22, this_year - 2, "Exercise and depressive symptoms in adolescents: randomized trial (synthetic)",
                     "120 adolescents with depression were randomized to exercise. Little is known about children.",
                     ["Journal Article", "Randomized Controlled Trial"]))
    recs.append(_rec(23, this_year - 3, "Physical activity and depression in a cohort of adults (synthetic)",
                     "A prospective cohort of 5000 adults; physical activity was associated with lower depression. "
                     "Further research is needed to establish causality.", ["Journal Article"]))
    recs.append(_rec(24, this_year - 1, "Yoga for depression: pilot randomized trial (synthetic)",
                     "In this pilot, n = 18 adults with depression were randomized to yoga or waitlist. The small "
                     "sample size is a limitation.", ["Journal Article", "Randomized Controlled Trial"]))
    recs.append(_rec(25, 2009, "Aerobic exercise for depression in adults: an early randomized trial (synthetic)",
                     "Adults with depression were randomized to aerobic exercise.", ["Journal Article"]))
    recs.append(_rec(26, this_year - 1, "Exercise and depression in adults: randomized trial without abstract (synthetic)",
                     "", ["Journal Article"]))
    return recs


def demo_bundle() -> SearchBundle:
    recs = demo_records()
    today = dt.date.today().isoformat()
    pubmed = [Record.from_dict(r.to_dict()) for r in recs[:18]]
    for r in pubmed:
        r.sources = ["PubMed"]
    epmc = []
    for r in recs[10:]:
        c = Record.from_dict(r.to_dict())
        c.sources, c.pmid = ["Europe PMC"], None
        epmc.append(c)
    s2 = []
    for r in recs[:6]:
        c = Record.from_dict(r.to_dict())
        c.sources, c.doi, c.pmid, c.record_id = ["Semantic Scholar"], None, None, ""
        c.s2_id = f"demo{r.pmid}"
        c.title = c.title.replace("randomized", "randomised")  # spelling variant -> fuzzy duplicate
        c.record_id = c.make_id()
        s2.append(c)
    log = [SearchLogEntry("PubMed", DEMO_QUERY, today, len(pubmed), len(pubmed), "synthetic"),
           SearchLogEntry("Europe PMC", DEMO_QUERY, today, len(epmc), len(epmc), "synthetic"),
           SearchLogEntry("Semantic Scholar", DEMO_QUERY, today, len(s2), len(s2), "synthetic")]
    return SearchBundle({"PubMed": pubmed, "Europe PMC": epmc, "Semantic Scholar": s2}, log)


def fill_demo_extraction(template: Path, out: Path, seed: int = 7) -> Path:
    """Populate an extraction template with plausible synthetic numbers."""
    rng = random.Random(seed)
    rows = list(csv.DictReader(template.open(encoding="utf-8")))
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for row in rows:
            n1, n2 = rng.randint(25, 110), rng.randint(25, 110)
            row.update(population="Adults with depressive symptoms", intervention="Structured exercise",
                       comparator="Usual care", country=rng.choice(["UK", "USA", "Brazil", "China", "Germany"]),
                       follow_up="12 weeks", subgroup=rng.choice(["Supervised", "Home-based"]))
            if "SMD" in row["outcome"]:
                d = rng.gauss(-0.45, 0.25)
                sd = rng.uniform(5, 8)
                row.update(outcome_type="continuous", measure="SMD", treat_n=n1, ctrl_n=n2,
                           ctrl_mean=round(rng.uniform(18, 24), 1), treat_sd=round(sd, 1), ctrl_sd=round(sd * 1.05, 1))
                row["treat_mean"] = round(float(row["ctrl_mean"]) + d * sd, 1)
                for k in ("treat_events", "treat_total", "ctrl_events", "ctrl_total"):
                    row[k] = ""
            else:
                p_c = rng.uniform(0.2, 0.35)
                p_t = min(0.9, p_c * rng.uniform(1.1, 1.9))
                row.update(outcome_type="dichotomous", measure="OR", treat_total=n1, ctrl_total=n2,
                           treat_events=round(n1 * p_t), ctrl_events=round(n2 * p_c))
                for k in ("treat_mean", "treat_sd", "treat_n", "ctrl_mean", "ctrl_sd", "ctrl_n"):
                    row[k] = ""
            w.writerow(row)
    return out


def write_demo_inputs(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    records = out_dir / "demo_records.json"
    records.write_text(json.dumps(demo_bundle().to_dict(), indent=2), encoding="utf-8")
    criteria = out_dir / "demo_criteria.json"
    criteria.write_text(json.dumps(DEMO_CRITERIA, indent=2), encoding="utf-8")
    return {"records": records, "criteria": criteria}
