# Tour Pass

Tour Pass 是一个 C++17 城市自由行行程规划算法服务作品集项目。当前使用长沙本地样例数据：`25` 个 POI 节点、`46` 条通勤边，其中包含酒店、景点、餐厅和夜间活动点。项目将样例 POI 建模为带时间窗约束的图，结合 Dijkstra/A* 最短路、兴趣评分、时间窗调度、餐饮插入、POI 检索和 LLM/模板解释生成多日旅行计划。

当前演示链路围绕面试展示优化：输入偏好后生成多候选行程，页面展示真实策略差异、候选对比指标、候选多样性指标、Pareto 非支配层级、站点评分拆解、每日通勤优化、严格时间窗复核、约束命中、未安排原因、路径查询、场景替换和自然语言说明。未配置 LLM 时仍会使用本地中文模板兜底，保证离线演示可运行。

边界说明：当前默认样例图规模很小，Dijkstra/A* 在这里不是用来证明大规模图搜索性能，而是展示建模方式、接口链路和后续扩展位置。项目新增高德 Web 服务采集流水线，可在本地用 `AMAP_API_KEY` 生成长沙几百个真实 POI；synthetic 数据只作为压力测试/复杂度趋势口径。`cpp-httplib` 用于本地演示 HTTP 服务，不包装成生产级 C++ Web 框架经验。

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
curl.exe "http://127.0.0.1:8080/route/shortest?from=hotel_wuyi&to=yuelu_academy&algorithm=astar"
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

## MVP 边界

- 默认样例通勤耗时来自 `data/edges.json`。
- 可通过高德 Web 服务脚本采集 `200+` 长沙真实 POI，并用距离测量/路径规划生成带来源标记的通勤边；正式真实数据报告建议使用 `--fallback fail --min-amap-ratio 0.8`，如果边来源是 `geo_estimated`，仍只能视为估算通勤图。
- 已提供 `web/` 本地演示台，由 C++ 服务直接托管，面向面试现场展示候选方案、约束解释、路径查询、替换方案和模板/LLM 说明。
- 已实现 A* 路径查询、Top-K 候选行程和场景替换方案。
- 已实现日内局部交换优化、优化摘要、约束解释、未安排原因、候选对比指标和站点级评分拆解。
- 已接入 SQLite 持久化规划请求、异步任务、benchmark 记录和数据版本，但不把 SQLite 放进规划热路径；POI/edge 仍在启动时加载到内存图。
- 当前并发目标是单机 200 并发挑战下的背压、结构化错误和指标可观察，不包装成分布式高并发系统。
- 当前 CMake 配置可构建现有轻量测试，并可选启用 GoogleTest。
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
node scripts/benchmark.js --app bin/tourpass.exe --port 8092 --duration 60 --warmup 5 --concurrency-steps 1,10,50,100,200 --job-iterations 20 --record-db --report docs/performance_report.md
node scripts/benchmark.js --app bin/tourpass.exe --port 8093 --duration 60 --warmup 5 --concurrency-steps 1,10,50,100 --job-iterations 10 --bypass-cache --report docs/performance_report_bypass_cache.md
node scripts/import_real_pois.js --input tests/fixtures/real_pois_sample.csv --out-dir output/real-import --neighbors 4
node scripts/validate_data.js --pois output/real-import/pois.json --edges output/real-import/edges.json
node scripts/fetch_amap_pois.js --config config/amap.changsha.json --out-dir output/amap-changsha --min-pois 200
node scripts/build_commute_edges.js --pois output/amap-changsha/pois.json --out-dir output/amap-changsha --neighbors 6 --fallback fail --min-amap-ratio 0.8 --mode mixed --batch-size 100
node scripts/validate_data.js --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --min-pois 200 --require-edge-source
node scripts/generate_synthetic_data.js --pois 1000 --out-dir output/synthetic-1000
node scripts/scale_experiment.js --app bin/tourpass.exe --port 8100 --sizes 100,500,1000 --iterations 3 --report docs/scale_experiment_report.md
node scripts/scale_experiment.js --app bin/tourpass.exe --port 8100 --dataset real --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --sizes 100,200 --iterations 5 --cache-mode auto --report docs/scale_experiment_report.md --json-report output/scale_experiment_report.json
node scripts/algorithm_quality_check.js --app bin/tourpass.exe --port 8110 --subset 9 --report docs/algorithm_quality_report.md
node scripts/load_test.js --url http://127.0.0.1:8080/health --concurrency 100 --duration 30 --report docs/load_test_report.md
powershell -ExecutionPolicy Bypass -File scripts/run_hey.ps1 -Url http://127.0.0.1:8080/health -Concurrency 100 -Duration 30s
```

`scripts/import_real_pois.js` 用于把 CSV/JSON 形式的真实 POI 清单标准化为项目 `pois.json`，并按地理距离生成近邻通勤边；它适合接入人工整理、公开数据或后续地图 API 导出的 POI 列表。数据质量校验会检查 POI 字段、坐标、时间窗、类型覆盖、边引用、边权合法性和图连通性；CI 与本地 `validate-data` 使用同一脚本，`--pois` / `--edges` 可校验导入后的临时数据集。

`scripts/fetch_amap_pois.js` 和 `scripts/build_commute_edges.js` 是真实规模数据主入口，详见 [docs/real_data_pipeline.md](docs/real_data_pipeline.md) 和 [docs/real_data_runbook.md](docs/real_data_runbook.md)。前者需要本地 `AMAP_API_KEY`，后者会在高德距离/路径不可用时按参数决定失败或退回地理估算并标记边来源；真实数据报告见 [docs/real_data_report.md](docs/real_data_report.md)。

性能报告只用于本地性能回归检查，不代表生产压测。`scripts/load_test.js` 提供无额外依赖的 HTTP 压测口径，可记录 QPS、avg、p95、p99 和错误率；`scripts/run_hey.ps1` 可在已安装 `hey` 时运行标准工具口径。正式生产压测仍需要真实部署、真实流量分布、资源监控，并明确 worker、队列、in-flight、是否绕过缓存、是否调用外部 LLM、是否包含真实地图 API 或数据库 IO。

如果本机已安装 Playwright 浏览器运行时，也可以启动服务后运行 UI 验证脚本：

```powershell
npx.cmd playwright install chromium
npx.cmd --yes --package playwright node scripts/verify_ui.js http://127.0.0.1:8080/
```
