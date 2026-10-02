"""PubMed / NCBI Entrez E-utilities client.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
Without an API key NCBI allows 3 requests/s; with ``NCBI_API_KEY`` 10/s.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ureme.apis.http import HttpClient, HttpError
from ureme.apis.text import element_text, jats_body_text
from ureme.models import Record

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


class PubMedClient:
    name = "PubMed"

    def __init__(self, http: HttpClient | None = None, email: str | None = None, api_key: str | None = None):
        self.http = http or HttpClient(min_interval=0.11 if api_key else 0.34)
        self.email = email
        self.api_key = api_key

    def _params(self, **kw) -> dict:
        p = {"tool": "ureme", **kw}
        if self.email:
            p["email"] = self.email
        if self.api_key:
            p["api_key"] = self.api_key
        return p

    def search_ids(self, query: str, max_results: int = 200, min_year: int | None = None,
                   max_year: int | None = None) -> tuple[int, list[str]]:
        params = self._params(db="pubmed", term=query, retmax=min(max_results, 9999), retmode="json", sort="relevance")
        if min_year or max_year:
            params.update(datetype="pdat", mindate=str(min_year or 1800), maxdate=str(max_year or 3000))
        data = self.http.get_json(BASE + "esearch.fcgi", params)
        res = data.get("esearchresult", {})
        return int(res.get("count", 0)), list(res.get("idlist", []))

    def fetch(self, pmids: list[str], batch_size: int = 200) -> list[Record]:
        records: list[Record] = []
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i : i + batch_size]
            xml_text = self.http.post_text(BASE + "efetch.fcgi", self._params(db="pubmed", id=",".join(batch), retmode="xml"))
            records.extend(parse_pubmed_xml(xml_text))
        return records

    def search(self, query: str, max_results: int = 200, min_year: int | None = None,
               max_year: int | None = None) -> tuple[int, list[Record]]:
        total, ids = self.search_ids(query, max_results, min_year, max_year)
        return total, self.fetch(ids) if ids else []

    def fetch_full_text(self, pmcid: str) -> str | None:
        """Open-access full text from PMC (returns None for non-OA articles)."""
        num = pmcid.upper().replace("PMC", "")
        try:
            xml_text = self.http.get_text(BASE + "efetch.fcgi", self._params(db="pmc", id=num, retmode="xml"))
        except HttpError:
            return None
        return jats_body_text(xml_text)

    def citations(self, pmid: str) -> dict[str, list[str]]:
        """Citation graph: PMIDs citing this paper and PMIDs it references."""
        out = {"cited_by": [], "references": []}
        for key, linkname in (("cited_by", "pubmed_pubmed_citedin"), ("references", "pubmed_pubmed_refs")):
            try:
                data = self.http.get_json(BASE + "elink.fcgi", self._params(dbfrom="pubmed", db="pubmed", id=pmid,
                                                                             linkname=linkname, retmode="json"))
            except HttpError:
                continue
            for ls in data.get("linksets", []):
                for db in ls.get("linksetdbs", []):
                    out[key].extend(f"pmid:{x}" for x in db.get("links", []))
        return out


def _year(article: ET.Element) -> int | None:
    for path in (".//Journal/JournalIssue/PubDate/Year", ".//ArticleDate/Year", ".//Journal/JournalIssue/PubDate/MedlineDate"):
        el = article.find(path)
        if el is not None and el.text:
            m = re.search(r"(1[89]|20)\d{2}", el.text)
            if m:
                return int(m.group(0))
    return None


def parse_pubmed_xml(xml_text: str) -> list[Record]:
    root = ET.fromstring(xml_text)
    records: list[Record] = []
    for art in root.iter("PubmedArticle"):
        cit = art.find("MedlineCitation")
        if cit is None:
            continue
        a = cit.find("Article")
        if a is None:
            continue
        pmid = (cit.findtext("PMID") or "").strip() or None
        parts = []
        for at in a.findall("Abstract/AbstractText"):
            label = at.get("Label")
            txt = element_text(at)
            parts.append(f"{label.title()}: {txt}" if label else txt)
        authors = []
        for au in a.findall("AuthorList/Author"):
            if au.findtext("CollectiveName"):
                authors.append(au.findtext("CollectiveName"))
            elif au.findtext("LastName"):
                authors.append(f"{au.findtext('LastName')} {au.findtext('Initials') or ''}".strip())
        ids = {aid.get("IdType"): (aid.text or "").strip() for aid in art.findall("PubmedData/ArticleIdList/ArticleId")}
        doi = ids.get("doi")
        if not doi:
            for eloc in a.findall("ELocationID"):
                if eloc.get("EIdType") == "doi":
                    doi = eloc.text
        records.append(Record(
            title=element_text(a.find("ArticleTitle")),
            abstract=" ".join(parts),
            authors=authors,
            year=_year(a),
            journal=a.findtext("Journal/Title") or "",
            doi=doi or None,
            pmid=pmid,
            pmcid=ids.get("pmc") or None,
            publication_types=[element_text(p) for p in a.findall("PublicationTypeList/PublicationType")],
            mesh_terms=[element_text(m) for m in cit.findall("MeshHeadingList/MeshHeading/DescriptorName")],
            keywords=[element_text(k) for k in cit.findall("KeywordList/Keyword")],
            language=a.findtext("Language"),
            is_open_access=bool(ids.get("pmc")),
            full_text_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{ids['pmc']}/" if ids.get("pmc") else None,
            sources=["PubMed"],
        ))
    return records
