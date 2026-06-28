import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from './App';

const newsPayload = {
  items: [
    {
      id: 'cluster-1',
      title: 'OpenAI 发布新的多模态模型能力',
      summary: '新模型强化了文本、图像和语音理解能力。',
      published_at: '2026-06-26T10:00:00.000Z',
      keywords: ['openai', '多模态'],
      source_count: 2,
      primary_url: 'https://example.com/primary',
      sources: [
        {
          source_name: 'Sample API',
          title: 'OpenAI 发布新的多模态模型能力',
          url: 'https://example.com/primary',
          published_at: '2026-06-26T10:00:00.000Z'
        },
        {
          source_name: 'RSS',
          title: 'OpenAI adds multimodal model features',
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
      if (url.includes('/api/refresh')) return okJson({});
      return okJson(newsPayload);
    })
  );
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
    await userEvent.click(screen.getByRole('button', { name: /关闭弹窗/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
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
