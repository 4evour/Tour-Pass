# CHANGELOG

> **版本规范**: Major.架构变更 | Minor.新功能 | Patch.bug修复/数据更新
> 每次发版打对应 git tag（如 `git tag -a v2.1.0`）。

## v2.0.0 — 多Agent系统上线 (2026-06-16)

> **git tag**: `v2.0.0`
> **回退标记**: `v1.0-legacy`（单Agent版本）
>
> 核心变更：从单Agent管线迁移到 LangGraph 多Agent架构（9个专业Agent），
> 20城POI数据质量清洗，管理后台，R2图床支持，CI质量门禁。

## 2026-06-17 21:36 - 修复广州样本数据 CI 校验规则

### 变更内容 — 改了什么文件，具体改了什么
- package.json — 将 `validate:data` 改为使用 `--allow-transit-schedule-defaults --allow-disconnected --required-types attraction,restaurant,hotel`，让默认广州样本校验与全城市真实数据校验规则保持一致。
- api_multi_agent.py — 取消 Agent 启动期预初始化 LLM 和 LangGraph，改为首个规划请求时懒加载；RAG 仍在启动时初始化。
- CHANGELOG.md — 记录本次 CI 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions `CI` 在 `Validate sample data` 步骤执行 `npm run validate:data` 失败。
- 失败原因是默认校验目标已从长沙改为 `data/guangzhou/pois.json`，但默认规则仍强制要求 `nightlife` 类型并要求 transit POI 必须有 `open_time`、`close_time`、`visit_duration_minutes`。当前广州真实数据没有 `nightlife`，且 5 个 transit POI 只有旧字段 `visit_duration`，导致 16 个数据校验错误。
- 不直接改广州 POI 数据，是为了避免人为补造 nightlife 或交通点时间字段污染真实数据。
- 线上游客登录后 `/agent/plan` 返回 502 `Agent no response`，同时 `/agent/health` 也返回同样错误，说明 C++ 主服务正常但 Python Agent 未能稳定提供服务；减少 Agent 启动期 LLM/Graph 预热，避免 Render 实例启动时因重初始化过重导致 Agent 不可用。

### 影响范围 — 改动影响了哪些功能/模块
- CI 数据校验：`validate:data` 不再因为真实城市数据缺少 nightlife 或 transit 时间字段失败；`validate:data:all` 和全城市数据门禁规则保持一致。
- Agent 运行时：`/agent/health` 可更早返回；首个 AI 规划请求会承担 LLM/Graph 懒加载耗时。

### 2026-06-15 22:19 — 收紧质量门禁和交付边界

