# Tour Pass 架构图

![Tour Pass 项目架构图](./architecture-diagram.svg)

本文档基于当前代码入口生成：

- C++ 主服务入口：[src/main.cpp](../src/main.cpp)
- HTTP 路由与网关：[src/api.cpp](../src/api.cpp)
- 默认 Agent 服务入口：[api_multi_agent.py](../api_multi_agent.py)
- 多 Agent 图构建：[graph.py](../graph.py)
- React 编辑器 API 封装：[web/editor/src/utils/api.ts](../web/editor/src/utils/api.ts)
- 容器启动脚本：[entrypoint.sh](../entrypoint.sh)

## 系统总览

上方 SVG 是可直接查看的图表版；下方 Mermaid 保留为可编辑源码，方便后续维护。

```mermaid
flowchart TB
    User["用户 / 浏览器"]
    DemoUI["主 Web 应用<br/>web/index.html + web/app.js<br/>Leaflet 地图 / AI 规划 / 行程保存"]
    Editor["React 行程编辑器<br/>web/editor<br/>Vite + TypeScript + Zustand"]
    Admin["管理与分享页面<br/>admin / profile / share"]

    User --> DemoUI
    User --> Editor
    User --> Admin

    subgraph Cpp["C++ 主服务 :8080<br/>cpp-httplib"]
        Static["静态资源服务<br/>web/ 与 web/editor-dist/"]
        Middleware["中间件<br/>CORS / JWT / 限流 / 安全头 / 指标"]
        Api["REST API 路由"]
        Auth["Auth / 用户 / 配额<br/>JWT + DataStore"]
        Store["DataStore<br/>PostgreSQL 或 SQLite"]
        Runtime["运行时能力<br/>线程池 / 响应缓存 / 异步任务 / metrics"]
        Planner["TripPlanner<br/>Beam Search / 候选方案 / Pareto"]
        GraphEngine["PoiGraph<br/>Dijkstra / A* / 距离缓存"]
        Search["SearchEngine<br/>BM25 检索"]
        LlmClient["LlmClient<br/>OpenAI 兼容接口 / 模板兜底"]
        AgentProxy["Agent 代理<br/>/agent/* 与 /api/xhs/*"]
    end

    DemoUI --> Static
    Editor --> Static
    Admin --> Static
    DemoUI --> Api
    Editor --> Api
    Admin --> Api

    Static --> Middleware
    Api --> Middleware
    Middleware --> Auth
    Middleware --> Runtime
    Api --> Planner
    Api --> GraphEngine
    Api --> Search
    Api --> LlmClient
    Api --> Store
    Api --> AgentProxy

    subgraph Py["Python 多 Agent 服务 :8090<br/>FastAPI + LangGraph"]
        AgentApi["Agent API<br/>SSE / 同步规划 / 多方案 / 聊天 / XHS"]
        TourGraph["LangGraph 工作流<br/>graph.py"]
        AgentNodes["Agents<br/>Intent / Retrieve / POI / Hotel / Weather / Restaurant / Scheduler / Reviewer / Ticket / Summary"]
        PyTools["Tools<br/>RAG / cache / session / route / XHS parser"]
        PyCache["Redis 可选<br/>内存 fallback"]
    end

    AgentProxy --> AgentApi
    AgentApi --> TourGraph
    TourGraph --> AgentNodes
    AgentNodes --> PyTools
    PyTools --> PyCache
    PyTools -->|"优化路线优先调用"| Api

    subgraph Data["数据与配置"]
        CityData["data/{city}/<br/>pois.json / edges.json / guidebook.json / city_guide.json / xhs_routes.json"]
        Config["config/<br/>高德城市配置 / LLM 示例配置"]
        Storage["storage/tourpass.sqlite<br/>本地默认持久化"]
        Postgres[("Render PostgreSQL<br/>DATABASE_URL")]
    end

    Planner --> CityData
    GraphEngine --> CityData
    Search --> CityData
    PyTools --> CityData
    Store --> Storage
    Store --> Postgres
    LlmClient --> ExternalLLM["DeepSeek / OpenAI 兼容 LLM"]
    AgentNodes --> ExternalLLM
    PyTools --> WeatherApi["和风天气 API"]
    GraphEngine --> Amap["高德路线 / POI API<br/>可选实时与采集"]
```

## 核心请求链路

```mermaid
sequenceDiagram
    participant Browser as 浏览器前端
    participant Cpp as C++ 主服务 :8080
    participant Store as DataStore
    participant Agent as Python Agent :8090
    participant Data as data/{city}
    participant LLM as DeepSeek/OpenAI 兼容 LLM

    Browser->>Cpp: GET / 或 /editor
    Cpp-->>Browser: 静态页面与资源

    Browser->>Cpp: POST /trip/plan
    Cpp->>Data: 读取已加载城市 POI/edges
    Cpp->>Cpp: TripPlanner + PoiGraph + SearchEngine
    Cpp->>Store: 记录请求/任务/用户数据
    Cpp-->>Browser: 结构化行程 JSON

    Browser->>Cpp: POST /agent/plan 或 /agent/plan-sync
    Cpp->>Agent: 代理 /agent/*
    Agent->>Data: 读取 POI、酒店、攻略、XHS 路线
    Agent->>LLM: 意图解析、酒店选择、审核、总结
    Agent->>Cpp: /api/optimize-route 或 /trip/plan
    Cpp-->>Agent: Beam Search 路线优化结果
    Agent-->>Cpp: SSE 事件或同步行程结果
    Cpp-->>Browser: 透传 Agent 响应
```

