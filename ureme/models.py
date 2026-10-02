"""Core data structures shared by every module."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any


@dataclass
class Record:
    """A bibliographic record harmonised across databases."""

    title: str
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    journal: str = ""
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    s2_id: str | None = None
    epmc_id: str | None = None
    publication_types: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    language: str | None = None
    is_open_access: bool = False
    full_text_url: str | None = None
    full_text: str | None = None
    citation_count: int | None = None
    references: list[str] = field(default_factory=list)
    cited_by: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    record_id: str = ""

    def __post_init__(self) -> None:
        if self.doi:
            self.doi = normalize_doi(self.doi)
        if not self.record_id:
            self.record_id = self.make_id()

    def make_id(self) -> str:
        if self.doi:
            return f"doi:{self.doi}"
        if self.pmid:
            return f"pmid:{self.pmid}"
        if self.pmcid:
            return f"pmcid:{self.pmcid}"
        if self.s2_id:
            return f"s2:{self.s2_id}"
        if self.epmc_id:
            return f"epmc:{self.epmc_id}"
        digest = hashlib.sha1(f"{self.title}|{self.year}".encode()).hexdigest()[:12]
        return f"title:{digest}"

    @property
    def first_author(self) -> str:
        return self.authors[0] if self.authors else ""

    @property
    def text(self) -> str:
        """Title + abstract, the default text used for screening and mining."""
        return f"{self.title}. {self.abstract}".strip()

    @property
    def best_text(self) -> str:
        """Full text when available, otherwise title + abstract."""
        return self.full_text or self.text

    def short_label(self) -> str:
        surname = self.first_author.split(" ")[0] if self.first_author else "Anon"
        return f"{surname} {self.year or 'n.d.'}"

    def citation(self) -> str:
        """Vancouver-style citation string."""
        if len(self.authors) > 6:
            auth = ", ".join(self.authors[:6]) + ", et al"
        else:
            auth = ", ".join(self.authors) or "Anonymous"
        parts = [f"{auth}.", f"{self.title.rstrip('.')}."]
        if self.journal:
            parts.append(f"{self.journal}.")
        if self.year:
            parts.append(f"{self.year}.")
        if self.doi:
            parts.append(f"doi:{self.doi}")
        elif self.pmid:
            parts.append(f"PMID:{self.pmid}")
        return " ".join(parts)

    def to_dict(self, include_full_text: bool = True) -> dict[str, Any]:
        d = asdict(self)
        if not include_full_text:
            d["full_text"] = None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Record":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def normalize_doi(doi: str) -> str:
    doi = doi.strip().lower()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    return doi.rstrip(".")


@dataclass
class SearchLogEntry:
    """One database query, kept for PRISMA-S style reporting."""

    database: str
    query: str
    date: str
    total_hits: int = 0
    retrieved: int = 0
    filters: str = ""
    error: str | None = None


@dataclass
class SearchBundle:
    records_by_db: dict[str, list[Record]] = field(default_factory=dict)
    log: list[SearchLogEntry] = field(default_factory=list)

    @property
    def all_records(self) -> list[Record]:
        out: list[Record] = []
        for recs in self.records_by_db.values():
            out.extend(recs)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "records_by_db": {db: [r.to_dict() for r in recs] for db, recs in self.records_by_db.items()},
            "log": [asdict(e) for e in self.log],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SearchBundle":
        return cls(
            records_by_db={db: [Record.from_dict(r) for r in recs] for db, recs in d.get("records_by_db", {}).items()},
            log=[SearchLogEntry(**e) for e in d.get("log", [])],
        )
