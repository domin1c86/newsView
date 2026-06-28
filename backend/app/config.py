from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RssSourceConfig:
    name: str
    url: str


@dataclass(frozen=True)
class Settings:
    database_path: str
    cors_origins: list[str]
    news_refresh_times: list[str]
    news_refresh_timezone: str
    news_retention_days: int
    special_link_url: str
    site_icp_number: str | None
    site_copyright_owner: str | None
    site_copyright_text: str | None
    manual_refresh_hourly_limit: int
    rss_sources: list[RssSourceConfig]
    news_queries: list[str]
    api_provider: str
    api_providers: list[str]
    gnews_api_key: str | None
    gnews_endpoint: str
    thenewsapi_api_key: str | None
    thenewsapi_endpoint: str
    currents_api_key: str | None
    currents_endpoint: str
    newsapi_api_key: str | None
    newsapi_endpoint: str
    guardian_api_key: str | None
    guardian_endpoint: str
    hn_algolia_endpoint: str
    translation_providers: list[str]
    translation_stop_at_ratio: float
    translation_billing_timezone: str
    mymemory_endpoint: str
    mymemory_email: str | None
    mymemory_daily_char_budget: int | None
    mymemory_requests_per_second: float
    tencent_translate_secret_id: str | None
    tencent_translate_secret_key: str | None
    tencent_translate_region: str
    tencent_translate_endpoint: str
    tencent_translate_project_id: int
    tencent_translate_monthly_char_budget: int | None
    tencent_translate_requests_per_second: float
    aliyun_translate_access_key_id: str | None
    aliyun_translate_access_key_secret: str | None
    aliyun_translate_region: str
    aliyun_translate_endpoint: str
    aliyun_translate_scene: str
    aliyun_translate_monthly_char_budget: int | None
    aliyun_translate_requests_per_second: float
    volcengine_translate_access_key_id: str | None
    volcengine_translate_secret_access_key: str | None
    volcengine_translate_region: str
    volcengine_translate_endpoint: str
    volcengine_translate_monthly_char_budget: int | None
    volcengine_translate_requests_per_second: float
    azure_translator_key: str | None
    azure_translator_region: str | None
    azure_translator_endpoint: str
    azure_translator_monthly_char_budget: int | None
    azure_translator_requests_per_second: float
    disable_scheduler: bool


DEFAULT_RSS_SOURCES = (
    "MIT Technology Review AI|https://www.technologyreview.com/topic/artificial-intelligence/feed/,"
    "VentureBeat AI|https://venturebeat.com/category/ai/feed/,"
    "The Decoder|https://the-decoder.com/feed/,"
    "TechCrunch AI|https://techcrunch.com/category/artificial-intelligence/feed/,"
    "OpenAI News|https://openai.com/news/rss.xml,"
    "Google AI Blog|https://blog.google/technology/ai/rss/,"
    "GitHub AI and ML|https://github.blog/ai-and-ml/feed/,"
    "AWS Machine Learning|https://aws.amazon.com/blogs/machine-learning/feed/,"
    "Hugging Face Blog|https://huggingface.co/blog/feed.xml,"
    "NVIDIA Generative AI|https://nvidianews.nvidia.com/cats/generative_al.xml,"
    "NVIDIA Models Libraries Frameworks|https://nvidianews.nvidia.com/cats/models_libraries_frameworks.xml,"
    "arXiv cs.AI|https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=20,"
    "arXiv cs.CL|https://export.arxiv.org/api/query?search_query=cat:cs.CL&sortBy=submittedDate&sortOrder=descending&max_results=20,"
    "HN AI Newest|https://hnrss.org/newest?q=AI+OR+LLM+OR+OpenAI+OR+Claude+OR+Nvidia&points=20,"
    "机器之心|https://www.jiqizhixin.com/rss,"
    "量子位|https://www.qbitai.com/feed,"
    "InfoQ 中文 AI|https://www.infoq.cn/feed,"
    "AI科技评论 RSSHub|https://rsshub.app/leiphone/category/ai,"
    "36氪人工智能 RSSHub|https://rsshub.app/36kr/newsflashes,"
    "虎嗅科技 RSSHub|https://rsshub.app/huxiu/article,"
    "Daily Juya|https://daily.juya.uk/rss.xml"
)


