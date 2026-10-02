"""Europe PMC REST client.  Docs: https://europepmc.org/RestfulWebService"""

from __future__ import annotations

from ureme.apis.http import HttpClient, HttpError
from ureme.apis.text import jats_body_text, strip_tags
from ureme.models import Record

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/"


class EuropePMCClient:
    name = "Europe PMC"

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient(min_interval=0.2)

    def search(self, query: str, max_results: int = 200, min_year: int | None = None,
               max_year: int | None = None) -> tuple[int, list[Record]]:
        q = query
        if min_year or max_year:
            q = f"({query}) AND (PUB_YEAR:[{min_year or 1800} TO {max_year or 3000}])"
        cursor, total, records = "*", 0, []
        while len(records) < max_results:
            data = self.http.get_json(BASE + "search", {
                "query": q, "format": "json", "resultType": "core",
                "pageSize": min(1000, max_results - len(records)), "cursorMark": cursor,
            })
            total = int(data.get("hitCount", 0))
            page = data.get("resultList", {}).get("result", [])
            records.extend(parse_epmc_result(r) for r in page)
            nxt = data.get("nextCursorMark")
            if not page or not nxt or nxt == cursor:
                break
            cursor = nxt
        return total, records[:max_results]

    def fetch_full_text(self, pmcid: str) -> str | None:
        try:
            return jats_body_text(self.http.get_text(f"{BASE}{pmcid.upper()}/fullTextXML"))
        except HttpError:
            return None

    def citations(self, source: str, ext_id: str) -> dict[str, list[str]]:
        out = {"cited_by": [], "references": []}
        for key, endpoint, list_key, item_key in (
            ("cited_by", "citations", "citationList", "citation"),
            ("references", "references", "referenceList", "reference"),
        ):
            try:
                data = self.http.get_json(f"{BASE}{source}/{ext_id}/{endpoint}", {"format": "json", "pageSize": 1000})
            except HttpError:
                continue
            for item in data.get(list_key, {}).get(item_key, []) or []:
                if item.get("id"):
                    prefix = "pmid" if item.get("source") == "MED" else "epmc"
                    out[key].append(f"{prefix}:{item['id']}")
        return out


def parse_epmc_result(r: dict) -> Record:
    authors = [a.get("fullName", "") for a in (r.get("authorList", {}) or {}).get("author", []) if a.get("fullName")]
    if not authors and r.get("authorString"):
        authors = [a.strip() for a in r["authorString"].rstrip(".").split(",") if a.strip()]
    journal = ((r.get("journalInfo") or {}).get("journal") or {}).get("title") or r.get("journalTitle", "")
    year = r.get("pubYear")
    oa_url = None
    for u in (r.get("fullTextUrlList") or {}).get("fullTextUrl", []) or []:
        if u.get("availabilityCode") == "OA":
            oa_url = u.get("url")
            break
    return Record(
        title=strip_tags(r.get("title", "")),
        abstract=strip_tags(r.get("abstractText", "")),
        authors=authors,
        year=int(year) if year and str(year).isdigit() else None,
        journal=journal,
        doi=r.get("doi"),
        pmid=r.get("pmid"),
        pmcid=r.get("pmcid"),
        epmc_id=f"{r.get('source', '')}:{r.get('id', '')}" if r.get("id") else None,
        publication_types=list((r.get("pubTypeList") or {}).get("pubType", []) or []),
        mesh_terms=[m.get("descriptorName", "") for m in (r.get("meshHeadingList") or {}).get("meshHeading", []) or []],
        keywords=list((r.get("keywordList") or {}).get("keyword", []) or []),
        language=r.get("language"),
        is_open_access=r.get("isOpenAccess") == "Y",
        full_text_url=oa_url,
        citation_count=r.get("citedByCount"),
        sources=["Europe PMC"],
    )
