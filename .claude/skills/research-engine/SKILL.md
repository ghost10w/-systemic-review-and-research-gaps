---
name: research-engine
description: Run the Unified Research & Meta-Analysis Engine (ureme) in this repository. Use when the user asks to find research gaps or generate research ideas/proposals on a topic, to conduct a PRISMA systematic review or meta-analysis, to pool study data (OR/RR/SMD), or to produce the gap-proposal / PRISMA manuscript Word documents.
---

# Running UREME as an agent

All commands run from the repository root. Use `python -m ureme` if the `ureme` entry point is not installed.

## 0. Preconditions
- `python -c "import docx, scipy, statsmodels, rich, matplotlib"`. If that fails: `pip install -r requirements.txt`.
- Live search needs network access to NCBI, EBI and Semantic Scholar. If you are offline, say so, and offer `ureme demo` or `--records-in <saved records json>`.

## 1. Gap analysis / novel ideas (Module A)
```bash
python -m ureme gaps -q '<PubMed-syntax Boolean query>' --years 3 --top 5 -o out/<topic>_gaps
```
- Write the query in PubMed syntax: quoted phrases, OR-groups of synonyms joined by AND, optional `[tiab]` and `[mh]` tags.
- If the user specified PICO elements, pass them with `--population/--intervention/--comparison/--outcome`.
- Read `gaps/proposals.json` and summarise the top proposals (title, hypothesis, FINER score), then point to `Research_Gap_Proposal.docx`.

## 2. Systematic review (Module B): two-stage loop
1. `python -m ureme init -o out/<topic>/criteria.json`. Fill it in from the user's question; `examples/criteria_example.json` is a model.
2. Stage 1: `python -m ureme review -q '<query>' -c out/<topic>/criteria.json -o out/<topic>`.
3. Audit screening. Open `review/screening_log.csv` and check exclusions that look wrong (e.g. a synonym missing from `include_concepts`). Prefer fixing the criteria and re-running. For individual records, write `review/screening_overrides.json` (format in `screening_overrides.example.json`) and pass `--overrides`.
4. Extraction. For each row of `review/extraction_template.csv`, verify the pre-filled numbers against `auto_candidates` and the full text, then fill the missing arm-level data. Confirm the risk-of-bias columns (`rob_suggestions.json` holds the supporting quotes). Never invent numbers: leave cells blank when the data is not reported, and the study will be listed as "Missing outcome data".
5. Stage 2: `python -m ureme review -c ... --records-in out/<topic>/search/records_raw.json -x <completed.csv> -o out/<topic>`.
6. Report the PRISMA counts (`review/prisma_flow.json`; `consistency_problems` must be empty), the pooled estimates and GRADE (`meta/meta_results.json`), and the manuscript path. Point out that automated judgements are provisional.

## 3. Combined
`python -m ureme combined -q '<query>' -c criteria.json [-x completed.csv] -o out/<topic>` runs both modules and cross-links them.

## 4. Meta-analysis only
`python -m ureme meta -x data.csv [--effect OR|RR|RD|SMD|MD] [--tau2 REML|DL|PM] [--hksj] -o out/meta`. The CSV columns are listed in the manual (section 6.3) and in `examples/extraction_example.csv`.