## Python 多 Agent 工作流

默认容器启动 `api_multi_agent:app`，其内部复用 `graph.py` 编译后的 LangGraph。

```mermaid
flowchart LR
    Start((START))
    Intent["IntentAgent<br/>解析城市、天数、偏好、必去点"]
    Retrieve["RetrieveAgent<br/>检索城市攻略上下文"]
    DataGather["Data Gather<br/>先 POI，后并行 Hotel / Weather / Restaurant"]
    Scheduler["SchedulerAgent<br/>分日排程与路线组织"]
    Reviewer{"ReviewerAgent<br/>是否通过"}
    Ticket["TicketAgent<br/>门票信息"]
    Summary["SummaryAgent<br/>最终总结"]
    End((END))

    Start --> Intent --> Retrieve --> DataGather --> Scheduler --> Reviewer
    Reviewer -->|"通过或达到循环上限"| Ticket --> Summary --> End
    Reviewer -->|"未通过且可修订"| Scheduler

    DataGather --> Poi["PoiAgent<br/>本地 POI 数据"]
    DataGather --> Hotel["HotelAgent<br/>住宿锚点"]
    DataGather --> Weather["WeatherAgent<br/>天气与建议"]
    DataGather --> Restaurant["RestaurantAgent<br/>餐饮补充"]
```

## C++ 主服务内部模块

```mermaid
flowchart TB
    Main["src/main.cpp<br/>加载城市数据 / 初始化 LLM / 选择 DataStore / 启动服务"]
    RunServer["runServer<br/>src/api.cpp"]
    Middleware["installMiddleware<br/>请求 ID / JWT / 限流 / CORS / CSP / 日志"]
    Routes["HTTP Routes<br/>trip / route / poi / auth / trips / admin / editor"]
    CityBundle["CityBundle<br/>PoiGraph + TripPlanner + SearchEngine"]
    Planner["TripPlanner<br/>时间窗 + Beam Search + 多策略候选"]
    Graph["PoiGraph<br/>最短路 / 路线坐标 / 距离缓存"]
    Search["SearchEngine<br/>BM25 + 字段权重"]
    Runtime["ServiceRuntime<br/>ResponseCache / TripJobStore / ServiceMetrics"]
    Store["DataStore<br/>SQLiteStore 或 PostgresStore"]
    Static["静态文件<br/>web / editor-dist / data 图片白名单"]
    AgentProxy["AgentProxy<br/>转发到 AGENT_BASE_URL"]

    Main --> RunServer --> Middleware --> Routes
    Main --> CityBundle
    CityBundle --> Planner
    CityBundle --> Graph
    CityBundle --> Search
    Routes --> Planner
    Routes --> Graph
    Routes --> Search
    Routes --> Runtime
    Routes --> Store
    Routes --> Static
    Routes --> AgentProxy
```

## 数据生产与消费

```mermaid
flowchart LR
    Scripts["scripts/<br/>采集 / 清洗 / enrich / validate"]
    Config["config/amap.*.json"]
    Raw["output/<br/>采集临时产物"]
    Data["data/{city}<br/>pois / edges / guidebook / city_guide / xhs_routes"]
    Tests["tests/<br/>数据质量、API、前端回归"]
    Cpp["C++ 服务<br/>规划、检索、路径"]
    Agent["Python Agent<br/>RAG、POI/酒店/餐饮、XHS"]
    Web["前端<br/>地图、编辑器、分享"]

    Config --> Scripts
    Scripts --> Raw
    Scripts --> Data
    Data --> Tests
    Data --> Cpp
    Data --> Agent
    Cpp --> Web
    Agent --> Web
```

## 部署形态

```mermaid
flowchart TB
    Render["Render Web Service<br/>Dockerfile"]
    Entrypoint["entrypoint.sh"]
    CppProc["/app/tourpass<br/>主进程 :8080"]
    AgentProc["uvicorn api_multi_agent:app<br/>后台进程 :8090"]
    Monitor["Agent 进程监控<br/>异常退出后重启"]
    Pg["Render PostgreSQL<br/>DATABASE_URL"]
    Sqlite["/app/storage/tourpass.sqlite<br/>fallback / 本地默认"]

    Render --> Entrypoint
    Entrypoint --> CppProc
    Entrypoint --> AgentProc
    Entrypoint --> Monitor
    Monitor --> AgentProc
    CppProc --> Pg
    CppProc --> Sqlite
    CppProc -->|"AGENT_BASE_URL=http://127.0.0.1:8090"| AgentProc
```

## 关键边界

- C++ 主服务是线上入口，负责静态资源、认证、持久化、核心规划、检索、路径与 Agent 代理。
- Python Agent 是增强规划层，负责自然语言理解、多 Agent 编排、多轮会话、RAG、天气、XHS 解析和行程总结。
- Python 路线优化优先回调 C++ `/api/optimize-route`，失败后才退回 Python 近邻 + 2-opt。
- 城市 POI、通勤边和攻略数据主要来自 `data/{city}`，采集和清洗脚本位于 `scripts/`。
- 持久化通过 `DataStore` 抽象切换 PostgreSQL 或 SQLite；Agent 缓存/会话通过 Redis 可选，缺省退回内存。
