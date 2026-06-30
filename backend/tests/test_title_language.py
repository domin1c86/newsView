import asyncio
import importlib
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.language import detect_title_language
from app.sources.base import ArticleCandidate


def test_detect_title_language_from_title_only():
    assert detect_title_language('AI agents are not your "coworkers" in 2026') == "en"
    assert detect_title_language("OpenAI 发布新的多模态模型能力") == "zh"
    assert detect_title_language("GPT 模型 update") == "unknown"
    assert detect_title_language("2026 / 06 / 30") == "unknown"


def test_mark_missing_title_languages_and_api_payload(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    monkeypatch.setenv("RSS_SOURCES", "")
    monkeypatch.setenv("NEWS_API_PROVIDERS", "")
    monkeypatch.setenv("DISABLE_SCHEDULER", "true")

    main = importlib.import_module("app.main")
    main = importlib.reload(main)

    with TestClient(main.app) as client:
        now = datetime.now(timezone.utc).isoformat()
        main.news_service._store_candidates(
            [
                ArticleCandidate(
                    source_name="Test Source",
                    title='AI agents are not your "coworkers"',
                    summary="OpenAI and Anthropic agent news.",
                    url="https://example.com/ai-agents-language-test",
                    published_at=now,
                ),
                ArticleCandidate(
                    source_name="Test Source",
                    title="OpenAI 发布新的模型能力",
                    summary="AI 模型能力更新。",
                    url="https://example.com/openai-zh-language-test",
                    published_at=now,
                ),
            ]
        )

        updated = main.news_service.mark_missing_title_languages()
        assert updated == 2

        payload = client.get("/api/news").json()
        languages = {item["title"]: item["title_language"] for item in payload["items"]}
        assert languages['AI agents are not your "coworkers"'] == "en"
        assert languages["OpenAI 发布新的模型能力"] == "zh"


def test_mark_missing_title_languages_does_not_overwrite_existing_value(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    monkeypatch.setenv("RSS_SOURCES", "")
    monkeypatch.setenv("NEWS_API_PROVIDERS", "")
    monkeypatch.setenv("DISABLE_SCHEDULER", "true")

    main = importlib.import_module("app.main")
    main = importlib.reload(main)

    with TestClient(main.app):
        now = datetime.now(timezone.utc).isoformat()
        main.news_service._store_candidates(
            [
                ArticleCandidate(
                    source_name="Test Source",
                    title="OpenAI 发布新的模型能力",
                    summary="AI 模型能力更新。",
                    url="https://example.com/openai-preserve-language-test",
                    published_at=now,
                )
            ]
        )
        with main.database.connect() as connection:
            connection.execute("UPDATE clusters SET title_language = 'en'")

        assert main.news_service.mark_missing_title_languages() == 0
        with main.database.connect() as connection:
            row = connection.execute("SELECT title_language FROM clusters").fetchone()
        assert row["title_language"] == "en"


def test_refresh_schedules_title_language_marking(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    monkeypatch.setenv("RSS_SOURCES", "")
    monkeypatch.setenv("NEWS_API_PROVIDERS", "")
    monkeypatch.setenv("DISABLE_SCHEDULER", "true")

    main = importlib.import_module("app.main")
    main = importlib.reload(main)
    main.news_service.init()

    calls = []
    monkeypatch.setattr(main.news_service, "schedule_title_language_marking", lambda: calls.append(True))

    asyncio.run(main.news_service.refresh())

    assert calls == [True]