DEFAULT_NEWS_QUERIES = (
    "AI large language model OR multimodal model,"
    "AI applications OR AI agents OR enterprise AI,"
    "AI compute GPU Nvidia data center,"
    "AI data copyright dataset training data,"
    "AI hardware device chip Apple price increase,"
    "AI startup funding acquisition investment,"
    "AI policy regulation safety governance"
)


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(value)


def _optional_str(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def _parse_refresh_times(value: str) -> list[str]:
    times: list[str] = []
    for part in _split_csv(value):
        hour, minute = part.split(":", 1)
        normalized = f"{int(hour):02d}:{int(minute):02d}"
        if normalized not in times:
            times.append(normalized)
    return sorted(times)


def _parse_rss_sources(value: str) -> list[RssSourceConfig]:
    sources: list[RssSourceConfig] = []
    for entry in _split_csv(value):
        if "|" in entry:
            name, url = entry.split("|", 1)
            sources.append(RssSourceConfig(name=name.strip(), url=url.strip()))
        else:
            sources.append(RssSourceConfig(name=entry.strip(), url=entry.strip()))
    return sources


def get_settings() -> Settings:
    api_provider = os.getenv("NEWS_API_PROVIDER", "hackernews").strip().lower()
    api_providers = _split_csv(os.getenv("NEWS_API_PROVIDERS", api_provider))
    return Settings(
        database_path=os.getenv("DATABASE_PATH", "./data/news.db"),
        cors_origins=_split_csv(os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")),
        news_refresh_times=_parse_refresh_times(os.getenv("NEWS_REFRESH_TIMES", "07:00,09:00,12:00,18:00,20:00,22:00")),
        news_refresh_timezone=os.getenv("NEWS_REFRESH_TIMEZONE", os.getenv("TZ", "Asia/Shanghai")),
        news_retention_days=int(os.getenv("NEWS_RETENTION_DAYS", "7")),
        special_link_url=os.getenv("SPECIAL_LINK_URL", "https://bing.com"),
        site_icp_number=_optional_str(os.getenv("SITE_ICP_NUMBER")),
        site_copyright_owner=_optional_str(os.getenv("SITE_COPYRIGHT_OWNER")),
        site_copyright_text=_optional_str(os.getenv("SITE_COPYRIGHT_TEXT")),
        manual_refresh_hourly_limit=int(os.getenv("MANUAL_REFRESH_HOURLY_LIMIT", "10")),
        rss_sources=_parse_rss_sources(os.getenv("RSS_SOURCES", DEFAULT_RSS_SOURCES)),
        news_queries=_split_csv(os.getenv("NEWS_QUERIES", DEFAULT_NEWS_QUERIES)),
        api_provider=api_provider,
        api_providers=[provider.strip().lower() for provider in api_providers],
        gnews_api_key=os.getenv("GNEWS_API_KEY") or None,
        gnews_endpoint=os.getenv("GNEWS_ENDPOINT", "https://gnews.io/api/v4/search"),
        thenewsapi_api_key=os.getenv("THENEWSAPI_API_KEY") or None,
        thenewsapi_endpoint=os.getenv("THENEWSAPI_ENDPOINT", "https://api.thenewsapi.com/v1/news/all"),
        currents_api_key=os.getenv("CURRENTS_API_KEY") or None,
        currents_endpoint=os.getenv("CURRENTS_ENDPOINT", "https://api.currentsapi.services/v1/search"),
        newsapi_api_key=os.getenv("NEWSAPI_API_KEY") or None,
        newsapi_endpoint=os.getenv("NEWSAPI_ENDPOINT", "https://newsapi.org/v2/everything"),
        guardian_api_key=os.getenv("GUARDIAN_API_KEY") or None,
        guardian_endpoint=os.getenv("GUARDIAN_ENDPOINT", "https://content.guardianapis.com/search"),
        hn_algolia_endpoint=os.getenv("HN_ALGOLIA_ENDPOINT", "https://hn.algolia.com/api/v1/search_by_date"),
        translation_providers=[
            provider.strip().lower()
            for provider in _split_csv(os.getenv("TRANSLATION_PROVIDERS", os.getenv("TRANSLATION_PROVIDER", "mymemory")))
        ],
        translation_stop_at_ratio=float(os.getenv("TRANSLATION_STOP_AT_RATIO", "0.9")),
        translation_billing_timezone=os.getenv("TRANSLATION_BILLING_TIMEZONE", "Asia/Shanghai"),
        mymemory_endpoint=os.getenv("MYMEMORY_ENDPOINT", os.getenv("TRANSLATION_ENDPOINT", "https://api.mymemory.translated.net/get")),
        mymemory_email=_optional_str(os.getenv("MYMEMORY_EMAIL")),
        mymemory_daily_char_budget=_optional_int(
            os.getenv("MYMEMORY_DAILY_CHAR_BUDGET")
            or os.getenv("MYMEMORY_DAYLY_CHAR_BUDGET")
            or os.getenv("MYMEMORY_MONTHLY_CHAR_BUDGET")
            or "50000"
        ),
        mymemory_requests_per_second=float(os.getenv("MYMEMORY_REQUESTS_PER_SECOND", "1")),
        tencent_translate_secret_id=_optional_str(os.getenv("TENCENT_TRANSLATE_SECRET_ID")),
        tencent_translate_secret_key=_optional_str(os.getenv("TENCENT_TRANSLATE_SECRET_KEY")),
        tencent_translate_region=os.getenv("TENCENT_TRANSLATE_REGION", "ap-guangzhou"),
        tencent_translate_endpoint=os.getenv("TENCENT_TRANSLATE_ENDPOINT", "https://tmt.tencentcloudapi.com"),
        tencent_translate_project_id=int(os.getenv("TENCENT_TRANSLATE_PROJECT_ID", "0")),
        tencent_translate_monthly_char_budget=_optional_int(os.getenv("TENCENT_TRANSLATE_MONTHLY_CHAR_BUDGET")),
        tencent_translate_requests_per_second=float(os.getenv("TENCENT_TRANSLATE_REQUESTS_PER_SECOND", "5")),
        aliyun_translate_access_key_id=_optional_str(os.getenv("ALIYUN_TRANSLATE_ACCESS_KEY_ID")),
        aliyun_translate_access_key_secret=_optional_str(os.getenv("ALIYUN_TRANSLATE_ACCESS_KEY_SECRET")),
        aliyun_translate_region=os.getenv("ALIYUN_TRANSLATE_REGION", "cn-hangzhou"),
        aliyun_translate_endpoint=os.getenv("ALIYUN_TRANSLATE_ENDPOINT", "mt.cn-hangzhou.aliyuncs.com"),
        aliyun_translate_scene=os.getenv("ALIYUN_TRANSLATE_SCENE", "general"),
        aliyun_translate_monthly_char_budget=_optional_int(os.getenv("ALIYUN_TRANSLATE_MONTHLY_CHAR_BUDGET")),
        aliyun_translate_requests_per_second=float(os.getenv("ALIYUN_TRANSLATE_REQUESTS_PER_SECOND", "5")),
        volcengine_translate_access_key_id=_optional_str(os.getenv("VOLCENGINE_TRANSLATE_ACCESS_KEY_ID")),
        volcengine_translate_secret_access_key=_optional_str(os.getenv("VOLCENGINE_TRANSLATE_SECRET_ACCESS_KEY")),
        volcengine_translate_region=os.getenv("VOLCENGINE_TRANSLATE_REGION", "cn-north-1"),
        volcengine_translate_endpoint=os.getenv("VOLCENGINE_TRANSLATE_ENDPOINT", "https://open.volcengineapi.com"),
        volcengine_translate_monthly_char_budget=_optional_int(os.getenv("VOLCENGINE_TRANSLATE_MONTHLY_CHAR_BUDGET")),
        volcengine_translate_requests_per_second=float(os.getenv("VOLCENGINE_TRANSLATE_REQUESTS_PER_SECOND", "5")),
        azure_translator_key=_optional_str(os.getenv("AZURE_TRANSLATOR_KEY")),
        azure_translator_region=_optional_str(os.getenv("AZURE_TRANSLATOR_REGION")),
        azure_translator_endpoint=os.getenv("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com"),
        azure_translator_monthly_char_budget=_optional_int(os.getenv("AZURE_TRANSLATOR_MONTHLY_CHAR_BUDGET", "2000000")),
        azure_translator_requests_per_second=float(os.getenv("AZURE_TRANSLATOR_REQUESTS_PER_SECOND", "5")),
        disable_scheduler=os.getenv("DISABLE_SCHEDULER", "false").strip().lower() in {"1", "true", "yes"},
    )
