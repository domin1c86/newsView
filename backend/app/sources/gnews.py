from __future__ import annotations

import httpx

from .base import ArticleCandidate


class GNewsAdapter:
    name = "gnews"

    def __init__(self, api_key: str, endpoint: str):
        self.api_key = api_key
        self.endpoint = endpoint

    async def fetch(self, query: str = "artificial intelligence") -> list[ArticleCandidate]:
        params = {
            "q": query,
            "lang": "en",
            "max": 20,
            "apikey": self.api_key,
        }
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()

        candidates: list[ArticleCandidate] = []
        for item in payload.get("articles", []):
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if not title or not url:
                continue
            source = item.get("source") or {}
            candidates.append(
                ArticleCandidate(
                    source_name=(source.get("name") or "GNews").strip(),
                    title=title,
                    summary=(item.get("description") or item.get("content") or "").strip(),
                    url=url,
                    published_at=(item.get("publishedAt") or "").strip(),
                )
            )
        return candidates
