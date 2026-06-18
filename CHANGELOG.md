# CHANGELOG

> **版本规范**: Major.架构变更 | Minor.新功能 | Patch.bug修复/数据更新
> 每次发版打对应 git tag（如 `git tag -a v2.1.0`）。

## v2.0.0 — 多Agent系统上线 (2026-06-16)

> **git tag**: `v2.0.0`
> **回退标记**: `v1.0-legacy`（单Agent版本）
>
> 核心变更：从单Agent管线迁移到 LangGraph 多Agent架构（9个专业Agent），
> 20城POI数据质量清洗，管理后台，R2图床支持，CI质量门禁。

## 2026-06-18 12:20 - 修复 Render Agent 反代 502

### 变更内容 — 改了什么文件，具体改了什么
- src/api.cpp — Linux/Render 的 `/agent/*` 反代从手写 raw socket 读取改为复用项目已有 `httplib::Client`，并补齐 query string 转发；Agent 不可达时返回结构化 `AGENT_PROXY_ERROR` 和底层错误原因。
- tools/rag.py — 新增单城市 RAG 初始化能力，避免首个规划请求一次加载 21 个城市的攻略/知识数据。
- agents/retrieve_agent.py — RetrieveAgent 改为只按当前请求城市懒加载 RAG。
- tests/test_multi_agent.py — 增加城市级 RAG 初始化回归测试，确认请求北京不会顺带索引上海。
- scripts/container_smoke.js — Agent health 失败时输出响应体片段，避免 CI 只显示 `HTTP 502` 而丢失代理错误细节。
- CHANGELOG.md — 记录本次 502 根因调查和修复范围。

### 原因 — 为什么要改
- 最新 GitHub Actions Docker smoke 和线上 `https://tour-pass.onrender.com/agent/health` 都返回 502，响应体为 `{"error":"Agent no response"}`。
- CI 容器日志显示 FastAPI Agent 已经完成 startup 并监听 `127.0.0.1:8090`，但 Python 侧没有收到 `/agent/health` 请求；失败点集中在 C++ Linux raw socket 反代实现，而不是 Agent 健康检查自身。
- Render 免费实例 521MB 内存限制可能仍会影响首个规划请求的 graph/RAG 懒加载，但 `/agent/health` 不触发这些重资源加载，当前可复现 502 需要先修反代可达性。
- 首个 `/agent/plan` 仍可能在免费实例中受内存限制影响，原 RetrieveAgent 会在请求期全量 `init_rag("data")`，需要改成城市级懒加载降低峰值内存。

### 影响范围 — 改动影响了哪些功能/模块
- Render/Docker Linux 环境：`/agent/ping`、`/agent/health`、`/agent/plan`、`/agent/plan-sync`、`/agent/plan-multi`、`/agent/chat` 等 C++ 到 Python Agent 的代理路径。
- Windows 本地 API smoke：不改 WinHTTP 反代分支。
- 前端 AI 多 Agent 规划：恢复 C++ 服务对 Python Agent 的可达性；SSE 响应经 `httplib::Client` 缓冲返回，后续如需优化实时流式可单独处理。
- 首个规划请求：RAG 只加载当前城市，减少 Render 免费实例上的内存峰值；跨城市请求会按城市逐步追加索引。
- CI Docker smoke：后续 Agent 502 会显示响应体和 C++ 代理错误日志，便于区分连接失败、读取失败和 Agent 业务失败。

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

## 2026-06-17 21:56 - 修复 Multi-Agent CI 测试缺失文件

### 变更内容 — 改了什么文件，具体改了什么
- tests/test_multi_agent.py — 将 `test:multi-agent` 使用的 Python 回归测试文件纳入版本控制。
- requirements-multi-agent.txt — 补充 `fastapi`、`httpx`、`python-dotenv`、`redis`，使 CI 测试依赖与 Agent/Docker 运行依赖保持一致。
- CHANGELOG.md — 记录二次 CI 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions 新 run `27693832302` 已通过 `Validate sample data`，但在 `Multi-Agent tests` 步骤失败。
- 失败原因是干净 checkout 中没有 `tests/test_multi_agent.py`，而 `package.json` 的 `test:multi-agent` 正在执行该路径；本地能通过是因为该文件只存在于未跟踪工作区。
- 测试会导入 `api_multi_agent.py`，因此 CI 也需要安装 API 导入依赖，否则补上测试文件后会继续因缺依赖失败。

