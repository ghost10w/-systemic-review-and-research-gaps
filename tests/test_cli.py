import json

from docx import Document

from ureme.cli import main


def _text(path):
    return "\n".join(p.text for p in Document(str(path)).paragraphs)


def test_demo_end_to_end(tmp_path):
    out = tmp_path / "demo"
    assert main(["demo", "-o", str(out)]) == 0
    flow = json.loads((out / "review" / "prisma_flow.json").read_text())
    assert flow["consistency_problems"] == [] and flow["included_studies"] == 14
    meta = json.loads((out / "meta" / "meta_results.json").read_text())
    assert set(meta["outcomes"]) == {"Depressive symptoms (SMD)", "Treatment response (OR)"}
    smd = meta["outcomes"]["Depressive symptoms (SMD)"]
    assert smd["result"]["k"] == 14 and smd["result"]["estimate"] < 0 and smd["grade"]["provisional"]
    for f in ("forest", "funnel"):
        assert (out / "meta" / f"{f}_depressive_symptoms_smd.png").exists()
    ms = _text(out / "PRISMA_Manuscript.docx")
    for heading in ("Abstract", "1. Introduction", "2. Methods", "3. Results", "4. Discussion",
                    "Summary of Findings", "Appendix A. PRISMA 2020 checklist", "SYNTHETIC"):
        assert heading in ms
    gp = _text(out / "Research_Gap_Proposal.docx")
    for heading in ("Executive Summary", "Identified Research Gaps", "Research Proposals", "H1 (alternative)"):
        assert heading in gp
    assert json.loads((out / "run_manifest.json").read_text())["command"] == "demo"


def test_review_and_meta_from_saved_records(tmp_path):
    demo = tmp_path / "demo"
    main(["demo", "-o", str(demo)])
    out = tmp_path / "review"
    rc = main(["review", "--records-in", str(demo / "search" / "records_raw.json"), "-c",
               str(demo / "inputs" / "demo_criteria.json"), "-x", str(demo / "inputs" / "demo_extraction_completed.csv"),
               "--tau2", "DL", "--hksj", "--no-full-text", "-o", str(out)])
    assert rc == 0
    meta = json.loads((out / "meta" / "meta_results.json").read_text())
    assert meta["settings"] == {"model": "random", "tau2_method": "DL", "hksj": True, "level": 0.95}
    rc = main(["meta", "-x", str(demo / "inputs" / "demo_extraction_completed.csv"), "--effect", "RR", "-o",
               str(tmp_path / "m")])
    assert rc == 0
    m = json.loads((tmp_path / "m" / "meta" / "meta_results.json").read_text())
    assert m["outcomes"]["Treatment response (OR)"]["measure"] == "RR"


def test_gaps_from_saved_records(tmp_path):
    demo = tmp_path / "demo"
    main(["demo", "-o", str(demo)])
    out = tmp_path / "gaps"
    assert main(["gaps", "--records-in", str(demo / "search" / "records_raw.json"), "-q", "exercise AND depression",
                 "--years", "5", "--top", "3", "--no-full-text", "--population", "older adults", "-o", str(out)]) == 0
    props = json.loads((out / "gaps" / "proposals.json").read_text())
    assert len(props) == 3 and all(p["pico"]["population"] == "older adults" for p in props)


def test_init_and_manual(tmp_path):
    assert main(["init", "-o", str(tmp_path / "c.json")]) == 0
    assert "include_concepts" in json.loads((tmp_path / "c.json").read_text())
    assert main(["manual", "-o", str(tmp_path / "m.docx")]) == 0
    txt = _text(tmp_path / "m.docx")
    assert "Installation" in txt and "ureme review" in txt and "Troubleshooting" in txt
