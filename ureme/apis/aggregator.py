"""Run one query across several databases and enrich records."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Callable

from ureme.apis.europepmc import EuropePMCClient
from ureme.apis.http import HttpClient
from ureme.apis.pubmed import PubMedClient
from ureme.apis.query import to_europepmc, to_pubmed, to_semantic_scholar
from ureme.apis.semantic_scholar import SemanticScholarClient
from ureme.config import Settings
from ureme.models import Record, SearchBundle, SearchLogEntry

log = logging.getLogger(__name__)

DATABASES = {"pubmed": "PubMed", "europepmc": "Europe PMC", "semanticscholar": "Semantic Scholar"}
_ALIASES = {"pm": "pubmed", "epmc": "europepmc", "s2": "semanticscholar", "semantic": "semanticscholar"}


def normalize_db_names(names: list[str]) -> list[str]:
    out = []
    for n in names:
        key = _ALIASES.get(n.strip().lower(), n.strip().lower().replace(" ", "").replace("_", ""))
        if key not in DATABASES:
            raise ValueError(f"Unknown database '{n}'. Choose from: {', '.join(DATABASES)} (aliases: {', '.join(_ALIASES)})")
        if key not in out:
            out.append(key)
    return out


class Clients:
    def __init__(self, settings: Settings):
        cache = settings.cache_dir
        kw = dict(cache_dir=cache, timeout=settings.timeout, max_retries=settings.max_retries)
        self.pubmed = PubMedClient(HttpClient(min_interval=0.11 if settings.ncbi_api_key else 0.34, **kw),
                                   email=settings.email, api_key=settings.ncbi_api_key)
        self.europepmc = EuropePMCClient(HttpClient(min_interval=0.2, **kw))
        s2_headers = {"x-api-key": settings.s2_api_key} if settings.s2_api_key else None
        self.semanticscholar = SemanticScholarClient(HttpClient(min_interval=1.05, headers=s2_headers, **kw))


def search_databases(query: str, databases: list[str], settings: Settings, max_per_db: int = 200,
                     min_year: int | None = None, max_year: int | None = None,
                     progress: Callable[[str], None] | None = None) -> SearchBundle:
    clients = Clients(settings)
    bundle = SearchBundle()
    translators = {"pubmed": to_pubmed, "europepmc": to_europepmc, "semanticscholar": to_semantic_scholar}
    today = dt.date.today().isoformat()
    filters = f"publication years {min_year or 'any'}-{max_year or 'any'}"
    for key in normalize_db_names(databases):
        name = DATABASES[key]
        client = getattr(clients, key)
        q = translators[key](query)
        if progress:
            progress(f"Searching {name} ...")
        entry = SearchLogEntry(database=name, query=q, date=today, filters=filters)
        try:
            total, recs = client.search(query if key != "europepmc" else q, max_per_db, min_year, max_year)
            entry.total_hits, entry.retrieved = total, len(recs)
            bundle.records_by_db[name] = recs
        except Exception as exc:  # one failing database must not sink the run
            log.error("%s search failed: %s", name, exc)
            entry.error = str(exc)
            bundle.records_by_db[name] = []
        bundle.log.append(entry)
    return bundle


def enrich_full_text(records: list[Record], settings: Settings, limit: int | None = None,
                     progress: Callable[[str], None] | None = None) -> int:
    """Fetch open-access full text (Europe PMC first, then PMC). Returns count fetched."""
    clients = Clients(settings)
    n = 0
    for rec in records:
        if limit is not None and n >= limit:
            break
        if rec.full_text or not rec.pmcid:
            continue
        if progress:
            progress(f"Full text {rec.pmcid}")
        text = clients.europepmc.fetch_full_text(rec.pmcid) or clients.pubmed.fetch_full_text(rec.pmcid)
        if text:
            rec.full_text = text
            rec.is_open_access = True
            n += 1
    return n


def enrich_citations(records: list[Record], settings: Settings, progress: Callable[[str], None] | None = None) -> None:
    """Populate ``cited_by`` / ``references`` (citation graph) for each record."""
    clients = Clients(settings)
    for rec in records:
        if progress:
            progress(f"Citations {rec.record_id}")
        if rec.s2_id or rec.doi:
            graph = clients.semanticscholar.citations(rec.s2_id or f"DOI:{rec.doi}")
        elif rec.pmid:
            graph = clients.pubmed.citations(rec.pmid)
        else:
            continue
        rec.cited_by = sorted(set(rec.cited_by) | set(graph["cited_by"]))
        rec.references = sorted(set(rec.references) | set(graph["references"]))
        if rec.citation_count is None:
            rec.citation_count = len(rec.cited_by)