### 影响范围 — 改动影响了哪些功能/模块
- CI 多 Agent 测试：干净 GitHub runner 可找到并执行测试文件。
- Python Agent 依赖：`requirements-multi-agent.txt` 可覆盖测试和运行时导入所需的轻量 API 依赖。

## 2026-06-17 22:02 - 修复 Windows API smoke 城市参数

### 变更内容 — 改了什么文件，具体改了什么
- scripts/api_smoke.ps1 — 路线 smoke 使用 `docs/sample_candidate_request.json` 中的城市作为 `/route/shortest` 的 `city` 参数。
- CHANGELOG.md — 记录 Windows API smoke 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions run `27694240231` 中 Ubuntu 已全部通过，Windows 在最后的 `API smoke` 步骤失败。
- 失败原因是 smoke 从根 `data/edges.json` 读取长沙边 `amap_f3d362be -> amap_b011c2`，但请求 `/route/shortest` 时没有显式传 `city`，服务会使用当前默认城市，导致用非长沙图查询长沙 POI 并返回 `NOT_FOUND`。

### 影响范围 — 改动影响了哪些功能/模块
- CI Windows API smoke：路线检查与样例候选请求城市保持一致，不受服务默认城市变化影响。
- 运行时接口：只影响测试脚本，不改变 `/route/shortest` 接口行为。

## 2026-06-17 22:09 - 修复 API smoke 路线样本来源

### 变更内容 — 改了什么文件，具体改了什么
- scripts/api_smoke.ps1 — 路线 smoke 改为从 `data/guangzhou/edges.json` 取样，并显式传 `city=广州`。
- CHANGELOG.md — 记录第三层 Windows API smoke 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions run `27694712668` 仍在 Windows `API smoke` 的 `/route/shortest` 检查失败。
- 失败原因是 `data/changsha/edges.json` 当前为空；服务按城市目录加载“长沙”，而 smoke 之前从根 `data/edges.json` 读取旧长沙边，导致路线样本和服务实际加载的城市图不一致。
- 广州是当前默认数据校验目标，且 `data/guangzhou/edges.json` 有有效边数据，用它做 smoke 样本更贴近当前 CI 数据入口。

### 影响范围 — 改动影响了哪些功能/模块
- CI Windows API smoke：路线检查使用真实已加载且有边的城市图。
- 运行时接口：只影响测试脚本，不改变服务行为。

## 2026-06-17 22:26 - 修复 Agent 健康检查启动阻塞

### 变更内容 — 改了什么文件，具体改了什么
- api_multi_agent.py — Agent 启动期不再全量执行 `rag_module.init_rag("data")`，RAG 与 LLM/Graph 一样改为首个检索/规划请求懒加载。
- scripts/container_smoke.js — 将 `/agent/health` 从非致命警告改为 Docker smoke 的硬性门禁。
- CHANGELOG.md — 记录线上 `/agent/health` 502 与 CI Docker smoke 漏检的原因和修复方式。

### 原因 — 为什么要改
- 最新 CI 虽然通过，但 Docker smoke 日志显示 `/agent/health` 实际返回 502，只是脚本把它标记为 non-fatal；线上 `https://tour-pass.onrender.com/agent/health` 和游客规划 `/agent/plan` 同样返回 502。
- 失败原因是 FastAPI lifespan 仍在启动期同步全量加载 RAG，读取 21 个城市的攻略和 POI 知识后才会响应健康检查；Render/Docker 中 C++ 反代在 Agent 未完成启动前只能返回 `Agent no response`。
- Agent 健康检查不应依赖 RAG 已完成索引，RAG 可由 `RetrieveAgent` 在首个规划请求中懒加载。

### 影响范围 — 改动影响了哪些功能/模块
- Agent 启动：`/agent/health` 可先返回，避免主服务健康但 Agent 反代一直 502。
- CI Docker smoke：后续若 Agent health 不可用，CI 会失败而不是放过问题。
- 首个 AI 规划请求：会承担 RAG 懒加载耗时。

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
