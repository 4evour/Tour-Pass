# Tour Pass

> **线上演示**：https://tour-pass.onrender.com

C++17 城市旅行行程规划算法服务。基于 **500+ 真实高德 POI** 和 **1900+ 条通勤边**，通过 Dijkstra/A* 最短路、Beam Search 时间槽规划、BM25 文本检索、Pareto 多目标排序生成多候选多日行程。前端集成 Leaflet 地图可视化，路线直接展示在 OpenStreetMap 上。已部署至 Render，支持 Docker 一键构建。

## 核心能力

- **LLM 自然语言规划**：`POST /trip/chat` 接收中文自然语言输入，LLM 提取意图、BM25 匹配 POI、Beam Search 生成行程、LLM 生成自然语言回复——Hybrid AI 架构
- **Beam Search**：在上午/午餐/下午/晚餐/晚上时间槽中保留 Top-K 状态，综合评分、通勤和时间窗约束规划路线
- **5 种策略候选**：少走路、紧凑、文化优先、美食优先、雨天室内，Pareto 非支配排序量化取舍
- **TravelTimeProvider**：可插拔通勤时间数据源，支持本地 edges.json 和高德实时路线 API 无缝切换
- **严格时间窗校验**：开放时间、餐饮窗口、站点顺序、当天结束时间
- **BM25 检索**：字段权重 + 匹配词解释
- **Leaflet 地图**：每日路线 polyline + marker popup 展示站点详情，A* 路径查询结果地图绘制
- **多城市支持**：`TOURPASS_CITY` 选择加载不同城市数据集，已采集 21 城数据

## 数据规模

- **21 城市**：共约 15000+ POI（景点 / 餐饮 / 酒店 / 交通 / 夜游）
- **通勤边**：每城市 1000-2000 条，高德真实路线占比 80%+
- 预置城市：长沙、武汉、北京、上海、广州、深圳、成都、重庆、杭州、南京、西安、青岛、厦门、苏州、昆明、大理、丽江、桂林、三亚、哈尔滨、张家界

## 环境要求

**本地开发（Windows）**：
- MinGW `g++` + `mingw32-make`，或 CMake 3.16+
- Node.js（脚本和前端）
- 可选：OpenSSL（仅在需要通过 CMake 直接请求 HTTPS LLM 接口时使用）

**Docker / 线上部署**：
- Docker（本地验证）
- Render / 任意支持 Docker 的 PaaS（线上部署）

## 常用命令

Makefile 构建：

```powershell
mingw32-make build       # 编译
mingw32-make test        # 运行测试
mingw32-make run         # 编译并启动服务
mingw32-make clean       # 清理构建产物
mingw32-make validate-data  # 数据质量校验
```

CMake 构建（默认跳过测试目标，适合 Docker 和生产环境）：

```powershell
cmake -S . -B build
cmake --build build
```

启用 CMake 测试目标：

```powershell
cmake -S . -B build -DTOURPASS_BUILD_TESTS=ON
cmake --build build
ctest --test-dir build
```

服务默认监听：

```text
http://127.0.0.1:8080
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PORT` | 监听端口 | `8080` |
| `HOST` | 监听地址 | `127.0.0.1` |
| `TOURPASS_CITY` | 加载城市数据 | `changsha` |
| `TOURPASS_DB_PATH` | SQLite 数据库路径 | `storage/tourpass.sqlite` |
| `LLM_DISABLED` | 禁用 LLM（演示模式） | `0` |
| `OPENAI_API_KEY` | LLM API Key | - |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | LLM 模型名 | `deepseek-chat` |
| `TOURPASS_JWT_SECRET` | JWT 签名密钥 | - |
| `TOURPASS_API_KEY` | API 访问密钥 | - |
| `TOURPASS_AMAP_API_KEY` | 高德地图 API Key | - |
| `TOURPASS_WORKERS` | 工作线程数 | `4` |
| `TOURPASS_BEAM_WIDTH` | Beam Search 宽度 | `5` |
| `TOURPASS_DISTANCE_CACHE_MODE` | 距离缓存模式 | `auto` |
| `VITE_HOTEL_API_KEY` | 前端酒店服务 API Key | - |

LLM 配置：默认读取 `config/llm.local.json`，格式参考 `config/llm.example.json`。本地配置存在密钥时不会被单独残留的 `OPENAI_API_KEY` 覆盖。

## Docker 部署

```powershell
docker build -t tour-pass:local .
docker run --rm -p 8080:8080 -e LLM_DISABLED=1 tour-pass:local
node scripts/container_smoke.js http://127.0.0.1:8080
```

Docker 镜像默认 `LLM_DISABLED=1` 作为演示安全默认值。部署细节见 [docs/deployment.md](docs/deployment.md)。

## API 接口

```powershell
# 健康检查
curl.exe http://127.0.0.1:8080/health

# 自然语言行程规划
curl.exe -X POST http://127.0.0.1:8080/trip/chat `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@docs/sample_chat_request.json"

# 结构化行程规划
curl.exe -X POST http://127.0.0.1:8080/trip/plan `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@docs/sample_trip_request.json"

# POI 搜索
curl.exe "http://127.0.0.1:8080/poi/search?q=橘子洲&limit=3"

# 最短路径查询
curl.exe "http://127.0.0.1:8080/route/shortest?from=amap_d0197c46&to=amap_f3d362be"

# 服务指标
curl.exe http://127.0.0.1:8080/metrics
```

完整 API 文档见 [docs/openapi.yaml](docs/openapi.yaml)。

## CI 与冒烟验证

仓库提供 GitHub Actions 工作流 `.github/workflows/ci.yml`，在 PR 和 main push 时执行 Ubuntu/Windows CMake 构建与 CTest，并在 Windows 上启动服务运行核心 API 冒烟测试。

本地验证：

```powershell
mingw32-make validate-data
powershell -ExecutionPolicy Bypass -File scripts/api_smoke.ps1 -AppPath bin/tourpass.exe -Port 8091
node scripts/benchmark.js --app bin/tourpass.exe --port 8092 --duration 60 --warmup 5 --concurrency-steps 1,10,50,100,200
```

## 项目结构

```text
├── src/                    # C++ 后端源码
├── include/tourpass/       # 头文件
├── third_party/            # 第三方库（httplib, json, sqlite3）
├── web/                    # 前端页面（C++ 服务直接托管）
│   ├── editor/             # React 行程编辑器（Vite + TypeScript）
│   ├── app.js              # 主应用脚本
│   └── admin.js            # 管理页面
├── data/                   # 城市 POI 和通勤边数据
├── config/                 # 配置文件（amap 城市配置、LLM 配置模板）
├── scripts/                # 数据采集、清洗、验证脚本
├── tests/                  # 测试文件
├── docs/                   # 文档
├── CMakeLists.txt          # CMake 构建配置
├── Makefile                # MinGW 构建配置
├── Dockerfile              # 多阶段 Docker 构建
└── render.yaml             # Render 部署配置
```

## 安全说明

- 密钥通过环境变量或 `config/llm.local.json`（已 gitignore）注入，代码中不硬编码
- `.gitignore` 已排除 `.claude/`、`.trae/`、`config/llm.local.json`、`.env`、`output/`、`storage/` 等敏感目录
- API Key 校验使用常量时间比较
- 密码哈希使用 PBKDF2（10000 轮迭代）
- SQL 查询全部参数化

## License

ISC