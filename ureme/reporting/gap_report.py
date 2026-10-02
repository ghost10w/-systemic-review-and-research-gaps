"""Research Gap Proposal document (Module A)."""

from __future__ import annotations

from pathlib import Path

from ureme.reporting import docx_utils as D


def build_gap_report(path: str | Path, query: str, search_log: list[dict], gap_result: dict, proposals: list,
                     records_by_id: dict, years: tuple[int, int] | None = None, meta_context: dict | None = None,
                     synthetic: bool = False) -> Path:
    doc = D.new_document()
    gaps = gap_result["gaps"]
    D.title_page(doc, "Research Gap Analysis & Proposal Portfolio", "Unified Research & Meta-Analysis Engine — Module A",
                 [("Search query", query), ("Literature window", f"{years[0]}–{years[1]}" if years else "all years"),
                  ("Records analysed", str(gap_result["n_records"])), ("Proposals", str(len(proposals)))])
    if synthetic:
        D.callout(doc, "This report was generated from SYNTHETIC demonstration data. It does not describe real "
                       "studies and must not be cited.", "DEMO")
    D.toc(doc)

    doc.add_heading("1. Executive Summary", 1)
    top = proposals[0] if proposals else None
    D.para(doc, f"The engine analysed {gap_result['n_records']} records retrieved for the query “{query}” and extracted "
                f"{gap_result['n_statements']} explicit gap/limitation statements. These were consolidated into "
                f"{len(gaps)} ranked research gaps and {len(proposals)} structured research proposals.")
    D.table(doc, ["Gap category", "Gap statements", "Consolidated gaps"],
            [[c, gap_result["statements_by_category"].get(c, 0), gap_result["gaps_by_category"].get(c, 0)]
             for c in gap_result["gaps_by_category"]], caption="Table 1. Gap landscape by category")
    if top:
        D.para(doc, top.title, bold_prefix="Highest-ranked proposal: ")
        D.para(doc, top.hypothesis, bold_prefix="Lead hypothesis: ")
    if meta_context:
        D.para(doc, meta_context.get("summary", ""), bold_prefix="Context from the quantitative synthesis: ")
    D.callout(doc, "Gaps, PICO elements and FINER scores are generated algorithmically from published text. They are "
                   "decision support for investigators, not a substitute for expert appraisal.", "Interpretation")

    doc.add_heading("2. Methods", 1)
    doc.add_heading("2.1 Literature search", 2)
    D.para(doc, "Live searches were run against the following academic databases:")
    D.table(doc, ["Database", "Query (as executed)", "Date", "Hits", "Retrieved", "Status"],
            [[e["database"], e["query"], e["date"], e["total_hits"], e["retrieved"], e.get("error") or "OK"]
             for e in search_log], widths_cm=[3, 7, 2.2, 1.6, 1.8, 2])
    doc.add_heading("2.2 Gap mining", 2)
    D.bullets(doc, [
        ("Limitation markers: ", "sentences containing explicit gap language (e.g., “further research is needed”, "
                                 "“remains unclear”, “small sample size”) were extracted from abstracts and open-access "
                                 "full texts."),
        ("Categorisation: ", "each statement was classified as Methodological, Population, Mechanistic or "
                             "Knowledge/Evidence using curated lexicons."),
        ("Theme clustering: ", "statements were grouped by their most frequent shared key phrase, and ranked by number "
                               "of distinct studies, recency and citation impact."),
        ("Conflicting evidence: ", "studies sharing a topic were classified by the direction of their main finding; "
                                   "topics with both significant and null findings were flagged."),
        ("Proposal synthesis: ", "the top gaps were converted into PICO-structured questions with hypotheses, "
                                 "suggested designs, power calculations (statsmodels) and FINER scores."),
    ])

    doc.add_heading("3. Identified Research Gaps", 1)
    D.table(doc, ["ID", "Category", "Theme", "Type", "Studies", "Score"],
            [[g.gap_id, g.category, g.theme, g.subtype, g.n_records, D.fmt(g.score)] for g in gaps],
            caption="Table 2. Ranked research gaps", widths_cm=[1.2, 3.2, 5, 3.2, 1.6, 1.6])
    for g in gaps:
        doc.add_heading(f"{g.gap_id} — {g.category}: {g.theme}", 3)
        D.para(doc, g.description)
        for ev in g.evidence[:4]:
            rec = records_by_id.get(ev["record_id"])
            src = rec.short_label() if rec else ev["record_id"]
            extra = f" [{ev['direction']} finding]" if ev.get("direction") else ""
            D.para(doc, f"“{ev['sentence']}” — {src}{extra}", italic=True, size=9.5, style="List Bullet")

    doc.add_heading("4. Research Proposals", 1)
    for p in proposals:
        doc.add_heading(f"{p.proposal_id}. {p.title}", 2)
        D.para(doc, f"{p.category} (from gap {p.gap_id})  •  FINER mean score {p.finer_total:.1f}/5",
               color=D.GREY, size=9.5)
        D.para(doc, p.research_question, bold_prefix="Research question: ")
        D.table(doc, ["PICO element", "Specification"],
                [["Population", p.pico["population"]], ["Intervention / exposure", p.pico["intervention"]],
                 ["Comparison", p.pico["comparison"]], ["Outcome", p.pico["outcome"]]], widths_cm=[4, 12])
        D.para(doc, p.hypothesis, bold_prefix="H1 (alternative): ")
        D.para(doc, p.null_hypothesis, bold_prefix="H0 (null): ")
        D.para(doc, p.rationale, bold_prefix="Scientific rationale: ")
        D.para(doc, p.design, bold_prefix="Suggested design: ")
        D.bullets(doc, p.methods)
        ss = p.sample_size
        rows = [[f"Continuous outcome, Cohen's {k}", v] for k, v in ss["continuous"].items()]
        rows += [[f"Binary outcome, {k}", v] for k, v in ss["dichotomous"].items()]
        D.table(doc, ["Scenario (α = 0.05, power = 0.80)", "N per arm"], rows, widths_cm=[10, 4],
                caption="Illustrative sample size")
        D.para(doc, ss["note"], italic=True, size=9)
        D.table(doc, ["FINER criterion", "Score (1–5)", "Rationale"],
                [[k, v["score"], v["rationale"]] for k, v in p.finer.items()], widths_cm=[3, 2, 11])
        if p.references:
            D.para(doc, "Key supporting literature:", size=10).runs[0].bold = True
            for ref in p.references:
                D.para(doc, ref, size=9, style="List Number")

    doc.add_heading("5. Bibliography", 1)
    used = []
    for g in gaps:
        for rid in g.record_ids:
            if rid not in used and rid in records_by_id:
                used.append(rid)
    for i, rid in enumerate(used, 1):
        D.para(doc, f"{i}. {records_by_id[rid].citation()}", size=9)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path
