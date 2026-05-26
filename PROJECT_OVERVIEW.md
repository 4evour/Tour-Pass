# Tour Pass 项目说明

## v4.0 Hybrid AI Architecture

- 新增 `POST /trip/chat` 自然语言行程规划端点：LLM 从用户中文输入中提取结构化 TripRequest，通过 BM25 模糊匹配 POI 名称，调用 Beam Search 生成多候选行程，再由 LLM 生成自然语言回复。这是 LLM + 传统算法 Hybrid 架构的核心端点。
- 新增 `TravelTimeProvider` 抽象接口：支持 `local`（本地 edges.json）和 `amap`（高德实时路线 API）两种数据源，通过 `TOURPASS_TRAVEL_TIME_PROVIDER` 环境变量切换；`AmapLiveProvider` 实现 LRU 缓存和 API 失败时自动 fallback 到本地数据。
- 新增多城市数据管理：`TOURPASS_CITY` 环境变量选择加载 `data/{city}/` 目录下的数据集；新增 `config/amap.wuhan.json` 武汉 POI 采集配置。
- `/health` 端点新增 `travel_provider` 字段，展示当前通勤时间数据源。
- `LlmClient` 重构：提取通用 `chatCompletion()` 方法，支持多轮对话上下文。
- 恢复 worktree 中的面试文档（interview Q&A、简历亮点、性能报告等 13 个文件）。

## v3.0 Real POI Map Demo

- 默认数据集已切换为长沙 `500` 个高德 POI 与 `1937` 条通勤边；原 `25` POI 样例数据保留为 `data/pois_sample.json` 与 `data/edges_sample.json`，测试改用样例数据以保持快速稳定。
- 规划停靠点 JSON 新增 `lat` / `lng`，`/route/shortest` 响应新增 `path_coords`，用于前端地图绘制。
- `web/` 演示台新增 Leaflet + OpenStreetMap 地图：规划结果按每日路线绘制 marker/polyline，A* 路径查询也会绘制路径点。
- 一批面试/报告类 `docs/*.md` 文档已从项目中删除；README 收敛为当前真实 POI 数据、地图演示和核心能力说明。

## v2.9 CI Dependency Updates

- 本地 `main` 已合并 GitHub 主线安全修复提交，并整合 Dependabot 的 GitHub Actions 升级分支：`actions/checkout` 升至 `v6.0.2`、`actions/setup-node` 升至 `v6.4.0`、`docker/login-action` 升至 `v4.2.0`；这些变更只影响 `.github/workflows/ci.yml` 的 CI action 版本锁定。

## v2.8 Real Data Ops

- 新增 `scripts/run_real_data_pipeline.js`，可一键串联高德 POI 采集、通勤边生成、数据校验和真实规模实验；默认口径沿用本机已验证的 `500 POI`、`neighbors=6`、`mode=driving`、`fallback=geo_estimated`、`min_amap_ratio=0.7`、`sizes=100,200,500`。
- 新增 `scripts/retry_geo_edges.js`，只重试 `source=geo_estimated` 的边并输出重试报告；2026-05-22 本机重试将 `231` 条估算边中的 `202` 条转为高德来源，使高德边比例从 `88.1%` 提升到 `98.5%`。
- 新增 `scripts/real_data_smoke.js`，用于验证真实数据服务的 `/health.distance_cache` 字段、POI/edge 数、高德边比例、`/trip/plan` 和 `/poi/search`。
- 新增 `docs/real_data_ops.md` 与 `docs/real_data_retry_report.md` 作为干净的命令和结果引用；完整高德产物、原始响应和 API key 仍只保存在被忽略的 `output/` 路径，不得提交。
- `TOURPASS_MAX_IN_FLIGHT` 默认由运行时环境推导为 worker 数的 4 倍；手动构造 `RuntimeConfig` 时 `maxInFlightRequests=0` 表示不启用额外 in-flight 限流，避免默认结构体误拒首个请求。

## 项目目标

