from ureme.demo import demo_records
from ureme.gaps.detector import classify_sentence, detect_gap_statements, expand_theme, find_gaps, finding_direction
from ureme.gaps.proposals import extract_population, generate_proposals, sample_size
from ureme.models import Record


def test_classification():
    assert classify_sentence("The small sample size and single-centre design limit power.")[0] == "Methodological"
    assert classify_sentence("Generalizability to older adults and ethnic minorities is unknown.")[0] == "Population"
    assert classify_sentence("The underlying molecular mechanism remains unclear.")[0] == "Mechanistic"
    assert classify_sentence("Little is known about long-term effects.")[0] == "Knowledge/Evidence"


def test_statements_and_directions():
    r = Record(title="t", abstract="Background: x is common. Further research is needed to clarify the pathway. "
                                   "Conclusions: Treatment did not significantly reduce pain.")
    st = detect_gap_statements([r])
    assert len(st) == 1 and st[0].category == "Mechanistic"
    assert finding_direction(r) == "null"
    r2 = Record(title="t", abstract="Conclusions: Treatment significantly reduced pain scores.")
    assert finding_direction(r2) == "positive"


def test_find_gaps_and_proposals():
    recs = demo_records()
    out = find_gaps(recs, ["exercise", "depression", "depressive", "symptoms"])
    cats = {g.category for g in out["gaps"]}
    assert {"Methodological", "Population", "Mechanistic", "Knowledge/Evidence"} <= cats
    assert any(g.subtype == "conflicting evidence" for g in out["gaps"])
    assert [g.gap_id for g in out["gaps"]][:2] == ["G01", "G02"]
    props = generate_proposals(out["gaps"], recs, ["exercise"], top_n=4, pico_overrides={"comparison": "stretching"})
    assert len(props) == 4
    for p in props:
        assert p.pico["comparison"] == "stretching" and set(p.finer) == {"Feasible", "Interesting", "Novel",
                                                                          "Ethical", "Relevant"}
        assert all(1 <= v["score"] <= 5 for v in p.finer.values())
        assert p.hypothesis and p.null_hypothesis and p.methods and p.references


def test_helpers():
    assert expand_theme("inflammatory", ["the role of inflammatory pathways is unclear",
                                         "inflammatory pathways need study"]) == "inflammatory pathways"
    pop = extract_population([Record(title="x", abstract="We enrolled 80 older adults with type 2 diabetes who "
                                                        "were sedentary.")], "d")
    assert pop == "older adults with type 2 diabetes"
    ss = sample_size("Methodological")
    assert ss["continuous"]["d=0.5"] == 64 and ss["continuous"]["d=0.3"] == 176
