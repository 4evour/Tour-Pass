# Tour Pass 项目说明

## 项目目标

Tour Pass 是一个 C++17 城市自由行行程规划算法服务。MVP 使用长沙本地样例数据，将景点、餐厅、酒店和夜间活动点建模为 POI 图，通过最短路、兴趣评分、时间窗调度、餐饮插入、文本检索和 LLM/模板解释生成多日旅游计划。

## 技术栈

- 语言：C++17
- 构建：Makefile + MinGW `g++` + `mingw32-make`
- CMake：已提供 `CMakeLists.txt`，本机使用 `D:\Tools\cmake-3.30.5-windows-x86_64\bin` 的 CMake 3.30.5 验证通过
- HTTP：`cpp-httplib` 单头文件，位于 `third_party/httplib.h`
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
- `docs/`：简历表达和项目说明材料
- `scripts/`：本地演示和验证脚本
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
3. `/trip/plan` 根据用户兴趣、必去点、节奏和时间窗生成多日行程。
4. `/poi/search` 使用轻量 TF-IDF 检索 POI 描述和标签。
5. `/route/shortest` 使用 Dijkstra 或 A* 返回 POI 间最短通勤路径。
6. `/trip/alternatives` 按下雨、闭馆、太累、预算降低等场景召回替换方案。
7. `/itinerary/explain` 优先调用 OpenAI/DeepSeek 兼容接口，失败或无密钥时返回本地中文模板。

## 关键约定

- GitHub 仓库地址：`https://github.com/4evour/Tour-Pass`。
- 环境变量优先于本地配置：`OPENAI_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
- 本地配置文件为 `config/llm.local.json`，不得提交真实密钥。
- 统一 API 错误格式为 `{ "error": { "code", "message", "details" } }`。
- MVP 不接真实地图 API，通勤时间全部来自 `edges.json`。

## 已知风险

- `curl.exe` 子进程调用 LLM 是 Windows MVP 方案，后续可替换为 libcurl 或其他 HTTP 客户端。
- 样例数据为演示级人工整理数据，不代表实时营业、拥堵或闭馆状态。
- Makefile 默认使用轻量测试运行器；CMake 可选启用 GoogleTest 目标。
- CMake 可通过 `-DTOURPASS_USE_GTEST=ON` 构建 GoogleTest 测试；当前已验证默认 CTest 目标。
- Windows PowerShell 直接内联中文 JSON 容易出现编码问题，文档示例统一使用 `--data-binary @docs/sample_trip_request.json`。
- v0.2 增加 `candidate_count` 候选行程、`/route/shortest` 路径查询和 `/trip/alternatives` 场景替换接口。
- v0.3 增加 `web/` 本地演示台，包含偏好输入、候选行程展示、路径查询、替换方案和行程解释。
- v0.4 增加日内局部交换优化、优化摘要、约束解释、未安排原因和 CMake 构建配置。
- v0.5 跑通 CMake + GoogleTest，新增 API 文档和一键演示脚本。
