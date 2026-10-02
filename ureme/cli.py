"""Command-line interface:  ``ureme <command> [options]``  (or ``python -m ureme``).

Commands
  search    Query databases and save records (search/records_raw.json)
  gaps      Module A: gap analysis + research proposals (.docx)
  review    Module B: PRISMA 2020 review + meta-analysis (.docx)
  combined  Module A + Module B in one run, cross-linked
  meta      Meta-analysis only, from a completed extraction CSV
  demo      Fully offline end-to-end run on synthetic data
  init      Write an example criteria.json to start a review
  manual    (Re)generate Unified_Engine_Manual.docx
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from ureme import __version__
from ureme.config import Settings

console = Console()


def _common(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("API & runtime")
    g.add_argument("--email", help="Contact e-mail sent to NCBI (or env NCBI_EMAIL)")
    g.add_argument("--ncbi-api-key", help="NCBI API key (or env NCBI_API_KEY) - raises limit to 10 req/s")
    g.add_argument("--s2-api-key", help="Semantic Scholar API key (or env S2_API_KEY)")
    g.add_argument("--cache-dir", help="Cache raw API responses here for reproducible re-runs (or env UREME_CACHE_DIR)")
    g.add_argument("--no-full-text", action="store_true", help="Do not download open-access full texts")
    g.add_argument("-v", "--verbose", action="store_true", help="Debug logging")


def _search_args(p: argparse.ArgumentParser, years_default: int | None = None) -> None:
    g = p.add_argument_group("Search")
    g.add_argument("-q", "--query", help="Search string; PubMed Boolean syntax (AND/OR/NOT, quotes, [tiab] tags)")
    g.add_argument("--query-file", help="Read the search string from a text file")
    g.add_argument("-d", "--databases", default="pubmed,europepmc,semanticscholar",
                   help="Comma list: pubmed, europepmc, semanticscholar (aliases pm, epmc, s2)")
    g.add_argument("-n", "--max-results", type=int, default=200, help="Maximum records per database (default 200)")
    g.add_argument("--min-year", type=int, help="Earliest publication year")
    g.add_argument("--max-year", type=int, help="Latest publication year")
    g.add_argument("--records-in", help="Skip live search; load records JSON from a previous run "
                                        "(search/records_raw.json) or a list of records")
    g.add_argument("-o", "--out-dir", default="ureme_output", help="Output directory (default ./ureme_output)")


def _gap_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("Gap analysis (Module A)")
    g.add_argument("--years", type=int, default=3, help="Recent-literature window in years (1-3 recommended)")
    g.add_argument("--top", type=int, default=5, help="Number of research proposals to generate")
    g.add_argument("--full-text-limit", type=int, default=25, help="Max open-access full texts to mine")
    g.add_argument("--citations", action="store_true", help="Also fetch citation graphs (slower)")
    for k in ("population", "intervention", "comparison", "outcome"):
        g.add_argument(f"--{k}", help=f"Override the auto-derived PICO {k}")


def _meta_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("Meta-analysis")
    g.add_argument("--effect", choices=["OR", "RR", "RD", "SMD", "MD"], type=str.upper,
                   help="Effect measure (default per outcome: OR for dichotomous, SMD for continuous)")
    g.add_argument("--model", choices=["random", "fixed"], default="random")
    g.add_argument("--tau2", choices=["REML", "DL", "PM"], type=str.upper, default="REML",
                   help="Between-study variance estimator (default REML)")
    g.add_argument("--hksj", action="store_true", help="Hartung-Knapp-Sidik-Jonkman CI adjustment")


def _review_args(p: argparse.ArgumentParser, criteria_required: bool = True) -> None:
    g = p.add_argument_group("Systematic review (Module B)")
    g.add_argument("-c", "--criteria", required=criteria_required, help="Eligibility criteria JSON (see `ureme init`)")
    g.add_argument("-x", "--extraction", help="Completed extraction CSV -> runs the meta-analysis")
    g.add_argument("--overrides", help="Screening overrides JSON for manual adjudication")
    g.add_argument("--review-full-text-limit", type=int, default=200, help="Max full texts for eligibility")
    _meta_args(p)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ureme", description="Unified Research & Meta-Analysis Engine",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--version", action="version", version=f"ureme {__version__}")
    sub = ap.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("search", help="Search databases and save records")
    _search_args(p)
    _common(p)

    p = sub.add_parser("gaps", help="Module A: gap analysis and research proposals")
    _search_args(p)
    _gap_args(p)
    _common(p)

    p = sub.add_parser("review", help="Module B: PRISMA 2020 systematic review + meta-analysis")
    _search_args(p)
    _review_args(p)
    _common(p)

    p = sub.add_parser("combined", help="Module A + B in one run")
    _search_args(p)
    _gap_args(p)
    _review_args(p)
    _common(p)

    p = sub.add_parser("meta", help="Meta-analysis only from an extraction CSV")
    p.add_argument("-x", "--extraction", required=True)
    p.add_argument("-o", "--out-dir", default="ureme_output")
    p.add_argument("-v", "--verbose", action="store_true")
    _meta_args(p)

    p = sub.add_parser("demo", help="Offline end-to-end demonstration on synthetic data")
    p.add_argument("-o", "--out-dir", default="ureme_demo")
    p.add_argument("-v", "--verbose", action="store_true")

    p = sub.add_parser("init", help="Write an example criteria.json")
    p.add_argument("-o", "--output", default="criteria.json")

    p = sub.add_parser("manual", help="Generate Unified_Engine_Manual.docx")
    p.add_argument("-o", "--output", default="Unified_Engine_Manual.docx")
    return ap


def _settings(a) -> Settings:
    return Settings.from_env(email=getattr(a, "email", None), ncbi_api_key=getattr(a, "ncbi_api_key", None),
                             s2_api_key=getattr(a, "s2_api_key", None), cache_dir=getattr(a, "cache_dir", None),
                             fetch_full_text=not getattr(a, "no_full_text", False))


def _query(a) -> str:
    if getattr(a, "query_file", None):
        return Path(a.query_file).read_text(encoding="utf-8").strip()
    if getattr(a, "query", None):
        return a.query
    if getattr(a, "records_in", None):
        return "(records imported from file)"
    raise SystemExit("error: provide --query, --query-file or --records-in")


def _pico(a) -> dict:
    return {k: getattr(a, k, None) for k in ("population", "intervention", "comparison", "outcome")}


def _progress(msg: str) -> None:
    console.log(msg)


def _print_search(bundle) -> None:
    t = Table(title="Search results", header_style="bold cyan")
    for c in ("Database", "Hits", "Retrieved", "Status"):
        t.add_column(c)
    for e in bundle.log:
        t.add_row(e.database, str(e.total_hits), str(e.retrieved), "[red]" + e.error[:60] if e.error else "[green]OK")
    console.print(t)


def _print_gaps(run) -> None:
    t = Table(title="Top research proposals", header_style="bold cyan", show_lines=True)
    for c in ("ID", "Category", "Title", "FINER"):
        t.add_column(c)
    for p in run["proposals"]:
        t.add_row(p.proposal_id, p.category, p.title, f"{p.finer_total:.1f}")
    console.print(t)


def _print_review(run) -> None:
    f = run.get("flow")
    if f is not None:
        console.print(Panel.fit(
            f"Identified {f.identified} -> duplicates removed {f.duplicates_removed} -> screened {f.screened} -> "
            f"excluded {f.excluded_screening} -> assessed {f.assessed} -> [bold green]included {f.included_studies}",
            title="PRISMA 2020 flow"))
    syn = run.get("synthesis")
    if syn and syn["outcomes"]:
        t = Table(title="Meta-analysis", header_style="bold cyan")
        for c in ("Outcome", "k", "Effect (95% CI)", "p", "I²", "GRADE"):
            t.add_column(c)
        for name, o in syn["outcomes"].items():
            r = o["result"]
            t.add_row(name, str(r["k"]), f"{r['measure']} {r['estimate_display']:.2f} "
                      f"({r['ci_low_display']:.2f}, {r['ci_high_display']:.2f})", f"{r['p']:.3g}",
                      f"{r['I2']:.0f}%", o["grade"]["certainty"])
        console.print(t)
    else:
        console.print(f"[yellow]No extraction supplied. Complete {run['template']} and re-run with "
                      f"--extraction <file> --records-in <out>/search/records_raw.json")


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if getattr(a, "verbose", False) else logging.WARNING,
                        format="%(message)s", handlers=[RichHandler(console=console, show_path=False)])
    from ureme import pipeline as P

    if a.command == "init":
        from ureme.demo import DEMO_CRITERIA
        crit = {k: v for k, v in DEMO_CRITERIA.items()}
        crit["title"] = "Your review title"
        crit["_comment"] = "Edit every field. See Unified_Engine_Manual.docx section 6 for the full schema."
        Path(a.output).write_text(json.dumps(crit, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote {a.output}")
        return 0
    if a.command == "manual":
        from ureme.reporting.manual import build_manual
        console.print(f"[green]Wrote {build_manual(a.output)}")
        return 0
    if a.command == "demo":
        return _demo(Path(a.out_dir))
    if a.command == "meta":
        out = Path(a.out_dir)
        syn = P.run_meta_only(a.extraction, out, a.effect, a.model, a.tau2, a.hksj)
        _print_review({"synthesis": syn, "template": a.extraction})
        console.print(f"[green]Results in {out / 'meta'}")
        P.write_manifest(out, a.command, vars(a))
        return 0

    settings = _settings(a)
    query = _query(a)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    console.print(Panel.fit(f"[bold]{query}", title=f"UREME {__version__} — {a.command}"))
    this_year = dt.date.today().year
    min_year, max_year = a.min_year, a.max_year
    if a.command == "gaps" and min_year is None:
        min_year, max_year = this_year - a.years, max_year or this_year
    bundle = P.acquire(query, a.databases.split(","), settings, out, a.max_results, min_year, max_year,
                       a.records_in, _progress)
    _print_search(bundle)
    if a.command == "search":
        console.print(f"[green]Saved {out / 'search' / 'records_raw.json'}")
    elif a.command == "gaps":
        run = P.run_gaps(query, bundle, out, settings, a.years, a.top, _pico(a), a.full_text_limit, a.citations,
                         progress=_progress)
        _print_gaps(run)
    else:
        from ureme.review.screening import Criteria
        criteria = Criteria.load(a.criteria)
        gap_summary = None
        if a.command == "combined":
            gap_run = P.run_gaps(query, bundle, out, settings, a.years, a.top, _pico(a), a.full_text_limit,
                                 a.citations, progress=_progress)
            _print_gaps(gap_run)
            gap_summary = P.gap_summary_for_manuscript(gap_run)
        run = P.run_review(query, criteria, bundle, out, settings, a.extraction, a.overrides, a.effect, a.model,
                           a.tau2, a.hksj, a.review_full_text_limit, gap_summary, progress=_progress)
        _print_review(run)
        if a.command == "combined" and run["synthesis"] and run["synthesis"]["outcomes"]:
            # refresh the gap report with the quantitative context
            ctx = "; ".join(f"{n}: {o['text']}" for n, o in run["synthesis"]["outcomes"].items())
            P.run_gaps(query, bundle, out, Settings.from_env(fetch_full_text=False), a.years, a.top, _pico(a), 0,
                       False, {"summary": ctx})
    P.write_manifest(out, a.command, vars(a))
    console.print(f"[bold green]Done. Outputs in {out.resolve()}")
    return 0


def _demo(out: Path) -> int:
    from ureme import pipeline as P
    from ureme.demo import DEMO_QUERY, demo_bundle, fill_demo_extraction, write_demo_inputs
    from ureme.review.screening import Criteria

    console.print(Panel.fit("Offline demonstration on SYNTHETIC data (no network required)", title="UREME demo"))
    inputs = write_demo_inputs(out / "inputs")
    settings = Settings(fetch_full_text=False)
    bundle = demo_bundle()
    P.write_json(out / "search" / "records_raw.json", bundle.to_dict())
    _print_search(bundle)
    gap_run = P.run_gaps(DEMO_QUERY, bundle, out, settings, years=5, top_n=5, synthetic=True, progress=_progress)
    _print_gaps(gap_run)
    criteria = Criteria.load(inputs["criteria"])
    first = P.run_review(DEMO_QUERY, criteria, bundle, out, settings, synthetic=True, progress=_progress)
    extraction = fill_demo_extraction(first["template"], out / "inputs" / "demo_extraction_completed.csv")
    run = P.run_review(DEMO_QUERY, criteria, bundle, out, settings, extraction=str(extraction),
                       gap_summary=P.gap_summary_for_manuscript(gap_run), synthetic=True, progress=_progress)
    _print_review(run)
    P.write_manifest(out, "demo", {"out_dir": str(out)})
    console.print(f"[bold green]Demo complete. Open {out / 'PRISMA_Manuscript.docx'} and "
                  f"{out / 'Research_Gap_Proposal.docx'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
