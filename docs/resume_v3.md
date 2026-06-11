# 易传承

**求职意向**：后端开发 / 算法服务 / AI 应用方向暑期实习

手机：18000785556 ｜ 邮箱：ycc20050401@qq.com
GitHub：https://github.com/4evour ｜ 博客：https://4evour.github.io/

## 教育背景

**2023.06 - 2027.06（预计）** 井冈山大学 计算机科学与技术 ｜ 本科
主修：数据结构、计算机网络、数据库系统、操作系统、Web 开发、软件工程

## 专业技能

**后端/工程**：Go、Gin、GORM、Python、FastAPI、LangChain、LangGraph、
JWT、RESTful API、WebSocket、Docker（三阶段构建）、OpenAPI、GitHub Actions。

**数据存储**：PostgreSQL（GORM/连接池）、Redis 限流/缓存、SQLite。

**AI / 检索**：RAG、BM25/TF-IDF 检索引擎、Agent Pipeline
（LangChain + LangGraph 多节点编排）、DashScope Embedding、Hybrid/Rerank、
SSE 流式输出、Prompt 约束、检索评估。

**C++ / 算法**：C++17、Dijkstra/A*、Beam Search、时间窗约束、Pareto 分层、
LRU/TTL 缓存、线程池、背压、异步任务、CMake/CTest。

**前端联调**：Vue 3、React、TypeScript、Vite、Leaflet 地图、PixiJS，
能完成管理后台、数据看板和 Live2D 数字人联调。

## 项目经历

### 2026 灵山胜境智能导览与 Live2D 数字人系统 项目负责人

**技术栈**：Go、Gin、PostgreSQL、Redis、Vue 3、TypeScript、Naive UI、
RAG、BM25、DashScope Embedding、LLM Reranking、SSE、WebSocket、
Live2D、Docker、Prometheus

面向景区导览的 AI 应用系统，架构不绑定特定景区，知识库、Prompt、Live2D
模型均可配置替换，可迁移至其他景区或垂直领域。Go 后端约 12,400 行、69 个
业务 API。

- 设计分层架构（Handler → Service → Repository → Model），RAG 拆分
  为知识管理、检索引擎、会话管理、生成服务四层，中间件按 build tag
  隔离 dev/prod 编译。
- 实现 RAG 多模式检索管线：BM25 倒排索引 + DashScope Embedding 向量
  检索 + RRF 融合排序 + LLM Reranking 四级级联；引入 Query Rewrite
  意图改写，Recall@8 从 85.5% 提升至 95.3%，检索 p95≈21ms。
- 构建 RAG 离线评估体系：122 个资料切片 + 203 条人工评测问答，开发
  rag-eval CLI 支持 5 种检索模式对比和 Recall@K/MRR@K 指标。
- 集成 SSE 流式接口 + 475 行 WebSocket 代理对接 Open-LLM-VTuber，
  支持语音打断；6 种情感映射驱动 Live2D 表情切换。
- 落地 JWT + Cookie 双通道鉴权、Redis/内存双模限流（故障自动降级）、
  HSTS/CSP 安全头、Prometheus 指标和三阶段 Docker 构建（非 root）。

### 2026 Tour Pass 城市自由行行程规划算法服务 项目负责人 ｜ [在线演示](https://tour-pass.onrender.com/)

**技术栈**：C++17、Python、FastAPI、LangChain、LangGraph、BM25/TF-IDF、
Dijkstra/A*、Beam Search、SSE、React、TypeScript、Leaflet、Docker

C++ 算法服务 + Python LangChain Agent **双服务架构**，覆盖 **21 城
15,000+ POI** 和 **2,000+ 条高德真实通勤边**，已部署至 Render 云端。

- **C++ 规划引擎**：POI 图模型含 8 类约束（开放时间/停留时长/消费水平
  /用户节奏等）；Dijkstra 全源预计算 + A* 按需查询 + LRU 缓存保护；
  Beam Search 5 时间槽 Top-K 调度，输出 5 类策略方案（少走路、紧凑、
  文化优先、美食优先、雨天室内）和 Pareto 非支配排序；规划 p95≈41ms，
  缓存命中 p95≈6ms，命中率 99.6%。
- **Python LangChain Agent**：LangChain + LangGraph 7 节点异步决策
  管线（意图解析 → RAG 攻略检索 → POI/酒店搜索 → 酒店锚点 → 每日规划
  → C++ Beam Search 路线优化 → LLM 总结），SSE 实时推送进度至前端。
- **RAG 检索引擎**：实现 TF-IDF/BM25 内存检索引擎，中英文 bigram
  分词，加载 21 城 7 类攻略知识（路线/美食/交通/避坑/时间/季节/隐藏
  玩法）和 POI 描述，为 Agent 决策提供目的地知识增强。
- **双服务协作与部署**：C++ 端 WinHTTP + chunked transfer 实现 SSE
  代理转发，两服务通过 REST API 深度协作；40+ 数据采集/清洗脚本，高德
  边覆盖率达 98.5%；React + Leaflet 地图行程编辑器；三级缓存（热门
  预生成 + 内存 TTL + 命中直返），加速比 7 倍，吞吐量超 500 req/s；
  GitHub Actions CI，已部署 Render 云端。

## 比赛奖项

- 2025 CCPC 邀请赛铜牌（郑州站/南昌站）
- 2025 蓝桥杯全国软件和信息技术专业人才大赛 国家三等奖
- 2025 中国大学生计算机设计大赛 国家三等奖

## 个人优势

具备 Go 后端、C++ 算法服务和 AI Agent（LangChain/LangGraph）落地经验，
能独立完成从数据建模、接口设计到云端部署的完整闭环；注重可运行、可复现、
可解释，项目均已部署至云端并支持在线演示。
