import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import {
  Bell,
  Bookmark,
  Box,
  Brain,
  Check,
  Cpu,
  Database,
  ExternalLink,
  Flame,
  Grid2X2,
  Heart,
  Languages,
  Newspaper,
  RefreshCw,
  Search,
  Settings,
  Shield,
  SlidersHorizontal,
  Sparkles,
  X,
  Zap
} from 'lucide-react';
import {
  fetchNews,
  fetchPublicConfig,
  fetchRefreshStatus,
  ManualRefreshLimitError,
  refreshNews,
  searchNews,
  translateTexts,
  TranslationQuotaExceededError
} from './api';
import type { LanguageMode, NewsCluster, NewsListResponse, PublicConfig, RefreshStatus, SearchResponse } from './types';

const SPECIAL_TRIGGER = '老岳中转';
const DEFAULT_PUBLIC_CONFIG: PublicConfig = {
  special_link_url: 'https://bing.com',
  site_icp_number: null,
  site_copyright_owner: null,
  site_copyright_text: null
};
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

type LoadState = 'idle' | 'loading' | 'error';
type PrimaryView = 'latest' | 'hot' | 'followed' | 'saved';
type UtilityView = 'sources' | 'settings';
type ActiveView = PrimaryView | UtilityView;
type TopbarPanel = 'filters' | 'notifications' | null;

interface GroupedNews {
  label: string;
  items: NewsCluster[];
}

interface TopicNavItem {
  label: string;
  icon: typeof Brain;
  terms: string[];
}

interface SourceStat {
  name: string;
  domain: string;
  count: number;
  latestAt: string;
}

