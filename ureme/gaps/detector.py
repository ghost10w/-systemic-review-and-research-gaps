"""Gap detection from titles/abstracts/full text of recent literature.

Pipeline: sentence split -> gap-marker detection -> category classification
(Methodological, Population, Mechanistic, Knowledge/Evidence) -> theme
clustering -> conflicting-evidence detection -> ranked ``Gap`` objects.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field

from ureme.gaps.lexicon import CATEGORY_LEXICON, GAP_MARKERS, NULL_FINDING, POSITIVE_FINDING, STOPWORDS
from ureme.models import Record

CATEGORIES = list(CATEGORY_LEXICON)
_MARKERS = [re.compile(p, re.I) for p in GAP_MARKERS]
_CAT = {c: [re.compile(p, re.I) for p in pats] for c, pats in CATEGORY_LEXICON.items()}
_POS = [re.compile(p, re.I) for p in POSITIVE_FINDING]
_NULL = [re.compile(p, re.I) for p in NULL_FINDING]


@dataclass
class GapStatement:
    record_id: str
    sentence: str
    markers: list[str]
    category: str
    category_scores: dict[str, int]
    year: int | None = None
    citations: int = 0


@dataclass
class Gap:
    gap_id: str
    category: str
    theme: str
    description: str
    score: float
    n_records: int
    evidence: list[dict] = field(default_factory=list)  # {record_id, sentence, year}
    subtype: str = "limitation"                         # limitation | conflicting evidence
    record_ids: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "")
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])", text)
    return [p.strip() for p in parts if len(p.strip()) > 25]


def classify_sentence(sentence: str) -> tuple[str, dict[str, int]]:
    scores = {c: sum(bool(p.search(sentence)) for p in pats) for c, pats in _CAT.items()}
    best = max(scores.items(), key=lambda kv: (kv[1], kv[0] == "Knowledge/Evidence"))
    return (best[0] if best[1] > 0 else "Knowledge/Evidence"), scores


def detect_gap_statements(records: list[Record], use_full_text: bool = True) -> list[GapStatement]:
    out = []
    for r in records:
        text = r.best_text if use_full_text else r.text
        seen = set()
        for s in split_sentences(text):
            markers = [m.group(0) for m in (p.search(s) for p in _MARKERS) if m]
            cat, scores = classify_sentence(s)
            strong_method = scores.get("Methodological", 0) >= 2 and re.search(r"\b(limit|small|short|only|lack)", s, re.I)
            if not markers and not strong_method:
                continue
            key = s.lower()[:120]
            if key in seen:
                continue
            seen.add(key)
            out.append(GapStatement(r.record_id, s, markers, cat, scores, r.year, r.citation_count or 0))
    return out


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z\-]{2,}", text.lower()) if t not in STOPWORDS]


def _phrases(text: str, exclude: set[str]) -> set[str]:
    toks = [t for t in _tokens(text) if t not in exclude]
    out = set(toks)
    words = re.findall(r"[a-z][a-z\-]{2,}", text.lower())
    for a, b in zip(words, words[1:]):
        if a not in STOPWORDS and b not in STOPWORDS and a not in exclude and b not in exclude:
            out.add(f"{a} {b}")
    return out


_VERBS = {"is", "are", "was", "were", "be", "been", "being", "has", "have", "had", "may", "might", "should",
          "could", "would", "will", "can", "did", "does", "do", "remain", "remains", "remained"}


def expand_theme(theme: str, sentences: list[str]) -> str:
    """Grow a key phrase into its most common 2-4 word context (e.g. 'inflammatory' -> 'inflammatory pathways')."""
    if theme.startswith("("):
        return theme
    counts: Counter = Counter()
    tw = theme.split()
    for s in sentences:
        words = re.findall(r"[a-z][a-z0-9\-]*", s.lower())
        for n in range(len(tw) + 1, min(len(tw) + 3, 5)):
            for i in range(len(words) - n + 1):
                gram = words[i : i + n]
                if any(gram[j : j + len(tw)] == tw for j in range(n - len(tw) + 1)) and \
                        gram[0] not in STOPWORDS and gram[-1] not in STOPWORDS and not _VERBS & set(gram):
                    counts[" ".join(gram)] += 1
    if not counts:
        return theme
    # prefer the most frequent context; on ties prefer forward expansion ("inflammatory pathways")
    # over phrases that end on the theme word ("role of inflammatory")
    best, c = max(counts.items(), key=lambda kv: (kv[1], kv[0].startswith(theme), -len(kv[0])))
    return best if c >= 1 and len(best) <= 45 else theme


def finding_direction(record: Record) -> str | None:
    """Classify the record's main finding as 'positive', 'null' or None from results/conclusion sentences."""
    sents = split_sentences(record.abstract or "")
    concl = [s for s in sents if re.match(r"(conclusions?|results?|findings?|interpretation)\s*:", s, re.I)] or sents[-3:]
    # a sentence with negated language ("did not significantly reduce") is null even though it
    # also contains positive wording, so null takes precedence within a sentence
    nul_s = [any(p.search(s) for p in _NULL) for s in concl]
    nul = sum(nul_s)
    pos = sum(any(p.search(s) for p in _POS) and not n for s, n in zip(concl, nul_s))
    if pos > nul:
        return "positive"
    if nul > pos:
        return "null"
    return None