Tour Pass 是一个 C++17 城市自由行行程规划算法服务作品集项目。MVP 使用长沙本地样例数据，将景点、餐厅、酒店和夜间活动点建模为 POI 图，通过最短路、兴趣评分、评分拆解、时间窗调度、餐饮插入、文本检索和 LLM/模板解释生成多日旅游计划。当前优先面向简历和面试展示，强调候选方案对比、约束解释、通勤优化和离线可演示性；对外表达时必须说明样例数据、本地基准和演示服务边界。

## 技术栈

- 语言：C++17
- 构建：Makefile + MinGW `g++` + `mingw32-make`
- CMake：已提供 `CMakeLists.txt`，本机使用 MinGW generator 验证通过；检测到 OpenSSL 时自动启用 HTTPS LLM 调用
- Docker：提供多阶段 `Dockerfile`，Linux 容器内 CMake Release 构建并运行 `tourpass`；容器默认 `HOST=0.0.0.0`、`PORT=8080`、`LLM_DISABLED=1`
- HTTP：`cpp-httplib` 单头文件，位于 `third_party/httplib.h`，用于本地演示服务和 LLM client 复用；Windows Makefile 构建在未启用 OpenSSL 时通过系统 WinHTTP 兜底发起 HTTPS LLM 请求。它适合轻量嵌入和面试演示，不按生产级 C++ Web 框架包装。
- 服务运行时：基于 `cpp-httplib` 线程池、中间件 hook、进程内 LRU/TTL 缓存、JSON 指标、异步规划任务仓库、in-flight 背压和 SQLite 持久化实现单机生产化雏形演示；HTTP 层仅按本地演示服务表达，不包装为生产级 C++ Web 框架经验
- JSON：`nlohmann/json` 单头文件，位于 `third_party/json.hpp`
- 数据：本地 JSON 文件，`data/pois.json` 和 `data/edges.json`；当前长沙样例为 `25` 个 POI 节点、`46` 条通勤边
- 测试：轻量 C++ 测试运行器，命令为 `mingw32-make test`；CMake 可选启用 GoogleTest 目标
- 前端验证：本地 npm 开发依赖 `playwright`；`npm.cmd run verify:ui -- http://127.0.0.1:8080/` 可在服务启动后运行 UI 冒烟验证，脚本会优先使用 Playwright 浏览器，缺失时自动尝试本机 Chrome/Edge

## 目录结构

- `include/tourpass/`：公共头文件和模块接口
- `src/`：服务端、算法、数据加载、检索和 LLM 实现
- `data/`：长沙 POI 与通勤边样例数据
- `tests/`：核心行为测试
- `third_party/`：第三方单头文件依赖
- `config/`：LLM 配置示例，真实本地配置不提交
- `docs/`：简历表达、API、架构、算法说明和项目说明材料
- `docs/project_explainer_for_interview.md`：面向面试复习的项目解释文档，串联业务目标、技术结构、核心算法、接口链路和可讲亮点。
- `docs/interview_questions_answers.md`：面试高频问题与标准答案，覆盖项目介绍、算法取舍、工程质量、局限与迭代方向。
- `scripts/`：本地演示和 API 冒烟验证脚本
- `web/`：本地静态演示页面，由 C++ 服务直接托管

## 运行与测试

- 构建：`mingw32-make build`
- 运行：`mingw32-make run`
- 测试：`mingw32-make test`
- 数据校验：`mingw32-make validate-data` 或 `node scripts/validate_data.js`
- UI 验证：服务启动后执行 `npm.cmd run verify:ui -- http://127.0.0.1:8080/`
- 清理：`mingw32-make clean`

默认监听 `127.0.0.1:8080`，可通过环境变量 `PORT` 修改端口。
演示页面地址为 `http://127.0.0.1:8080/`。

## 核心流程

