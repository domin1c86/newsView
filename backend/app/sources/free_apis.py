from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from .base import ArticleCandidate


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


class TheNewsApiAdapter:
    name = "thenewsapi"

    def __init__(self, api_key: str, endpoint: str):
        self.api_key = api_key
        self.endpoint = endpoint

    async def fetch(self, query: str) -> list[ArticleCandidate]:
        params = {
            "api_token": self.api_key,
            "search": query,
            "language": "en",
            "limit": 3,
        }
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()

        candidates: list[ArticleCandidate] = []
        for item in payload.get("data", []):
            title = _text(item.get("title"))
            url = _text(item.get("url"))
            if not title or not url:
                continue
            candidates.append(
                ArticleCandidate(
                    source_name=_text(item.get("source")) or "The News API",
                    title=title,
                    summary=_text(item.get("description") or item.get("snippet")),
                    url=url,
                    published_at=_text(item.get("published_at")) or _now_iso(),
                )
            )
        return candidates


class CurrentsApiAdapter:
    name = "currents"

    def __init__(self, api_key: str, endpoint: str):
        self.api_key = api_key
        self.endpoint = endpoint

    async def fetch(self, query: str) -> list[ArticleCandidate]:
        params = {
            "apiKey": self.api_key,
            "keywords": query,
            "language": "en",
            "page_size": 20,
        }
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()

        candidates: list[ArticleCandidate] = []
        for item in payload.get("news", []):
            title = _text(item.get("title"))
            url = _text(item.get("url"))
            if not title or not url:
                continue
            candidates.append(
                ArticleCandidate(
                    source_name=_text(item.get("author")) or "Currents",
                    title=title,
                    summary=_text(item.get("description")),
                    url=url,
                    published_at=_text(item.get("published")) or _now_iso(),
                )
            )
        return candidates


class NewsApiAdapter:
    name = "newsapi"

    def __init__(self, api_key: str, endpoint: str):
        self.api_key = api_key
        self.endpoint = endpoint

    async def fetch(self, query: str) -> list[ArticleCandidate]:
        params = {
            "apiKey": self.api_key,
            "q": query,
            "language": "en",
            "pageSize": 20,
            "sortBy": "publishedAt",
        }
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()

        candidates: list[ArticleCandidate] = []
        for item in payload.get("articles", []):
            title = _text(item.get("title"))
            url = _text(item.get("url"))
            if not title or not url:
                continue
            source = item.get("source") or {}
            candidates.append(
                ArticleCandidate(
                    source_name=_text(source.get("name")) or "NewsAPI",
                    title=title,
                    summary=_text(item.get("description") or item.get("content")),
                    url=url,
                    published_at=_text(item.get("publishedAt")) or _now_iso(),
                )
            )
        return candidates


class GuardianAdapter:
    name = "guardian"

    def __init__(self, api_key: str, endpoint: str):
        self.api_key = api_key
        self.endpoint = endpoint

    async def fetch(self, query: str) -> list[ArticleCandidate]:
        params = {
            "api-key": self.api_key,
            "q": query,
            "order-by": "newest",
            "page-size": 20,
            "show-fields": "trailText,bodyText",
        }
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()

        candidates: list[ArticleCandidate] = []
        for item in payload.get("response", {}).get("results", []):
            title = _text(item.get("webTitle"))
            url = _text(item.get("webUrl"))
            if not title or not url:
                continue
            fields = item.get("fields") or {}
            candidates.append(
                ArticleCandidate(
                    source_name="The Guardian",
                    title=title,
                    summary=_text(fields.get("trailText") or fields.get("bodyText")),
                    url=url,
                    published_at=_text(item.get("webPublicationDate")) or _now_iso(),
                )
            )
        return candidates


class HackerNewsAlgoliaAdapter:
    name = "hackernews"

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    async def fetch(self, query: str) -> list[ArticleCandidate]:
        params = {
            "query": query,
            "tags": "story",
            "hitsPerPage": 20,
        }
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()

        candidates: list[ArticleCandidate] = []
        for item in payload.get("hits", []):
            title = _text(item.get("title") or item.get("story_title"))
            url = _text(item.get("url") or item.get("story_url"))
            if not title or not url:
                continue
            candidates.append(
                ArticleCandidate(
                    source_name="Hacker News",
                    title=title,
                    summary=_text(item.get("comment_text")),
                    url=url,
                    published_at=_text(item.get("created_at")) or _now_iso(),
                )
            )
        return candidates
