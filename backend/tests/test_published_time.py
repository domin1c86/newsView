import importlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.sources.base import ArticleCandidate


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def test_future_candidate_published_at_is_clamped_to_server_now(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    monkeypatch.setenv("RSS_SOURCES", "")
    monkeypatch.setenv("NEWS_API_PROVIDERS", "")
    monkeypatch.setenv("DISABLE_SCHEDULER", "true")

    main = importlib.import_module("app.main")
    main = importlib.reload(main)

    with TestClient(main.app) as client:
        future = datetime.now(timezone.utc) + timedelta(days=1)
        main.news_service._store_candidates(
            [
                ArticleCandidate(
                    source_name="Test Source",
                    title="OpenAI 发布新的 AI 模型",
                    summary="AI 模型能力更新。",
                    url="https://example.com/future-published-at-test",
                    published_at=future.isoformat(),
                )
            ]
        )

        payload = client.get("/api/news").json()
        item = payload["items"][0]
        source = item["sources"][0]
        assert _parse_utc(item["published_at"]) <= datetime.now(timezone.utc) + timedelta(seconds=1)
        assert _parse_utc(source["published_at"]) <= datetime.now(timezone.utc) + timedelta(seconds=1)


def test_existing_future_published_times_are_normalized(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    monkeypatch.setenv("RSS_SOURCES", "")
    monkeypatch.setenv("NEWS_API_PROVIDERS", "")
    monkeypatch.setenv("DISABLE_SCHEDULER", "true")

    main = importlib.import_module("app.main")
    main = importlib.reload(main)

    with TestClient(main.app):
        now = datetime.now(timezone.utc).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        main.news_service._store_candidates(
            [
                ArticleCandidate(
                    source_name="Test Source",
                    title="Anthropic 发布新的 AI 工具",
                    summary="AI 工具能力更新。",
                    url="https://example.com/existing-future-time-test",
                    published_at=now,
                )
            ]
        )
        with main.database.connect() as connection:
            connection.execute("UPDATE clusters SET published_at = ?", (future,))
            connection.execute("UPDATE articles SET published_at = ?", (future,))

        assert main.news_service.normalize_future_published_times() == 2
        with main.database.connect() as connection:
            cluster = connection.execute("SELECT published_at FROM clusters").fetchone()
            article = connection.execute("SELECT published_at FROM articles").fetchone()

        assert _parse_utc(cluster["published_at"]) <= datetime.now(timezone.utc) + timedelta(seconds=1)
        assert _parse_utc(article["published_at"]) <= datetime.now(timezone.utc) + timedelta(seconds=1)
