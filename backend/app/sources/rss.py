from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from ..config import RssSourceConfig
from ..text import clean_text
from .base import ArticleCandidate


def parse_date(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        try:
            parsed_iso = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed_iso.tzinfo is None:
                parsed_iso = parsed_iso.replace(tzinfo=timezone.utc)
            return parsed_iso.astimezone(timezone.utc).isoformat()
        except ValueError:
            return datetime.now(timezone.utc).isoformat()


def _text(element: ElementTree.Element, names: tuple[str, ...]) -> str:
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def parse_rss(content: str, source_name: str) -> list[ArticleCandidate]:
    root = ElementTree.fromstring(content)
    candidates: list[ArticleCandidate] = []

    for item in root.findall(".//item"):
        title = _text(item, ("title",))
        url = _text(item, ("link", "guid"))
        if not title or not url:
            continue
        candidates.append(
            ArticleCandidate(
                source_name=source_name,
                title=clean_text(title),
                summary=clean_text(_text(item, ("description", "summary"))),
                url=url,
                published_at=parse_date(_text(item, ("pubDate", "published", "updated"))),
            )
        )

    namespaces = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", namespaces):
        title = _text(entry, ("{http://www.w3.org/2005/Atom}title",))
        link_element = entry.find("{http://www.w3.org/2005/Atom}link")
        url = link_element.attrib.get("href", "").strip() if link_element is not None else ""
        if not title or not url:
            continue
        candidates.append(
            ArticleCandidate(
                source_name=source_name,
                title=clean_text(title),
                summary=clean_text(_text(entry, ("{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content"))),
                url=url,
                published_at=parse_date(_text(entry, ("{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"))),
            )
        )

    return candidates


class RssAdapter:
    def __init__(self, sources: list[RssSourceConfig]):
        self.sources = sources

    async def fetch(self) -> list[ArticleCandidate]:
        candidates: list[ArticleCandidate] = []
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            for source in self.sources:
                try:
                    response = await client.get(source.url)
                    response.raise_for_status()
                    candidates.extend(parse_rss(response.text, source.name))
                except (httpx.HTTPError, ElementTree.ParseError):
                    continue
        return candidates
