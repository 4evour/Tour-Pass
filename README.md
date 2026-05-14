# Tour Pass

Tour Pass 是一个 C++17 城市自由行行程规划算法服务。MVP 使用长沙本地样例数据，将景点、餐厅、酒店和夜间活动点建模为 POI 图，结合 Dijkstra 最短路、兴趣评分、时间窗调度、餐饮插入、POI 检索和 LLM/模板解释生成多日旅行计划。

## 环境要求

- Windows
- MinGW `g++`
- `mingw32-make`
- `curl.exe`，仅在配置 LLM 远程调用时使用

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

## LLM 配置

环境变量优先：

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:LLM_BASE_URL="https://api.openai.com/v1"
$env:LLM_MODEL="gpt-4o-mini"
```

也可以复制 `config/llm.example.json` 为 `config/llm.local.json` 后填写本地配置。`config/llm.local.json` 已被 `.gitignore` 排除。

未配置密钥或远程调用失败时，`/itinerary/explain` 会自动使用本地中文模板。

## API 示例

完整 API 文档见 [docs/api.md](docs/api.md)。

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

生成 Top-K 候选行程：

```powershell
curl.exe -X POST http://127.0.0.1:8080/trip/plan `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@docs/sample_candidate_request.json"
```

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

## MVP 边界

- 不接真实地图 API，通勤耗时来自 `data/edges.json`。
- 已提供 `web/` 本地演示页面，由 C++ 服务直接托管。
- 已实现 A* 路径查询、Top-K 候选行程和场景替换方案。
- 已实现日内局部交换优化、优化摘要、约束解释和未安排原因。
- 暂不实现 SQLite 和天气/闭馆动态调整。
- 当前 CMake 配置可构建现有轻量测试，并可选启用 GoogleTest。
- CMake 可通过 `-DTOURPASS_USE_GTEST=ON` 构建 GoogleTest 测试目标。

## 一键演示

```powershell
powershell -ExecutionPolicy Bypass -File scripts/demo.ps1
```

脚本会构建服务、启动本地进程、检查 `/health` 并输出候选行程冒烟测试结果。
