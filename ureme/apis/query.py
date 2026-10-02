"""Boolean query handling and translation between database syntaxes.

Queries are written in PubMed syntax (AND / OR / NOT, parentheses, quoted
phrases, optional field tags such as ``[tiab]`` or ``[MeSH Terms]``) and
translated for the other databases.
"""

from __future__ import annotations

import re

_TAGGED = re.compile(r'("[^"]+"|[\w\-*]+)\s*\[([A-Za-z][A-Za-z :]*)\]')
_BOOL = re.compile(r"\b(AND|OR|NOT)\b|[()]")
_STOP = {"and", "or", "not", "the", "of", "in", "a", "an", "for", "with", "on", "to", "by", "vs", "versus"}


def is_boolean(query: str) -> bool:
    return bool(_BOOL.search(query)) or "[" in query


def to_pubmed(query: str) -> str:
    return query.strip()


def _epmc_field(term: str, tag: str) -> str:
    tag = tag.strip().lower()
    if tag in {"tiab", "title/abstract"}:
        return f"(TITLE:{term} OR ABSTRACT:{term})"
    if tag in {"ti", "title"}:
        return f"TITLE:{term}"
    if tag in {"ab", "abstract"}:
        return f"ABSTRACT:{term}"
    if tag in {"mh", "mesh", "mesh terms", "majr"}:
        return f"MESH:{term}"
    if tag in {"au", "author"}:
        return f"AUTH:{term}"
    if tag in {"pt", "publication type"}:
        return f"PUB_TYPE:{term}"
    return term


def to_europepmc(query: str) -> str:
    return _TAGGED.sub(lambda m: _epmc_field(m.group(1), m.group(2)), query).strip()


def strip_field_tags(query: str) -> str:
    return re.sub(r"\s*\[[A-Za-z][A-Za-z :]*\]", "", query)


def to_semantic_scholar(query: str) -> str:
    """Translate to Semantic Scholar bulk-search syntax (+ AND, | OR, - NOT)."""
    q = strip_field_tags(query)
    q = re.sub(r"\bNOT\s+", "-", q)
    q = re.sub(r"\bAND\b", "+", q)
    q = re.sub(r"\bOR\b", "|", q)
    return re.sub(r"\s+", " ", q).strip()


def to_plain_terms(query: str) -> str:
    """Free-text version for relevance-ranked endpoints."""
    q = strip_field_tags(query)
    q = re.sub(r"\bNOT\s+(\"[^\"]+\"|\S+)", "", q)
    q = re.sub(r"\b(AND|OR)\b|[()*]", " ", q)
    return re.sub(r"\s+", " ", q.replace('"', "")).strip()


def concept_terms(query: str) -> list[str]:
    """Distinct content terms/phrases in a query, in order (used by gap mining)."""
    q = strip_field_tags(query)
    q = re.sub(r"\bNOT\s+(\"[^\"]+\"|\S+)", "", q)
    tokens = re.findall(r'"([^"]+)"|([\w\-]+\*?)', q)
    out: list[str] = []
    for phrase, word in tokens:
        term = (phrase or word).strip("*").lower()
        if term and term not in _STOP and term not in out and len(term) > 2:
            out.append(term)
    return out


def concept_groups(query: str) -> list[list[str]]:
    """Split a query on top-level AND into OR-groups of terms."""
    q = strip_field_tags(query)
    depth, buf, parts = 0, "", []
    i = 0
    while i < len(q):
        ch = q[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and q[i : i + 5] == " AND ":
            parts.append(buf)
            buf = ""
            i += 5
            continue
        buf += ch
        i += 1
    parts.append(buf)
    return [g for g in (concept_terms(p) for p in parts) if g]
