import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from './App';

const newsPayload = {
  items: [
    {
      id: 'cluster-1',
      title: 'OpenAI 发布新的多模态模型能力',
      title_language: 'zh',
      summary: '新模型强化了文本、图像和语音理解能力。',
      published_at: '2026-06-26T10:00:00.000Z',
      keywords: ['openai', '多模态'],
      source_count: 2,
      primary_url: 'https://example.com/primary',
      sources: [
        {
          source_name: 'Sample API',
          title: 'OpenAI 发布新的多模态模型能力',
          summary: '这是一段较长的来源正文预览，会介绍模型更新的背景、能力变化和更多细节。',
          content: '这是一段较长的来源正文预览，会介绍模型更新的背景、能力变化和更多细节。',
          url: 'https://example.com/primary',
          published_at: '2026-06-26T10:00:00.000Z'
        },
        {
          source_name: 'RSS',
          title: 'OpenAI adds multimodal model features',
          summary: '<img src="https://example.com/a.jpg" />短正文预览。',
          content: '<img src="https://example.com/a.jpg" />短正文预览。',
          url: 'https://example.com/rss',
          published_at: '2026-06-26T09:00:00.000Z'
        }
      ]
    }
  ],
  page: 1,
  page_size: 40,
  total: 1
};

const publicConfigPayload = {
  special_link_url: 'https://example.com/custom-link',
  site_icp_number: '京ICP备00000000号',
  site_copyright_owner: 'AI News Owner',
  site_copyright_text: 'All rights reserved.'
};

const refreshStatusPayload = {
  used: 0,
  limit: 10,
  remaining: 10,
  window_ends_at: '2026-06-26T11:00:00+08:00'
};

function okJson(payload: unknown) {
  return {
    ok: true,
    json: async () => payload
  };
}

function stubDefaultFetch(overrides?: (url: string, init?: RequestInit) => unknown | undefined) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const override = overrides?.(url, init);
      if (override) return override;
      if (url.includes('/api/config')) return okJson(publicConfigPayload);
      if (url.includes('/api/refresh/status')) return okJson(refreshStatusPayload);
      if (url.includes('/api/refresh')) return okJson({ fetched: 0, inserted: 0, clustered: 0, queued: true });
      return okJson(newsPayload);
    })
  );
}

function mockMatchMedia(matches: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn()
    }))
  );
}

function makeNewsItem(index: number, publishedAt: string) {
  return {
    id: `cluster-${index}`,
    title: `中文标题 ${index}`,
    title_language: null,
    summary: `中文摘要 ${index}`,
    published_at: publishedAt,
    keywords: ['ai'],
    source_count: 1,
    primary_url: `https://example.com/${index}`,
    sources: [
      {
        source_name: '测试来源',
        title: `来源标题 ${index}`,
        summary: `来源摘要 ${index}`,
        content: `新闻预览 ${index}`,
        url: `https://example.com/${index}`,
        published_at: publishedAt
      }
    ]
  };
}

