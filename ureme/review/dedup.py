"""Duplicate detection: identifiers (DOI/PMID/PMCID/S2), then title + year + first-author similarity."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ureme.models import Record, normalize_doi


def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _surname(rec: Record) -> str:
    return normalize_title(rec.first_author.split(" ")[0]) if rec.first_author else ""


@dataclass
class DedupResult:
    unique: list[Record]
    duplicates: list[dict] = field(default_factory=list)  # {removed, kept, reason}

    @property
    def n_removed(self) -> int:
        return len(self.duplicates)


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[max(ra, rb)] = min(ra, rb)
        return True


def _richness(r: Record) -> tuple:
    filled = sum(bool(getattr(r, f)) for f in ("doi", "pmid", "pmcid", "journal", "year", "authors", "mesh_terms"))
    return (bool(r.full_text), len(r.abstract or "") > 0, filled, len(r.abstract or ""))


def _merge(primary: Record, other: Record) -> None:
    for f in ("abstract", "doi", "pmid", "pmcid", "s2_id", "epmc_id", "journal", "year", "language",
              "full_text_url", "full_text", "citation_count"):
        if not getattr(primary, f) and getattr(other, f):
            setattr(primary, f, getattr(other, f))
    if other.citation_count and (primary.citation_count or 0) < other.citation_count:
        primary.citation_count = other.citation_count
    for f in ("authors", "publication_types", "mesh_terms", "keywords"):
        if not getattr(primary, f):
            setattr(primary, f, list(getattr(other, f)))
    for f in ("publication_types", "keywords", "references", "cited_by", "sources"):
        merged = list(dict.fromkeys(getattr(primary, f) + getattr(other, f)))
        setattr(primary, f, merged)
    primary.is_open_access = primary.is_open_access or other.is_open_access


def deduplicate(records: list[Record], title_threshold: float = 0.93) -> DedupResult:
    n = len(records)
    uf = _UnionFind(n)
    reasons: dict[tuple[int, int], str] = {}

    def link(i: int, j: int, why: str) -> None:
        if uf.union(i, j):
            reasons[(min(i, j), max(i, j))] = why

    # 1. Exact identifier matches
    for attr, label in (("doi", "DOI"), ("pmid", "PMID"), ("pmcid", "PMCID"), ("s2_id", "Semantic Scholar ID")):
        seen: dict[str, int] = {}
        for i, r in enumerate(records):
            val = getattr(r, attr)
            if not val:
                continue
            key = normalize_doi(val) if attr == "doi" else str(val).upper()
            if key in seen:
                link(seen[key], i, f"identical {label}")
            else:
                seen[key] = i

    # 2. Exact normalised title (+ compatible year)
    titles = [normalize_title(r.title) for r in records]
    by_title: dict[str, list[int]] = {}
    for i, t in enumerate(titles):
        if len(t) >= 20:
            by_title.setdefault(t, []).append(i)
    for idx in by_title.values():
        for j in idx[1:]:
            a, b = records[idx[0]], records[j]
            if a.year is None or b.year is None or abs(a.year - b.year) <= 1:
                link(idx[0], j, "identical normalised title")

    # 3. Fuzzy title, blocked by year (+-1), requiring compatible first author
    by_year: dict[int | None, list[int]] = {}
    for i, r in enumerate(records):
        by_year.setdefault(r.year, []).append(i)
    for year, idx in by_year.items():
        candidates = list(idx)
        if year is not None:
            candidates += by_year.get(year + 1, [])
        for ii, i in enumerate(idx):
            for j in candidates:
                if j <= i or uf.find(i) == uf.find(j) or len(titles[i]) < 20 or len(titles[j]) < 20:
                    continue
                sm = SequenceMatcher(None, titles[i], titles[j])
                if sm.real_quick_ratio() < title_threshold or sm.quick_ratio() < title_threshold:
                    continue
                ratio = sm.ratio()
                if ratio >= title_threshold:
                    sa, sb = _surname(records[i]), _surname(records[j])
                    if not sa or not sb or sa == sb:
                        link(i, j, f"title similarity {ratio:.2f}")

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    unique: list[Record] = []
    dups: list[dict] = []
    for members in groups.values():
        best = max(members, key=lambda m: _richness(records[m]))
        keep = records[best]
        for m in members:
            if m == best:
                continue
            _merge(keep, records[m])
            key = (min(m, best), max(m, best))
            why = reasons.get(key) or next((v for (a, b), v in reasons.items() if m in (a, b)), "linked duplicate")
            dups.append({"removed": records[m].record_id, "removed_source": ",".join(records[m].sources),
                         "kept": keep.record_id, "reason": why, "title": records[m].title})
        unique.append(keep)
    unique.sort(key=lambda r: records.index(r))
    return DedupResult(unique=unique, duplicates=dups)
