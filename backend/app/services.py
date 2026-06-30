from __future__ import annotations

import asyncio
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .article_text import fetch_article_content, should_fetch_article_content
from .config import Settings
from .database import Database, from_json, to_json
from .dedupe import is_same_topic
from .keywords import extract_keywords, has_special_trigger, is_ai_related, keyword_score
from .schemas import NewsCluster, NewsListResponse, NewsSourceItem, RefreshResponse, RefreshStatusResponse, SearchResponse
from .sources.base import ArticleCandidate
from .sources.free_apis import CurrentsApiAdapter, GuardianAdapter, HackerNewsAlgoliaAdapter, NewsApiAdapter, TheNewsApiAdapter
from .sources.gnews import GNewsAdapter
from .sources.rss import RssAdapter
from .text import clean_text


class NewsService:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings
        self._refresh_lock = asyncio.Lock()

    def init(self) -> None:
        self.database.init()

    async def refresh(self) -> RefreshResponse:
        async with self._refresh_lock:
            started_at = datetime.now(timezone.utc).isoformat()
            candidates = await self._fetch_candidates()
            inserted, clustered = self._store_candidates(candidates)
            self._prune_irrelevant_clusters()
            self.prune_old_news()
            finished_at = datetime.now(timezone.utc).isoformat()
            with self.database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO refresh_runs (started_at, finished_at, fetched, inserted, clustered)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (started_at, finished_at, len(candidates), inserted, clustered),
                )
            return RefreshResponse(fetched=len(candidates), inserted=inserted, clustered=clustered)

    async def _fetch_candidates(self) -> list[ArticleCandidate]:
        tasks = [RssAdapter(self.settings.rss_sources).fetch()]
        providers = set(self.settings.api_providers)
        use_all = "all" in providers

        if (use_all or "gnews" in providers) and self.settings.gnews_api_key:
            adapter = GNewsAdapter(self.settings.gnews_api_key, self.settings.gnews_endpoint)
            tasks.extend(adapter.fetch(query) for query in self.settings.news_queries)

        if (use_all or "thenewsapi" in providers) and self.settings.thenewsapi_api_key:
            adapter = TheNewsApiAdapter(self.settings.thenewsapi_api_key, self.settings.thenewsapi_endpoint)
            tasks.extend(adapter.fetch(query) for query in self.settings.news_queries)

        if (use_all or "currents" in providers) and self.settings.currents_api_key:
            adapter = CurrentsApiAdapter(self.settings.currents_api_key, self.settings.currents_endpoint)
            tasks.extend(adapter.fetch(query) for query in self.settings.news_queries)

        if (use_all or "newsapi" in providers) and self.settings.newsapi_api_key:
            adapter = NewsApiAdapter(self.settings.newsapi_api_key, self.settings.newsapi_endpoint)
            tasks.extend(adapter.fetch(query) for query in self.settings.news_queries)

        if (use_all or "guardian" in providers) and self.settings.guardian_api_key:
            adapter = GuardianAdapter(self.settings.guardian_api_key, self.settings.guardian_endpoint)
            tasks.extend(adapter.fetch(query) for query in self.settings.news_queries)

        if use_all or "hackernews" in providers:
            adapter = HackerNewsAlgoliaAdapter(self.settings.hn_algolia_endpoint)
            tasks.extend(adapter.fetch(query) for query in self.settings.news_queries)

        candidates: list[ArticleCandidate] = []
        for result in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(result, Exception):
                continue
            candidates.extend(result)
        return await self._enrich_article_content(candidates)

    async def _enrich_article_content(self, candidates: list[ArticleCandidate]) -> list[ArticleCandidate]:
        targets = [candidate for candidate in candidates if should_fetch_article_content(candidate.summary)]
        if not targets:
            return candidates

        semaphore = asyncio.Semaphore(8)

        async def fetch_one(client: httpx.AsyncClient, candidate: ArticleCandidate) -> tuple[str, str]:
            async with semaphore:
                try:
                    return candidate.url, await fetch_article_content(client, candidate.url)
                except httpx.HTTPError:
                    return candidate.url, ""

        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            fetched = dict(await asyncio.gather(*(fetch_one(client, candidate) for candidate in targets)))
        return [
            ArticleCandidate(
                source_name=candidate.source_name,
                title=candidate.title,
                summary=candidate.summary,
                url=candidate.url,
                published_at=candidate.published_at,
                content=fetched.get(candidate.url, candidate.content),
            )
            for candidate in candidates
        ]

    def _store_candidates(self, candidates: list[ArticleCandidate]) -> tuple[int, int]:
        inserted = 0
        new_clusters = 0
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            for candidate in candidates:
                if not candidate.title.strip() or not candidate.url.strip():
                    continue
                title = clean_text(candidate.title)
                summary = clean_text(candidate.summary)
                if not is_ai_related(f"{title} {summary} {candidate.url}"):
                    continue
                keywords = extract_keywords(f"{title} {summary}")
                existing_article = connection.execute("SELECT id, content FROM articles WHERE url = ?", (candidate.url,)).fetchone()
                if existing_article:
                    content = clean_text(candidate.content)
                    if content and not clean_text(existing_article["content"]):
                        connection.execute("UPDATE articles SET content = ? WHERE id = ?", (content, existing_article["id"]))
                    continue
                cleaned_candidate = ArticleCandidate(
                    source_name=candidate.source_name,
                    title=title,
                    summary=summary,
                    url=candidate.url,
                    published_at=candidate.published_at,
                    content=clean_text(candidate.content),
                )
                cluster_id = self._find_cluster(connection, cleaned_candidate, keywords)
                if cluster_id is None:
                    cluster_id = str(uuid.uuid4())
                    new_clusters += 1
                    connection.execute(
                        """
                        INSERT INTO clusters (id, title, summary, published_at, keywords_json, primary_url, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            cluster_id,
                            cleaned_candidate.title,
                            cleaned_candidate.summary,
                            candidate.published_at,
                            to_json(keywords),
                            candidate.url,
                            fetched_at,
                        ),
                    )
                else:
                    self._update_cluster_if_newer(connection, cluster_id, cleaned_candidate, keywords, fetched_at)

                connection.execute(
                    """
                    INSERT INTO articles (id, cluster_id, source_name, title, summary, content, url, published_at, fetched_at, keywords_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        cluster_id,
                        candidate.source_name,
                        cleaned_candidate.title,
                        cleaned_candidate.summary,
                        cleaned_candidate.content,
                        candidate.url,
                        candidate.published_at,
                        fetched_at,
                        to_json(keywords),
                    ),
                )
                inserted += 1
        return inserted, new_clusters

    def _prune_irrelevant_clusters(self) -> None:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT id, title, summary, primary_url FROM clusters").fetchall()
            for row in rows:
                if not is_ai_related(f"{row['title']} {row['summary']} {row['primary_url']}"):
                    connection.execute("DELETE FROM clusters WHERE id = ?", (row["id"],))

    def prune_old_news(self) -> None:
        cutoff = self._retention_cutoff()
        with self.database.connect() as connection:
            connection.execute("DELETE FROM clusters WHERE published_at < ?", (cutoff,))

    def _retention_cutoff(self) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=self.settings.news_retention_days)).isoformat()

    def refresh_status(self) -> RefreshStatusResponse:
        window_key, window_ends_at = self._manual_refresh_window()
        used = self._manual_refresh_count(window_key)
        limit = max(self.settings.manual_refresh_hourly_limit, 0)
        return RefreshStatusResponse(
            used=used,
            limit=limit,
            remaining=max(limit - used, 0),
            window_ends_at=window_ends_at.isoformat(),
        )

    def record_manual_refresh(self) -> tuple[bool, RefreshStatusResponse]:
        window_key, window_ends_at = self._manual_refresh_window()
        limit = max(self.settings.manual_refresh_hourly_limit, 0)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT request_count FROM manual_refresh_usage WHERE window_key = ?",
                (window_key,),
            ).fetchone()
            used = int(row["request_count"]) if row else 0
            if used >= limit:
                return False, RefreshStatusResponse(
                    used=used,
                    limit=limit,
                    remaining=0,
                    window_ends_at=window_ends_at.isoformat(),
                )

            updated_used = used + 1
            connection.execute(
                """
                INSERT INTO manual_refresh_usage (window_key, request_count, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(window_key) DO UPDATE SET
                    request_count = excluded.request_count,
                    updated_at = excluded.updated_at
                """,
                (window_key, updated_used, datetime.now(timezone.utc).isoformat()),
            )
        return True, RefreshStatusResponse(
            used=updated_used,
            limit=limit,
            remaining=max(limit - updated_used, 0),
            window_ends_at=window_ends_at.isoformat(),
        )

    def _manual_refresh_count(self, window_key: str) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT request_count FROM manual_refresh_usage WHERE window_key = ?",
                (window_key,),
            ).fetchone()
        return int(row["request_count"]) if row else 0

    def _manual_refresh_window(self) -> tuple[str, datetime]:
        now = datetime.now(self._configured_timezone())
        window_start = now.replace(minute=0, second=0, microsecond=0)
        window_end = window_start + timedelta(hours=1)
        return window_start.strftime("%Y-%m-%dT%H:00%z"), window_end

    def _configured_timezone(self):
        try:
            return ZoneInfo(self.settings.news_refresh_timezone)
        except ZoneInfoNotFoundError:
            if self.settings.news_refresh_timezone == "Asia/Shanghai":
                return timezone(timedelta(hours=8), "Asia/Shanghai")
            return datetime.now().astimezone().tzinfo

    def _find_cluster(self, connection: sqlite3.Connection, candidate: ArticleCandidate, keywords: list[str]) -> str | None:
        rows = connection.execute(
            "SELECT id, title, summary, keywords_json FROM clusters ORDER BY published_at DESC LIMIT 250"
        ).fetchall()
        for row in rows:
            if is_same_topic(
                candidate.title,
                candidate.summary,
                keywords,
                row["title"],
                row["summary"],
                extract_keywords(f"{row['title']} {row['summary']}"),
            ):
                return row["id"]
        return None

    def _update_cluster_if_newer(
        self,
        connection: sqlite3.Connection,
        cluster_id: str,
        candidate: ArticleCandidate,
        keywords: list[str],
        fetched_at: str,
    ) -> None:
        row = connection.execute("SELECT published_at, keywords_json FROM clusters WHERE id = ?", (cluster_id,)).fetchone()
        existing_keywords = set(from_json(row["keywords_json"]))
        merged_keywords = list(dict.fromkeys([*keywords, *existing_keywords]))[:10]
        if candidate.published_at >= row["published_at"]:
            connection.execute(
                """
                UPDATE clusters
                SET title = ?, summary = ?, published_at = ?, keywords_json = ?, primary_url = ?, updated_at = ?
                WHERE id = ?
                """,
                (candidate.title, candidate.summary, candidate.published_at, to_json(merged_keywords), candidate.url, fetched_at, cluster_id),
            )
        else:
            connection.execute(
                "UPDATE clusters SET keywords_json = ?, updated_at = ? WHERE id = ?",
                (to_json(merged_keywords), fetched_at, cluster_id),
            )

    def list_news(
        self,
        page: int = 1,
        page_size: int = 20,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> NewsListResponse:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        where_parts: list[str] = ["published_at >= ?"]
        params: list[str | int] = [self._retention_cutoff()]
        if date_from:
            where_parts.append("published_at >= ?")
            params.append(date_from)
        if date_to:
            where_parts.append("published_at <= ?")
            params.append(date_to)
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        with self.database.connect() as connection:
            total = connection.execute(f"SELECT COUNT(*) AS count FROM clusters {where_clause}", params).fetchone()["count"]
            rows = connection.execute(
                f"""
                SELECT * FROM clusters
                {where_clause}
                ORDER BY published_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
            return NewsListResponse(
                items=[self._cluster_from_row(connection, row) for row in rows],
                page=page,
                page_size=page_size,
                total=total,
            )

    def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResponse:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        keywords = extract_keywords(query)
        special_link = self.settings.special_link_url if has_special_trigger(query) else None
        if not keywords:
            news = self.list_news(page=page, page_size=page_size)
            payload = news.model_dump() if hasattr(news, "model_dump") else news.dict()
            return SearchResponse(**payload, query=query, keywords=keywords, special_link=special_link)

        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM clusters WHERE published_at >= ? ORDER BY published_at DESC",
                (self._retention_cutoff(),),
            ).fetchall()
            scored = []
            for row in rows:
                item_keywords = from_json(row["keywords_json"])
                score = keyword_score(keywords, f"{row['title']} {row['summary']}", item_keywords)
                if score > 0:
                    scored.append((score, row))
            scored.sort(key=lambda item: (item[0], item[1]["published_at"]), reverse=True)
            start = (page - 1) * page_size
            selected = [row for _, row in scored[start : start + page_size]]
            return SearchResponse(
                items=[self._cluster_from_row(connection, row) for row in selected],
                page=page,
                page_size=page_size,
                total=len(scored),
                query=query,
                keywords=keywords,
                special_link=special_link,
            )

    def _cluster_from_row(self, connection: sqlite3.Connection, row: sqlite3.Row) -> NewsCluster:
        source_rows = connection.execute(
            """
            SELECT source_name, title, summary, content, url, published_at
            FROM articles
            WHERE cluster_id = ?
            ORDER BY published_at DESC
            """,
            (row["id"],),
        ).fetchall()
        sources = [
            NewsSourceItem(
                source_name=source["source_name"],
                title=clean_text(source["title"]),
                summary=clean_text(source["summary"]),
                content=clean_text(source["content"]),
                url=source["url"],
                published_at=source["published_at"],
            )
            for source in source_rows
        ]
        return NewsCluster(
            id=row["id"],
            title=clean_text(row["title"]),
            summary=clean_text(row["summary"]),
            published_at=row["published_at"],
            keywords=from_json(row["keywords_json"]),
            source_count=len(sources),
            primary_url=row["primary_url"],
            sources=sources,
        )
