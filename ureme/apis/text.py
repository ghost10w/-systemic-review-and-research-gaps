"""Small text utilities shared by API parsers."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET


def strip_tags(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def element_text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def jats_body_text(xml_text: str) -> str | None:
    """Extract readable body text (with section titles) from JATS/PMC XML."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    body = root.find(".//body")
    if body is None:
        return None
    chunks: list[str] = []
    for el in body.iter():
        if el.tag == "title":
            chunks.append("\n" + element_text(el) + "\n")
        elif el.tag == "p":
            chunks.append(element_text(el))
    text = "\n".join(c for c in chunks if c.strip())
    return text or None
