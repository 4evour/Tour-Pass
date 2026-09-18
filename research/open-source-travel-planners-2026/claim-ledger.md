# Claim Ledger

| ID | Type | Claim | Evidence | Confidence | Article Location |
|---|---|---|---|---|---|
| C-001 | FACT | OTP README 将项目定位为多模态公共交通规划器，输入主要是 GTFS/OSM，输出通过 GraphQL 提供给客户端。 | `sources/otp/README.md:3-16`; `https://github.com/opentripplanner/OpenTripPlanner` (访问 2026-09-18) | high | Landscape |
| C-002 | FACT | OTP 的 GraphBuilder 按 OSM、GTFS、NeTEx 等数据源装配模块，并在构建前检查输入、按队列执行模块。 | `sources/otp/GraphBuilder.java:38-42,72-131,206-222` | high | Routing infrastructure |
| C-003 | FACT | OTP 路由入口检查超时和起终点，经过 RequestPreProcessor 后交给 RoutingWorker；空结果无错误会记录 warning。 | `sources/otp/DefaultRoutingService.java:138-147,186-208` | high | Routing infrastructure |
| C-004 | FACT | OTP 仓库包含集成、性能、schema 等 GitHub Actions workflow，并有大量测试目录。 | `opentripplanner__OpenTripPlanner-tree.txt:.github/workflows/*`; `.../application/src/test/*`; `sources/otp/README.md:35-40` | high | Engineering evidence |
| C-005 | FACT | AWS 示例从 Redshift 查询用户画像和酒店预订，用结果构造 prompt template 和 Bedrock ConversationChain。 | `sources/aws/travel_planner.py:29-65,92-136,138-167` | high | AI personalization |
| C-006 | FACT | AWS Streamlit 应用通过 session 保存用户 ID、问题、答案和 LLM chain。 | `sources/aws/chatbot_app.py:10-24,72-101` | high | AI personalization |
| C-007 | FACT | AWS CloudFormation 模板创建 Redshift Serverless、网络、EC2/Cognito 等资源，部署面较大。 | `sources/aws/Cloudformation.yaml:1-4,182-220,249-260`; `sources/aws/README.md:18-50` | high | Operations |
| C-008 | FACT | Trip Planner CLI 调用 Google Places text search，按评分/评论/类型过滤，补 Wikipedia 摘要并输出 CSV。 | `sources/adl/fetch.py:12-22,31-44,46-65,80-113` | high | POI discovery |
| C-009 | FACT | Wanderlust 的 Trip 与 Destination 是一对多关系，Destination 记录地址、坐标、方向、URL并支持评论；controller提供创建、更新和邮件分享。 | `sources/wanderlust/trip.rb:1-5`; `sources/wanderlust/destination.rb:1-8`; `sources/wanderlust/trips_controller.rb:62-109`; `sources/wanderlust/schema.rb:33-67` | high | Collaboration |
| C-010 | FACT | Wanderlust README 使用 Rails 3.2.13、PostgreSQL、Devise、RSpec，并把 Authorization 标为 None。 | `sources/wanderlust/README.textile:14-44` | high | Limitations |
| C-011 | FACT | JourneyJolt 生成流程限制 1–5 天，调用 Gemini `sendMessage` 后直接 JSON.parse 并写入 Firestore Trips 文档。 | `sources/journey-jolt/CreateTrip.jsx:68-101,103-147,200-208` | high | Consumer AI planners |
| C-012 | FACT | JourneyJolt 的 Gemini chat history 包含固定 Bhopal 示例，响应 schema包含酒店、坐标、价格、时间等字段。 | `sources/journey-jolt/AiModel.jsx:7-42` | high | Consumer AI planners |
| C-013 | FACT | JourneyJolt 的 GlobalApi 封装 Google Places 字段掩码和后端 route endpoint，但异常时返回 null。 | `sources/journey-jolt/GlobalApi.jsx:3-18,40-59` | high | Consumer AI planners |
| C-014 | FACT | AI Travel Planner 前端把目的地、预算、兴趣、交通等表单拼接成 prompt，POST 到 Altogic endpoint，把文本响应渲染为 Markdown 并下载 txt。 | `sources/ai-travel-planner/App.js:608-619,632-661,671-680,812-830` | high | Consumer AI planners |
| C-015 | FACT | Multi-Agent AI Travel Advisor README 声称 3 agents、4 组 API、RAG，并采用“API 取事实、AI 做分析”的架构。 | `kbhujbal__Multi-Agent-AI-Travel-Advisor-README.md:1-28` | medium | Multi-agent comparison |
| C-016 | FACT | Tour Pass 的工作流并行查询地点、路线和天气，把路线来源/response hash写入计划，并对无证据路线使用显式 estimate。 | `trip_agent/workflow.py:1296-1344,1578-1626,1866-1923,2129-2191`; `README.md:26-51` | high | Tour Pass |
| C-017 | FACT | Tour Pass HardValidator 能报告未解析实体、重复 POI、开放时间冲突和缺少路线证据；store按 owner 隔离 session 和版本。 | `trip_agent/validation.py:86-91,556-581,628-669`; `trip_agent/store.py:43-74,119-160`; `README.md:57-63` | high | Tour Pass |
| C-018 | FACT | Tour Pass 有 SSE 主入口、共享/公开快照、PDF、SQLite/Postgres 和 replay 评测流程。 | `README.md:14-24,82-89,109-117` | high | Tour Pass |
| C-019 | INFERENCE | 开源旅游规划项目大多只把一个系统层做深，缺少同时覆盖事实证据、约束排程和治理交付的公开闭环。 | C-002 + C-003 + C-008 + C-009 + C-011 + C-014 + C-016 + C-017 | medium | Central thesis |
| C-020 | INFERENCE | Tour Pass 最可防守的优势是“证据化约束规划”，而不是模型/Agent 数量。 | C-016 + C-017 + C-019 | medium | Central thesis |
| C-021 | INFERENCE | OTP 的图构建、请求预处理和性能回归经验可转化为 Tour Pass 的 Provider contract、缓存快照和路线证据质量门，但不应直接承担行程叙事。 | C-002 + C-003 + C-004 | medium | Recommendations |
| C-022 | INFERENCE | JourneyJolt 的展示完整度与 Tour Pass 的证据链可以互补：Tour Pass 需要持续提升地图/酒店卡片、移动端和协作视觉体验。 | C-011 + C-012 + C-013 + C-016 + C-018 | medium | Recommendations |
| C-023 | OPINION | 下一阶段产品叙事应围绕“每个关键建议都知道依据和不确定性”，并把 warning/estimate/unresolved 做成用户可理解的状态。 | criteria: trust, executability, auditability | medium | Product direction |
| C-024 | OPEN | Tour Pass 是否在真实城市、同一模型和同一 Provider 约束下优于这些项目，当前没有公平盲评证据。 | `open-questions.md:OQ-002,OQ-003,OQ-004` | low | Limitations |
| C-025 | OPEN | Multi-Agent AI Travel Advisor 的 README 架构是否与当前 commit 的运行代码完全一致，本轮未完成源码复核。 | `open-questions.md:OQ-001` | low | Limitations |
