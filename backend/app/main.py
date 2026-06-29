from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Database
from .schemas import NewsListResponse, PublicConfigResponse, RefreshResponse, RefreshStatusResponse, SearchResponse, TranslationRequest, TranslationResponse
from .services import NewsService
from .translation import TranslationQuotaExhausted, TranslationService


settings = get_settings()
database = Database(settings.database_path)
news_service = NewsService(database, settings)
translation_service = TranslationService(database, settings)
logger = logging.getLogger(__name__)
manual_refresh_tasks: set[asyncio.Task] = set()


async def run_manual_refresh() -> None:
    try:
        await news_service.refresh()
    except Exception:
        logger.exception("Manual background refresh failed")


def queue_manual_refresh() -> None:
    task = asyncio.create_task(run_manual_refresh())
    manual_refresh_tasks.add(task)
    task.add_done_callback(manual_refresh_tasks.discard)


async def scheduler_loop() -> None:
    while True:
        await asyncio.sleep(seconds_until_next_refresh(scheduler_now(), settings.news_refresh_times))
        await news_service.refresh()


def scheduler_now() -> datetime:
    try:
        configured_timezone = ZoneInfo(settings.news_refresh_timezone)
    except ZoneInfoNotFoundError:
        if settings.news_refresh_timezone == "Asia/Shanghai":
            configured_timezone = timezone(timedelta(hours=8), "Asia/Shanghai")
        else:
            configured_timezone = datetime.now().astimezone().tzinfo
    return datetime.now(configured_timezone)


def next_refresh_at(now: datetime, refresh_times: list[str]) -> datetime:
    for refresh_time in refresh_times:
        hour, minute = [int(part) for part in refresh_time.split(":", 1)]
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate
    first_hour, first_minute = [int(part) for part in refresh_times[0].split(":", 1)]
    return (now + timedelta(days=1)).replace(hour=first_hour, minute=first_minute, second=0, microsecond=0)


def seconds_until_next_refresh(now: datetime, refresh_times: list[str]) -> float:
    return max((next_refresh_at(now, refresh_times) - now).total_seconds(), 0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    news_service.init()
    news_service.prune_old_news()
    task: asyncio.Task | None = None
    if not settings.disable_scheduler:
        task = asyncio.create_task(scheduler_loop())
    try:
        yield
    finally:
        if task:
            task.cancel()
        for refresh_task in manual_refresh_tasks:
            refresh_task.cancel()


app = FastAPI(title="AI News Aggregator", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config", response_model=PublicConfigResponse)
def public_config() -> PublicConfigResponse:
    return PublicConfigResponse(
        special_link_url=settings.special_link_url,
        site_icp_number=settings.site_icp_number,
        site_copyright_owner=settings.site_copyright_owner,
        site_copyright_text=settings.site_copyright_text,
    )


@app.get("/api/news", response_model=NewsListResponse)
def list_news(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    date_from: str | None = None,
    date_to: str | None = None,
) -> NewsListResponse:
    return news_service.list_news(page=page, page_size=page_size, date_from=date_from, date_to=date_to)


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> SearchResponse:
    return news_service.search(query=q, page=page, page_size=page_size)


@app.get("/api/refresh/status", response_model=RefreshStatusResponse)
def refresh_status() -> RefreshStatusResponse:
    return news_service.refresh_status()


@app.post("/api/refresh", response_model=RefreshResponse)
async def refresh() -> RefreshResponse:
    recorded, _status = news_service.record_manual_refresh()
    if not recorded:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "manual_refresh_hourly_limit_exceeded",
                "message": "刷新次数已达到本小时上限",
            },
        )
    queue_manual_refresh()
    return RefreshResponse(fetched=0, inserted=0, clustered=0, queued=True)


@app.post("/api/translate", response_model=TranslationResponse)
async def translate(payload: TranslationRequest) -> TranslationResponse:
    try:
        return await translation_service.translate(payload.texts, payload.target_language)
    except TranslationQuotaExhausted as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "translation_quota_exhausted",
                "message": "额度已耗尽，请使用浏览器自带翻译",
            },
        ) from exc
