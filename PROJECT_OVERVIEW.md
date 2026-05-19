# Tour Pass 项目说明

## 项目目标

Tour Pass 是一个 C++17 城市自由行行程规划算法服务。MVP 使用长沙本地样例数据，将景点、餐厅、酒店和夜间活动点建模为 POI 图，通过最短路、兴趣评分、评分拆解、时间窗调度、餐饮插入、文本检索和 LLM/模板解释生成多日旅游计划。当前优先面向简历和面试展示，强调候选方案对比、约束解释、通勤优化和离线可演示性。

## 技术栈

- 语言：C++17
- 构建：Makefile + MinGW `g++` + `mingw32-make`
- CMake：已提供 `CMakeLists.txt`，本机使用 MinGW generator 验证通过；检测到 OpenSSL 时自动启用 HTTPS LLM 调用
- HTTP：`cpp-httplib` 单头文件，位于 `third_party/httplib.h`，服务端和 LLM client 复用同一依赖；Windows Makefile 构建在未启用 OpenSSL 时通过系统 WinHTTP 兜底发起 HTTPS LLM 请求
- 服务运行时：基于 `cpp-httplib` 线程池、中间件 hook、进程内 LRU/TTL 缓存、JSON 指标和异步规划任务仓库实现请求治理与并发演示
- JSON：`nlohmann/json` 单头文件，位于 `third_party/json.hpp`
- 数据：本地 JSON 文件，`data/pois.json` 和 `data/edges.json`
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
2. 建立 POI 图，并用 Dijkstra 计算 POI 间最短通勤时间。
3. `/trip/plan` 根据用户兴趣、必去点、节奏和时间窗生成多日行程；日内路线使用 Beam Search 在固定时间槽保留 Top-K 局部状态；`candidate_count` 大于 1 时生成轻松少走路、紧凑多覆盖、文化优先、美食优先、雨天室内等候选策略方案。
4. `/poi/search` 使用轻量 BM25、字段权重和热度加权检索 POI 描述和标签，并返回匹配词与排序解释。
5. `/route/shortest` 使用 Dijkstra 或 A* 返回 POI 间最短通勤路径。
6. `/trip/alternatives` 按下雨、闭馆、太累、预算降低等场景召回替换方案。
7. `/itinerary/explain` 使用内置 `cpp-httplib` client 调用 OpenAI/DeepSeek 兼容接口，失败或无密钥时返回本地中文模板。
8. `web/` 演示台按规划概览、候选对比、路线明细、算法解释和工具箱分阶段展示；覆盖偏好输入、候选方案概览、路线与时间轴可视化、候选对比指标、候选多样性指标、Pareto 非支配层级、Beam Search 调试轨迹、BM25 排序贡献、站点评分拆解、严格时间窗复核、每日 KPI、约束命中、未安排原因、路径查询、替换方案和自然语言说明。

## 关键约定

- GitHub 仓库地址：`https://github.com/4evour/Tour-Pass`。
- LLM 默认读取 `config/llm.local.json`；本地配置存在密钥时不会被单独残留的 `OPENAI_API_KEY` 覆盖，只有未配置本地密钥或显式设置 `LLM_BASE_URL` / `LLM_MODEL` 切换提供商时，环境变量才会覆盖。
- `LLM_DISABLED=1` 可在面试或离线演示时强制禁用远程 LLM，使用本地中文模板兜底。
- `TOURPASS_WORKERS`、`TOURPASS_MAX_QUEUE`、`TOURPASS_MAX_BODY_BYTES`、`TOURPASS_CACHE_ENTRIES`、`TOURPASS_CACHE_TTL_SECONDS` 和 `TOURPASS_MAX_TRIP_JOBS` 可调整 HTTP 线程池、队列、请求体限制、缓存和异步任务容量。
- GitHub Actions 工作流 `.github/workflows/ci.yml` 在 Ubuntu/Windows 上运行数据验证、CMake 构建和 CTest，并在 Windows 上执行 `scripts/api_smoke.ps1`。
- 本地配置文件为 `config/llm.local.json`，不得提交真实密钥。
- 统一 API 错误格式为 `{ "error": { "code", "message", "details" } }`。
- MVP 不接真实地图 API，通勤时间全部来自 `edges.json`。
- 样例数据更新后应运行 `scripts/validate_data.js`；校验覆盖 POI 字段、坐标、时间窗、类型覆盖、边引用、边权合法性和图连通性。
- 规划结果解释优先复用既有响应字段，并向 `/trip/plan` 响应补充 `strategy`、`comparison`、`comparison.pareto_debug`、`comparison.diversity_*`、`days[].beam_trace`、`days[].time_window_*`、`stops[].time_window_*` 和 `stops[].score_breakdown`；不额外引入破坏性路由结构。

## 已知风险

- Makefile 默认链接 `winhttp`，Windows 本地演示可在无 OpenSSL 时调用 DeepSeek/OpenAI 兼容 HTTPS LLM；CMake 检测到 OpenSSL 时仍使用 `cpp-httplib` HTTPS 支持。
- 样例数据为演示级人工整理数据，不代表实时营业、拥堵或闭馆状态。
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
