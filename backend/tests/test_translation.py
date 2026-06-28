import asyncio

import pytest

from app.config import get_settings
from app.database import Database
from app.translation import ProviderResult, ProviderRuntimeConfig, TranslationProviderError, TranslationQuotaExhausted, TranslationService


class FakeProvider:
    def __init__(self, name: str, translated_text: str = "", *, budget: int = 1000, quota_period: str = "monthly", fail: bool = False):
        self.name = name
        self.translated_text = translated_text
        self.fail = fail
        self.calls = 0
        self._runtime = ProviderRuntimeConfig(name=name, char_budget=budget, quota_period=quota_period, requests_per_second=100)

    @property
    def runtime(self) -> ProviderRuntimeConfig:
        return self._runtime

    def is_configured(self) -> bool:
        return True

    async def translate(self, text: str, source_language: str, target_language: str) -> ProviderResult:
        self.calls += 1
        if self.fail:
            raise TranslationProviderError("provider failed")
        return ProviderResult(translated_text=self.translated_text, used_characters=len(text))


def make_service(monkeypatch) -> tuple[TranslationService, Database]:
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    monkeypatch.setenv("TRANSLATION_PROVIDERS", "mymemory,tencent,aliyun,volcengine,azure")
    settings = get_settings()
    database = Database(settings.database_path)
    database.init()
    return TranslationService(database, settings), database


def read_usage(database: Database, provider: str) -> tuple[int, int, int]:
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT used_characters, request_count, failed_count
            FROM translation_usage_monthly
            WHERE provider = ?
            """,
            (provider,),
        ).fetchone()
    if not row:
        return 0, 0, 0
    return int(row["used_characters"]), int(row["request_count"]), int(row["failed_count"])


def test_translation_cache_hit_does_not_call_provider_or_count_usage(monkeypatch):
    service, database = make_service(monkeypatch)
    cache_key = service._cache_key("Hello", "en", "zh-CN")
    service._write_cache(cache_key, "en", "zh-CN", "Hello", "你好", "mymemory")
    provider = FakeProvider("mymemory", "不应调用")
    service._providers = [provider]

    response = asyncio.run(service.translate(["Hello"], "zh"))

    assert response.items[0].translated_text == "你好"
    assert provider.calls == 0
    assert read_usage(database, "mymemory") == (0, 0, 0)


def test_translation_falls_back_to_next_provider_after_failure(monkeypatch):
    service, database = make_service(monkeypatch)
    mymemory = FakeProvider("mymemory", fail=True)
    tencent = FakeProvider("tencent", "腾讯译文")
    aliyun = FakeProvider("aliyun", "阿里译文")
    service._providers = [mymemory, tencent, aliyun]

    response = asyncio.run(service.translate(["OpenAI model"], "zh"))

    assert response.items[0].translated_text == "腾讯译文"
    assert mymemory.calls == 1
    assert tencent.calls == 1
    assert aliyun.calls == 0
    assert read_usage(database, "mymemory") == (0, 1, 1)
    assert read_usage(database, "tencent") == (12, 1, 0)


def test_translation_skips_provider_past_ninety_percent_budget(monkeypatch):
    service, _database = make_service(monkeypatch)
    mymemory = FakeProvider("mymemory", "不应调用", budget=10, quota_period="daily")
    tencent = FakeProvider("tencent", "腾讯译文", budget=100)
    service._providers = [mymemory, tencent]
    service._upsert_usage(mymemory.runtime, used_characters=9, request_count=1, failed_count=0)

    response = asyncio.run(service.translate(["OpenAI model"], "zh"))

    assert response.items[0].translated_text == "腾讯译文"
    assert mymemory.calls == 0
    assert tencent.calls == 1


def test_mymemory_usage_is_counted_by_day(monkeypatch):
    service, database = make_service(monkeypatch)
    provider = FakeProvider("mymemory", "你好", budget=100, quota_period="daily")
    service._providers = [provider]

    response = asyncio.run(service.translate(["Hello"], "zh"))

    assert response.items[0].translated_text == "你好"
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT year_month, used_characters
            FROM translation_usage_monthly
            WHERE provider = 'mymemory'
            """
        ).fetchone()
    assert row is not None
    assert len(row["year_month"]) == 10
    assert row["used_characters"] == 5


def test_cloud_provider_usage_is_counted_by_month(monkeypatch):
    service, database = make_service(monkeypatch)
    provider = FakeProvider("tencent", "你好", budget=100, quota_period="monthly")
    service._providers = [provider]

    response = asyncio.run(service.translate(["Hello"], "zh"))

    assert response.items[0].translated_text == "你好"
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT year_month, used_characters
            FROM translation_usage_monthly
            WHERE provider = 'tencent'
            """
        ).fetchone()
    assert row is not None
    assert len(row["year_month"]) == 7
    assert row["used_characters"] == 5


def test_translation_raises_when_all_providers_are_exhausted(monkeypatch):
    service, _database = make_service(monkeypatch)
    service._providers = [FakeProvider("mymemory", "不应调用", budget=1)]

    with pytest.raises(TranslationQuotaExhausted):
        asyncio.run(service.translate(["OpenAI model"], "zh"))


def test_same_language_translation_does_not_spend_quota(monkeypatch):
    service, database = make_service(monkeypatch)
    provider = FakeProvider("mymemory", "不应调用")
    service._providers = [provider]

    response = asyncio.run(service.translate(["中文标题"], "zh"))

    assert response.items[0].translated_text == "中文标题"
    assert provider.calls == 0
    assert read_usage(database, "mymemory") == (0, 0, 0)