function formatDateLabel(value: string): string {
  const date = new Date(value);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${month} - ${day}, ${WEEKDAYS[date.getDay()]}`;
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  });
}

function formatSourceDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function groupByDate(items: NewsCluster[]): GroupedNews[] {
  const groups = new Map<string, NewsCluster[]>();
  for (const item of items) {
    const label = formatDateLabel(item.published_at);
    groups.set(label, [...(groups.get(label) ?? []), item]);
  }
  return Array.from(groups.entries()).map(([label, groupedItems]) => ({ label, items: groupedItems }));
}

function hasSearchKeywords(data: NewsListResponse | SearchResponse): data is SearchResponse {
  return Array.isArray((data as SearchResponse).keywords);
}

function displayKeywords(keywords: string[], limit = 6): string[] {
  const blocked = new Set(['porn']);
  return keywords.filter((keyword) => !blocked.has(keyword.toLowerCase())).slice(0, limit);
}

const primaryNav = [
  { id: 'latest', label: '最新', icon: Sparkles },
  { id: 'hot', label: '热门', icon: Flame },
  { id: 'followed', label: '关注', icon: Heart },
  { id: 'saved', label: '稍后读', icon: Bookmark }
] satisfies Array<{ id: PrimaryView; label: string; icon: typeof Sparkles }>;

const utilityNav = [
  { id: 'sources', label: '来源', icon: Newspaper },
  { id: 'settings', label: '设置', icon: Settings }
] satisfies Array<{ id: UtilityView; label: string; icon: typeof Newspaper }>;

const topicNav: TopicNavItem[] = [
  { label: '大模型', icon: Brain, terms: ['大模型', '模型', 'llm', 'gpt', 'claude', 'gemini', 'llama', 'openai', 'anthropic'] },
  { label: '应用', icon: Grid2X2, terms: ['应用', 'agent', 'agents', '智能体', '助手', '产品', 'chatbot', 'copilot', '客服', '财务'] },
  { label: '算力', icon: Cpu, terms: ['算力', 'gpu', 'nvidia', '芯片', 'blackwell', 'cuda', '训练', '推理', '数据中心', '服务器'] },
  { label: '数据', icon: Database, terms: ['数据', 'dataset', '语料', '合成数据', '标注', '版权', '授权数据', '训练数据', '数据采购'] },
  { label: '硬件', icon: Box, terms: ['硬件', '设备', '终端', '端侧', '端侧ai', 'apple', '苹果', '涨价', '成本', '内存', '散热', 'robot', '机器人', '芯片', '服务器'] },
  { label: '投融资', icon: Zap, terms: ['融资', '投资', '估值', '收购', '并购', 'funding', 'venture', '创业公司', '基础设施'] },
  { label: '政策', icon: Shield, terms: ['政策', '监管', '法规', '法案', '治理', '审查', '安全', '欧盟', '白宫'] }
];

function getSearchText(item: NewsCluster): string {
  return `${item.title} ${item.summary} ${item.keywords.join(' ')} ${item.sources.map((source) => source.source_name).join(' ')}`.toLowerCase();
}

function matchesTopic(item: NewsCluster, topic: TopicNavItem): boolean {
  const text = getSearchText(item);
  return topic.terms.some((term) => text.includes(term.toLowerCase()));
}

function getStoredList(key: string, fallback: string[]): string[] {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((value) => typeof value === 'string') : fallback;
  } catch {
    return fallback;
  }
}

function getStoredString<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  try {
    const value = window.localStorage.getItem(key) as T | null;
    return value && allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function collectTranslatableTexts(items: NewsCluster[]): string[] {
  const texts: string[] = [];
  for (const item of items) {
    texts.push(item.title, item.summary);
    for (const source of item.sources) {
      texts.push(source.title);
    }
  }
  return listUnique(texts.filter((text) => text.trim()));
}

function listUnique(values: string[]): string[] {
  return Array.from(new Set(values));
}

function applyTranslations(item: NewsCluster, translations: Record<string, string>): NewsCluster {
  return {
    ...item,
    title: translations[item.title] || item.title,
    summary: translations[item.summary] || item.summary,
    sources: item.sources.map((source) => ({
      ...source,
      title: translations[source.title] || source.title
    }))
  };
}

function languageLabel(language: LanguageMode): string {
  if (language === 'zh') return '中文';
  if (language === 'en') return 'English';
  return '自动';
}

function collectSourceStats(items: NewsCluster[]): SourceStat[] {
  const stats = new Map<string, SourceStat>();
  for (const item of items) {
    for (const source of item.sources) {
      const existing = stats.get(source.source_name);
      if (!existing) {
        stats.set(source.source_name, {
          name: source.source_name,
          domain: formatSourceDomain(source.url),
          count: 1,
          latestAt: source.published_at
        });
        continue;
      }
      existing.count += 1;
      if (new Date(source.published_at).getTime() > new Date(existing.latestAt).getTime()) {
        existing.latestAt = source.published_at;
      }
    }
  }
  return Array.from(stats.values()).sort((a, b) => b.count - a.count || new Date(b.latestAt).getTime() - new Date(a.latestAt).getTime());
}

function Sidebar({
  activeView,
  activeTopic,
  onSelectView,
  onSelectTopic
}: {
  activeView: ActiveView;
  activeTopic: string | null;
  onSelectView: (view: ActiveView) => void;
  onSelectTopic: (topic: string) => void;
}) {
  return (
    <aside className="sidebar" aria-label="应用导航">
      <div className="brand-mark" aria-label="AI 快讯">
        <span>AI</span>
        <strong>快讯</strong>
      </div>

      <nav className="nav-section" aria-label="新闻视图">
        {primaryNav.map((item) => {
          const Icon = item.icon;
          return (
            <button type="button" className={`nav-item${activeView === item.id ? ' active' : ''}`} key={item.label} onClick={() => onSelectView(item.id)}>
              <Icon size={18} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="nav-group-label">主题</div>
      <nav className="nav-section" aria-label="主题筛选">
        {topicNav.map((item) => {
          const Icon = item.icon;
          return (
            <button type="button" className={`nav-item${activeTopic === item.label ? ' active' : ''}`} key={item.label} onClick={() => onSelectTopic(item.label)}>
              <Icon size={18} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <nav className="nav-section nav-footer" aria-label="辅助入口">
        {utilityNav.map((item) => {
          const Icon = item.icon;
          return (
            <button type="button" className={`nav-item${activeView === item.id ? ' active' : ''}`} key={item.label} onClick={() => onSelectView(item.id)}>
              <Icon size={18} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-version">
        <span>关于</span>
        <span>v1.0.0</span>
      </div>
    </aside>
  );
}

function NewsCard({
  item,
  saved,
  onOpen,
  onToggleSaved
}: {
  item: NewsCluster;
  saved: boolean;
  onOpen: (item: NewsCluster) => void;
  onToggleSaved: (id: string) => void;
}) {
  function handleKeyDown(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onOpen(item);
    }
  }

  return (
    <article
      className="news-card"
      role="button"
      tabIndex={0}
      onClick={() => onOpen(item)}
      onKeyDown={handleKeyDown}
      aria-label={`打开新闻：${item.title}`}
    >
      <h2>{item.title}</h2>
      <div className="card-meta">
        <span>{formatTime(item.published_at)}</span>
        <span>{displayKeywords(item.keywords, 1)[0] || 'AI'}</span>
        <span>{item.sources[0]?.source_name || 'AI快讯'}</span>
      </div>
      <p className="summary">{item.summary || '暂无摘要，点击原文查看完整内容。'}</p>
      <div className="keyword-row">
        {displayKeywords(item.keywords, 3).map((keyword) => (
          <span key={keyword}>{keyword}</span>
        ))}
      </div>
      <div className="card-actions">
        <span>{item.source_count} 来源</span>
        <button
          type="button"
          className={`bookmark-button${saved ? ' saved' : ''}`}
          onClick={(event) => {
            event.stopPropagation();
            onToggleSaved(item.id);
          }}
          aria-label={saved ? `从稍后读移除：${item.title}` : `加入稍后读：${item.title}`}
        >
          <Bookmark size={19} aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}

function NewsModal({
  item,
  saved,
  onClose,
  onToggleSaved
}: {
  item: NewsCluster;
  saved: boolean;
  onClose: () => void;
  onToggleSaved: (id: string) => void;
}) {
  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
      }
    }
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="news-modal" role="dialog" aria-modal="true" aria-labelledby="news-modal-title" onClick={(event) => event.stopPropagation()}>
        <button type="button" className="modal-close" onClick={onClose} aria-label="关闭弹窗">
          <X size={24} aria-hidden="true" />
        </button>

        <div className="modal-kicker">{displayKeywords(item.keywords, 1)[0] || 'AI 新闻'}</div>

        <header className="modal-header">
          <div>
            <h2 id="news-modal-title">{item.title}</h2>
            <div className="modal-meta">
              <span>AI快讯</span>
              <span>{formatTime(item.published_at)}</span>
              <span>{item.source_count} 来源</span>
            </div>
          </div>
          <button type="button" className={`read-later-button${saved ? ' saved' : ''}`} onClick={() => onToggleSaved(item.id)}>
            <Bookmark size={18} aria-hidden="true" />
            {saved ? '已稍后读' : '稍后读'}
          </button>
        </header>

        <div className="modal-content">
          <h3>摘要</h3>
          <p>{item.summary || '暂无摘要，请打开原文查看完整内容。'}</p>
        </div>

        <div className="modal-content modal-points">
          <h3>关键要点</h3>
          <ul>
            {displayKeywords(item.keywords, 4).map((keyword) => (
              <li key={keyword}>
                <strong>{keyword}</strong>
                <span>相关报道已被合并到同一事件，可从下方来源继续阅读全文。</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="modal-section">
          <h3>来源 ({item.source_count})</h3>
          <div className="source-list">
            {item.sources.map((source) => (
              <a key={`${source.url}-${source.source_name}`} href={source.url} target="_blank" rel="noreferrer">
                <span className="source-logo">{source.source_name.slice(0, 1).toUpperCase()}</span>
                <span className="source-copy">
                  <strong>{source.source_name}</strong>
                  <small>{formatSourceDomain(source.url)}</small>
                  <em>{source.title}</em>
                </span>
                <time>{formatTime(source.published_at)}</time>
                <span className="source-link">
                  原文链接
                  <ExternalLink size={13} aria-hidden="true" />
                </span>
              </a>
            ))}
          </div>
        </div>

        <div className="modal-footer">
          <a href={item.primary_url} target="_blank" rel="noreferrer" className="primary-link">
            查看代表原文
            <ExternalLink size={16} aria-hidden="true" />
          </a>
        </div>
      </section>
    </div>
  );
}

export function App() {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<NewsCluster[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [status, setStatus] = useState<LoadState>('idle');
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [publicConfig, setPublicConfig] = useState<PublicConfig>(DEFAULT_PUBLIC_CONFIG);
  const [refreshStatus, setRefreshStatus] = useState<RefreshStatus | null>(null);
  const [selectedItem, setSelectedItem] = useState<NewsCluster | null>(null);
  const [activeView, setActiveView] = useState<ActiveView>('latest');
  const [activeTopic, setActiveTopic] = useState<string | null>(null);
  const [activeSource, setActiveSource] = useState<string | null>(null);
  const [savedIds, setSavedIds] = useState<string[]>(() => getStoredList('ai-news-saved', []));
  const [followedTopics, setFollowedTopics] = useState<string[]>(() => getStoredList('ai-news-followed-topics', ['大模型', '应用']));
  const [languageMode, setLanguageMode] = useState<LanguageMode>(() => getStoredString<LanguageMode>('ai-news-language', 'auto', ['auto', 'zh', 'en']));
  const [topbarPanel, setTopbarPanel] = useState<TopbarPanel>(null);
  const [showLanguageDialog, setShowLanguageDialog] = useState(false);
  const [translationMap, setTranslationMap] = useState<Record<string, string>>({});
  const [translating, setTranslating] = useState(false);
  const [translationError, setTranslationError] = useState('');
  const [showQuotaDialog, setShowQuotaDialog] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const didRunInitialSearch = useRef(false);
  const showSpecialLink = query.includes(SPECIAL_TRIGGER);

  useEffect(() => {
    let active = true;
    setStatus('loading');
    Promise.allSettled([fetchPublicConfig(), fetchRefreshStatus(), fetchNews()])
      .then((results) => {
        if (!active) return null;
        const [configResult, refreshStatusResult, newsResult] = results;
        if (configResult.status === 'fulfilled') {
          setPublicConfig(configResult.value);
        }
        if (refreshStatusResult.status === 'fulfilled') {
          setRefreshStatus(refreshStatusResult.value);
        }
        if (newsResult.status === 'rejected') {
          throw newsResult.reason;
        }
        return newsResult.value;
      })
      .then((data) => {
        if (!data) return;
        if (!active) return;
        setItems(data.items);
        setKeywords([]);
        setLastUpdatedAt(new Date().toISOString());
        setStatus('idle');
      })
      .catch((err: Error) => {
        if (!active) return;
        setError(err.message);
        setStatus('error');
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!didRunInitialSearch.current) {
      didRunInitialSearch.current = true;
      return;
    }
    const trimmed = query.trim();
    const timer = window.setTimeout(() => {
      setStatus('loading');
      const request = trimmed ? searchNews(trimmed) : fetchNews();
      request
        .then((data) => {
          setItems(data.items);
          setKeywords(hasSearchKeywords(data) ? data.keywords : []);
          setLastUpdatedAt(new Date().toISOString());
          setStatus('idle');
          setError('');
        })
        .catch((err: Error) => {
          setError(err.message);
          setStatus('error');
        });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    window.localStorage.setItem('ai-news-saved', JSON.stringify(savedIds));
  }, [savedIds]);

  useEffect(() => {
    if (!lastUpdatedAt || query.trim() || status === 'loading') return;
    const currentItemIds = new Set(items.map((item) => item.id));
    setSavedIds((current) => current.filter((id) => currentItemIds.has(id)));
  }, [items, lastUpdatedAt, query, status]);

  useEffect(() => {
    window.localStorage.setItem('ai-news-followed-topics', JSON.stringify(followedTopics));
  }, [followedTopics]);

  useEffect(() => {
    window.localStorage.setItem('ai-news-language', languageMode);
  }, [languageMode]);

  useEffect(() => {
    if (!showQuotaDialog) return;
    const timer = window.setTimeout(() => setShowQuotaDialog(false), 3000);
    return () => window.clearTimeout(timer);
  }, [showQuotaDialog]);

  const sourceStats = useMemo(() => collectSourceStats(items), [items]);

  const visibleItems = useMemo(() => {
    let next = [...items];
    if (activeSource) {
      next = next.filter((item) => item.sources.some((source) => source.source_name === activeSource));
    }
    if (activeTopic) {
      const topic = topicNav.find((item) => item.label === activeTopic);
      if (topic) next = next.filter((item) => matchesTopic(item, topic));
    }
    if (activeView === 'hot') {
      next = next.sort((a, b) => b.source_count - a.source_count || new Date(b.published_at).getTime() - new Date(a.published_at).getTime());
    }
    if (activeView === 'followed') {
      const followed = topicNav.filter((topic) => followedTopics.includes(topic.label));
      next = followed.length > 0 ? next.filter((item) => followed.some((topic) => matchesTopic(item, topic))) : [];
    }
    if (activeView === 'saved') {
      next = next.filter((item) => savedIds.includes(item.id));
    }
    return next;
  }, [activeSource, activeTopic, activeView, followedTopics, items, savedIds]);

  useEffect(() => {
    let active = true;
    if (languageMode === 'auto') {
      setTranslationMap({});
      setTranslating(false);
      setTranslationError('');
      return;
    }
    const texts = collectTranslatableTexts(visibleItems);
    if (texts.length === 0) {
      setTranslationMap({});
      setTranslating(false);
      setTranslationError('');
      return;
    }
    setTranslating(true);
    setTranslationError('');
    translateTexts(texts, languageMode)
      .then((response) => {
        if (!active) return;
        const nextMap = Object.fromEntries(response.items.map((item) => [item.original_text, item.translated_text]));
        setTranslationMap(nextMap);
        setShowQuotaDialog(false);
      })
      .catch((err: Error) => {
        if (!active) return;
        if (err instanceof TranslationQuotaExceededError) {
          setLanguageMode('auto');
          setShowQuotaDialog(true);
          setTranslationError('');
          setTranslationMap({});
          return;
        }
        setTranslationError(err.message || '翻译失败');
        setTranslationMap({});
      })
      .finally(() => {
        if (active) setTranslating(false);
      });
    return () => {
      active = false;
    };
  }, [languageMode, visibleItems]);

  const displayItems = useMemo(() => {
    if (languageMode === 'auto') return visibleItems;
    return visibleItems.map((item) => applyTranslations(item, translationMap));
  }, [languageMode, translationMap, visibleItems]);

  const grouped = useMemo(() => groupByDate(displayItems), [displayItems]);

  const viewTitle = useMemo(() => {
    if (activeSource) return `${activeSource} 来源`;
    if (activeTopic) return activeTopic;
    if (activeView === 'hot') return '热门';
    if (activeView === 'followed') return '关注';
    if (activeView === 'saved') return '稍后读';
    if (activeView === 'sources') return '来源';
    if (activeView === 'settings') return '设置';
    return '最新';
  }, [activeSource, activeTopic, activeView]);

  function handleSelectView(view: ActiveView) {
    setActiveView(view);
    setActiveTopic(null);
    if (view !== 'sources') {
      setActiveSource(null);
    }
  }

  function handleSelectTopic(topic: string) {
    setActiveView('latest');
    setActiveSource(null);
    setActiveTopic((current) => (current === topic ? null : topic));
  }

  function toggleSaved(id: string) {
    setSavedIds((current) => (current.includes(id) ? current.filter((savedId) => savedId !== id) : [...current, id]));
  }

  function toggleFollowedTopic(topic: string) {
    setFollowedTopics((current) => (current.includes(topic) ? current.filter((item) => item !== topic) : [...current, topic]));
  }

  async function handleRefresh() {
    setRefreshing(true);
    try {
      const currentStatus = await fetchRefreshStatus();
      setRefreshStatus(currentStatus);
      if (currentStatus.remaining <= 0) {
        setError('刷新次数已达到本小时上限');
        setStatus('error');
        return;
      }
      await refreshNews();
      const nextRefreshStatus = await fetchRefreshStatus();
      setRefreshStatus(nextRefreshStatus);
      const data = query.trim() ? await searchNews(query.trim()) : await fetchNews();
      setItems(data.items);
      setKeywords(hasSearchKeywords(data) ? data.keywords : []);
      setLastUpdatedAt(new Date().toISOString());
      setError('');
      setStatus('idle');
    } catch (err) {
      setError(err instanceof ManualRefreshLimitError ? '刷新次数已达到本小时上限' : err instanceof Error ? err.message : '刷新失败');
      setStatus('error');
      fetchRefreshStatus()
        .then(setRefreshStatus)
        .catch(() => undefined);
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} activeTopic={activeTopic} onSelectView={handleSelectView} onSelectTopic={handleSelectTopic} />

      <main className="workspace">
        <header className="topbar">
          <div className="search-panel" aria-label="新闻搜索">
            <div className="search-box">
              <Search size={19} aria-hidden="true" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索 AI 资讯、公司、产品或关键词"
                aria-label="搜索新闻"
              />
              <kbd>/</kbd>
            </div>
            {showSpecialLink && (
              <a href={publicConfig.special_link_url} target="_blank" rel="noreferrer" className="special-link">
                打开老岳中转
                <ExternalLink size={15} aria-hidden="true" />
              </a>
            )}
            {keywords.length > 0 && (
              <div className="search-keywords" aria-label="拆解后的关键词">
                {keywords.map((keyword) => (
                  <span key={keyword}>{keyword}</span>
                ))}
              </div>
            )}
          </div>

          <div className="toolbar-shell">
            <div className="toolbar-actions">
              <button
                type="button"
                className={`tool-button${topbarPanel === 'filters' ? ' active' : ''}`}
                onClick={() => setTopbarPanel((current) => (current === 'filters' ? null : 'filters'))}
              >
                <SlidersHorizontal size={18} aria-hidden="true" />
                <span className="tool-label">筛选</span>
              </button>
              <button
                type="button"
                className="tool-button language-button"
                onClick={() => setShowLanguageDialog(true)}
                aria-label="切换语言"
              >
                <Languages size={18} aria-hidden="true" />
                <span>{languageLabel(languageMode)}</span>
              </button>
              <button
                type="button"
                className={`icon-button${topbarPanel === 'notifications' ? ' active' : ''}`}
                onClick={() => setTopbarPanel((current) => (current === 'notifications' ? null : 'notifications'))}
                aria-label="通知"
              >
                <Bell size={19} aria-hidden="true" />
              </button>
              <button
                type="button"
                className="icon-button refresh-icon-button"
                onClick={handleRefresh}
                disabled={refreshing || refreshStatus?.remaining === 0}
                aria-label={`刷新新闻${refreshStatus ? `，本小时剩余 ${refreshStatus.remaining} 次` : ''}`}
                title={refreshStatus ? `本小时剩余 ${refreshStatus.remaining}/${refreshStatus.limit} 次` : '刷新新闻'}
              >
                <RefreshCw size={19} aria-hidden="true" className={refreshing ? 'spinning' : ''} />
                {refreshStatus && <span className="refresh-limit-badge">{refreshStatus.remaining}</span>}
              </button>
            </div>

            {topbarPanel === 'filters' && (
              <section className="topbar-popover" aria-label="筛选面板">
                <div className="popover-header">
                  <strong>筛选</strong>
                  <button type="button" className="mini-button" onClick={() => setTopbarPanel(null)}>
                    <X size={15} aria-hidden="true" />
                  </button>
                </div>
                <div className="popover-section">
                  <span className="popover-label">视图</span>
                  <div className="segmented-grid">
                    {primaryNav.map((item) => (
                      <button
                        type="button"
                        className={activeView === item.id ? 'selected' : ''}
                        key={item.id}
                        onClick={() => handleSelectView(item.id)}
                      >
                        {activeView === item.id && <Check size={14} aria-hidden="true" />}
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="popover-section">
                  <span className="popover-label">主题</span>
                  <div className="settings-options compact">
                    {topicNav.map((topic) => (
                      <button
                        type="button"
                        className={`setting-chip${activeTopic === topic.label ? ' active' : ''}`}
                        key={topic.label}
                        onClick={() => handleSelectTopic(topic.label)}
                      >
                        {topic.label}
                      </button>
                    ))}
                  </div>
                </div>
                <button
                  type="button"
                  className="ghost-button full-width"
                  onClick={() => {
                    setActiveView('latest');
                    setActiveTopic(null);
                    setActiveSource(null);
                    setTopbarPanel(null);
                  }}
                >
                  清除筛选
                </button>
              </section>
            )}

            {topbarPanel === 'notifications' && (
              <section className="topbar-popover notification-popover" aria-label="通知面板">
                <div className="popover-header">
                  <strong>通知</strong>
                  <button type="button" className="mini-button" onClick={() => setTopbarPanel(null)}>
                    <X size={15} aria-hidden="true" />
                  </button>
                </div>
                <div className="notification-list">
                  <div>
                    <strong>{refreshing ? '正在刷新新闻' : '新闻缓存已就绪'}</strong>
                    <span>
                      {lastUpdatedAt ? `最后更新 ${formatTime(lastUpdatedAt)}` : '等待首次加载完成'}
                      {refreshStatus ? ` · 本小时刷新剩余 ${refreshStatus.remaining}/${refreshStatus.limit}` : ''}
                    </span>
                  </div>
                  <div>
                    <strong>当前语言：{languageLabel(languageMode)}</strong>
                    <span>{languageMode === 'auto' ? '展示源语言' : translating ? '正在翻译当前列表' : translationError || '翻译缓存可用'}</span>
                  </div>
                  <div>
                    <strong>当前列表 {visibleItems.length} 条</strong>
                    <span>总缓存 {items.length} 条，稍后读 {savedIds.length} 条</span>
                  </div>
                </div>
              </section>
            )}
          </div>
        </header>

        <div className="mobile-brand">
          <span>AI</span>
          <strong>快讯</strong>
        </div>

        <section className="feed-panel">
          <div className="view-summary">
            <div>
              <h1>{viewTitle}</h1>
              <p>
                {activeView === 'settings'
                  ? '管理本地关注主题和稍后读列表。'
                  : activeView === 'sources'
                    ? '按来源统计当前新闻缓存，点击来源可查看对应报道。'
                    : `当前显示 ${visibleItems.length} 条新闻事件。`}
              </p>
            </div>
            {(activeTopic || activeSource || activeView !== 'latest') && (
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setActiveView('latest');
                  setActiveTopic(null);
                  setActiveSource(null);
                }}
              >
                清除筛选
              </button>
            )}
          </div>

          {showQuotaDialog && (
            <div className="quota-dialog-layer" role="presentation" data-testid="quota-dialog-layer" onClick={() => setShowQuotaDialog(false)}>
              <section className="quota-dialog" role="alertdialog" aria-live="assertive" onClick={(event) => event.stopPropagation()}>
                额度已耗尽，请使用浏览器自带翻译
              </section>
            </div>
          )}

          {status === 'loading' && <div className="state-row">正在加载新闻...</div>}
          {status === 'error' && <div className="state-row error">{error}</div>}
          {translating && <div className="state-row compact-state">正在翻译为 {languageLabel(languageMode)}...</div>}
          {translationError && <div className="state-row error compact-state">翻译失败，当前显示源语言：{translationError}</div>}
          {status !== 'loading' && activeView !== 'settings' && grouped.length === 0 && <div className="state-row">没有匹配的新闻事件。</div>}

          {activeView === 'sources' && (
            <section className="source-directory" aria-label="来源列表">
              {sourceStats.map((source) => (
                <button
                  type="button"
                  className={`source-card${activeSource === source.name ? ' active' : ''}`}
                  key={source.name}
                  onClick={() => setActiveSource((current) => (current === source.name ? null : source.name))}
                >
                  <span className="source-logo">{source.name.slice(0, 1).toUpperCase()}</span>
                  <span>
                    <strong>{source.name}</strong>
                    <small>{source.domain}</small>
                  </span>
                  <em>{source.count} 条</em>
                </button>
              ))}
            </section>
          )}

          {activeView === 'settings' && (
            <section className="settings-panel" aria-label="设置">
              <div className="settings-block">
                <h2>关注主题</h2>
                <p>“关注”入口会展示这些主题匹配到的新闻。</p>
                <div className="settings-options">
                  {topicNav.map((topic) => (
                    <button
                      type="button"
                      className={`setting-chip${followedTopics.includes(topic.label) ? ' active' : ''}`}
                      key={topic.label}
                      onClick={() => toggleFollowedTopic(topic.label)}
                    >
                      {topic.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="settings-block">
                <h2>稍后读</h2>
                <p>当前保存了 {savedIds.length} 条新闻。</p>
                <button type="button" className="ghost-button" onClick={() => setSavedIds([])} disabled={savedIds.length === 0}>
                  清空稍后读
                </button>
              </div>
            </section>
          )}

          {activeView !== 'settings' && (
          <section className="feed" aria-label="新闻列表">
            {grouped.map((group) => (
              <div className="date-group" key={group.label}>
                <div className="date-heading">
                  <h2>{group.label}</h2>
                  <span>{group.items.length} 条事件</span>
                </div>
                <div className="card-grid">
                  {group.items.map((item) => (
                    <NewsCard item={item} key={item.id} saved={savedIds.includes(item.id)} onOpen={setSelectedItem} onToggleSaved={toggleSaved} />
                  ))}
                </div>
              </div>
            ))}
          </section>
          )}
        </section>
        {selectedItem && (
          <NewsModal item={selectedItem} saved={savedIds.includes(selectedItem.id)} onClose={() => setSelectedItem(null)} onToggleSaved={toggleSaved} />
        )}
        {showLanguageDialog && (
          <div className="modal-backdrop" role="presentation" onClick={() => setShowLanguageDialog(false)}>
            <section
              className="language-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="language-modal-title"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="popover-header">
                <strong id="language-modal-title">切换语言</strong>
                <button type="button" className="mini-button" onClick={() => setShowLanguageDialog(false)} aria-label="关闭语言弹窗">
                  <X size={16} aria-hidden="true" />
                </button>
              </div>
              <div className="language-options">
                {[
                  { id: 'auto' as const, title: '自动', description: '不处理新闻语言，源头是什么语言就展示什么语言。' },
                  { id: 'zh' as const, title: '中文', description: '把非中文标题、摘要和来源标题翻译为中文。' },
                  { id: 'en' as const, title: 'English', description: 'Translate non-English titles, summaries, and source titles to English.' }
                ].map((option) => (
                  <button
                    type="button"
                    className={`language-option${languageMode === option.id ? ' selected' : ''}`}
                    key={option.id}
                    onClick={() => {
                      setLanguageMode(option.id);
                      setShowLanguageDialog(false);
                    }}
                  >
                    <span>
                      <strong>{option.title}</strong>
                      <small>{option.description}</small>
                    </span>
                    {languageMode === option.id && <Check size={18} aria-hidden="true" />}
                  </button>
                ))}
              </div>
            </section>
          </div>
        )}
        {(publicConfig.site_icp_number || publicConfig.site_copyright_owner || publicConfig.site_copyright_text) && (
          <footer className="site-footer">
            {publicConfig.site_icp_number && <span>{publicConfig.site_icp_number}</span>}
            {publicConfig.site_copyright_owner && <span>© {new Date().getFullYear()} {publicConfig.site_copyright_owner}</span>}
            {publicConfig.site_copyright_text && <span>{publicConfig.site_copyright_text}</span>}
          </footer>
        )}
      </main>
    </div>
  );
}
