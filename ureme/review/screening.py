"""Rule-based screening with reason-coded exclusions (PRISMA 2020 items 8 & 16).

Two stages:
  * ``title_abstract`` - year, language, publication type, abstract presence,
    exclusion terms, required concept groups, study design.
  * ``eligibility``    - full text (when retrieved) re-checked against the
    same concepts plus full-text-only rules (minimum sample size, outcome data).

Human / agent adjudication is supported through an overrides JSON file.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ureme.models import Record

TITLE_ABSTRACT = "title_abstract"
ELIGIBILITY = "eligibility"

DEFAULT_EXCLUDED_PUB_TYPES = ["Review", "Systematic Review", "Meta-Analysis", "Editorial", "Comment", "Letter",
                              "Case Reports", "News", "Published Erratum", "Retracted Publication"]


# A record tagged with one of these is kept even if it also carries an excluded tag
# (e.g. a trial labelled both "Randomized Controlled Trial" and "Comment").
PRIMARY_STUDY_TYPES = {"randomized controlled trial", "clinical trial", "controlled clinical trial",
                       "pragmatic clinical trial", "observational study", "multicenter study"}




def _norm_pt(pt: str) -> str:
    """Normalise publication-type labels across databases ("Case Reports" == S2 "CaseReport")."""
    return re.sub(r"[^a-z]", "", pt.lower()).rstrip("s")


_PRIMARY = {_norm_pt(t) for t in PRIMARY_STUDY_TYPES}


@dataclass
class Criteria:
    title: str = ""
    question: str = ""
    pico: dict = field(default_factory=dict)
    year_min: int | None = None
    year_max: int | None = None
    languages: list[str] = field(default_factory=list)
    require_abstract: bool = True
    exclude_publication_types: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDED_PUB_TYPES))
    include_concepts: dict[str, list[str]] = field(default_factory=dict)  # label -> any-of terms (AND across labels)
    exclude_terms: dict[str, list[str]] = field(default_factory=dict)     # reason -> any-of terms
    study_design_terms: list[str] = field(default_factory=list)
    study_design_label: str = "Ineligible study design"
    min_sample_size: int | None = None
    full_text_required_terms: dict[str, list[str]] = field(default_factory=dict)  # reason -> any-of terms
    full_text_policy: str = "abstract_fallback"  # or "strict"
    outcomes: list[str] = field(default_factory=list)
    effect_measure: str | None = None  # OR | RR | RD | SMD | MD

    @classmethod
    def from_dict(cls, d: dict) -> "Criteria":
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(d) - known - {"_comment", "comment", "notes"}
        if unknown:
            raise ValueError(f"Unknown criteria keys: {sorted(unknown)}")
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def load(cls, path: str | Path) -> "Criteria":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Decision:
    record_id: str
    stage: str
    included: bool
    reason: str | None = None
    detail: str = ""
    source: str = "auto"  # auto | override


def term_regex(term: str) -> re.Pattern:
    """Whole-word, case-insensitive pattern; trailing * is a wildcard (e.g. randomi*)."""
    t = term.strip()
    wildcard = t.endswith("*")
    body = re.escape(t.rstrip("*")).replace(r"\ ", r"[\s\-]+")
    tail = r"[\w-]*" if wildcard else ""
    return re.compile(r"(?<![\w])" + body + tail + r"(?![\w])", re.I)


def find_terms(text: str, terms: list[str]) -> list[str]:
    return [t for t in terms if term_regex(t).search(text or "")]


_LANG = {"en": "eng", "english": "eng", "eng": "eng", "fr": "fre", "french": "fre", "fre": "fre", "de": "ger",
         "german": "ger", "ger": "ger", "es": "spa", "spanish": "spa", "spa": "spa", "zh": "chi", "chinese": "chi",
         "chi": "chi", "ar": "ara", "arabic": "ara", "ara": "ara"}


def _lang(code: str | None) -> str | None:
    return _LANG.get(code.lower(), code.lower()) if code else None


_SAMPLE = re.compile(r"(?:\b[Nn]\s*=\s*(\d{1,6})\b|\b(\d{1,6})\s+(?:patients|participants|subjects|individuals|adults|"
                     r"children|women|men|people)\s+(?:were\s+)?(?:randomi[sz]ed|enrolled|included|recruited|allocated))")


def detect_sample_size(text: str) -> int | None:
    nums = [int(a or b) for a, b in _SAMPLE.findall(text or "")]
    return max(nums) if nums else None


def _concept_checks(text: str, c: Criteria) -> tuple[str, str] | None:
    for reason, terms in c.exclude_terms.items():
        hit = find_terms(text, terms)
        if hit:
            return reason, f"matched exclusion term(s): {', '.join(hit[:3])}"
    for label, terms in c.include_concepts.items():
        if terms and not find_terms(text, terms):
            return f"{label} criterion not met", f"none of: {', '.join(terms[:5])}"
    if c.study_design_terms and not find_terms(text, c.study_design_terms):
        return c.study_design_label, f"no design term among: {', '.join(c.study_design_terms[:5])}"
    return None


def screen_title_abstract(records: list[Record], c: Criteria) -> list[Decision]:
    out = []
    excluded_types = {_norm_pt(t) for t in c.exclude_publication_types}
    langs = {_lang(l) for l in c.languages}
    for r in records:
        reason, detail = None, ""
        if c.year_min and r.year and r.year < c.year_min:
            reason, detail = "Outside publication date range", f"year {r.year} < {c.year_min}"
        elif c.year_max and r.year and r.year > c.year_max:
            reason, detail = "Outside publication date range", f"year {r.year} > {c.year_max}"
        elif langs and r.language and _lang(r.language) not in langs:
            reason, detail = "Language not eligible", f"language {r.language}"
        elif (any(_norm_pt(pt) in excluded_types for pt in r.publication_types)
              and not any(_norm_pt(pt) in _PRIMARY for pt in r.publication_types)):
            hit = [pt for pt in r.publication_types if _norm_pt(pt) in excluded_types]
            reason, detail = "Ineligible publication type", ", ".join(hit)
        elif c.require_abstract and not (r.abstract or "").strip():
            reason, detail = "No abstract available", ""
        else:
            res = _concept_checks(r.text, c)
            if res:
                reason, detail = res
        out.append(Decision(r.record_id, TITLE_ABSTRACT, reason is None, reason, detail))
    return out


def assess_eligibility(records: list[Record], c: Criteria) -> tuple[list[Decision], list[str]]:
    """Returns (decisions for assessed reports, record_ids not retrieved)."""
    decisions, not_retrieved = [], []
    for r in records:
        if not r.full_text:
            if c.full_text_policy == "strict":
                not_retrieved.append(r.record_id)
                continue
        text = r.best_text
        basis = "full text" if r.full_text else "abstract (full text not openly available)"
        reason, detail = None, ""
        res = _concept_checks(text, c)
        if res:
            reason, detail = res
        if not reason:
            for why, terms in c.full_text_required_terms.items():
                if terms and not find_terms(text, terms):
                    reason, detail = why, f"none of: {', '.join(terms[:5])}"
                    break
        if not reason and c.min_sample_size:
            n = detect_sample_size(text)
            if n is not None and n < c.min_sample_size:
                reason, detail = f"Sample size below {c.min_sample_size}", f"detected N = {n}"
        decisions.append(Decision(r.record_id, ELIGIBILITY, reason is None, reason, f"{detail} [{basis}]".strip()))
    return decisions, not_retrieved


def load_overrides(path: str | Path | None) -> dict[str, dict]:
    """``{record_id: {"stage": "title_abstract"|"eligibility", "decision": "include"|"exclude", "reason": "..."}}``"""
    if not path or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def apply_overrides(decisions: list[Decision], overrides: dict[str, dict], stage: str) -> list[Decision]:
    out = []
    for d in decisions:
        o = overrides.get(d.record_id)
        if o and o.get("stage", stage) == stage:
            inc = str(o.get("decision", "")).lower().startswith("incl")
            d = Decision(d.record_id, stage, inc, None if inc else (o.get("reason") or "Excluded by reviewer"),
                         o.get("note", "manual adjudication"), "override")
        out.append(d)
    return out
