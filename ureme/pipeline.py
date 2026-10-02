"""High-level workflows used by the CLI.  Every stage writes inspectable JSON/CSV
artefacts into the output directory so that humans or agents can review/edit
them and re-run downstream stages.

Output layout (``out_dir``)::

    search/records_raw.json        SearchBundle (all records per database + search log)
    gaps/gaps.json, proposals.json Module A results
    review/duplicates.json         removed duplicates with reasons
    review/screening_log.csv       every decision (stage, include, reason, detail)
    review/prisma_flow.json/.png   PRISMA 2020 counts + diagram
    review/included_records.json
    review/rob_suggestions.json    provisional RoB 2 / ROBINS-I judgements
    review/extraction_template.csv sheet to complete for meta-analysis
    review/screening_overrides.example.json
    meta/meta_results.json, *.png  synthesis results + forest/funnel plots
    Research_Gap_Proposal.docx, PRISMA_Manuscript.docx
    run_manifest.json
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from ureme import __version__
from ureme.apis.aggregator import enrich_citations, enrich_full_text, search_databases
from ureme.apis.query import concept_terms
from ureme.config import Settings
from ureme.gaps.detector import find_gaps
from ureme.gaps.proposals import generate_proposals
from ureme.meta.synthesis import synthesize
from ureme.models import Record, SearchBundle, SearchLogEntry
from ureme.reporting.gap_report import build_gap_report
from ureme.reporting.manuscript import build_manuscript
from ureme.review.dedup import deduplicate
from ureme.review.extraction import build_extraction_template, infer_design, load_extraction
from ureme.review.prisma import build_flow, render_flow_diagram
from ureme.review.rob import render_traffic_light, rob_matrix, suggest_rob
from ureme.review.screening import (ELIGIBILITY, TITLE_ABSTRACT, Criteria, apply_overrides, assess_eligibility,
                                    load_overrides, screen_title_abstract)

log = logging.getLogger(__name__)
Progress = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def load_records_file(path: str | Path) -> SearchBundle:
    """Accept a SearchBundle JSON (from a previous run) or a plain list of record dicts."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "records_by_db" in data:
        return SearchBundle.from_dict(data)
    if isinstance(data, list):
        recs = [Record.from_dict(d) for d in data]
        return SearchBundle({"Imported": recs}, [SearchLogEntry("Imported", str(path), dt.date.today().isoformat(),
                                                                len(recs), len(recs))])
    raise ValueError(f"Unrecognised records file format: {path}")


def acquire(query: str, databases: list[str], settings: Settings, out_dir: Path, max_per_db: int,
            min_year: int | None, max_year: int | None, records_in: str | None = None,
            progress: Progress = _noop) -> SearchBundle:
    if records_in:
        progress(f"Loading records from {records_in}")
        bundle = load_records_file(records_in)
    else:
        bundle = search_databases(query, databases, settings, max_per_db, min_year, max_year, progress)
    write_json(out_dir / "search" / "records_raw.json", bundle.to_dict())
    return bundle


def _filter_years(records: list[Record], min_year: int | None, max_year: int | None) -> list[Record]:
    return [r for r in records if (r.year is None or ((min_year is None or r.year >= min_year) and
                                                      (max_year is None or r.year <= max_year)))]


