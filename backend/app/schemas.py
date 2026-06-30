from __future__ import annotations

from pydantic import BaseModel


class NewsSourceItem(BaseModel):
    source_name: str
    title: str
    summary: str
    content: str
    url: str
    published_at: str


class NewsCluster(BaseModel):
    id: str
    title: str
    summary: str
    published_at: str
    keywords: list[str]
    source_count: int
    primary_url: str
    sources: list[NewsSourceItem]


class NewsListResponse(BaseModel):
    items: list[NewsCluster]
    page: int
    page_size: int
    total: int


class SearchResponse(NewsListResponse):
    query: str
    keywords: list[str]
    special_link: str | None


class RefreshResponse(BaseModel):
    fetched: int
    inserted: int
    clustered: int
    queued: bool = False


class PublicConfigResponse(BaseModel):
    special_link_url: str
    site_icp_number: str | None
    site_copyright_owner: str | None
    site_copyright_text: str | None


class RefreshStatusResponse(BaseModel):
    used: int
    limit: int
    remaining: int
    window_ends_at: str


class TranslationRequest(BaseModel):
    target_language: str
    texts: list[str]


class TranslationItem(BaseModel):
    original_text: str
    translated_text: str
    source_language: str
    target_language: str


class TranslationResponse(BaseModel):
    target_language: str
    items: list[TranslationItem]