def detect_conflicts(records: list[Record], exclude_terms: set[str], min_each: int = 2, top_terms: int = 40) -> list[Gap]:
    directions = {r.record_id: finding_direction(r) for r in records}
    term_records: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        for t in _phrases(r.title + " " + " ".join(r.keywords) + " " + " ".join(r.mesh_terms), exclude_terms):
            term_records[t].append(r)
    candidates = sorted(term_records.items(), key=lambda kv: -len(kv[1]))[:top_terms]
    gaps, used = [], set()
    for term, recs in candidates:
        pos = [r for r in recs if directions[r.record_id] == "positive"]
        nul = [r for r in recs if directions[r.record_id] == "null"]
        if len(pos) < min_each or len(nul) < min_each:
            continue
        key = frozenset(r.record_id for r in pos + nul)
        if key in used:
            continue
        used.add(key)
        balance = min(len(pos), len(nul)) / (len(pos) + len(nul))
        ev = [{"record_id": r.record_id, "sentence": _conclusion(r), "year": r.year, "direction": d}
              for d, rs in (("positive", pos), ("null", nul)) for r in rs[:3]]
        gaps.append(Gap(
            gap_id="", category="Knowledge/Evidence", theme=term, subtype="conflicting evidence",
            description=(f"Conflicting evidence on '{term}': {len(pos)} studies report a significant effect or "
                         f"association while {len(nul)} report null findings. A definitive, adequately powered study "
                         f"or a quantitative synthesis could resolve this inconsistency."),
            score=round((len(pos) + len(nul)) * (0.5 + balance), 2), n_records=len(pos) + len(nul), evidence=ev,
            record_ids=[r.record_id for r in pos + nul], details={"positive": len(pos), "null": len(nul)},
        ))
    return gaps


def _conclusion(r: Record) -> str:
    sents = split_sentences(r.abstract)
    return (sents[-1] if sents else r.title)[:350]


_DESCRIBE = {
    "Methodological": "Methodological limitations concerning '{theme}' recur across {n} studies, limiting confidence "
                      "in current estimates (e.g., {markers}).",
    "Population": "Evidence regarding '{theme}' is restricted to narrow populations; {n} studies flag limited "
                  "generalisability or under-represented groups.",
    "Mechanistic": "The mechanisms underlying '{theme}' remain insufficiently characterised; {n} studies call for "
                   "mechanistic or causal investigation.",
    "Knowledge/Evidence": "Key questions about '{theme}' remain unanswered; {n} studies explicitly report missing or "
                          "insufficient evidence.",
}


def cluster_gaps(statements: list[GapStatement], exclude_terms: set[str], current_year: int | None = None,
                 min_records: int = 1) -> list[Gap]:
    current_year = current_year or dt.date.today().year
    gaps: list[Gap] = []
    for cat in CATEGORIES:
        sts = [s for s in statements if s.category == cat]
        if not sts:
            continue
        phrase_sets = [_phrases(s.sentence, exclude_terms) for s in sts]
        # document frequency counted over distinct records
        df: Counter = Counter()
        for s, ph in zip(sts, phrase_sets):
            for p in ph:
                df[(p, s.record_id)] = 1
        freq = Counter(p for (p, _rid) in df)
        clusters: dict[str, list[GapStatement]] = defaultdict(list)
        for s, ph in zip(sts, phrase_sets):
            if not ph:
                clusters["(general)"].append(s)
                continue
            best = max(ph, key=lambda p: (freq[p], " " in p, len(p)))
            clusters[best if freq[best] > 1 else "(general)"].append(s)
        for theme, members in clusters.items():
            rids = list(dict.fromkeys(m.record_id for m in members))
            if len(rids) < min_records:
                continue
            recency = sum(1.0 / (1 + max(0, current_year - (m.year or current_year - 3))) for m in members) / len(members)
            cites = sum(m.citations for m in members) / len(members)
            score = round(len(rids) * (1 + recency) + math.log1p(cites), 2)
            markers = Counter(mk.lower() for m in members for mk in m.markers).most_common(3)
            theme_txt = (expand_theme(theme, [m.sentence for m in members]) if theme != "(general)"
                         else f"{cat.lower()} issues")
            gaps.append(Gap(
                gap_id="", category=cat, theme=theme_txt,
                description=_DESCRIBE[cat].format(theme=theme_txt, n=len(rids),
                                                  markers=", ".join(m for m, _ in markers) or "explicit limitations"),
                score=score, n_records=len(rids),
                evidence=[{"record_id": m.record_id, "sentence": m.sentence[:400], "year": m.year} for m in members[:6]],
                record_ids=rids,
            ))
    return gaps


def find_gaps(records: list[Record], query_terms: list[str] | None = None, top_n: int | None = None,
              min_records: int = 1) -> dict:
    exclude = set()
    for t in query_terms or []:
        exclude.update(t.lower().split())
    statements = detect_gap_statements(records)
    gaps = cluster_gaps(statements, exclude, min_records=min_records) + detect_conflicts(records, exclude)
    gaps.sort(key=lambda g: (-g.score, g.category, g.theme))
    for i, g in enumerate(gaps, start=1):
        g.gap_id = f"G{i:02d}"
    counts = Counter(g.category for g in gaps)
    stmt_counts = Counter(s.category for s in statements)
    return {
        "n_records": len(records),
        "n_statements": len(statements),
        "statements_by_category": {c: stmt_counts.get(c, 0) for c in CATEGORIES},
        "gaps_by_category": {c: counts.get(c, 0) for c in CATEGORIES},
        "gaps": gaps[:top_n] if top_n else gaps,
        "statements": statements,
    }
