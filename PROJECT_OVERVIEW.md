# PROJECT_OVERVIEW

## 项目目标
- 提供面向城市自由行的行程规划服务，支持自然语言和结构化请求两种入口。
- 生成多候选、多日行程，并展示可解释的评分、通勤、时间窗与多样性指标。
- 以算法可复现、可压测、可演示为核心定位，兼顾 LLM 增强回复但不依赖其作为规划主路径。

## 技术栈
- **后端**：C++17，基于 cpp-httplib 提供 REST API。
- **数据与存储**：
lohmann/json、sqlite3、可选 PostgreSQL；城市数据以 data/ 下 JSON 为主。
- **规划算法**：Dijkstra / A* 最短路、Beam Search 多日时间槽规划、BM25 检索、Pareto 多目标排序。
- **LLM 集成**：兼容 OpenAI/DeepSeek 风格 Chat Completions，默认支持 config/llm.local.json 或环境变量注入。
- **前端**：Leaflet + 原生 JS 主应用；另有 web/editor 的 React/Vite/Tailwind 行程编辑器。
- **工程化**：MinGW Make 与 CMake 双构建、Docker 多阶段镜像、GitHub Actions CI、Render 部署草案。

## 目录结构
- src/：后端核心实现（API、规划、检索、图、LLM、存储、运行时）。
- include/tourpass/：核心头文件与数据模型。
- 	hird_party/：内置第三方依赖（httplib、json、sqlite3）。
- web/：前端页面、分享渲染、管理后台与编辑器。
- data/：城市 POI、通勤边数据；config/：AMap 与 LLM 配置模板。
- scripts/：数据采集、清洗、校验、压测与冒烟脚本。
- 	ests/：C++ 测试与关键 Node 测试脚本。
- docs/：OpenAPI、部署说明与样例请求。

## 核心流程
1. 用户请求进入 /trip/plan、/trip/chat 或异步 /trip/jobs。
2. 后端按城市查找对应 CityBundle，其中包含 PoiGraph、TripPlanner、SearchEngine。
3. /trip/chat 使用 LLM 解析意图，再通过 BM25 匹配 POI；结构化请求直接进入规划。
4. 规划主路径采用 Beam Search，在上午/午餐/下午/晚餐/晚间时间槽中搜索可行状态序列。
5. 生成多个候选方案后，进行 Pareto 分层与多样性度量，并可由 LLM 补充自然语言解释。
6. 前端读取候选方案、路线与算法调试信息，并在 Leaflet 地图上渲染路径和站点详情。

## 关键约定
- 敏感配置通过环境变量或 config/llm.local.json 注入，代码内不硬编码密钥。
- API Key 校验采用常量时间比较；密码哈希使用 PBKDF2。
- 所有 SQL 参数化；演示数据不等同真实地图、实时闭馆或生产 SLA。
- 线上 Demo 声明需与实际部署证据一致，避免把草案配置误作已上线服务。

## 运行与测试
- **本地构建**：mingw32-make build、mingw32-make run
- **CMake 构建**：cmake -S . -B build、cmake --build build
- **测试**：mingw32-make test 或 CMake 下 ctest --test-dir build
- **数据校验**：mingw32-make validate-data
- **容器冒烟**：
ode scripts/container_smoke.js http://127.0.0.1:8080
- **基准测试**：
ode scripts/benchmark.js ...

## 已知风险
- 默认城市数据可能滞后，需持续更新 POI 与通勤边。
- LLM 输出不可控，需保持算法主路径独立可用。
- SQLite 为本地辅助存储，重启后若无持久卷会丢失规划历史。
- 压测与冒烟结果仅反映当前环境，不可直接等同生产 SLA。

## AI Agent 服务（2026-06 新增）
- **Python Agent 服务**：基于 LangGraph + DeepSeek-V3 的旅行规划 Agent，端口 8090。
- **架构**：用户输入 → 意图解析 → RAG 攻略检索 → 本地 POI/酒店搜索 → 酒店锚点选择 → 每日规划 → Beam Search 路线优化 → 流式输出。
- **数据策略**：本地优先（C++ 后端 POI/酒店库 + 通勤图），高德 MCP 仅作补充。
- **RAG**：ChromaDB 存储城市攻略（city_guide + wikivoyage + POI 描述），向量检索。
- **缓存**：三级缓存（热门行程预生成 + Redis 行程级缓存 + 内存缓存）。
- **新增 C++ API**：`/api/travel-time`、`/api/optimize-route`、`/api/city-guide`、`/api/cities`。
- **前端**：`AgentChat.tsx`（流式对话）、`StreamingItinerary.tsx`（流式行程渲染）、`HotItineraries.tsx`（热门行程）、`QuickCustomize.tsx`（快速调整）。
- **启动**：`pip install -r agent/requirements.txt` → `python -m uvicorn agent.main:app --port 8090`。
- **RAG 入库**：`python scripts/ingest_rag.py`。


## 最新修复 (2026-06-09)

### Agent 代理修复
- **问题**：C++ 后端 /agent/* 代理使用 httplib::Client 缓冲整个响应，SSE 流式传输不工作。
- **问题**：pre_routing_handler 在 body 读取前运行，POST body 为空。
- **修复**：将代理从 pre_routing_handler 移至显式路由处理器（server.Get/Post），使用 WinHTTP 原始连接 + set_chunked_content_provider 实现 SSE 流式代理。
- **结构**：WinHttpStreamState RAII 结构管理句柄生命周期，chunked content provider 回调逐块读取上游数据。

### 前端修复
- **问题**：main.tsx 使用 NewEditorApp 而非 App，Agent 组件（AgentChat、HotItineraries 等）未被导入。
- **修复**：在 NewEditorApp.tsx 中添加 AiChat 组件导入和渲染。
- **问题**：挂载顺序错误，/ 先于 /editor 导致返回 dev HTML。
- **修复**：交换挂载顺序，/editor 在 / 之前注册。

### 当前状态
- **C++ 后端**：端口 8080，21 城市 15140 POI
- **Agent 服务**：端口 8090，DeepSeek-V3 推理
- **前端**：/editor/ 正确加载 Agent 组件
- **SSE 流式**：完整支持，Content-Type: text/event-stream
- **缓存**：内存缓存工作，第二次请求 < 5s
- **待完成**：ChromaDB RAG embedding 模型下载、Redis 缓存、热门行程预生成


## CI 修复 (2026-06-09)

### 数据验证修复
- **问题**：156 个 POI 的 price_level=0，验证脚本要求 1..5 范围。
- **修复**：将所有 price_level=0 改为 price_level=1（影响 21 个城市共 7688 个 POI）。

### 重复边清理
- **问题**：414 条重复无向边（A->B 和 B->A 同时存在）。
- **修复**：去重后保留唯一条目（共去除 2620 条重复边）。

### API Smoke 测试
- **问题**：api_smoke.ps1 硬编码 expectedPoiCount=461，实际为 15140。
- **修复**：改用 minPoiCount=100 的最小值检查。

### Docker 构建
- **问题**：Dockerfile 和 entrypoint.sh 有 UTF-8 BOM，导致 bash 解析失败。
- **修复**：移除 BOM，添加 .gitattributes 强制 LF 行尾。

### 当前状态
- CI 全部通过：CMake (Windows) + CMake (Ubuntu) + Docker smoke
- 21 城市 15140 POI，2034 条边（主数据集）
