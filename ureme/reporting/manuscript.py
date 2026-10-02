"""Full PRISMA 2020 manuscript (Module B)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from ureme.meta.effect_sizes import MEASURE_NAMES, null_value
from ureme.meta.models import p_text
from ureme.reporting import docx_utils as D
from ureme.review.rob import COLORS

PRISMA_CHECKLIST = [
    ("1", "Title", "Identify the report as a systematic review", "Title page"),
    ("2", "Abstract", "PRISMA 2020 for Abstracts checklist", "Abstract"),
    ("3", "Rationale", "Describe the rationale for the review", "Introduction"),
    ("4", "Objectives", "Explicit statement of objectives/questions", "Introduction"),
    ("5", "Eligibility criteria", "Inclusion and exclusion criteria", "Methods 2.1"),
    ("6", "Information sources", "Databases and dates searched", "Methods 2.2"),
    ("7", "Search strategy", "Full search strategies", "Methods 2.3 / Appendix"),
    ("8", "Selection process", "Methods used to decide inclusion", "Methods 2.4"),
    ("9", "Data collection process", "Methods used to collect data", "Methods 2.5"),
    ("10", "Data items", "Outcomes and other variables sought", "Methods 2.5"),
    ("11", "Study risk of bias assessment", "Tools used", "Methods 2.6"),
    ("12", "Effect measures", "Effect measures used", "Methods 2.7"),
    ("13", "Synthesis methods", "Methods of synthesis, heterogeneity, sensitivity", "Methods 2.8"),
    ("14", "Reporting bias assessment", "Methods for missing results", "Methods 2.9"),
    ("15", "Certainty assessment", "Methods to assess certainty", "Methods 2.10"),
    ("16", "Study selection", "Results of search and selection (flow diagram)", "Results 3.1"),
    ("17", "Study characteristics", "Cite and present characteristics", "Results 3.2"),
    ("18", "Risk of bias in studies", "Present assessments", "Results 3.3"),
    ("19", "Results of individual studies", "Summary statistics and effect estimates", "Results 3.4 (forest plots)"),
    ("20", "Results of syntheses", "Summary, heterogeneity, sensitivity", "Results 3.4"),
    ("21", "Reporting biases", "Assessments of risk of bias due to missing results", "Results 3.5"),
    ("22", "Certainty of evidence", "Certainty for each outcome", "Results 3.6 / SoF table"),
    ("23", "Discussion", "Interpretation, limitations, implications", "Discussion"),
    ("24", "Registration and protocol", "Registration information", "Other information"),
    ("25", "Support", "Sources of support", "Other information"),
    ("26", "Competing interests", "Declarations", "Other information"),
    ("27", "Availability of data, code and other materials", "Where to find them", "Other information"),
]

_RATIO = {"OR", "RR"}


def _effect_str(res: dict) -> str:
    return (f"{res['measure']} {res['estimate_display']:.2f} (95% CI {res['ci_low_display']:.2f} to "
            f"{res['ci_high_display']:.2f})")


def _direction(res: dict) -> str:
    nv = null_value(res["measure"])
    lo, hi, est = res["ci_low_display"], res["ci_high_display"], res["estimate_display"]
    if lo <= nv <= hi:
        return "no statistically significant difference between groups"
    word = "higher" if est > nv else "lower"
    return f"a statistically significant {word} value in the intervention group"


def build_manuscript(path: str | Path, criteria, query: str, search_log: list[dict], flow, included_records: list,
                     studies: list | None, synthesis: dict | None, rob_matrix: dict | None, figures: dict,
                     gap_summary: dict | None = None, synthetic: bool = False, settings: dict | None = None) -> Path:
    settings = settings or {}
    doc = D.new_document()
    title = criteria.title or f"{query}: a systematic review and meta-analysis"
    if "systematic review" not in title.lower():
        title += ": a systematic review and meta-analysis"
    D.title_page(doc, title, "Manuscript draft prepared in accordance with PRISMA 2020",
                 [("Review question", criteria.question or query), ("Studies included", str(flow.included_studies))])
    if synthetic:
        D.callout(doc, "Generated from SYNTHETIC demonstration data. Not a real systematic review; do not cite.", "DEMO")
    D.callout(doc, "This manuscript was drafted automatically. Screening decisions, extracted data, risk-of-bias "
                   "judgements and GRADE ratings marked provisional must be verified by two independent reviewers "
                   "before submission.", "Author verification required")
    outcomes = (synthesis or {}).get("outcomes", {})
    has_meta = bool(outcomes)

    # ---------------- Abstract ----------------
    doc.add_heading("Abstract", 1)
    dbs = ", ".join(e["database"] for e in search_log)
    last = max((e["date"] for e in search_log), default=dt.date.today().isoformat())
    D.para(doc, criteria.question or f"To synthesise the evidence on {query}.", bold_prefix="Background: ")
    D.para(doc, f"We searched {dbs} up to {last}. Eligible studies were selected using pre-specified criteria. Risk of "
                f"bias was assessed with Cochrane RoB 2 (randomised trials) or ROBINS-I (non-randomised studies). "
                f"Effects were pooled with a {settings.get('model', 'random')}-effects model "
                f"({settings.get('tau2_method', 'REML')} estimator of τ²) and certainty was rated with GRADE.",
           bold_prefix="Methods: ")
    res_txt = (f"Of {flow.identified} records identified, {flow.duplicates_removed} duplicates were removed, "
               f"{flow.screened} were screened and {flow.included_studies} studies were included. ")
    for name, o in list(outcomes.items())[:3]:
        r = o["result"]
        res_txt += (f"For {name} (k = {r['k']}, n = {o['total_participants']}), the pooled "
                    f"{_effect_str(r)} indicated {_direction(r)} (I² = {r['I2']:.0f}%; certainty: "
                    f"{o['grade']['certainty'].lower()}). ")
    if not has_meta:
        res_txt += "Quantitative synthesis is pending completion of data extraction."
    D.para(doc, res_txt, bold_prefix="Results: ")
    concl = ("The certainty of the evidence and the consistency of effects should guide interpretation; see the "
             "Summary of Findings table.") if has_meta else "Conclusions will be drawn once data extraction is complete."
    D.para(doc, concl, bold_prefix="Conclusions: ")
    D.para(doc, "[insert PROSPERO ID]", bold_prefix="Registration: ")
    D.page_break(doc)

    # ---------------- Introduction ----------------
    doc.add_heading("1. Introduction", 1)
    D.para(doc, f"Evidence on {query} continues to accumulate, but individual studies differ in populations, "
                f"interventions, outcome definitions and methodological quality, which leaves uncertainty about the "
                f"magnitude and consistency of effects. A systematic review with quantitative synthesis can provide "
                f"a transparent, reproducible summary of the totality of the evidence.")
    if gap_summary:
        D.para(doc, gap_summary.get("summary", ""))
    D.para(doc, f"The objective of this review was: {criteria.question or 'to evaluate ' + query}.")
    if criteria.pico:
        D.table(doc, ["Element", "Definition"], [[k.title(), v] for k, v in criteria.pico.items()],
                caption="Table 1. Review question (PICO)", widths_cm=[4, 12])

    # ---------------- Methods ----------------
    doc.add_heading("2. Methods", 1)
    D.para(doc, "This review is reported according to the Preferred Reporting Items for Systematic Reviews and "
                "Meta-Analyses (PRISMA) 2020 statement. [Insert protocol registration details.]")
    doc.add_heading("2.1 Eligibility criteria", 2)
    items = []
    if criteria.include_concepts:
        items += [(f"{k}: ", "any of " + "; ".join(v)) for k, v in criteria.include_concepts.items()]
    if criteria.study_design_terms:
        items.append(("Study design: ", "; ".join(criteria.study_design_terms)))
    if criteria.year_min or criteria.year_max:
        items.append(("Publication period: ", f"{criteria.year_min or 'inception'}–{criteria.year_max or 'present'}"))
    if criteria.languages:
        items.append(("Languages: ", ", ".join(criteria.languages)))
    if criteria.exclude_publication_types:
        items.append(("Excluded publication types: ", ", ".join(criteria.exclude_publication_types)))
    for reason, terms in criteria.exclude_terms.items():
        items.append((f"Excluded — {reason}: ", ", ".join(terms)))
    if criteria.min_sample_size:
        items.append(("Minimum sample size: ", str(criteria.min_sample_size)))
    D.bullets(doc, items or ["As specified in the protocol."])
    doc.add_heading("2.2 Information sources", 2)
    D.para(doc, f"We searched {dbs}. Searches were executed programmatically through the official application "
                f"programming interfaces (NCBI E-utilities, Europe PMC REST API and the Semantic Scholar Academic "
                f"Graph API). The last search was run on {last}.")
    doc.add_heading("2.3 Search strategy", 2)
    D.para(doc, "The full search strategy for each database is reported in Table 2.")
    D.table(doc, ["Database", "Search string", "Limits", "Date", "Records"],
            [[e["database"], e["query"], e.get("filters", ""), e["date"], e["retrieved"]] for e in search_log],
            caption="Table 2. Search strategies", widths_cm=[2.6, 8, 3, 2, 1.6])
    doc.add_heading("2.4 Selection process", 2)
    D.para(doc, "Records from all sources were merged and de-duplicated using exact identifier matching (DOI, PMID, "
                "PMCID, Semantic Scholar ID), exact normalised title matching and fuzzy title matching (similarity "
                "≥ 0.93, publication year ±1, concordant first author). Titles and abstracts were screened against "
                "the eligibility criteria with a reason-coded, rule-based screening engine; open-access full texts were "
                "retrieved from Europe PMC/PubMed Central and assessed for eligibility. "
                + ("Where no open-access full text was available, eligibility was assessed on the abstract. "
                   if criteria.full_text_policy != "strict" else "Reports without accessible full text were recorded "
                                                                  "as not retrieved. ")
                + "All automated decisions were logged and could be overridden by reviewers; [describe dual "
                  "independent verification].")
    doc.add_heading("2.5 Data collection process and data items", 2)
    D.para(doc, "Data were extracted into a structured sheet capturing study identifiers, design, population, "
                "intervention, comparator, follow-up, and outcome data (events and totals for dichotomous outcomes; "
                "means, standard deviations and sample sizes for continuous outcomes). Candidate numerical values "
                "were pre-identified by text mining and verified by reviewers.")
    if criteria.outcomes:
        D.para(doc, ", ".join(criteria.outcomes), bold_prefix="Outcomes: ")
    doc.add_heading("2.6 Risk of bias assessment", 2)
    D.para(doc, "Randomised trials were assessed with the Cochrane Risk of Bias 2 (RoB 2) tool across five domains "
                "(randomisation process, deviations from intended interventions, missing outcome data, measurement of "
                "the outcome, selection of the reported result). Non-randomised studies were assessed with ROBINS-I "
                "across seven domains. Overall judgements followed each tool's algorithm (RoB 2: any 'High' domain, or "
                "'Some concerns' in multiple domains, leads to 'High'; ROBINS-I: the most severe domain).")
    doc.add_heading("2.7 Effect measures", 2)
    measures = sorted({o["measure"] for o in outcomes.values()}) or [criteria.effect_measure or "OR/SMD"]
    D.para(doc, "Effect measures: " + "; ".join(MEASURE_NAMES.get(m, m) for m in measures) + ". Ratio measures were "
                "analysed on the log scale. Hedges' g was used for the standardised mean difference. A continuity "
                "correction of 0.5 was applied to studies with zero cells; studies with no events in both arms were "
                "considered non-estimable.")
    doc.add_heading("2.8 Synthesis methods", 2)
    D.para(doc, f"Inverse-variance {settings.get('model', 'random')}-effects meta-analysis was performed "
                f"(τ² estimator: {settings.get('tau2_method', 'REML')}"
                f"{'; Hartung–Knapp–Sidik–Jonkman adjustment' if settings.get('hksj') else ''}). Heterogeneity was "
                f"quantified with Cochran's Q, I² and τ² (95% CI by the Q-profile method), and 95% prediction "
                f"intervals were computed when at least three studies were available. Sensitivity analyses included "
                f"leave-one-out analysis, the alternative (fixed/random) model, and exclusion of studies at high risk "
                f"of bias. Pre-specified subgroup analyses used a test for subgroup differences (Q-between).")
    doc.add_heading("2.9 Reporting bias assessment", 2)
    D.para(doc, "Small-study effects were explored with funnel plots, Egger's regression test and Begg's rank "
                "correlation test, interpreted cautiously when fewer than ten studies were available.")
    doc.add_heading("2.10 Certainty assessment", 2)
    D.para(doc, "Certainty of evidence was rated using the GRADE approach (risk of bias, inconsistency, imprecision, "
                "publication bias; indirectness by reviewer judgement). Automated ratings are provisional.")

    # ---------------- Results ----------------
    doc.add_heading("3. Results", 1)
    doc.add_heading("3.1 Study selection", 2)
    D.para(doc, f"The searches identified {flow.identified} records ("
                + ", ".join(f"{db}: {n}" for db, n in flow.identified_by_db.items())
                + f"). After removing {flow.duplicates_removed} duplicates, {flow.screened} records were screened, of "
                  f"which {flow.excluded_screening} were excluded. {flow.sought} reports were sought for retrieval, "
                  f"{flow.not_retrieved} could not be retrieved, and {flow.assessed} were assessed for eligibility. "
                  f"{sum(flow.excluded_eligibility.values())} reports were excluded, leaving {flow.included_studies} "
                  f"studies (Figure 1).")
    D.figure(doc, figures.get("prisma"), "Figure 1. PRISMA 2020 flow diagram", width_cm=15)
    rows = [[r, n] for r, n in flow.screening_reasons.items()] + [[f"[Full text] {r}", n] for r, n in
                                                                 flow.excluded_eligibility.items()]
    if rows:
        D.table(doc, ["Reason for exclusion", "n"], rows, caption="Table 3. Reasons for exclusion", widths_cm=[12, 2])

    doc.add_heading("3.2 Study characteristics", 2)
    srows = []
    by_rec = {}
    for s in studies or []:
        by_rec.setdefault(s.record_id, s)
    for rec in included_records:
        s = by_rec.get(rec.record_id)
        srows.append([rec.short_label(), (s.design if s else "") or "–", rec.journal[:40],
                      (s.extra.get("population") if s else "") or "–", (s.extra.get("intervention") if s else "") or "–",
                      (s.extra.get("comparator") if s else "") or "–", (s.extra.get("country") if s else "") or "–"])
    D.table(doc, ["Study", "Design", "Journal", "Population", "Intervention", "Comparator", "Country"], srows,
            caption=f"Table 4. Characteristics of included studies (n = {len(included_records)})", font_size=8)

    doc.add_heading("3.3 Risk of bias in studies", 2)
    if rob_matrix:
        for tool, m in rob_matrix.items():
            short = [d.split(" ")[0] for d in m["domains"]]
            rows, fills = [], {}
            for ri, row in enumerate(m["rows"]):
                vals = [row["judgements"].get(d, "") for d in m["domains"]] + [row["overall"]]
                rows.append([row["study"]] + [v or "–" for v in vals])
                for ci, v in enumerate(vals, start=1):
                    if v in COLORS and v:
                        fills[(ri, ci)] = COLORS[v].lstrip("#")
            D.table(doc, ["Study"] + short + ["Overall"], rows, fills=fills, font_size=8,
                    caption=f"Table 5{'a' if tool == 'RoB2' else 'b'}. Risk of bias ({'Cochrane RoB 2' if tool == 'RoB2' else 'ROBINS-I'})")
            D.para(doc, "; ".join(m["domains"]), size=8, italic=True)
            D.figure(doc, figures.get(f"rob_{tool}"), f"Figure. Risk-of-bias traffic-light plot ({tool})", width_cm=14)
    else:
        D.para(doc, "Risk-of-bias assessments will be reported after data extraction.")

    doc.add_heading("3.4 Results of syntheses", 2)
    if not has_meta:
        D.callout(doc, "No extracted outcome data were supplied. Complete the extraction sheet (extraction_template.csv) "
                       "and re-run with --extraction to populate this section.", "Pending")
    fig_no = 2
    for name, o in outcomes.items():
        r = o["result"]
        doc.add_heading(name, 3)
        pred = (f" The 95% prediction interval ranged from {r['pred_low_display']:.2f} to {r['pred_high_display']:.2f}."
                if r.get("pred_low_display") is not None else "")
        tci = f" (95% CI {r['tau2_ci'][0]:.3f} to {r['tau2_ci'][1]:.3f})" if r.get("tau2_ci") else ""
        D.para(doc, f"{r['k']} studies (n = {o['total_participants']}) contributed to this outcome. The pooled "
                    f"{MEASURE_NAMES.get(r['measure'], r['measure']).lower()} was {_effect_str(r)}, "
                    f"{p_text(r['p'])}, indicating {_direction(r)}. Heterogeneity: Q({r['Q_df']}) = {r['Q']:.2f}, "
                    f"{p_text(r['Q_p'])}; I² = {r['I2']:.0f}%; τ² = {r['tau2']:.3f}{tci}.{pred}")
        frows = [[x["label"], D.fmt(x["effect"]), f"{D.fmt(x['ci_low'])} to {D.fmt(x['ci_high'])}",
                  f"{x['weight_pct']:.1f}"] for x in o["forest"]["rows"]]
        frows.append(["Pooled", D.fmt(r["estimate_display"]),
                      f"{D.fmt(r['ci_low_display'])} to {D.fmt(r['ci_high_display'])}", "100"])
        D.table(doc, ["Study", r["measure"], "95% CI", "Weight (%)"], frows, widths_cm=[5, 2.5, 4, 2.5], font_size=8.5)
        D.figure(doc, o["figures"].get("forest"), f"Figure {fig_no}. Forest plot — {name}")
        fig_no += 1
        if o["sensitivity"] or o["leave_one_out"]:
            srows = [[s["analysis"], s["k"], D.fmt(s["estimate"]), f"{D.fmt(s['ci_low'])} to {D.fmt(s['ci_high'])}",
                      f"{s['I2']:.0f}%"] for s in o["sensitivity"]]
            srows += [[f"Omitting {s['omitted']}", r["k"] - 1, D.fmt(s["estimate"]),
                       f"{D.fmt(s['ci_low'])} to {D.fmt(s['ci_high'])}", f"{s['I2']:.0f}%"] for s in o["leave_one_out"]]
            D.table(doc, ["Sensitivity analysis", "k", r["measure"], "95% CI", "I²"], srows, font_size=8,
                    caption=f"Sensitivity analyses — {name}")
            changed = [s for s in o["leave_one_out"]
                       if (s["ci_low"] <= null_value(r["measure"]) <= s["ci_high"]) !=
                       (r["ci_low_display"] <= null_value(r["measure"]) <= r["ci_high_display"])]
            D.para(doc, "Leave-one-out analysis: " + (
                "statistical significance changed when omitting " + ", ".join(s["omitted"] for s in changed) + "."
                if changed else "no single study changed the statistical conclusion."))
        if o.get("subgroups"):
            sg = o["subgroups"]
            rows = [[g, v["k"], f"{v['estimate_display']:.2f}", f"{v['ci_low_display']:.2f} to {v['ci_high_display']:.2f}",
                     f"{v['I2']:.0f}%"] for g, v in sg["subgroups"].items()]
            D.table(doc, ["Subgroup", "k", r["measure"], "95% CI", "I²"], rows, font_size=8.5,
                    caption=f"Subgroup analysis — {name}")
            D.para(doc, f"Test for subgroup differences: Q = {sg['Q_between']:.2f}, df = {sg['df']}, "
                        f"{p_text(sg['p_between'])}.")

    doc.add_heading("3.5 Reporting biases", 2)
    for name, o in outcomes.items():
        eg, bg = o.get("egger"), o.get("begg")
        if eg:
            D.para(doc, f"{name}: Egger's intercept = {eg['intercept']:.2f} ({p_text(eg['p'])}); Begg's "
                        f"Kendall τ = {bg['kendall_tau']:.2f} ({p_text(bg['p'])})."
                        + ("" if eg["adequately_powered"] else " With fewer than 10 studies these tests have low power."))
            D.figure(doc, o["figures"].get("funnel"), f"Figure {fig_no}. Funnel plot — {name}", width_cm=12)
            fig_no += 1
        else:
            D.para(doc, f"{name}: too few studies (k < 3) to assess small-study effects.")
    if not outcomes:
        D.para(doc, "Pending data extraction.")

    doc.add_heading("3.6 Certainty of evidence — Summary of Findings", 2)
    if outcomes:
        rows = []
        for name, o in outcomes.items():
            r, g = o["result"], o["grade"]
            rows.append([name, f"{r['k']} ({o['total_participants']})", _effect_str(r).split(" ", 1)[1],
                         f"{r['I2']:.0f}%", g["certainty"], "; ".join(g["downgrades"]) or "No downgrading"])
        D.table(doc, ["Outcome", "Studies (participants)", "Effect (95% CI)", "I²", "Certainty (GRADE)",
                      "Reasons"], rows, caption="Table 6. Summary of Findings (provisional GRADE)", font_size=8.5,
                widths_cm=[3, 2.4, 3.6, 1.2, 2.2, 5])
        D.para(doc, "Indirectness was not assessed automatically and must be judged by the review team.", italic=True,
               size=9)

    # ---------------- Discussion ----------------
    doc.add_heading("4. Discussion", 1)
    doc.add_heading("4.1 Summary of main findings", 2)
    if outcomes:
        for name, o in outcomes.items():
            r = o["result"]
            D.para(doc, f"For {name}, pooled data from {r['k']} studies showed {_direction(r)} "
                        f"({_effect_str(r)}), with {'substantial' if r['I2'] >= 50 else 'moderate' if r['I2'] >= 30 else 'low'} "
                        f"heterogeneity and {o['grade']['certainty'].lower()} certainty of evidence.")
    else:
        D.para(doc, "[To be completed after quantitative synthesis.]")
    doc.add_heading("4.2 Comparison with existing evidence", 2)
    D.para(doc, "[Authors to contextualise findings against previous reviews and guidelines.]")
    doc.add_heading("4.3 Strengths and limitations", 2)
    D.bullets(doc, [
        "Strengths: multi-database search through official APIs, transparent and reproducible reason-coded screening "
        "log, standardised effect-size computation, and pre-specified sensitivity analyses.",
        "Limitations of the evidence: risk of bias in primary studies, heterogeneity of populations and outcome "
        "definitions, and possible small-study effects.",
        "Limitations of the review process: automated screening may misclassify records; full texts were limited to "
        "open-access sources; grey literature and trial registers were not searched unless added by the authors.",
    ])
    if gap_summary and gap_summary.get("gaps"):
        doc.add_heading("4.4 Implications for research", 2)
        D.para(doc, "Research gaps identified by the companion gap analysis (Module A):")
        D.bullets(doc, gap_summary["gaps"][:5])
    doc.add_heading("4.5 Conclusions", 2)
    D.para(doc, concl)

    # ---------------- Other information ----------------
    doc.add_heading("5. Other Information", 1)
    D.bullets(doc, [("Registration and protocol: ", "[PROSPERO ID / protocol reference]"),
                    ("Support: ", "[Funding sources]"), ("Competing interests: ", "[Declarations]"),
                    ("Availability of data, code and other materials: ",
                     "Search logs, screening decisions, extraction sheets and analysis outputs are provided as "
                     "supplementary files generated by the Unified Research & Meta-Analysis Engine.")])
    doc.add_heading("Appendix A. PRISMA 2020 checklist", 1)
    D.table(doc, ["#", "Item", "Checklist requirement", "Location"], [list(x) for x in PRISMA_CHECKLIST],
            font_size=8, widths_cm=[1, 4, 7, 4])
    doc.add_heading("References (included studies)", 1)
    for i, rec in enumerate(included_records, 1):
        D.para(doc, f"{i}. {rec.citation()}", size=9)
    D.para(doc, "Page MJ, McKenzie JE, Bossuyt PM, et al. The PRISMA 2020 statement: an updated guideline for "
                "reporting systematic reviews. BMJ. 2021;372:n71.", size=9)
    D.para(doc, "Sterne JAC, Savović J, Page MJ, et al. RoB 2: a revised tool for assessing risk of bias in randomised "
                "trials. BMJ. 2019;366:l4898.", size=9)
    D.para(doc, "Sterne JA, Hernán MA, Reeves BC, et al. ROBINS-I: a tool for assessing risk of bias in non-randomised "
                "studies of interventions. BMJ. 2016;355:i4919.", size=9)
    D.para(doc, "DerSimonian R, Laird N. Meta-analysis in clinical trials. Control Clin Trials. 1986;7:177-88.", size=9)
    D.para(doc, "Viechtbauer W. Bias and efficiency of meta-analytic variance estimators in the random-effects model. "
                "J Educ Behav Stat. 2005;30:261-93.", size=9)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path
