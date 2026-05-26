# Tour Pass

C++17 城市旅行行程规划算法服务。基于长沙 **500 个真实高德 POI** 和 **1937 条通勤边**，通过 Dijkstra/A* 最短路、Beam Search 时间槽规划、BM25 文本检索、Pareto 多目标排序生成多候选多日行程。前端集成 Leaflet 地图可视化，路线直接展示在 OpenStreetMap 上。

核心能力：
- **Beam Search** 在上午/午餐/下午/晚餐/晚上时间槽中保留 Top-K 状态，综合评分、通勤和时间窗约束规划路线
- **5 种策略候选**：少走路、紧凑、文化优先、美食优先、雨天室内，Pareto 非支配排序量化取舍
- **严格时间窗复核**：开放时间、餐饮窗口、站点顺序、当日结束时间
- **BM25 检索**：字段权重 + 匹配词解释
- **Leaflet 地图**：每日路线 polyline + marker popup 展示站点详情，A* 路径查询结果地图绘制
- **LLM 解释**：OpenAI/DeepSeek 兼容接口，无密钥时自动使用本地中文模板兜底

数据规模：500 POI（240 景点 / 160 餐饮 / 65 酒店 / 35 夜生活），覆盖长沙 9 个区。

## 环境要求

- Windows
- MinGW `g++`
- `mingw32-make`
- 可选 OpenSSL，仅在需要通过 CMake 直接请求 HTTPS LLM 接口时使用

## 常用命令

Makefile 构建：

```powershell
mingw32-make build
mingw32-make test
mingw32-make run
mingw32-make clean
```

CMake 构建：

```powershell
cmake -S . -B build
cmake --build build
ctest --test-dir build
```

CMake 会在检测到 OpenSSL 时自动为 `cpp-httplib` 启用 HTTPS LLM 调用；没有 OpenSSL 时仍可构建和使用模板兜底、本地 HTTP mock 或离线演示。

启用 GoogleTest 版本测试：

```powershell
cmake -S . -B build -DTOURPASS_USE_GTEST=ON
cmake --build build
ctest --test-dir build
```

当前仓库仍保留轻量测试程序，方便没有 CMake 或 GoogleTest 的环境直接验证。

服务默认监听：

```text
http://127.0.0.1:8080
```

启动后可直接打开本地演示页面：

```text
http://127.0.0.1:8080/
```

可用环境变量修改端口：

```powershell
$env:PORT="8090"
mingw32-make run
```

也可以调整服务端运行时参数：

```powershell
$env:TOURPASS_WORKERS="8"
$env:TOURPASS_MAX_QUEUE="64"
$env:TOURPASS_MAX_IN_FLIGHT="32"
$env:TOURPASS_JOB_WORKERS="2"
$env:TOURPASS_CACHE_ENTRIES="64"
$env:TOURPASS_DISTANCE_CACHE_MODE="auto"
$env:TOURPASS_DISTANCE_CACHE_MAX_POIS="500"
$env:TOURPASS_DISTANCE_CACHE_ENTRIES="10000"
$env:TOURPASS_BEAM_WIDTH="5"
$env:TOURPASS_BRANCH_FACTOR="6"
$env:TOURPASS_DB_PATH="storage/tourpass.sqlite"
mingw32-make run
```

服务会为响应附加 `X-Request-Id` 和 `X-Response-Time-Ms`；`/route/shortest`、`/poi/search` 和 `/trip/plan` 支持进程内热点缓存，并通过 `X-Cache` 展示命中状态。POI 最短路缓存支持 `auto|all_pairs|on_demand|disabled`：默认在 `500` POI 以内使用全量缓存，几百点规模优先采用简单方案；超过阈值才切到按需 LRU，LRU 是保护策略而不是小规模亮点。SQLite 默认写入 `storage/tourpass.sqlite`，用于规划请求、异步任务、benchmark 和数据版本记录；规划热路径仍使用启动时加载的内存图。

## LLM 配置

默认读取 `config/llm.local.json`。如果同时存在本地配置和一个残留的 `OPENAI_API_KEY`，本地配置优先；只有未配置本地密钥，或显式设置 `LLM_BASE_URL` / `LLM_MODEL` 切换提供商时，环境变量才会覆盖：

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:LLM_BASE_URL="https://api.openai.com/v1"
$env:LLM_MODEL="gpt-4o-mini"
```

也可以复制 `config/llm.example.json` 为 `config/llm.local.json` 后填写本地配置。`config/llm.local.json` 已被 `.gitignore` 排除。
DeepSeek 可使用 OpenAI 兼容配置，例如 `base_url` 为 `https://api.deepseek.com`，`model` 为 `deepseek-v4-flash`。

远程调用使用内置 `cpp-httplib` HTTP client 发起 OpenAI 兼容 `chat/completions` 请求，不再通过 `curl.exe` 子进程拼接命令。未配置密钥或远程调用失败时，`/itinerary/explain` 会自动使用本地中文模板。
Windows Makefile 构建在未启用 OpenSSL 时会通过系统 WinHTTP 兜底发起 HTTPS LLM 请求；CMake 检测到 OpenSSL 时仍优先使用 `cpp-httplib` HTTPS 支持。
面试或离线演示时可显式禁用远程 LLM，强制使用模板兜底：

```powershell
$env:LLM_DISABLED="1"
mingw32-make run
```

## API 示例

