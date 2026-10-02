"""Generates Unified_Engine_Manual.docx.  The CLI reference is built by
introspecting the argparse parser, so the manual never drifts from the code."""

from __future__ import annotations

import argparse
from pathlib import Path

from ureme import __version__
from ureme.reporting import docx_utils as D
from ureme.review.extraction import COLUMNS


def _cli_tables(doc) -> None:
    from ureme.cli import build_parser

    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    helps = {c.dest: c.help for c in sub._choices_actions}
    for name, sp in sub.choices.items():
        doc.add_heading(f"ureme {name}", 3)
        D.para(doc, helps.get(name, ""))
        rows = []
        for act in sp._actions:
            if isinstance(act, argparse._HelpAction):
                continue
            flags = ", ".join(act.option_strings) or act.dest
            default = "" if act.default in (None, False, argparse.SUPPRESS) else str(act.default)
            req = "yes" if act.required else ""
            rows.append([flags, act.help or "", default, req])
        D.table(doc, ["Argument", "Description", "Default", "Required"], rows, font_size=8,
                widths_cm=[4.2, 8.5, 2.8, 1.5])


def build_manual(path: str | Path = "Unified_Engine_Manual.docx") -> Path:
    doc = D.new_document()
    D.title_page(doc, "Unified Research & Meta-Analysis Engine", "User Manual",
                 [("Version", __version__), ("Command", "ureme")])
    D.toc(doc)

    doc.add_heading("1. Overview", 1)
    D.para(doc, "The Unified Research & Meta-Analysis Engine (UREME) is a Python command-line system that connects to "
                "live academic databases and produces two families of deliverables:")
    D.bullets(doc, [
        ("Module A — Gap & Idea Generator: ", "mines recent literature (last 1–3 years) for limitations, conflicting "
                                              "evidence and unanswered questions; categorises gaps as Methodological, "
                                              "Population, Mechanistic or Knowledge/Evidence; and writes PICO/FINER "
                                              "research proposals with hypotheses, designs and power calculations."),
        ("Module B — PRISMA 2020 Review Engine: ", "deduplicates records, screens them against your criteria with "
                                                   "reason-coded exclusions, builds the PRISMA flow diagram, supports "
                                                   "data extraction and RoB 2 / ROBINS-I assessment, and runs "
                                                   "fixed/random-effects meta-analyses (OR, RR, RD, SMD, MD) with "
                                                   "heterogeneity, sensitivity, subgroup and publication-bias analyses."),
        ("Reporting: ", "both modules write professionally formatted Word documents — Research_Gap_Proposal.docx "
                        "and PRISMA_Manuscript.docx."),
    ])
    D.table(doc, ["Database", "API", "Used for"], [
        ["PubMed / NCBI", "E-utilities (esearch, efetch, elink)", "Records, MeSH, PMC open-access full text, citations"],
        ["Europe PMC", "REST API (search, fullTextXML, citations)", "Records, open-access full text, citation counts"],
        ["Semantic Scholar", "Academic Graph API (search, bulk search)", "Records, citation counts, citation graph"],
    ], caption="Table 1. Supported data sources", widths_cm=[3.2, 5.5, 7.3])

    doc.add_heading("2. Installation", 1)
    doc.add_heading("2.1 Requirements", 2)
    D.bullets(doc, ["Python 3.10 or newer (3.11 recommended)", "Internet access to eutils.ncbi.nlm.nih.gov, "
                    "www.ebi.ac.uk and api.semanticscholar.org (not needed for the offline demo)",
                    "Microsoft Word, LibreOffice or any .docx viewer to open reports"])
    doc.add_heading("2.2 Steps", 2)
    for step in ["git clone <repository-url> && cd <repository-folder>",
                 "python -m venv .venv",
                 "source .venv/bin/activate        (Windows: .venv\\Scripts\\activate)",
                 "pip install -r requirements.txt",
                 "pip install -e .                 (installs the `ureme` command)",
                 "ureme demo -o ureme_demo         (verifies the installation offline)",
                 "pytest                           (optional: run the test-suite)"]:
        D.para(doc, step, style="List Number")
    D.callout(doc, "Without `pip install -e .` you can always run the engine as `python -m ureme <command>` from the "
                   "repository root.", "Tip")
    doc.add_heading("2.3 API keys and environment variables", 2)
    D.table(doc, ["Variable", "Purpose", "Required"], [
        ["NCBI_EMAIL", "Contact e-mail sent to NCBI as requested by their usage policy", "Recommended"],
        ["NCBI_API_KEY", "Raises the PubMed rate limit from 3 to 10 requests/s", "Optional"],
        ["S2_API_KEY", "Semantic Scholar key for higher, more reliable rate limits", "Optional (recommended)"],
        ["UREME_CACHE_DIR", "Folder caching raw API responses for reproducible re-runs", "Optional"],
    ], widths_cm=[3.5, 9.5, 3])
    D.para(doc, "Keys can also be passed per run with --ncbi-api-key, --s2-api-key and --email. Keys are never written "
                "to output files or cache keys.")

    doc.add_heading("3. Quick start", 1)
    examples = [
        ("Offline demonstration", "ureme demo -o ureme_demo"),
        ("Gap analysis (last 3 years)", 'ureme gaps -q "(sarcopenia) AND (resistance training)" --years 3 --top 5 '
                                        '-o out_gaps'),
        ("Start a systematic review", "ureme init -o criteria.json   (then edit criteria.json)"),
        ("Review, stage 1 (search → screening → extraction sheet)",
         'ureme review -q "<boolean query>" -c criteria.json -o out_review'),
        ("Review, stage 2 (meta-analysis, re-using the saved search)",
         "ureme review -c criteria.json --records-in out_review/search/records_raw.json "
         "-x out_review/review/extraction_completed.csv -o out_review"),
        ("Combined workflow", 'ureme combined -q "<boolean query>" -c criteria.json -o out_all'),
        ("Meta-analysis only", "ureme meta -x my_extraction.csv --effect RR --tau2 REML --hksj -o out_meta"),
        ("Regenerate this manual", "ureme manual -o Unified_Engine_Manual.docx"),
    ]
    D.table(doc, ["Task", "Command"], [list(e) for e in examples], widths_cm=[5, 11], font_size=8.5)

    doc.add_heading("4. Workflows", 1)
    doc.add_heading("4.1 Module A — gap analysis", 2)
    D.bullets(doc, [
        "Searches the selected databases restricted to the last N years (--years, default 3).",
        "Deduplicates records and downloads up to --full-text-limit open-access full texts.",
        "Extracts sentences containing limitation markers, classifies each into the four gap categories, clusters "
        "them into themes, and detects conflicting evidence (topics with both significant and null findings).",
        "Ranks gaps by number of studies, recency and citation impact, then generates --top proposals with PICO, "
        "H1/H0, rationale, suggested design, sample-size table and FINER scores.",
        "Override any PICO element with --population/--intervention/--comparison/--outcome.",
    ], numbered=True)
    doc.add_heading("4.2 Module B — PRISMA 2020 systematic review", 2)
    D.bullets(doc, [
        "Write criteria.json (ureme init gives a template).",
        "Run `ureme review`. Records are searched, deduplicated, screened (title/abstract), full texts are retrieved "
        "where open access, eligibility is assessed and every decision is logged in review/screening_log.csv.",
        "Inspect the screening log. To adjudicate a decision, copy review/screening_overrides.example.json to "
        "screening_overrides.json, edit it and pass --overrides.",
        "Complete review/extraction_template.csv: verify the pre-filled numbers (auto_candidates shows the text they "
        "came from), fill missing outcome data and confirm the provisional risk-of-bias judgements.",
        "Re-run with --extraction <completed.csv> and --records-in <out>/search/records_raw.json so that the same "
        "records are used (reproducible). The meta-analysis, plots and full manuscript are produced.",
    ], numbered=True)
    doc.add_heading("4.3 Combined workflow", 2)
    D.para(doc, "`ureme combined` runs Module A and Module B on the same search. The manuscript's introduction and "
                "'Implications for research' cite the identified gaps, and the gap report is refreshed with the "
                "pooled estimates once an extraction sheet is supplied.")

    doc.add_heading("5. Command-line reference", 1)
    D.para(doc, "Every command accepts -h/--help. The tables below are generated from the program itself.")
    _cli_tables(doc)

    doc.add_heading("6. Input file formats", 1)
    doc.add_heading("6.1 Search queries", 2)
    D.para(doc, "Write queries in PubMed syntax: AND / OR / NOT (upper case), parentheses, \"quoted phrases\", "
                "truncation with * and optional field tags ([tiab], [ti], [ab], [mh], [au], [pt]). The engine "
                "translates them for Europe PMC (TITLE:, ABSTRACT:, MESH: …) and Semantic Scholar (+, |, -). "
                "Long strategies can be stored in a text file and passed with --query-file.")
    doc.add_heading("6.2 criteria.json", 2)
    D.table(doc, ["Key", "Type", "Meaning"], [
        ["title / question", "text", "Review title and question (used in the manuscript)"],
        ["pico", "object", "population / intervention / comparison / outcome descriptions"],
        ["year_min / year_max", "integer", "Publication-year limits"],
        ["languages", "list", "Allowed languages, e.g. [\"eng\"]"],
        ["require_abstract", "bool", "Exclude records without an abstract"],
        ["exclude_publication_types", "list", "e.g. Review, Editorial, Letter, Case Reports"],
        ["include_concepts", "object", "{label: [terms]} — every label must match at least one term"],
        ["exclude_terms", "object", "{reason: [terms]} — any match excludes with that reason"],
        ["study_design_terms / study_design_label", "list / text", "Required design terms (e.g. randomi*)"],
        ["min_sample_size", "integer", "Full-text stage: exclude when the detected N is smaller"],
        ["full_text_required_terms", "object", "{reason: [terms]} — must appear in full text/abstract"],
        ["full_text_policy", "text", "abstract_fallback (default) or strict (no OA full text = not retrieved)"],
        ["outcomes", "list", "Outcome names → one extraction row per study per outcome"],
        ["effect_measure", "text", "Default measure: OR, RR, RD, SMD or MD"],
    ], widths_cm=[5, 2.2, 8.8], font_size=8.5)
    D.para(doc, "Terms are matched case-insensitively as whole words; a trailing * matches any ending (randomi* → "
                "randomised, randomized, randomization). Spaces also match hyphens.")
    doc.add_heading("6.3 Extraction sheet (CSV)", 2)
    D.para(doc, "Columns: " + ", ".join(COLUMNS))
    D.bullets(doc, [
        "One row per study per outcome. Rows with include_in_meta = no are ignored.",
        "Dichotomous outcomes: treat_events, treat_total, ctrl_events, ctrl_total.",
        "Continuous outcomes: treat_mean, treat_sd, treat_n, ctrl_mean, ctrl_sd, ctrl_n.",
        "Generic inverse variance: yi and sei on the analysis scale (log scale for OR/RR).",
        "subgroup: label used for subgroup analysis. design: RCT or NRSI.",
        "rob_tool: RoB2 (domains rob_d1–rob_d5) or ROBINS-I (rob_d1–rob_d7). Judgements: Low / Some concerns / "
        "High (RoB 2) or Low / Moderate / Serious / Critical (ROBINS-I). rob_overall is computed when blank.",
    ])

    doc.add_heading("7. Outputs", 1)
    D.table(doc, ["File", "Content"], [
        ["search/records_raw.json", "All retrieved records per database + search log (re-usable via --records-in)"],
        ["gaps/gaps.json, gaps/proposals.json", "Gap statements, ranked gaps, proposals (machine-readable)"],
        ["Research_Gap_Proposal.docx", "Module A report"],
        ["review/duplicates.json", "Each removed duplicate, the record kept and the matching rule"],
        ["review/screening_log.csv", "Every screening/eligibility decision with reason"],
        ["review/prisma_flow.json / .png", "PRISMA 2020 counts (with arithmetic check) and diagram"],
        ["review/rob_suggestions.json", "Provisional RoB judgements with supporting text"],
        ["review/extraction_template.csv", "Extraction sheet to complete"],
        ["meta/meta_results.json", "All statistics, forest/funnel data, sensitivity, subgroups, GRADE"],
        ["meta/forest_*.png, funnel_*.png, rob_*.png", "Figures"],
        ["PRISMA_Manuscript.docx", "Full manuscript draft"],
        ["run_manifest.json", "Engine version, command and arguments (API keys omitted)"],
    ], widths_cm=[6, 10], font_size=8.5)

    doc.add_heading("8. Statistical methods", 1)
    D.bullets(doc, [
        "Odds ratio and risk ratio on the log scale (0.5 continuity correction for zero cells; double-zero studies "
        "are non-estimable). Risk difference on the natural scale.",
        "Standardised mean difference = Hedges' g with small-sample correction J = 1 − 3/(4(n1+n2) − 9).",
        "Inverse-variance fixed-effect and random-effects models; τ² by REML (default), DerSimonian–Laird or "
        "Paule–Mandel; optional Hartung–Knapp–Sidik–Jonkman CI.",
        "Heterogeneity: Cochran's Q, I², H², τ² with Q-profile 95% CI, 95% prediction interval (k ≥ 3).",
        "Publication bias: Egger's regression (statsmodels OLS), Begg's rank correlation, funnel plot.",
        "Sensitivity: leave-one-out, alternative model, exclusion of high risk-of-bias studies. Subgroups: "
        "Q-between test.",
        "Validated against published metafor results for the BCG vaccine dataset (see tests).",
    ])

    doc.add_heading("9. Using the engine with Claude Code or other agents", 1)
    D.para(doc, "The repository contains CLAUDE.md and a project skill (.claude/skills/research-engine). An agent can: "
                "run the CLI, read the JSON artefacts, adjudicate screening decisions by writing an overrides file, "
                "complete the extraction CSV from full texts, and re-run downstream stages. Every automated judgement "
                "is stored in an editable file, so agent or human corrections are always traceable.")

    doc.add_heading("10. Troubleshooting", 1)
    D.table(doc, ["Symptom", "Remedy"], [
        ["HTTP 429 / rate limited", "Add NCBI_API_KEY / S2_API_KEY, reduce --max-results, or re-run (responses are "
                                    "retried with exponential back-off)"],
        ["A database shows an error in the search table", "The run continues with the other databases; the error is "
                                                          "recorded in the search log and manuscript"],
        ["Too many / too few records included", "Refine include_concepts / exclude_terms, inspect "
                                                "review/screening_log.csv, use --overrides"],
        ["'Missing outcome data' in meta_results.json", "Fill the numeric columns of the extraction sheet"],
        ["Table of contents is empty in Word", "Right-click the table of contents → Update field (or press F9)"],
        ["No network (offline)", "Use --records-in with a saved records file, or run `ureme demo`"],
    ], widths_cm=[6, 10], font_size=8.5)

    doc.add_heading("11. Responsible use", 1)
    D.para(doc, "UREME accelerates evidence synthesis but does not replace expert judgement. PRISMA 2020 and the "
                "Cochrane Handbook require dual independent screening, extraction and risk-of-bias assessment; treat "
                "all automated decisions as a first pass to be verified. Respect the terms of use of each API.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path
