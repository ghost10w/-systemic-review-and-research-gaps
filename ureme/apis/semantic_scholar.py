"""Semantic Scholar Academic Graph API client.

Docs: https://api.semanticscholar.org/api-docs/graph
Boolean queries use the bulk endpoint (``+`` AND, ``|`` OR, ``-`` NOT);
plain queries use relevance-ranked search.  Set ``S2_API_KEY`` for higher limits.
"""

from __future__ import annotations

from ureme.apis.http import HttpClient, HttpError
from ureme.apis.query import is_boolean, to_plain_terms, to_semantic_scholar
from ureme.models import Record

BASE = "https://api.semanticscholar.org/graph/v1/"
FIELDS = ("paperId,externalIds,title,abstract,year,venue,authors,citationCount,"
          "isOpenAccess,openAccessPdf,publicationTypes,journal")
GRAPH_FIELDS = "paperId,externalIds,title,year"


class SemanticScholarClient:
    name = "Semantic Scholar"

    def __init__(self, http: HttpClient | None = None, api_key: str | None = None):
        headers = {"x-api-key": api_key} if api_key else None
        self.http = http or HttpClient(min_interval=1.05, headers=headers)
        if http and api_key:
            self.http.session.headers["x-api-key"] = api_key

    def search(self, query: str, max_results: int = 200, min_year: int | None = None,
               max_year: int | None = None) -> tuple[int, list[Record]]:
        year = f"{min_year or ''}-{max_year or ''}" if (min_year or max_year) else None
        records: list[Record] = []
        total = 0
        if is_boolean(query):
            params = {"query": to_semantic_scholar(query), "fields": FIELDS}
            if year:
                params["year"] = year
            while len(records) < max_results:
                data = self.http.get_json(BASE + "paper/search/bulk", params)
                total = int(data.get("total", 0))
                records.extend(parse_s2_paper(p) for p in data.get("data", []) or [])
                if not data.get("token"):
                    break
                params["token"] = data["token"]
        else:
            offset = 0
            while len(records) < max_results and offset < 1000:
                limit = min(100, max_results - len(records))
                params = {"query": to_plain_terms(query), "fields": FIELDS, "offset": offset, "limit": limit}
                if year:
                    params["year"] = year
                data = self.http.get_json(BASE + "paper/search", params)
                total = int(data.get("total", 0))
                page = data.get("data", []) or []
                records.extend(parse_s2_paper(p) for p in page)
                if len(page) < limit:
                    break
                offset += limit
        return total, records[:max_results]

    def citations(self, paper_id: str) -> dict[str, list[str]]:
        out = {"cited_by": [], "references": []}
        for key, endpoint, inner in (("cited_by", "citations", "citingPaper"), ("references", "references", "citedPaper")):
            try:
                data = self.http.get_json(f"{BASE}paper/{paper_id}/{endpoint}", {"fields": GRAPH_FIELDS, "limit": 1000})
            except HttpError:
                continue
            for item in data.get("data", []) or []:
                p = item.get(inner) or {}
                ext = p.get("externalIds") or {}
                if ext.get("DOI"):
                    out[key].append(f"doi:{ext['DOI'].lower()}")
                elif p.get("paperId"):
                    out[key].append(f"s2:{p['paperId']}")
        return out


def parse_s2_paper(p: dict) -> Record:
    ext = p.get("externalIds") or {}
    pmc = ext.get("PubMedCentral")
    return Record(
        title=p.get("title") or "",
        abstract=p.get("abstract") or "",
        authors=[a.get("name", "") for a in p.get("authors") or [] if a.get("name")],
        year=p.get("year"),
        journal=((p.get("journal") or {}).get("name")) or p.get("venue") or "",
        doi=ext.get("DOI"),
        pmid=str(ext["PubMed"]) if ext.get("PubMed") else None,
        pmcid=f"PMC{pmc}" if pmc and not str(pmc).startswith("PMC") else pmc,
        s2_id=p.get("paperId"),
        publication_types=list(p.get("publicationTypes") or []),
        is_open_access=bool(p.get("isOpenAccess")),
        full_text_url=(p.get("openAccessPdf") or {}).get("url"),
        citation_count=p.get("citationCount"),
        sources=["Semantic Scholar"],
    )
