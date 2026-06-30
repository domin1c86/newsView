export interface NewsSourceItem {
  source_name: string;
  title: string;
  summary: string;
  content: string;
  url: string;
  published_at: string;
}

export interface NewsCluster {
  id: string;
  title: string;
  title_language: 'zh' | 'en' | 'unknown' | null;
  summary: string;
  published_at: string;
  keywords: string[];
  source_count: number;
  primary_url: string;
  sources: NewsSourceItem[];
}

export interface NewsListResponse {
  items: NewsCluster[];
  page: number;
  page_size: number;
  total: number;
}

export interface SearchResponse extends NewsListResponse {
  query: string;
  keywords: string[];
  special_link: string | null;
}

export interface PublicConfig {
  special_link_url: string;
  site_icp_number: string | null;
  site_copyright_owner: string | null;
  site_copyright_text: string | null;
}

export interface RefreshStatus {
  used: number;
  limit: number;
  remaining: number;
  window_ends_at: string;
}

export interface RefreshResponse {
  fetched: number;
  inserted: number;
  clustered: number;
  queued: boolean;
}

export type LanguageMode = 'auto' | 'zh' | 'en';

export interface TranslationItem {
  original_text: string;
  translated_text: string;
  source_language: string;
  target_language: string;
}

export interface TranslationResponse {
  target_language: string;
  items: TranslationItem[];
}
