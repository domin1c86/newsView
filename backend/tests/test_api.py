import importlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.sources.base import ArticleCandidate


def test_news_and_search_endpoints(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    monkeypatch.setenv("RSS_SOURCES", "")
    monkeypatch.setenv("NEWS_API_PROVIDERS", "")
    monkeypatch.setenv("DISABLE_SCHEDULER", "true")
    monkeypatch.setenv("SPECIAL_LINK_URL", "https://example.com/special")
    monkeypatch.setenv("SITE_ICP_NUMBER", "京ICP备00000000号")
    monkeypatch.setenv("SITE_COPYRIGHT_OWNER", "AI News Owner")
    monkeypatch.setenv("SITE_COPYRIGHT_TEXT", "Copyright 2026")

    main = importlib.import_module("app.main")
    main = importlib.reload(main)

    with TestClient(main.app) as client:
        config_response = client.get("/api/config")
        assert config_response.status_code == 200
        config_payload = config_response.json()
        assert config_payload["special_link_url"] == "https://example.com/special"
        assert config_payload["site_icp_number"] == "京ICP备00000000号"
        assert config_payload["site_copyright_owner"] == "AI News Owner"
        assert config_payload["site_copyright_text"] == "Copyright 2026"

        now = datetime.now(timezone.utc)
        main.news_service._store_candidates(
            [
                ArticleCandidate(
                    source_name="Test Source",
                    title="OpenAI 发布新的多模态模型能力",
                    summary="新模型强化了文本、图像和语音理解能力。",
                    url="https://example.com/openai-multimodal-test",
                    published_at=(now - timedelta(hours=2)).isoformat(),
                ),
                ArticleCandidate(
                    source_name="Test Source",
                    title="苹果产品涨价被分析师归因于 AI 硬件成本上升",
                    summary="端侧 AI 功能增加了内存、芯片和散热组件成本。",
                    url="https://example.com/apple-ai-hardware-price-test",
                    published_at=(now - timedelta(hours=3)).isoformat(),
                ),
                ArticleCandidate(
                    source_name="Test Source",
                    title="OpenAI 八天前发布模型更新",
                    summary="这是一条超过一周的 AI 新闻。",
                    url="https://example.com/old-openai-test",
                    published_at=(now - timedelta(days=8)).isoformat(),
                ),
            ]
        )

        news_response = client.get("/api/news")
        assert news_response.status_code == 200
        news_payload = news_response.json()
        assert news_payload["items"]
        assert news_payload["items"][0]["source_count"] >= 1
        assert news_payload["items"][0]["sources"][0]["summary"]
        assert "content" in news_payload["items"][0]["sources"][0]
        assert all("八天前" not in item["title"] for item in news_payload["items"])

        search_response = client.get("/api/search", params={"q": "OpenAI 多模态"})
        assert search_response.status_code == 200
        search_payload = search_response.json()
        assert "openai" in search_payload["keywords"]
        assert search_payload["items"]
        assert all("八天前" not in item["title"] for item in search_payload["items"])

        indirect_response = client.get("/api/search", params={"q": "苹果产品涨价 AI 硬件成本"})
        assert indirect_response.status_code == 200
        indirect_payload = indirect_response.json()
        assert indirect_payload["items"]
        assert any("苹果产品涨价" in item["title"] for item in indirect_payload["items"])

        special_response = client.get("/api/search", params={"q": "老岳中转"})
        assert special_response.status_code == 200
        assert special_response.json()["special_link"] == "https://example.com/special"

        translate_response = client.post("/api/translate", json={"target_language": "zh", "texts": ["中文标题"]})
        assert translate_response.status_code == 200
        translate_payload = translate_response.json()
        assert translate_payload["items"][0]["translated_text"] == "中文标题"
        assert translate_payload["items"][0]["source_language"] == "zh-CN"

        refresh_response = client.post("/api/refresh")
        assert refresh_response.status_code == 200
        old_response = client.get("/api/search", params={"q": "八天前 OpenAI"})
        assert old_response.status_code == 200
        assert all("八天前" not in item["title"] for item in old_response.json()["items"])


def test_translate_endpoint_returns_quota_exhausted_code(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    monkeypatch.setenv("RSS_SOURCES", "")
    monkeypatch.setenv("NEWS_API_PROVIDERS", "")
    monkeypatch.setenv("DISABLE_SCHEDULER", "true")
    monkeypatch.setenv("TRANSLATION_PROVIDERS", "mymemory")
    monkeypatch.setenv("MYMEMORY_DAILY_CHAR_BUDGET", "1")

    main = importlib.import_module("app.main")
    main = importlib.reload(main)

    with TestClient(main.app) as client:
        response = client.post("/api/translate", json={"target_language": "zh", "texts": ["OpenAI model"]})

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "translation_quota_exhausted"


def test_manual_refresh_hourly_limit(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    monkeypatch.setenv("RSS_SOURCES", "")
    monkeypatch.setenv("NEWS_API_PROVIDERS", "")
    monkeypatch.setenv("DISABLE_SCHEDULER", "true")
    monkeypatch.setenv("MANUAL_REFRESH_HOURLY_LIMIT", "2")

    main = importlib.import_module("app.main")
    main = importlib.reload(main)

    with TestClient(main.app) as client:
        status_response = client.get("/api/refresh/status")
        assert status_response.status_code == 200
        assert status_response.json()["remaining"] == 2

        assert client.post("/api/refresh").status_code == 200
        assert client.post("/api/refresh").status_code == 200

        limited_response = client.post("/api/refresh")
        assert limited_response.status_code == 429
        assert limited_response.json()["detail"]["code"] == "manual_refresh_hourly_limit_exceeded"

        status_payload = client.get("/api/refresh/status").json()
        assert status_payload["used"] == 2
        assert status_payload["remaining"] == 0


def test_automatic_refresh_does_not_count_against_manual_limit(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    monkeypatch.setenv("RSS_SOURCES", "")
    monkeypatch.setenv("NEWS_API_PROVIDERS", "")
    monkeypatch.setenv("DISABLE_SCHEDULER", "true")
    monkeypatch.setenv("MANUAL_REFRESH_HOURLY_LIMIT", "1")

    main = importlib.import_module("app.main")
    main = importlib.reload(main)

    with TestClient(main.app) as client:
        assert client.get("/api/refresh/status").json()["remaining"] == 1
        import asyncio

        asyncio.run(main.news_service.refresh())
        assert client.get("/api/refresh/status").json()["remaining"] == 1