1. 启动时加载 `data/pois.json` 与 `data/edges.json`。
2. 建立 POI 图，并在启动期预计算 POI 两两最短通勤缓存；`shortestMinutes()` 供规划热路径 O(1) 读取，`/route/shortest` 仍保留 Dijkstra/A* 路径查询能力。
3. `/trip/plan` 根据用户兴趣、必去点、节奏和时间窗生成多日行程；日内路线使用 Beam Search 在固定时间槽保留 Top-K 局部状态，进入完整评分前先按类型、时间窗、策略标签和必去点裁剪候选池；`candidate_count` 大于 1 时生成轻松少走路、紧凑多覆盖、文化优先、美食优先、雨天室内等候选策略方案。
4. `/poi/search` 使用轻量 BM25、字段权重和热度加权检索 POI 描述和标签，并返回匹配词与排序解释。
5. `/route/shortest` 使用 Dijkstra 或 A* 返回 POI 间最短通勤路径。
6. `/trip/alternatives` 按下雨、闭馆、太累、预算降低等场景召回替换方案。
7. `/itinerary/explain` 使用内置 `cpp-httplib` client 调用 OpenAI/DeepSeek 兼容接口，失败或无密钥时返回本地中文模板。
8. `web/` 演示台按规划概览、候选对比、路线明细、算法解释和工具箱分阶段展示；覆盖偏好输入、候选方案概览、路线与时间轴可视化、候选对比指标、候选多样性指标、Pareto 非支配层级、Beam Search 调试轨迹、BM25 排序贡献、站点评分拆解、严格时间窗复核、每日 KPI、约束命中、未安排原因、路径查询、替换方案和自然语言说明。

## 关键约定

