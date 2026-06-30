import type { LanguageMode, NewsListResponse, PublicConfig, RefreshResponse, RefreshStatus, SearchResponse, TranslationResponse } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export class TranslationQuotaExceededError extends Error {
  constructor() {
    super('额度已耗尽，请使用浏览器自带翻译');
    this.name = 'TranslationQuotaExceededError';
  }
}

export class ManualRefreshLimitError extends Error {
  constructor() {
    super('刷新次数已达到本小时上限');
    this.name = 'ManualRefreshLimitError';
  }
}

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const detail = typeof payload === 'object' && payload !== null && 'detail' in payload ? (payload as { detail?: unknown }).detail : null;
    if (
      response.status === 429 &&
      typeof detail === 'object' &&
      detail !== null &&
      'code' in detail &&
      (detail as { code?: string }).code === 'translation_quota_exhausted'
    ) {
      throw new TranslationQuotaExceededError();
    }
    if (
      response.status === 429 &&
      typeof detail === 'object' &&
      detail !== null &&
      'code' in detail &&
      (detail as { code?: string }).code === 'manual_refresh_hourly_limit_exceeded'
    ) {
      throw new ManualRefreshLimitError();
    }
    const detailMessage =
      typeof detail === 'object' &&
      detail !== null &&
      'message' in detail &&
      typeof (detail as { message?: unknown }).message === 'string'
        ? (detail as { message: string }).message
        : '';
    throw new ApiRequestError(response.status, detailMessage || `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchPublicConfig(): Promise<PublicConfig> {
  return request<PublicConfig>('/api/config');
}

export function fetchNews(): Promise<NewsListResponse> {
  return request<NewsListResponse>('/api/news?page=1&page_size=100');
}

export function searchNews(query: string): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, page: '1', page_size: '40' });
  return request<SearchResponse>(`/api/search?${params.toString()}`);
}

export function refreshNews(): Promise<RefreshResponse> {
  return request<RefreshResponse>('/api/refresh', { method: 'POST' });
}

export function fetchRefreshStatus(): Promise<RefreshStatus> {
  return request<RefreshStatus>('/api/refresh/status');
}

export function translateTexts(texts: string[], targetLanguage: Exclude<LanguageMode, 'auto'>): Promise<TranslationResponse> {
  return request<TranslationResponse>('/api/translate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      target_language: targetLanguage,
      texts
    })
  });
}