# --------------------------------------------------------------------------- Module A
def run_gaps(query: str, bundle: SearchBundle, out_dir: Path, settings: Settings, years: int = 3, top_n: int = 5,
             pico_overrides: dict | None = None, full_text_limit: int = 25, citations: bool = False,
             meta_context: dict | None = None, synthetic: bool = False, progress: Progress = _noop) -> dict:
    out_dir = Path(out_dir)
    this_year = dt.date.today().year
    min_year = this_year - years
    dedup = deduplicate([Record.from_dict(r.to_dict()) for r in bundle.all_records])
    records = _filter_years(dedup.unique, min_year, this_year)
    progress(f"{len(records)} unique records from {min_year}-{this_year} for gap mining")
    if settings.fetch_full_text and full_text_limit:
        n = enrich_full_text(records, settings, limit=full_text_limit, progress=progress)
        progress(f"Retrieved {n} open-access full texts")
    if citations:
        enrich_citations(records, settings, progress)
    terms = concept_terms(query)
    result = find_gaps(records, terms)
    proposals = generate_proposals(result["gaps"], records, terms, top_n=top_n, pico_overrides=pico_overrides)
    gdir = out_dir / "gaps"
    write_json(gdir / "gaps.json", {k: ([g.to_dict() for g in v] if k == "gaps" else
                                        [asdict(s) for s in v] if k == "statements" else v)
                                    for k, v in result.items()})
    write_json(gdir / "proposals.json", [p.to_dict() for p in proposals])
    write_json(gdir / "records_analysed.json", [r.to_dict(include_full_text=False) for r in records])
    report = build_gap_report(out_dir / "Research_Gap_Proposal.docx", query, [asdict(e) for e in bundle.log],
                              {**result, "gaps": result["gaps"][: max(top_n * 3, 10)]}, proposals,
                              {r.record_id: r for r in records}, (min_year, this_year), meta_context, synthetic)
    progress(f"Wrote {report}")
    return {"result": result, "proposals": proposals, "records": records, "report": report}


def gap_summary_for_manuscript(gap_run: dict) -> dict:
    gaps = gap_run["result"]["gaps"]
    return {
        "summary": (f"A companion analysis of recent literature identified {len(gaps)} research gaps, most often "
                    f"{max(gap_run['result']['gaps_by_category'].items(), key=lambda kv: kv[1])[0].lower()} in "
                    f"nature, motivating this synthesis.") if gaps else "",
        "gaps": [f"{g.gap_id} ({g.category}): {g.description}" for g in gaps[:5]],
    }


# --------------------------------------------------------------------------- Module B
def _write_screening_log(path: Path, decisions, records_by_id: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["record_id", "stage", "included", "reason", "detail", "source", "year", "title"])
        for d in decisions:
            r = records_by_id.get(d.record_id)
            w.writerow([d.record_id, d.stage, d.included, d.reason or "", d.detail, d.source,
                        r.year if r else "", r.title if r else ""])