describe('App', () => {
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('renders grouped news cards and opens the full news modal', async () => {
    stubDefaultFetch();

    render(<App />);
    expect(await screen.findByText('OpenAI 发布新的多模态模型能力')).toBeInTheDocument();
    expect(screen.getByText('06 - 26, Fri')).toBeInTheDocument();
    expect(screen.getByText('京ICP备00000000号')).toBeInTheDocument();
    expect(screen.getByText(/AI News Owner/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /打开新闻：OpenAI 发布新的多模态模型能力/i }));
    expect(screen.getByRole('dialog', { name: /OpenAI 发布新的多模态模型能力/i })).toBeInTheDocument();
    expect(screen.getByText('OpenAI adds multimodal model features')).toBeInTheDocument();
    expect(screen.getByText('新闻预览')).toBeInTheDocument();
    expect(screen.getByText(/来自 RSS/)).toBeInTheDocument();
    expect(screen.getByText('短正文预览。')).toBeInTheDocument();
    expect(screen.queryByText(/img src/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /展开/i }));
    expect(screen.getByRole('button', { name: /收起/i })).toHaveAttribute('aria-expanded', 'true');
    await userEvent.click(screen.getByRole('button', { name: /关闭弹窗/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('renders news dates and times in Shanghai timezone', async () => {
    const shanghaiNextDayItem = makeNewsItem(99, '2026-06-25T18:30:00.000Z');
    stubDefaultFetch((url) => {
      if (url.includes('/api/news')) {
        return okJson({ items: [shanghaiNextDayItem], page: 1, page_size: 40, total: 1 });
      }
      return undefined;
    });

    render(<App />);
    expect(await screen.findByText('中文标题 99')).toBeInTheDocument();
    expect(screen.getByText('06 - 26, Fri')).toBeInTheDocument();
    expect(screen.getByText('02:30')).toBeInTheDocument();
  });

  it('shows the special link when search includes 老岳中转', async () => {
    stubDefaultFetch();

    render(<App />);
    await userEvent.type(screen.getByLabelText('搜索新闻'), '老岳中转 ai');
    expect(screen.getByRole('link', { name: /打开老岳中转/i })).toHaveAttribute('href', 'https://example.com/custom-link');
    await waitFor(() => expect(fetch).toHaveBeenCalled());
  });

  it('supports sidebar saved news and removes subscription navigation', async () => {
    stubDefaultFetch();

    render(<App />);
    expect(await screen.findByText('OpenAI 发布新的多模态模型能力')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '订阅' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /加入稍后读：OpenAI 发布新的多模态模型能力/i }));
    expect(screen.getByRole('button', { name: /从稍后读移除：OpenAI 发布新的多模态模型能力/i })).toHaveClass('saved');
    await userEvent.click(screen.getByRole('button', { name: '稍后读' }));
    expect(screen.getByText('当前显示 1 条新闻事件。')).toBeInTheDocument();
    expect(screen.getByText('OpenAI 发布新的多模态模型能力')).toBeInTheDocument();
  });

  it('opens the sidebar navigation as a mobile filter drawer', async () => {
    mockMatchMedia(true);
    stubDefaultFetch();

    render(<App />);
    expect(await screen.findByText('OpenAI 发布新的多模态模型能力')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '筛选' }));

    const drawer = screen.getByRole('dialog', { name: '导航筛选' });
    expect(drawer).toBeInTheDocument();
    expect(document.querySelector('.app-shell')).toHaveClass('mobile-menu-open');

    await userEvent.click(within(drawer).getByRole('button', { name: '大模型' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '导航筛选' })).not.toBeInTheDocument());
    expect(screen.getByRole('heading', { name: '大模型' })).toBeInTheDocument();
  });

  it('prunes saved news ids that are no longer in the one-week news cache', async () => {
    window.localStorage.setItem('ai-news-saved', JSON.stringify(['cluster-1', 'expired-cluster']));
    stubDefaultFetch();

    render(<App />);
    expect(await screen.findByText('OpenAI 发布新的多模态模型能力')).toBeInTheDocument();
    await waitFor(() => {
      expect(JSON.parse(window.localStorage.getItem('ai-news-saved') ?? '[]')).toEqual(['cluster-1']);
    });
  });

  it('opens the language dialog and translates displayed news titles', async () => {
    stubDefaultFetch((url) => {
      if (url.includes('/api/translate')) {
        return {
          ok: true,
          json: async () => ({
            target_language: 'en',
            items: [
              {
                original_text: 'OpenAI 发布新的多模态模型能力',
                translated_text: 'OpenAI releases new multimodal model capabilities',
                source_language: 'zh-CN',
                target_language: 'en'
              },
              {
                original_text: '新模型强化了文本、图像和语音理解能力。',
                translated_text: 'The new model improves text, image, and speech understanding.',
                source_language: 'zh-CN',
                target_language: 'en'
              },
              {
                original_text: 'OpenAI adds multimodal model features',
                translated_text: 'OpenAI adds multimodal model features',
                source_language: 'en',
                target_language: 'en'
              }
            ]
          })
        };
      }
      return undefined;
    });

    render(<App />);
    expect(await screen.findByText('OpenAI 发布新的多模态模型能力')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /切换语言/i }));
    await userEvent.click(screen.getByRole('button', { name: /English/i }));
    expect(await screen.findByText('OpenAI releases new multimodal model capabilities')).toBeInTheDocument();
  });

  it('translates cards lazily by latest day and scroll threshold', async () => {
    const items = [
      ...Array.from({ length: 6 }, (_, index) => makeNewsItem(index + 1, '2026-06-30T10:00:00.000Z')),
      ...Array.from({ length: 6 }, (_, index) => makeNewsItem(index + 7, '2026-06-29T10:00:00.000Z'))
    ];
    const translationBodies: Array<{ texts: string[] }> = [];
    stubDefaultFetch((url, init) => {
      if (url.includes('/api/news')) {
        return okJson({
          items,
          page: 1,
          page_size: 40,
          total: items.length
        });
      }
      if (url.includes('/api/translate')) {
        const body = JSON.parse(String(init?.body || '{}')) as { texts: string[]; target_language: string };
        translationBodies.push({ texts: body.texts });
        return okJson({
          target_language: body.target_language,
          items: body.texts.map((text) => ({
            original_text: text,
            translated_text: `${text} EN`,
            source_language: 'zh-CN',
            target_language: 'en'
          }))
        });
      }
      return undefined;
    });

    render(<App />);
    expect(await screen.findByText('中文标题 1')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /切换语言/i }));
    await userEvent.click(screen.getByRole('button', { name: /English/i }));

    await waitFor(() => expect(translationBodies).toHaveLength(3));
    expect(translationBodies.every((body) => body.texts.length === 6)).toBe(true);
    expect(translationBodies.flatMap((body) => body.texts)).toEqual(
      expect.arrayContaining(['中文标题 1', '中文摘要 1', '新闻预览 1', '中文标题 6', '中文摘要 6', '新闻预览 6'])
    );
    expect(translationBodies.flatMap((body) => body.texts)).not.toContain('中文标题 7');

    const cards = Array.from(document.querySelectorAll<HTMLElement>('[data-news-card-id]'));
    cards.forEach((card, index) => {
      card.getBoundingClientRect = vi.fn(() => ({
        x: 0,
        y: index === 3 ? 120 : 1200,
        width: 320,
        height: 180,
        top: index === 3 ? 120 : 1200,
        right: 320,
        bottom: index === 3 ? 300 : 1380,
        left: 0,
        toJSON: () => ({})
      }));
    });
    window.dispatchEvent(new Event('scroll'));

    await waitFor(() => expect(translationBodies).toHaveLength(6));
    expect(translationBodies.flatMap((body) => body.texts)).toEqual(expect.arrayContaining(['中文标题 7', '中文摘要 12', '新闻预览 12']));
  });

  it('uses title_language to skip cards already in the target language', async () => {
    const translationBodies: Array<{ texts: string[] }> = [];
    stubDefaultFetch((url, init) => {
      if (url.includes('/api/translate')) {
        const body = JSON.parse(String(init?.body || '{}')) as { texts: string[] };
        translationBodies.push({ texts: body.texts });
      }
      return undefined;
    });

    render(<App />);
    expect(await screen.findByText('OpenAI 发布新的多模态模型能力')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /切换语言/i }));
    await userEvent.click(screen.getByRole('button', { name: /中文/i }));

    await waitFor(() => expect(screen.getByText('OpenAI 发布新的多模态模型能力')).toBeInTheDocument());
    expect(translationBodies).toHaveLength(0);
  });

  it('uses title_language to translate English cards into Chinese', async () => {
    const englishItem = {
      ...makeNewsItem(1, '2026-06-30T10:00:00.000Z'),
      title: 'AI agents are not your coworkers',
      title_language: 'en',
      summary: 'A story about new AI agent products.',
      sources: [
        {
          source_name: 'Test Source',
          title: 'AI agents are not your coworkers',
          summary: 'A story about new AI agent products.',
          content: 'Short English preview',
          url: 'https://example.com/en',
          published_at: '2026-06-30T10:00:00.000Z'
        }
      ]
    };
    const translationBodies: Array<{ texts: string[] }> = [];
    stubDefaultFetch((url, init) => {
      if (url.includes('/api/news')) {
        return okJson({ items: [englishItem], page: 1, page_size: 40, total: 1 });
      }
      if (url.includes('/api/translate')) {
        const body = JSON.parse(String(init?.body || '{}')) as { texts: string[]; target_language: string };
        translationBodies.push({ texts: body.texts });
        return okJson({
          target_language: body.target_language,
          items: body.texts.map((text) => ({
            original_text: text,
            translated_text: `${text} 中文`,
            source_language: 'en',
            target_language: 'zh'
          }))
        });
      }
      return undefined;
    });

    render(<App />);
    expect(await screen.findByText('AI agents are not your coworkers')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /切换语言/i }));
    await userEvent.click(screen.getByRole('button', { name: /中文/i }));

    await waitFor(() => expect(translationBodies).toHaveLength(1));
    expect(translationBodies[0].texts).toEqual(
      expect.arrayContaining(['AI agents are not your coworkers', 'A story about new AI agent products.', 'Short English preview'])
    );
  });

  it('shows and dismisses the quota exhausted dialog when translation quota is depleted', async () => {
    const user = userEvent.setup();
    stubDefaultFetch((url) => {
      if (url.includes('/api/translate')) {
        return {
          ok: false,
          status: 429,
          json: async () => ({
            detail: {
              code: 'translation_quota_exhausted',
              message: '额度已耗尽，请使用浏览器自带翻译'
            }
          })
        };
      }
      return undefined;
    });

    render(<App />);
    expect(await screen.findByText('OpenAI 发布新的多模态模型能力')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /切换语言/i }));
    await user.click(screen.getByRole('button', { name: /English/i }));

    expect(await screen.findByRole('alertdialog')).toHaveTextContent('额度已耗尽，请使用浏览器自带翻译');
    await user.click(screen.getByTestId('quota-dialog-layer'));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /切换语言/i }));
    await user.click(screen.getByRole('button', { name: /English/i }));
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('额度已耗尽，请使用浏览器自带翻译');
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(), { timeout: 3500 });
  }, 8000);

  it('shows manual refresh limit feedback from the server', async () => {
    stubDefaultFetch((url) => {
      if (url.includes('/api/refresh/status')) {
        return okJson({ ...refreshStatusPayload, used: 10, remaining: 0 });
      }
      if (url.includes('/api/refresh')) {
        return {
          ok: false,
          status: 429,
          json: async () => ({
            detail: {
              code: 'manual_refresh_hourly_limit_exceeded',
              message: '刷新次数已达到本小时上限'
            }
          })
        };
      }
      return undefined;
    });

    render(<App />);
    expect(await screen.findByText('OpenAI 发布新的多模态模型能力')).toBeInTheDocument();
    const refreshButton = screen.getByRole('button', { name: /刷新新闻/ });
    expect(refreshButton).toBeDisabled();
    expect(refreshButton).toHaveTextContent('0');
  });
});
