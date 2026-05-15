# Tour Pass 项目说明

## 项目目标

Tour Pass 是一个 C++17 城市自由行行程规划算法服务。MVP 使用长沙本地样例数据，将景点、餐厅、酒店和夜间活动点建模为 POI 图，通过最短路、兴趣评分、评分拆解、时间窗调度、餐饮插入、文本检索和 LLM/模板解释生成多日旅游计划。当前优先面向简历和面试展示，强调候选方案对比、约束解释、通勤优化和离线可演示性。

## 技术栈

- 语言：C++17
- 构建：Makefile + MinGW `g++` + `mingw32-make`
- CMake：已提供 `CMakeLists.txt`，本机使用 MinGW generator 验证通过；检测到 OpenSSL 时自动启用 HTTPS LLM 调用
- HTTP：`cpp-httplib` 单头文件，位于 `third_party/httplib.h`，服务端和 LLM client 复用同一依赖
- JSON：`nlohmann/json` 单头文件，位于 `third_party/json.hpp`
- 数据：本地 JSON 文件，`data/pois.json` 和 `data/edges.json`
- 测试：轻量 C++ 测试运行器，命令为 `mingw32-make test`；CMake 可选启用 GoogleTest 目标

## 目录结构

- `include/tourpass/`：公共头文件和模块接口
- `src/`：服务端、算法、数据加载、检索和 LLM 实现
- `data/`：长沙 POI 与通勤边样例数据
- `tests/`：核心行为测试
- `third_party/`：第三方单头文件依赖
- `config/`：LLM 配置示例，真实本地配置不提交
- `docs/`：简历表达、API、架构和项目说明材料
- `scripts/`：本地演示和 API 冒烟验证脚本
- `web/`：本地静态演示页面，由 C++ 服务直接托管

## 运行与测试

- 构建：`mingw32-make build`
- 运行：`mingw32-make run`
- 测试：`mingw32-make test`
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
8. `web/` 演示台展示偏好输入、候选方案概览、路线与时间轴可视化、候选对比指标、Pareto 非支配层级、站点评分拆解、每日 KPI、约束命中、未安排原因、路径查询、替换方案和自然语言说明。

## 关键约定

- GitHub 仓库地址：`https://github.com/4evour/Tour-Pass`。
- 环境变量优先于本地配置：`OPENAI_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
- `LLM_DISABLED=1` 可在面试或离线演示时强制禁用远程 LLM，使用本地中文模板兜底。
- GitHub Actions 工作流 `.github/workflows/ci.yml` 在 Ubuntu/Windows 上运行数据验证、CMake 构建和 CTest，并在 Windows 上执行 `scripts/api_smoke.ps1`。
- 本地配置文件为 `config/llm.local.json`，不得提交真实密钥。
- 统一 API 错误格式为 `{ "error": { "code", "message", "details" } }`。
- MVP 不接真实地图 API，通勤时间全部来自 `edges.json`。
- 规划结果解释优先复用既有响应字段，并向 `/trip/plan` 响应补充 `strategy`、`comparison` 和 `stops[].score_breakdown`；不额外引入破坏性路由结构。

## 已知风险

- Makefile 默认不链接 OpenSSL；如需 HTTPS LLM 可通过 CMake 自动检测 OpenSSL，或在 Makefile 中显式传入 `OPENSSL_CXXFLAGS=-DCPPHTTPLIB_OPENSSL_SUPPORT` 与对应链接参数。
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