- GitHub 仓库地址：`https://github.com/4evour/Tour-Pass`。
- LLM 默认读取 `config/llm.local.json`；本地配置存在密钥时不会被单独残留的 `OPENAI_API_KEY` 覆盖，只有未配置本地密钥或显式设置 `LLM_BASE_URL` / `LLM_MODEL` 切换提供商时，环境变量才会覆盖。
- `LLM_DISABLED=1` 可在面试或离线演示时强制禁用远程 LLM，使用本地中文模板兜底。
- `TOURPASS_WORKERS`、`TOURPASS_MAX_QUEUE`、`TOURPASS_MAX_BODY_BYTES`、`TOURPASS_CACHE_ENTRIES`、`TOURPASS_CACHE_TTL_SECONDS`、`TOURPASS_MAX_TRIP_JOBS` 和 `TOURPASS_JOB_WORKERS` 可调整 HTTP 线程池、队列、请求体限制、缓存和异步任务容量。
- `TOURPASS_MAX_IN_FLIGHT` 控制进行中请求背压；`TOURPASS_DB_PATH` 控制 SQLite 路径，默认 `storage/tourpass.sqlite`；`TOURPASS_DB_DISABLED=1` 可禁用 SQLite 退回纯内存模式。
- `TOURPASS_POIS_PATH` 和 `TOURPASS_EDGES_PATH` 可覆盖默认 `data/` 样例路径，用于 synthetic POI 规模实验或高德真实 POI 临时数据集。
- `TOURPASS_DISTANCE_CACHE_MODE=auto|all_pairs|on_demand|disabled` 控制 POI 最短路缓存策略；`TOURPASS_DISTANCE_CACHE_MAX_POIS` 控制 `auto` 模式全量缓存阈值，默认 `500`，使 200 级真实 POI 优先使用简单全量缓存；`TOURPASS_DISTANCE_CACHE_ENTRIES` 控制超阈值按需 LRU 缓存容量。
- `TOURPASS_BEAM_WIDTH` 和 `TOURPASS_BRANCH_FACTOR` 控制 Beam Search 保留状态数和每槽候选分支数，默认保持 `5` / `6`。
- `scripts/import_real_pois.js` 可将 CSV/JSON 形式的真实 POI 清单标准化为项目 `pois.json`，并按地理距离生成近邻通勤边；`scripts/validate_data.js --pois <path> --edges <path>` 可校验导入后的临时数据集。
- `scripts/fetch_amap_pois.js` 可通过高德 Web 服务按配置分页采集长沙真实 POI，依赖本地 `AMAP_API_KEY`，支持 `--min-pois 200` 门禁，并输出 `pois.json`、manifest、类型/区域/重复/失败页统计和采集报告；`scripts/build_commute_edges.js` 为 POI 近邻生成通勤边，支持高德距离/路径优先、`--fallback fail|geo_estimated`、`--min-amap-ratio`、`--mode driving|walking|mixed` 和 `--batch-size`，edge 会标记 `source`、`provider`、`mode`、`duration_seconds` 与 `amap_status`。
- `scripts/algorithm_quality_check.js` 用 8-10 个候选 POI 子集的精确枚举基线、贪心 baseline 与 Beam Search 同口径对照，报告写入 `docs/algorithm_quality_report.md`。
- `docs/real_data_runbook.md` 记录从 `AMAP_API_KEY` 到 `200+`/`500` POI、真实通勤边、数据校验和真实规模实验的命令链；`docs/real_data_report.md` 记录 2026-05-22 本机聚合结果：`500 POI / 1937 edges`、`amap=1706`、`geo_estimated=231`、高德边比例 `88.1%`、500 POI scale p95 约 `128.9 ms`；`docs/demo_recording_checklist.md` 记录 Docker/报告/接口的 3 分钟演示录屏脚本。
- GitHub Actions 工作流 `.github/workflows/ci.yml` 在 Ubuntu/Windows 上运行数据验证、CMake 构建和 CTest，并在 Windows 上执行 `scripts/api_smoke.ps1`；Docker job 会构建镜像、启动容器、运行 `scripts/container_smoke.js`，main push 可推送 GHCR 镜像。
- OpenAPI/Swagger 规范位于 `docs/openapi.yaml`；部署指南位于 `docs/deployment.md`；通用 HTTP 压测脚本为 `scripts/load_test.js`，报告写入 `docs/load_test_report.md`；`scripts/run_hey.ps1` 可在本机已安装 `hey` 时运行标准工具压测口径。
- 本地配置文件为 `config/llm.local.json`，不得提交真实密钥。
- 统一 API 错误格式为 `{ "error": { "code", "message", "details" } }`。
- MVP 不接真实地图 API，通勤时间全部来自 `edges.json`。
- 样例数据更新后应运行 `scripts/validate_data.js`；校验覆盖 POI 字段、坐标、时间窗、类型覆盖、边引用、边权合法性和图连通性。
- 规划结果解释优先复用既有响应字段，并向 `/trip/plan` 响应补充 `strategy`、`comparison`、`comparison.pareto_debug`、`comparison.diversity_*`、`days[].beam_trace`、`days[].time_window_*`、`stops[].time_window_*` 和 `stops[].score_breakdown`；不额外引入破坏性路由结构。

## 已知风险

