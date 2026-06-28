# AI 新闻聚合 Web 应用

前后端分离应用，用于按日期从新到旧展示近期 AI 新闻事件。后端聚合 RSS 与可配置新闻 API，写入 SQLite 后做同主题去重；前端提供搜索、关键词展示、卡片流和来源展开。

## 启动

```bash
docker compose up --build -d backend frontend
```

- 前端：http://localhost:5173
- 后端：http://localhost:18000
- 健康检查：http://localhost:18000/health

默认 `NEWS_API_PROVIDERS=hackernews`，并使用 RSS 作为主要新闻来源；不再启用 sample 示例 API。
默认 RSS 覆盖大模型、应用、算力、数据、硬件、投融资、政策，也包含与 AI 形成间接联系的事件来源，例如端侧 AI 硬件成本上升导致的消费电子产品涨价。

## 配置

项目根目录的 `.env` 是 Docker Compose 实际读取的本机配置；`.env.example` 是模板，方便以后复制或对照。两者都被 `.gitignore` 已被忽略。

- `BACKEND_HOST_PORT=18000`：后端映射到宿主机的端口，容器内部仍是 `8000`。
- `FRONTEND_HOST_PORT=5173`：前端映射到宿主机的端口。
- `SITE_ICP_NUMBER`、`SITE_COPYRIGHT_OWNER`、`SITE_COPYRIGHT_TEXT`：页面底栏展示的备案号、版权归属和版权文案；空值不会显示。
- `MANUAL_REFRESH_HOURLY_LIMIT=10`：顶栏手动刷新按钮的服务器端每小时上限；自动定时刷新不计入。
- `NEWS_API_PROVIDER=hackernews`：兼容旧配置字段。
- `NEWS_API_PROVIDERS=hackernews`：启用多个免费 API 适配器，支持 `hackernews`、`gnews`、`thenewsapi`、`currents`、`newsapi`、`guardian`、`all`。
- `NEWS_API_PROVIDER=gnews` 且设置 `GNEWS_API_KEY`：启用 GNews 适配器。
- `GNEWS_API_KEY`、`THENEWSAPI_API_KEY`、`CURRENTS_API_KEY`、`NEWSAPI_API_KEY`、`GUARDIAN_API_KEY`：对应免费 API 的 key；不填会自动跳过。
- `TRANSLATION_PROVIDERS=mymemory,tencent,aliyun,volcengine,azure`：展示语言切换使用的翻译器顺序，缓存未命中时按顺序尝试。
- `TRANSLATION_STOP_AT_RATIO=0.9`：翻译供应商达到配置额度 90% 后自动停止使用；MyMemory 按日统计，其他云厂商按月统计。
- `MYMEMORY_*`：MyMemory 的端点、邮箱、日字符预算和每秒请求限制；支持 `MYMEMORY_DAILY_CHAR_BUDGET`，并兼容已有的 `MYMEMORY_DAYLY_CHAR_BUDGET`。
- `TENCENT_TRANSLATE_*`、`ALIYUN_TRANSLATE_*`、`VOLCENGINE_TRANSLATE_*`、`AZURE_TRANSLATOR_*`：各云翻译 API 的端点、密钥、月度字符预算和每秒请求限制；密钥或预算为空会跳过对应云供应商。
- 翻译结果会写入 SQLite 缓存；重复标题、摘要和来源标题不会重复消耗免费额度。所有供应商额度耗尽时，前端会提示“额度已耗尽，请使用浏览器自带翻译”。
- `NEWS_QUERIES`：聚合 API 的查询列表。后端调用 GNews、TheNewsAPI、Currents、NewsAPI、Guardian、Hacker News 等 API 适配器时，会逐条用这些 query 拉取新闻候选；它不影响 RSS，RSS 按 `RSS_SOURCES` 抓取。默认 query 覆盖大模型、应用、算力、数据、硬件、投融资、政策，也包含 `AI hardware Apple price increase` 这类间接关联主题。
- `RSS_SOURCES`：用逗号分隔，每项格式为 `名称|URL`；默认包含国外 AI 源、arXiv、Hacker News、机器之心、量子位、InfoQ 中文、AI 科技评论、36 氪、虎嗅、Daily Juya 等来源。
- `NEWS_REFRESH_TIMES=07:00,09:00,12:00,18:00,20:00,22:00`：后台刷新时刻。
- `NEWS_REFRESH_TIMEZONE=Asia/Shanghai`：后台刷新使用的 IANA 时区；Compose 也会把它写入容器 `TZ`。如果生产服务器使用其他时区，改这里即可。
- `NEWS_RETENTION_DAYS=7`：SQLite 只保留近 7 天新闻，网页列表和搜索也只显示近 7 天内容。
- `DATABASE_PATH`：SQLite 文件路径，Compose 中默认为 `/data/news.db`。

