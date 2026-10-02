import json

from ureme.apis.europepmc import EuropePMCClient, parse_epmc_result
from ureme.apis.pubmed import PubMedClient, parse_pubmed_xml
from ureme.apis.query import (concept_groups, concept_terms, is_boolean, to_europepmc, to_plain_terms,
                              to_semantic_scholar)
from ureme.apis.semantic_scholar import SemanticScholarClient, parse_s2_paper
from ureme.apis.text import jats_body_text


def test_parse_pubmed_xml(fixtures):
    recs = parse_pubmed_xml((fixtures / "pubmed_efetch.xml").read_text())
    assert len(recs) == 2
    r = recs[0]
    assert r.pmid == "11111111" and r.doi == "10.1000/test.1" and r.pmcid == "PMC1234567"
    assert r.title.startswith("Aerobic exercise for depression")
    assert "Conclusions: Further research" in r.abstract
    assert r.authors == ["Smith J", "TEST Trial Group"]
    assert r.year == 2024 and "Randomized Controlled Trial" in r.publication_types
    assert r.mesh_terms == ["Depression"] and r.keywords == ["exercise"]
    assert r.record_id == "doi:10.1000/test.1"
    assert recs[1].year == 2019 and recs[1].abstract == ""


def test_pubmed_client_search(fixtures, fake_http):
    http = fake_http({"esearch": json.dumps({"esearchresult": {"count": "2", "idlist": ["11111111", "22222222"]}}),
                      "efetch": (fixtures / "pubmed_efetch.xml").read_text()})
    total, recs = PubMedClient(http, email="a@b.c", api_key="SECRET").search("exercise AND depression", 10, 2015, 2025)
    assert total == 2 and len(recs) == 2
    params = http.calls[0][1]
    assert params["mindate"] == "2015" and params["api_key"] == "SECRET" and params["email"] == "a@b.c"


def test_parse_epmc(fixtures):
    data = json.loads((fixtures / "europepmc_search.json").read_text())
    recs = [parse_epmc_result(r) for r in data["resultList"]["result"]]
    assert recs[0].abstract.startswith("Background Depression")
    assert recs[0].is_open_access and recs[0].citation_count == 7
    assert recs[0].full_text_url.endswith("PMC1234567")
    assert recs[1].authors == ["Doe J"] and recs[1].epmc_id == "PPR:PPR123"


def test_epmc_client_paginates_once(fixtures, fake_http):
    body = (fixtures / "europepmc_search.json").read_text()
    http = fake_http({"search": body})
    total, recs = EuropePMCClient(http).search("exercise", max_results=2, min_year=2020)
    assert total == 2 and len(recs) == 2
    assert "PUB_YEAR:[2020 TO 3000]" in http.calls[0][1]["query"]


def test_parse_s2(fixtures):
    data = json.loads((fixtures / "s2_search.json").read_text())
    r = parse_s2_paper(data["data"][0])
    assert r.doi == "10.1000/test.1" and r.pmid == "11111111" and r.pmcid == "PMC1234567"
    assert r.citation_count == 9 and r.full_text_url == "https://example.org/pdf"
    empty = parse_s2_paper(data["data"][1])
    assert empty.abstract == "" and empty.record_id == "s2:def456"


def test_s2_client_uses_bulk_for_boolean(fixtures, fake_http):
    http = fake_http({"paper/search": (fixtures / "s2_search.json").read_text()})
    SemanticScholarClient(http).search('"exercise" AND depression', 5)
    url, params = http.calls[0]
    assert url.endswith("paper/search/bulk") and params["query"] == '"exercise" + depression'
    http2 = fake_http({"paper/search": (fixtures / "s2_search.json").read_text()})
    SemanticScholarClient(http2).search("exercise depression", 5)
    assert http2.calls[0][0].endswith("paper/search")


def test_query_translation():
    q = '("exercise"[tiab] OR yoga[mh]) AND depress* NOT mice[ti]'
    assert is_boolean(q) and not is_boolean("exercise depression")
    assert to_europepmc(q) == '((TITLE:"exercise" OR ABSTRACT:"exercise") OR MESH:yoga) AND depress* NOT TITLE:mice'
    assert to_semantic_scholar(q) == '("exercise" | yoga) + depress* -mice'
    assert to_plain_terms(q) == "exercise yoga depress"
    assert concept_terms(q) == ["exercise", "yoga", "depress"]
    assert concept_groups('(exercise OR "physical activity") AND (depression OR anxiety)') == [
        ["exercise", "physical activity"], ["depression", "anxiety"]]


def test_jats_body_text():
    xml = "<article><front><title>x</title></front><body><sec><title>Methods</title><p>We randomized 40.</p></sec></body></article>"
    assert jats_body_text(xml) == "\nMethods\n\nWe randomized 40."
    assert jats_body_text("<article><front/></article>") is None