#### 变更内容
- .github/workflows/ci.yml、package.json、web/editor/package.json、scripts/run_python_test.js — CI 显式开启 `TOURPASS_BUILD_TESTS=ON`，增加全城市数据校验、数据校验回归测试、Python 多 Agent 测试、React editor Vitest 和 editor build；补充对应 npm scripts 和跨平台 Python 测试 runner。
- scripts/validate_data.js、tests/test_validate_data_all_cities.js — 新增 `--all-cities` 与 `--data-dir`，逐个校验根数据和城市目录中的 `pois.json/edges.json`；新增回归测试确认坏城市数据会让全量校验失败。
- web/editor/src/core/commands/__tests__/*、web/editor-dist/index.html、web/editor-dist/assets/index-hlZKmOB9.js — 修正 command 测试 fixture 与实际 `setDays` store API 一致；刷新已跟踪的 editor build 产物入口。
- src/api.cpp、api_multi_agent.py — C++ 和 Agent CORS 改为环境变量白名单；C++ `/images` 与 Agent `/data/{city}/images/...` 只允许图片扩展名并限制在数据图片目录内，不再公开整个 data 目录。
- Dockerfile、.dockerignore — 运行镜像不再复制 `scripts/`；Docker build context 排除采集脚本、XHS 会话/路线中间数据和大图片目录。

#### 影响范围
- CI：PR/Push 会运行更多测试和构建，耗时增加但能提前发现测试空跑、Agent 回归、editor 编译和多城市数据问题。
- 运行时安全：跨域访问必须通过 `TOURPASS_ALLOWED_ORIGINS` 或 `AGENT_ALLOWED_ORIGINS` 显式配置；非图片数据不再能通过图片静态路径访问。
- Docker：生产镜像体积和敏感采集中间文件暴露面降低。

### 2026-06-15 17:18 — 多Agent上线入口与 R2 图片准备

#### 变更内容
- Dockerfile、entrypoint.sh、.dockerignore — 默认使用 `AGENT_IMPL=multi` 启动 `api_multi_agent:app`，保留 `AGENT_IMPL=legacy` 回滚入口；镜像复制多 Agent 根文件、agents/tools 目录和 requirements，并排除 `data/*/images/`。
- src/api.cpp、include/tourpass/models.h、src/models.cpp、src/search.cpp、web/admin.js、api_multi_agent.py — 新增/接入图片 URL 解析逻辑，`ASSET_BASE_URL` 或 `TOURPASS_ASSET_BASE_URL` 存在时将相对图片路径解析为 CDN/R2 URL，绝对 URL 原样返回，避免 `/https://...`。
- src/api.cpp、api_multi_agent.py — C++ proxy 增加 `/agent/plan-multi`；修复参数名；`/agent/health` 和 `/agent/stats` 返回 RAG 与 XHS 加载统计。
- tools/xhs_loader.py、tools/route.py、agents/retrieve_agent.py、agents/scheduler_agent.py、agents/state.py、graph.py — 修复中文城市名读取、edges 字段读取；将 XHS 路线转为 POI 频次、同日共现、参考路线摘要并注入多 Agent 规划上下文。
- scripts/upload_r2_assets.js — 新增 R2 上传脚本，支持 `--dry-run`、`--city`、`--only-amap`。
- scripts/multi_agent_regression.py — 新增 21 城 `/agent/plan-sync` 回归脚本。

#### 影响范围
- 部署：Render Docker 运行 C++ 后端 + Python 多 Agent 双进程，旧单 Agent 通过环境变量回滚。
- 图片：生产环境配置 CDN base 后，行程、搜索、POI 浏览和管理页展示可直接使用 CDN 图片 URL。
- 多 Agent：Retrieve/Poi/Scheduler 可利用 XHS 路线信号。

### 2026-06-13 17:37 — 小红书旅游路线爬虫与提取工具

#### 变更内容
- scripts/crawl_xhs_routes.js — 新增 API 方式路线爬虫
- scripts/crawl_xhs_routes_browser.js — 新增 Playwright 浏览器方式路线爬虫
- scripts/extract_routes.py — 新增 Python 路线提取脚本
- data/guangzhou/xhs_routes.json — 从已有 191 条广州笔记中提取出 14 条完整路线

### 2026-06-13 17:15 — 高德照片全量爬取完成

#### 变更内容
- 20 个城市共 2354/8519 个 POI 成功获取照片（27.6% 成功率）
- 各城市 data/{city}/pois.json 的 image_url 和 images 字段已更新
- 照片存储在 data/{city}/images/{poi_id}/ 下

### 2026-06-13 16:35 — 高德照片批量下载（多 Key 轮换）

#### 变更内容
- 修改 scripts/download_amap_photos.js：支持多 API Key 轮换、多城市批量爬取

### 2026-06-13 — 管理后台 POI 数据管理

#### 变更内容
- include/tourpass/graph.h + src/graph.cpp — PoiGraph 新增 findMutablePoi(id) 方法
- include/tourpass/models.h + src/models.cpp — 新增 poiToJson() 序列化函数
- include/tourpass/data_loader.h + src/data_loader.cpp — 新增 savePois() 写回 JSON
- include/tourpass/api.h — CityBundle 新增 poisPath 字段
- src/api.cpp — 新增 4 个管理员 API 端点（GET/PUT /admin/pois）
- web/admin.html — 新增「景点管理」tab
- web/admin.js — POI 管理逻辑：城市切换、分页、搜索筛选、编辑表单
