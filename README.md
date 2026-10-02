# Unified Research & Meta-Analysis Engine (UREME)

A Python research-intelligence system that connects to live academic databases and turns a search into:

* **Module A: Scientific Gap & Novel Idea Generator.** It mines the last 1–3 years of literature for limitation statements, conflicting evidence and unanswered questions. It sorts gaps into Methodological, Population, Mechanistic and Knowledge/Evidence categories and writes PICO/FINER research proposals with hypotheses, designs and power calculations. Output: **`Research_Gap_Proposal.docx`**.
* **Module B: PRISMA 2020 Systematic Review & Meta-Analysis Engine.** It deduplicates records, screens them with reason-coded exclusions, builds the PRISMA flow diagram, and supports data extraction and RoB 2 / ROBINS-I assessment. It then runs fixed- and random-effects meta-analysis (OR, RR, RD, SMD, MD; DL, REML or PM τ²; optional HKSJ) with I², Q, τ² CI, prediction intervals, leave-one-out, subgroup, Egger and Begg tests, forest and funnel plots, and provisional GRADE. Output: **`PRISMA_Manuscript.docx`**.
* **User manual:** **`Unified_Engine_Manual.docx`** (regenerate with `ureme manual`).

Data sources: **PubMed / NCBI Entrez E-utilities**, **Europe PMC REST**, **Semantic Scholar Academic Graph**. These provide records, abstracts, MeSH terms, open-access full text (PMC / Europe PMC) and citation graphs.

## Install

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .            # provides the `ureme` command (or use `python -m ureme`)
ureme demo -o ureme_demo    # offline end-to-end check on synthetic data
pytest                      # 30 tests, all offline
```

Optional environment variables: `NCBI_EMAIL`, `NCBI_API_KEY`, `S2_API_KEY`, `UREME_CACHE_DIR`.

## Usage

```bash
# Module A: gaps + proposals from the last 3 years
ureme gaps -q '("sarcopenia") AND ("resistance training" OR "exercise")' --years 3 --top 5 -o out_gaps

# Module B, stage 1: search → dedup → screening → PRISMA → extraction sheet + draft manuscript
ureme init -o criteria.json                 # then edit it
ureme review --query-file examples/query_example.txt -c criteria.json -o out_review

# Module B, stage 2: fill out_review/review/extraction_template.csv, then re-use the saved search
ureme review -c criteria.json --records-in out_review/search/records_raw.json \
             -x out_review/review/extraction_completed.csv --tau2 REML -o out_review

# Both modules, cross-linked
ureme combined -q '<boolean query>' -c criteria.json -o out_all

# Statistics only
ureme meta -x examples/extraction_example.csv --effect RR --hksj -o out_meta
```

Run `ureme <command> -h` for every option. Queries use PubMed Boolean syntax and are translated automatically for Europe PMC and Semantic Scholar.

## Project layout

```
ureme/
  apis/        PubMed, Europe PMC, Semantic Scholar clients; HTTP client (rate limit, retry, cache); query translation
  gaps/        Module A: lexicons, gap detector, conflicting-evidence detection, PICO/FINER proposal generator
  review/      Module B: dedup, screening, PRISMA flow, extraction sheet, RoB 2 / ROBINS-I, GRADE
  meta/        effect sizes, FE/RE models, publication bias, sensitivity/subgroups, plots, per-outcome synthesis
  reporting/   python-docx helpers, gap report, PRISMA manuscript, user manual
  pipeline.py  orchestration (every stage writes JSON/CSV artefacts)
  cli.py       argparse + rich CLI
  demo.py      synthetic offline dataset
tests/         offline tests incl. metafor reference values (BCG dataset) and API parser fixtures
examples/      criteria, query and extraction examples
```

## Validation

The random-effects implementation reproduces published `metafor` results for the BCG vaccine dataset (REML: log RR −0.7145, SE 0.1798, τ² 0.3132, Q-profile CI 0.120–1.112; DL τ² 0.3088; PM τ² 0.3181; FE −0.4303). It also matches `statsmodels.stats.meta_analysis.combine_effects` exactly. See `tests/test_meta.py`.

## Responsible use

Automated screening, extraction suggestions, risk-of-bias judgements and GRADE ratings are labelled **provisional**. PRISMA 2020 and the Cochrane Handbook require verification by two independent reviewers. Every automated decision is stored in an editable file (`screening_log.csv`, overrides JSON, extraction CSV) so that human or agent corrections stay traceable.