完整 API 文档见 [docs/api.md](docs/api.md)，OpenAPI/Swagger 规范见 [docs/openapi.yaml](docs/openapi.yaml)，架构与面试演示路径见 [docs/architecture.md](docs/architecture.md)，算法细节与面试讲解路径见 [docs/algorithm.md](docs/algorithm.md)。

健康检查：

```powershell
curl.exe http://127.0.0.1:8080/health
```

生成行程：

```powershell
curl.exe -X POST http://127.0.0.1:8080/trip/plan `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@docs/sample_trip_request.json"
```

检索 POI：

```powershell
curl.exe "http://127.0.0.1:8080/poi/search?q=历史文化&limit=5"
```

检索模块使用轻量 BM25、字段权重和匹配词解释，响应包含 `matched_terms` 与 `score_explanation`，方便说明为什么某个 POI 排在前面。

生成 Top-K 候选行程：

```powershell
curl.exe -X POST http://127.0.0.1:8080/trip/plan `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@docs/sample_candidate_request.json"
```

候选方案会通过 `variant_name`、`strategy`、`comparison` 和每日 `summary` 说明差异，例如轻松少走路、紧凑多覆盖、文化优先、美食优先和雨天室内。`comparison` 还包含相对基线的 POI 重合率、区域重合率、独有 POI 和多样性标签，用于量化候选之间到底有多不同。每个站点的 `reason` 和 `score_breakdown` 字段会解释兴趣匹配、通勤成本、策略加权、评分和开放时间等决策依据。
日内路线由 Beam Search 在上午、午餐、下午、晚餐、晚上等时间槽中保留 Top-K 局部状态，综合评分、通勤、开放时间和必去覆盖选择路线。
最终路线会输出 `time_window_feasible`、`time_window_diagnostics`、`stops[].time_window_status` 和 `stops[].time_window_reason`，统一复核站点顺序、开放时间、餐饮窗口和当日结束时间。
`docs/sample_candidate_request.json` 默认请求 5 个候选，适合一次展示完整策略矩阵。
`comparison.pareto_rank` 会标记多目标非支配层级，用于说明候选方案在评分、通勤、风险和必去覆盖之间的取舍。

查询最短路径：

```powershell
curl.exe "http://127.0.0.1:8080/route/shortest?from=amap_d0197c46&to=amap_f3d362be&algorithm=astar"
```

获取替换方案：

```powershell
curl.exe -X POST http://127.0.0.1:8080/trip/alternatives `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@docs/sample_alternatives_request.json"
```

解释行程：

```powershell
curl.exe -X POST http://127.0.0.1:8080/itinerary/explain `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@docs/sample_trip_request.json"
```

提交异步规划任务：

```powershell
curl.exe -X POST http://127.0.0.1:8080/trip/jobs `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@docs/sample_candidate_request.json"
```

查询服务指标：

```powershell
curl.exe http://127.0.0.1:8080/metrics
```

查询持久化任务历史：

```powershell
curl.exe "http://127.0.0.1:8080/history/jobs?limit=20"
```

## 项目边界

- 默认数据为高德采集的 500 个长沙真实 POI + 1937 条通勤边，测试使用 25-POI 样本数据。
- 规划热路径使用启动时加载的内存图，SQLite 仅用于请求记录、异步任务和 benchmark，不参与规划计算。
- 前端由 C++ 服务直接托管，集成 Leaflet + OpenStreetMap 地图可视化。
- 并发目标为单机背压、结构化错误和指标可观察，不做分布式。
- CMake 可通过 `-DTOURPASS_USE_GTEST=ON` 构建 GoogleTest 测试目标。

## Docker 与部署

本地构建镜像：

```powershell
docker build -t tour-pass:local .
docker run --rm -p 8080:8080 -e LLM_DISABLED=1 tour-pass:local
node scripts/container_smoke.js http://127.0.0.1:8080
```

Docker 镜像默认监听 `0.0.0.0:8080`，并将 `LLM_DISABLED=1` 作为演示安全默认值。部署细节、GHCR 镜像、Render/Fly/Railway 风格配置、SQLite 持久化和健康检查说明见 [docs/deployment.md](docs/deployment.md)。

## 一键演示

```powershell
powershell -ExecutionPolicy Bypass -File scripts/demo.ps1
```

脚本会构建服务、启动本地进程、检查 `/health` 并输出候选行程冒烟测试结果。

## CI 与冒烟验证

仓库提供 GitHub Actions 工作流 `.github/workflows/ci.yml`，在 PR 和 main push 时执行 Ubuntu/Windows CMake 构建与 CTest，并在 Windows 上启动服务运行核心 API 冒烟测试。本地也可以运行：

```powershell
mingw32-make validate-data
node scripts/validate_data.js
powershell -ExecutionPolicy Bypass -File scripts/api_smoke.ps1 -AppPath bin/tourpass.exe -Port 8091
node scripts/benchmark.js --app bin/tourpass.exe --port 8092 --duration 60 --warmup 5 --concurrency-steps 1,10,50,100,200 --job-iterations 20 --record-db
node scripts/import_real_pois.js --input tests/fixtures/real_pois_sample.csv --out-dir output/real-import --neighbors 4
node scripts/validate_data.js --pois data/pois.json --edges data/edges.json --min-pois 200
```

数据质量校验检查 POI 字段、坐标、时间窗、类型覆盖、边引用、边权合法性和图连通性。

如果本机已安装 Playwright 浏览器运行时，也可以启动服务后运行 UI 验证脚本：

```powershell
npx.cmd playwright install chromium
npx.cmd --yes --package playwright node scripts/verify_ui.js http://127.0.0.1:8080/
```