def run_review(query: str, criteria: Criteria, bundle: SearchBundle, out_dir: Path, settings: Settings,
               extraction: str | None = None, overrides: str | None = None, measure: str | None = None,
               model: str = "random", tau2_method: str = "REML", hksj: bool = False, full_text_limit: int = 200,
               gap_summary: dict | None = None, synthetic: bool = False, progress: Progress = _noop) -> dict:
    out_dir = Path(out_dir)
    rdir, mdir = out_dir / "review", out_dir / "meta"
    raw_counts = {db: len(recs) for db, recs in bundle.records_by_db.items()}
    records = [Record.from_dict(r.to_dict()) for r in bundle.all_records]
    dd = deduplicate(records)
    progress(f"Deduplication: {len(records)} -> {len(dd.unique)} ({dd.n_removed} duplicates)")
    write_json(rdir / "duplicates.json", dd.duplicates)
    by_id = {r.record_id: r for r in dd.unique}

    ov = load_overrides(overrides)
    ta = apply_overrides(screen_title_abstract(dd.unique, criteria), ov, TITLE_ABSTRACT)
    passed = [by_id[d.record_id] for d in ta if d.included]
    progress(f"Title/abstract screening: {len(passed)} of {len(ta)} retained")
    if settings.fetch_full_text and full_text_limit:
        n = enrich_full_text(passed, settings, limit=full_text_limit, progress=progress)
        progress(f"Retrieved {n} open-access full texts")
    el, not_retrieved = assess_eligibility(passed, criteria)
    el = apply_overrides(el, ov, ELIGIBILITY)
    included = [by_id[d.record_id] for d in el if d.included]
    progress(f"Eligibility: {len(included)} studies included")
    _write_screening_log(rdir / "screening_log.csv", ta + el, by_id)
    write_json(rdir / "screening_overrides.example.json", {
        "_comment": "Copy to screening_overrides.json, edit, and pass with --overrides to adjudicate decisions.",
        **({ta[0].record_id: {"stage": "title_abstract", "decision": "include", "reason": "",
                              "note": "example"}} if ta else {}),
    })
    flow = build_flow(raw_counts, dd.n_removed, ta, not_retrieved, el)
    problems = flow.check()
    if problems:
        log.warning("PRISMA arithmetic check failed: %s", problems)
    write_json(rdir / "prisma_flow.json", {**flow.to_dict(), "consistency_problems": problems})
    figures = {"prisma": str(render_flow_diagram(flow, rdir / "prisma_flow.png"))}
    write_json(rdir / "included_records.json", [r.to_dict(include_full_text=False) for r in included])

    rob_sugg = {r.record_id: suggest_rob(r, infer_design(r)) for r in included}
    write_json(rdir / "rob_suggestions.json", rob_sugg)
    template = build_extraction_template(included, rdir / "extraction_template.csv", criteria.outcomes or None,
                                         rob_sugg, measure or criteria.effect_measure)
    progress(f"Extraction template: {template}")

    studies = synthesis = matrix = None
    if extraction:
        studies = load_extraction(extraction)
        known = {r.record_id for r in included}
        unknown = sorted({s.record_id for s in studies} - known)
        if unknown and included:
            log.warning("Extraction rows not among included studies: %s", unknown[:5])
        synthesis = synthesize(studies, measure or criteria.effect_measure, model, tau2_method, hksj,
                               figures_dir=mdir)
        write_json(mdir / "meta_results.json", synthesis)
        matrix = rob_matrix([s for s in studies if s.include])
        write_json(mdir / "rob_matrix.json", matrix)
        for tool, m in matrix.items():
            figures[f"rob_{tool}"] = str(render_traffic_light(m, mdir / f"rob_{tool}.png"))
        if not included:  # meta-only mode: report the extracted studies themselves
            seen = {}
            for s in studies:
                seen.setdefault(s.record_id, Record(title=s.study_label, year=s.year, record_id=s.record_id))
            included = list(seen.values())
    manuscript = build_manuscript(out_dir / "PRISMA_Manuscript.docx", criteria, query, [asdict(e) for e in bundle.log],
                                  flow, included, studies, synthesis, matrix, figures, gap_summary, synthetic,
                                  {"model": model, "tau2_method": tau2_method, "hksj": hksj})
    progress(f"Wrote {manuscript}")
    return {"flow": flow, "included": included, "synthesis": synthesis, "manuscript": manuscript,
            "template": template, "dedup": dd}


def run_meta_only(extraction: str, out_dir: Path, measure: str | None = None, model: str = "random",
                  tau2_method: str = "REML", hksj: bool = False) -> dict:
    out_dir = Path(out_dir)
    studies = load_extraction(extraction)
    synthesis = synthesize(studies, measure, model, tau2_method, hksj, figures_dir=out_dir / "meta")
    write_json(out_dir / "meta" / "meta_results.json", synthesis)
    matrix = rob_matrix([s for s in studies if s.include])
    write_json(out_dir / "meta" / "rob_matrix.json", matrix)
    for tool, m in matrix.items():
        render_traffic_light(m, out_dir / "meta" / f"rob_{tool}.png")
    return synthesis


def write_manifest(out_dir: Path, command: str, args: dict) -> None:
    write_json(Path(out_dir) / "run_manifest.json", {
        "engine": "Unified Research & Meta-Analysis Engine", "version": __version__, "command": command,
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "arguments": {k: v for k, v in args.items() if "key" not in k.lower()},
    })
