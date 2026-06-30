from __future__ import annotations

from html.parser import HTMLParser

import httpx

from .text import clean_text

SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "nav", "header", "footer", "form", "button", "audio", "video"}
TEXT_TAGS = {"p", "li", "blockquote", "h2", "h3"}
PLACEHOLDER_SUMMARY_MARKERS = (
    "点击查看原文",
    "查看原文",
    "阅读全文",
    "read more",
    "continue reading",
)


class ArticleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._text_depth = 0
        self._current: list[str] = []
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in TEXT_TAGS:
            self._text_depth += 1
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in TEXT_TAGS and self._text_depth:
            self._text_depth -= 1
            chunk = clean_text(" ".join(self._current))
            if len(chunk) >= 12:
                self._chunks.append(chunk)
            self._current = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not self._text_depth:
            return
        self._current.append(data)

    def text(self) -> str:
        return clean_text("\n".join(self._chunks))


def should_fetch_article_content(summary: str) -> bool:
    normalized = clean_text(summary).lower()
    if len(normalized) < 80:
        return True
    return any(marker in normalized for marker in PLACEHOLDER_SUMMARY_MARKERS)


def extract_article_text(html: str, max_length: int = 5000) -> str:
    parser = ArticleTextParser()
    parser.feed(html)
    return parser.text()[:max_length].strip()


async def fetch_article_content(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AI-News-Preview/1.0; +https://layoverlens.site)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "xml" not in content_type and content_type:
        return ""
    return extract_article_text(response.text)