- Makefile 默认链接 `winhttp`，Windows 本地演示可在无 OpenSSL 时调用 DeepSeek/OpenAI 兼容 HTTPS LLM；CMake 检测到 OpenSSL 时仍使用 `cpp-httplib` HTTPS 支持。
- 样例数据为演示级人工整理数据，不代表实时营业、拥堵或闭馆状态。
- `docs/performance_report.md` 的性能数据来自本地样例和 `LLM_DISABLED=1`，适合说明回归检查；必须区分冷缓存、热缓存、绕过缓存、梯度并发、P95/P99、吞吐量和错误率，不应表述为生产压测结果。
- `docs/scale_experiment_report.md` 的 synthetic 规模实验用于暴露趋势和瓶颈；当前报告覆盖 `25,100,200` POI、`LLM_DISABLED=1`，报告 avg/p95/p99/max、失败数、最短路缓存 entries 和边来源比例。该口径只能说明本地算法热路径趋势，不代表真实地图、真实交通或生产压测。
- 真实 POI 导入脚本生成的是近邻估算通勤边，不等价于真实地图路网；面试表达中应说它解决“真实 POI 数据进入项目格式”的工程入口，真实通勤仍需地图 API 或人工校准。
- 最短路缓存为 `O(POI^2)` entries，适合当前 synthetic 规模和本地演示；若扩展到几万 POI，应改为热点缓存、区域分层图或按需缓存，不能无脑全量预计算。
- v2.6+ 已将最短路缓存改为可配置策略：`500` POI 以内默认全量缓存，超过阈值才使用按需 LRU；`/health.distance_cache` 会暴露 mode、entries、startup_ms、hits、misses 和 evictions。面试表达应强调几百点规模优先简单方案，LRU 是超阈值保护策略。
- 高德真实 POI 采集需要用户本地提供 `AMAP_API_KEY`，不得提交密钥或原始响应；2026-05-22 本机真实数据用 `fallback=geo_estimated` 生成可运行连通图，需明确披露 `geo_estimated` 占比，不能表达为完整真实地图路网。强门禁 `--fallback fail --min-amap-ratio 0.8` 可用于拒绝低覆盖数据。
- `cpp-httplib` 用于降低依赖和方便本地复现；如果后续生产化，应评估 Drogon、Pistache、Boost.Beast 或 Go/Java 服务框架，并补充更完整的连接治理、观测和部署方案。
- SQLite 用于规划请求、异步任务、benchmark 和数据版本持久化；规划热路径仍使用内存图，不能表述为数据库支撑高并发。
- Docker 镜像、OpenAPI、部署指南和压测报告用于说明工程完备性；压测报告必须记录 `LLM_DISABLED`、worker、队列、in-flight、DB 和缓存口径，仍不能把当前项目包装成已上线生产平台、生产 SLA 或已有线上 Demo。
- Makefile 默认使用轻量测试运行器；CMake 可选启用 GoogleTest 目标。
- CMake 可通过 `-DTOURPASS_USE_GTEST=ON` 构建 GoogleTest 测试；当前已验证默认 CTest 目标。
- Windows PowerShell 直接内联中文 JSON 容易出现编码问题，文档示例统一使用 `--data-binary @docs/sample_trip_request.json`。
- v0.2 增加 `candidate_count` 候选行程、`/route/shortest` 路径查询和 `/trip/alternatives` 场景替换接口。
- v0.3 增加 `web/` 本地演示台，包含偏好输入、候选行程展示、路径查询、替换方案和行程解释。
- v0.4 增加日内局部交换优化、优化摘要、约束解释、未安排原因和 CMake 构建配置。
- v0.5 跑通 CMake + GoogleTest，新增 API 文档和一键演示脚本。
- v0.6 增强面试展示链路：候选方案差异说明、站点级决策依据、算法/约束解释文案、Web 候选概览、演示状态提示和 `LLM_DISABLED` 模板演示开关。
- v0.7 增加候选方案对比指标和站点评分拆解，Web 演示台可直接展示方案取舍和分数来源。
- v0.8 增加真实候选策略权重：轻松少走路、紧凑多覆盖、文化优先、美食优先和雨天室内会通过不同评分组件影响 POI 选择与解释；候选演示样例默认请求 5 个方案。
- v0.9 增加候选方案 Pareto 非支配排序，在 `comparison` 中输出 `pareto_rank`、`dominated` 和 `tradeoff_summary`，用于解释评分、通勤、风险和必去覆盖之间的多目标取舍。
- v1.0 将日内规划升级为 Beam Search Top-K 状态搜索，替换 LLM `curl.exe` 子进程为内置 HTTP client，并新增 GitHub Actions 跨平台 CMake/CTest 与 Windows API 冒烟验证。
- v1.1 将候选排序改为标准 Pareto 非支配分层，检索升级为 BM25 + 字段权重，新增 `scripts/validate_data.js` 数据质量门禁和 `docs/architecture.md` 架构说明。
- v1.2 增加 Web 路线带与每日时间轴可视化，新增 `scripts/benchmark.js` 性能基准脚本和 `docs/performance_report.md` 基准报告。
- v1.3 增强数据质量门禁，新增本地 `validate-data` 目标，并补充 `docs/algorithm.md` 说明 Dijkstra/A*、Beam Search、评分拆解、Pareto 非支配排序和 BM25 检索。
- v1.4 增加算法可视化/调试输出：`days[].beam_trace`、`comparison.pareto_debug` 和 `/poi/search` 的 `score_contributions`，Web 演示台展示 Beam Search 保留状态、Pareto 分层依据和 BM25 排序贡献。
- v1.5 增加候选多样性指标：相对基线方案计算 POI 重合率、区域重合率、独有 POI、差异标签和多样性摘要，Web 演示台展示候选是否真正不同。
- v1.6 增加严格时间窗可行性复核：最终顺序统一检查站点顺序、开放时间、餐饮窗口和当日结束时间；理论通勤优化只有在交换顺序仍可行时才计入收益。
- v1.7 优化 Web 演示台信息架构：新增阶段导航，将首页默认收束为规划概览，并把候选对比、路线明细、算法解释和路径/检索/替换/LLM 工具拆到独立演示视图。
- v1.8 补充面试复习材料：新增项目解释文档和面试高频问答文档，用于将架构、算法、API、工程质量与项目边界转化为可讲述的面试表达。
- v1.9 增加后端工程运行时：请求 ID/耗时/安全头/异常兜底中间件、显式线程池、热点缓存、`/trip/jobs` 异步规划任务、`/metrics` JSON 指标、并发 benchmark 和增强 API 冒烟验证。
- v2.0 简历可信度表达调整：项目定位统一为 C++ 算法服务作品集，强调长沙样例 POI、本地演示 HTTP 服务、可解释规划链路和本地基准口径；简历中避免把短周期迭代、`cpp-httplib` 和缓存命中率包装成生产级服务经验。
- v2.1 增加可信性能与规模实验能力：`/health` 输出边数，异步任务改为可配置 worker pool，`/metrics` 输出任务排队/执行耗时，benchmark 支持持续时长、梯度并发、缓存绕过、吞吐量、错误率和 P99，新增 synthetic POI 数据生成脚本。
- v2.2 增加单机生产化雏形：vendored SQLite 3.53.1、规划/任务/benchmark/数据版本持久化、in-flight 背压、`QUEUE_FULL`、`/history/jobs` 和 benchmark `--record-db`。
- v2.3 增强技术含量与可信规模表达：`PoiGraph` 启动期预计算两两最短通勤缓存，`/health.distance_cache` 暴露缓存规模；Beam Search 评分前增加候选池粗筛并复用评分/通勤结果；`scripts/scale_experiment.js` 默认运行 25/100/500 POI synthetic 实验并记录真实失败数，简历表达收敛到可解释规划、热路径优化和可复现实验。
- v2.4 增加真实 POI 导入入口：新增 `scripts/import_real_pois.js` 支持 CSV/JSON POI 清单导入、字段标准化、默认标签/时间兜底和近邻通勤边生成；`validate_data.js` 支持 `--pois` / `--edges` 校验非默认数据集，并新增导入脚本测试。
- v2.5 增加工程完备性交付闭环：新增 Dockerfile/.dockerignore、容器冒烟脚本、GitHub Actions Docker 构建与 GHCR 推送路径、OpenAPI 规范、部署指南和通用 HTTP 压测脚本/报告；服务支持 `HOST`/`TOURPASS_HOST` 配置以适配容器端口映射。
- v2.6 增加真实规模与可信性能改造：新增高德 POI 采集脚本、通勤边生成脚本、真实数据流水线文档、边来源校验、可配置最短路缓存、Beam Search 参数环境变量、小规模算法质量报告、真实/合成 scale experiment 口径和 Render 部署草案。
- v2.7 增加可信数据与演示证据二次优化：真实 POI 已在本机跑通 `500` 个，POI 采集新增最小数量、区域、重复和失败页统计，通勤边生成新增高德来源比例门禁、fallback fail、mode/batch 参数、连通分量桥接和 edge 元数据；缓存默认阈值改为 `500`，算法质量报告新增贪心 baseline，同步补充真实数据 runbook、真实数据聚合报告和 3 分钟录屏清单。