默认会做 AI 相关性过滤：泛科技 RSS 中如果标题和摘要不包含 AI、大模型、算力、芯片、硬件、训练数据、投融资、监管政策等相关信号，不会写入缓存。

新闻处理流程：

- 服务启动时先初始化 SQLite，并清理 7 天以外的旧新闻；不会因为重启额外消耗新闻 API 配额。
- 刷新会并行聚合两类来源：`RSS_SOURCES` 中配置的 RSS，以及 `NEWS_API_PROVIDERS` 启用的新闻 API；API 查询词来自 `NEWS_QUERIES`。
- 每条候选新闻会被规范化为统一结构，提取关键词，做 AI 相关性过滤，再按标题、摘要、关键词和发布时间做同主题聚合去重。
- 每次刷新完成后会把新增内容追加进 SQLite，并把同主题内容合并到事件簇中；已存在 URL 不会重复写入。
- SQLite 中保存近 7 天事件簇和原始来源链接；前端读取的是聚合后的事件簇，卡片展开后显示合并前的来源。
- 默认每天按 `NEWS_REFRESH_TIMEZONE` 指定时区的 07:00、09:00、12:00、18:00、20:00、22:00 刷新，共 6 次；默认是北京时间 `Asia/Shanghai`。
- 调用 `POST /api/refresh` 会立即手动刷新一次，不会改变后续固定时刻刷新。
- 手动刷新会按 `NEWS_REFRESH_TIMEZONE` 对应时区统计当前小时窗口，默认每小时最多 10 次；可以先调用 `GET /api/refresh/status` 查看剩余次数。
- 云厂商翻译额度以 `YYYY-MM` 为统计键，因此每月 1 日自然进入新额度周期；MyMemory 以 `YYYY-MM-DD` 为统计键，按日重置。

## API

- `GET /api/news?page=1&page_size=20`
- `GET /api/search?q=OpenAI&page=1&page_size=20`
- `GET /api/config`：返回前端公开配置，包括特殊链接和底栏备案/版权字段。
- `GET /api/refresh/status`：返回当前小时手动刷新已用次数、上限、剩余次数和窗口结束时间。
- `POST /api/refresh`：手动刷新；超过小时上限时返回 `429`，`detail.code` 为 `manual_refresh_hourly_limit_exceeded`。
- `POST /api/translate`：按缓存和供应商额度返回译文；所有供应商不可用或超过 90% 预算时返回 `429`，`detail.code` 为 `translation_quota_exhausted`。

前端语言切换有三种模式：

- `自动`：不处理新闻语言，源头是什么语言就展示什么语言。
- `中文`：把非中文标题、摘要和来源标题翻译为中文。
- `English`：把非英文标题、摘要和来源标题翻译为英文。

来源名称不会翻译。

## 本地开发

后端：

```bash
cd backend
pyenv install 3.12.10
pyenv local 3.12.10
pyenv exec python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

如果不用 Docker，前端请求默认走当前域名下的 `/api`，可以通过 `VITE_API_BASE_URL=http://localhost:8000` 指向本地后端。Docker 部署时后端对外端口默认是 `18000`，但前端容器内部仍通过 `backend:8000` 访问后端服务。

## 测试

```bash
cd backend
pytest
```

```bash
cd frontend
npm test
```
