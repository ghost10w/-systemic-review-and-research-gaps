"""Data extraction: auto-suggested outcome numbers + a CSV extraction sheet.

Workflow
--------
1. ``build_extraction_template`` writes one row per included study (x outcome)
   with auto-detected candidate numbers in ``auto_candidates`` and suggested
   risk-of-bias judgements pre-filled.
2. A reviewer (human or agent) verifies/fills the numeric columns.
3. ``load_extraction`` reads the sheet back for meta-analysis.

Columns (see ``COLUMNS``): one outcome per row; dichotomous rows use
``*_events``/``*_total``; continuous rows use ``*_mean``/``*_sd``/``*_n``;
alternatively give a precomputed ``yi``/``sei`` on the analysis scale
(log scale for OR/RR).
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from ureme.meta.effect_sizes import CONTINUOUS_MEASURES, DICHOTOMOUS_MEASURES, EffectSize, compute_effect
from ureme.models import Record

ROB_DOMAIN_COLS = [f"rob_d{i}" for i in range(1, 8)]
COLUMNS = (["record_id", "study_label", "year", "include_in_meta", "outcome", "outcome_type", "measure",
            "subgroup", "design", "country", "population", "intervention", "comparator", "follow_up",
            "treat_events", "treat_total", "ctrl_events", "ctrl_total",
            "treat_mean", "treat_sd", "treat_n", "ctrl_mean", "ctrl_sd", "ctrl_n",
            "yi", "sei", "rob_tool"] + ROB_DOMAIN_COLS + ["rob_overall", "notes", "auto_candidates"])

_FRACTION = re.compile(r"\b(\d{1,6})\s*/\s*(\d{1,6})\s*\(\s*(\d{1,3}(?:\.\d+)?)\s*%\s*\)")
_EVENTS_OF = re.compile(r"\b(\d{1,6})\s+of\s+(\d{1,6})\b")
_MEAN_SD = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:±|\+/-|\+-)\s*(\d+(?:\.\d+)?)")
_MEAN_PAREN_SD = re.compile(r"\bmeans?\s*\(?(?:SD|s\.d\.)?\)?\s*(?:of|=|:)?\s*(-?\d+(?:\.\d+)?)\s*\(\s*(?:SD\s*)?(\d+(?:\.\d+)?)\s*\)", re.I)
_N = re.compile(r"\b[nN]\s*=\s*(\d{1,6})\b")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z(])", text or "") if s.strip()]


def suggest_outcome_data(text: str, max_snippets: int = 6) -> dict:
    """Heuristic number mining. Returns candidate values *with context* - always verify."""
    out = {"dichotomous": [], "continuous": [], "sample_sizes": [], "snippets": []}
    for s in _sentences(text):
        fr = [(int(a), int(b)) for a, b, _ in _FRACTION.findall(s) if int(a) <= int(b)]
        fr += [(int(a), int(b)) for a, b in _EVENTS_OF.findall(s) if int(a) <= int(b)]
        ms = [(float(m), float(sd)) for m, sd in _MEAN_SD.findall(s)] + \
             [(float(m), float(sd)) for m, sd in _MEAN_PAREN_SD.findall(s)]
        ns = [int(n) for n in _N.findall(s)]
        if fr:
            out["dichotomous"].append({"pairs": fr, "context": s[:300]})
        if ms:
            out["continuous"].append({"mean_sd": ms, "n": ns, "context": s[:300]})
        out["sample_sizes"].extend(ns)
        if (fr or ms) and len(out["snippets"]) < max_snippets:
            out["snippets"].append(s[:300])
    # Convenience pre-fill: a sentence with exactly two event fractions -> treatment vs control
    out["prefill"] = {}
    for d in out["dichotomous"]:
        if len(d["pairs"]) == 2:
            (a, n1), (c, n2) = d["pairs"]
            out["prefill"] = {"treat_events": a, "treat_total": n1, "ctrl_events": c, "ctrl_total": n2}
            break
    if not out["prefill"]:
        for d in out["continuous"]:
            if len(d["mean_sd"]) == 2 and len(d["n"]) >= 2:
                (m1, s1), (m2, s2) = d["mean_sd"]
                out["prefill"] = {"treat_mean": m1, "treat_sd": s1, "treat_n": d["n"][0],
                                  "ctrl_mean": m2, "ctrl_sd": s2, "ctrl_n": d["n"][1]}
                break
    return out


def infer_design(rec: Record) -> str:
    text = (rec.text + " " + " ".join(rec.publication_types)).lower()
    if re.search(r"randomi[sz]ed|randomly (assigned|allocated)|\brct\b", text) and "non-randomi" not in text:
        return "RCT"
    if re.search(r"cohort|case[- ]control|cross[- ]sectional|observational|registry|retrospective|prospective", text):
        return "NRSI"
    return "Unclear"


@dataclass
class StudyOutcome:
    record_id: str
    study_label: str
    outcome: str
    outcome_type: str
    measure: str | None
    data: dict
    subgroup: str = ""
    design: str = ""
    year: int | None = None
    rob_tool: str = ""
    rob_domains: dict = field(default_factory=dict)
    rob_overall: str = ""
    include: bool = True
    extra: dict = field(default_factory=dict)

    def effect(self, measure: str) -> EffectSize | None:
        if self.data.get("yi") is not None and self.data.get("sei") is not None:
            return EffectSize(float(self.data["yi"]), float(self.data["sei"]) ** 2, measure.upper())
        return compute_effect(measure, **self.data)

    def has_data_for(self, measure: str) -> bool:
        m = measure.upper()
        if self.data.get("yi") is not None and self.data.get("sei") is not None:
            return True
        keys = (["treat_events", "treat_total", "ctrl_events", "ctrl_total"] if m in DICHOTOMOUS_MEASURES
                else ["treat_mean", "treat_sd", "treat_n", "ctrl_mean", "ctrl_sd", "ctrl_n"])
        return all(self.data.get(k) is not None for k in keys)


def build_extraction_template(records: list[Record], path: str | Path, outcomes: list[str] | None = None,
                              rob_suggestions: dict[str, dict] | None = None, measure: str | None = None) -> Path:
    from ureme.review.rob import ROB2_DOMAINS, ROBINS_I_DOMAINS

    outcomes = outcomes or ["Primary outcome"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in records:
            sugg = suggest_outcome_data(r.best_text)
            design = infer_design(r)
            rob = (rob_suggestions or {}).get(r.record_id, {})
            tool = rob.get("tool", "RoB2" if design == "RCT" else "ROBINS-I")
            domains = ROB2_DOMAINS if tool == "RoB2" else ROBINS_I_DOMAINS
            otype = ""
            if measure:
                otype = "dichotomous" if measure.upper() in DICHOTOMOUS_MEASURES else "continuous"
            for oc in outcomes:
                row = {c: "" for c in COLUMNS}
                row.update(record_id=r.record_id, study_label=r.short_label(), year=r.year or "",
                           include_in_meta="yes", outcome=oc, outcome_type=otype, measure=measure or "",
                           design=design, rob_tool=tool, rob_overall=rob.get("overall", ""),
                           auto_candidates=" || ".join(sugg["snippets"]))
                for k, v in sugg["prefill"].items():
                    if not otype or (otype == "dichotomous") == k.endswith(("events", "total")):
                        row[k] = v
                for i, d in enumerate(domains, start=1):
                    row[f"rob_d{i}"] = rob.get("domains", {}).get(d, {}).get("judgement", "")
                w.writerow(row)
    return path


def _num(v: str | None) -> float | None:
    if v is None:
        return None
    v = str(v).strip().replace(",", "")
    if v == "" or v.lower() in {"na", "nr", "n/a", "none", "-"}:
        return None
    x = float(v)
    return None if math.isnan(x) else x


def load_extraction(path: str | Path) -> list[StudyOutcome]:
    from ureme.review.rob import ROB2_DOMAINS, ROBINS_I_DOMAINS

    rows = []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if not (row.get("record_id") or row.get("study_label")):
                continue
            data = {k: _num(row.get(k)) for k in ("treat_events", "treat_total", "ctrl_events", "ctrl_total",
                                                  "treat_mean", "treat_sd", "treat_n", "ctrl_mean", "ctrl_sd",
                                                  "ctrl_n", "yi", "sei")}
            otype = (row.get("outcome_type") or "").strip().lower()
            if not otype:
                otype = "dichotomous" if data["treat_events"] is not None else (
                    "continuous" if data["treat_mean"] is not None else "generic")
            tool = (row.get("rob_tool") or "").strip()
            names = ROB2_DOMAINS if tool.lower().replace(" ", "") in {"rob2", "rob-2"} else ROBINS_I_DOMAINS
            domains = {names[i - 1]: row.get(f"rob_d{i}", "").strip() for i in range(1, len(names) + 1)
                       if row.get(f"rob_d{i}", "").strip()}
            year = _num(row.get("year"))
            rows.append(StudyOutcome(
                record_id=row.get("record_id", "").strip() or row["study_label"],
                study_label=row.get("study_label", "").strip() or row["record_id"],
                outcome=row.get("outcome", "").strip() or "Primary outcome",
                outcome_type=otype,
                measure=(row.get("measure") or "").strip().upper() or None,
                data=data,
                subgroup=(row.get("subgroup") or "").strip(),
                design=(row.get("design") or "").strip(),
                year=int(year) if year else None,
                rob_tool=tool,
                rob_domains=domains,
                rob_overall=(row.get("rob_overall") or "").strip(),
                include=(row.get("include_in_meta") or "yes").strip().lower() not in {"no", "n", "false", "0"},
                extra={k: row.get(k, "") for k in ("country", "population", "intervention", "comparator",
                                                   "follow_up", "notes")},
            ))
    return rows


def default_measure(outcome_type: str) -> str:
    return "OR" if outcome_type == "dichotomous" else "SMD"


__all__ = ["COLUMNS", "StudyOutcome", "build_extraction_template", "load_extraction", "suggest_outcome_data",
           "infer_design", "default_measure", "CONTINUOUS_MEASURES"]
