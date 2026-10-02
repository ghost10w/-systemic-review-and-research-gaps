# CLAUDE.md: guide for Claude Code (and other agents)

**UREME (Unified Research & Meta-Analysis Engine)** is a Python CLI package (`ureme/`). It searches PubMed, Europe PMC and Semantic Scholar. Module A finds research gaps and writes proposals. Module B runs a PRISMA 2020 systematic review and meta-analysis. Both write `.docx` reports.

## Commands

```bash
pip install -r requirements.txt && pip install -e .   # deps (+ `ureme` entry point)
python -m pytest -q                                   # full offline test-suite (~20 s)
python -m ureme demo -o /tmp/ureme_demo               # offline end-to-end smoke test
python -m ureme manual -o Unified_Engine_Manual.docx  # regenerate the committed manual after CLI changes
python -m ureme <search|gaps|review|combined|meta|init> -h
```

## Architecture (data flow)

`cli.py` → `pipeline.py` → modules. Every stage writes artefacts into `--out-dir`:

1. `apis/aggregator.search_databases` → `SearchBundle` (records per DB + `SearchLogEntry`) → `search/records_raw.json`. Later runs can skip the network with `--records-in`.
2. Module A, `pipeline.run_gaps`: `review/dedup.deduplicate` → year filter → `gaps/detector.find_gaps` (marker sentences → category → theme clusters + `detect_conflicts`) → `gaps/proposals.generate_proposals` → `reporting/gap_report.py`.
3. Module B, `pipeline.run_review`: dedup → `review/screening.screen_title_abstract` → OA full text → `assess_eligibility` → overrides → `review/prisma.build_flow` → `rob.suggest_rob` + `extraction.build_extraction_template`. If `-x` is given: `meta/synthesis.synthesize` (per outcome: `meta.models.meta_analyze`, bias, sensitivity, subgroups, `review/grade.py`, plots) → `reporting/manuscript.py`.

Core types: `models.Record` (harmonised bibliographic record; `record_id` is `doi:` > `pmid:` > `pmcid:` > `s2:` > `epmc:` > `title:` hash), `models.SearchBundle`, `review.screening.Criteria` / `Decision`, `review.extraction.StudyOutcome`, `meta.models.MetaResult`, `gaps.detector.Gap`, `gaps.proposals.Proposal`.

## Conventions

* Ratio measures (OR, RR) are analysed on the **log scale**. `MetaResult.display()` / `*_display` fields back-transform them. Never pool exponentiated values.
* Every automated judgement (screening, RoB, GRADE, PICO) must stay **auditable and overridable**: keep reasons/rationale strings and the `provisional` flags.
* Database failures must not abort a run. They are recorded in `SearchLogEntry.error`.
* Secrets (API keys) never go into outputs, cache keys or `run_manifest.json`.
* Reports must label synthetic data. `demo.py` uses DOI prefix `10.0000/ureme-demo`.
* The manual's CLI tables are generated from `cli.build_parser()`. After changing CLI flags, re-run `ureme manual` and commit the `.docx`.
* Tests are fully offline. API clients are tested with fixtures in `tests/fixtures/` via the `FakeHttp` stub in `tests/conftest.py`. Statistical changes must keep `tests/test_meta.py` (metafor reference values) passing.
* Tune gap mining through `gaps/lexicon.py` (regex lists), not by hard-coding in the detector.

## Acting as a reviewer with this engine

When a user asks you to run a review, use the project skill `.claude/skills/research-engine/SKILL.md`. Its loop is: run stage 1 → read `review/screening_log.csv` and adjudicate edge cases via an overrides JSON → complete `review/extraction_template.csv` from the full texts (verify every auto-filled number against `auto_candidates`) → re-run with `--records-in` and `-x` → report the PRISMA counts and pooled estimates.

## Network note

Live searches need outbound HTTPS to `eutils.ncbi.nlm.nih.gov`, `www.ebi.ac.uk` and `api.semanticscholar.org`. In sandboxes without that access, use `ureme demo` or `--records-in`.
