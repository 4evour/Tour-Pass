# Evidence Map

## Source State

本轮研究固定在 `source-state.md` 所列的外部 commit，研究日为 2026-09-18。已有本地研究 `research/tour-pass-agent-harness-reuse` 只作为 Tour Pass 编排背景，不覆盖本轮竞品结论。

## README Reuse Map

| 项目 | reuse | adapt | verify | exclude |
|---|---|---|---|---|
| OpenTripPlanner | 多模态公共交通、GTFS/OSM、GraphQL、实时更新的定位 | 将“路由内核”放入旅游规划系统层比较 | 性能、部署规模、实时覆盖、每个城市的可用性 | badge、社区宣传、stars |
| AWS personalized planner | Bedrock + Redshift + Streamlit 的参考架构意图 | 讨论用户画像注入和云部署成本 | 个性化质量、回答正确性、生产安全 | CloudFormation 展示性内容 |
| Multi-Agent AI Travel Advisor | 3 个 AI agent、4 类实时服务、RAG、2–3 次 AI 调用的架构声明 | 讨论“真实数据先于 LLM”的方向 | 11 个 API 的实际可用性、并行/降级行为、价格新鲜度 | 任何未由源码或测试支持的“real”质量结论 |
| Trip Planner CLI | Google Places 筛选、评分/评论阈值、CSV + Wikipedia 摘要流程 | 讨论景点发现子系统 | 覆盖率、API 配额、导出数据的新鲜度 | 示例中的具体景点事实 |
| Wanderlust | 多人共享目的地板、Rails/Postgres/Devise/RSpec 组合 | 讨论协作对象和分享体验 | 当前可部署性、权限行为、运营状态 | 2013 年产品宣传与站点状态 |
| JourneyJolt | 表单化偏好、Gemini JSON、Google Places、Firebase、酒店/景点展示 | 讨论“可见的产品完成度” | 生成数据准确性、路线端点是否进入主链路、Firestore 规则、前端 key 安全 | README 中的“optimal”“revolutionize” |
| AI Travel Planner | GPT-3 + Altogic endpoint、预算/语言/兴趣表单、Markdown 下载 | 讨论最小可行生成器 | 事实正确性、结构一致性、Altogic 服务可用性 | 示例 API endpoint 与宣传性措辞 |

## Official Claims

- OpenTripPlanner README 将自身定义为开源多模态行程规划器，核心是排定公共交通与步行、骑行、共享单车/网约车的组合；输入主要来自 GTFS 和 OpenStreetMap，并通过 GraphQL 暴露服务。
- AWS README 描述的链路是：从 Redshift 读取用户画像和酒店预订，再把拼接后的上下文交给 Bedrock/Claude，通过 Streamlit 交互。
- Multi-Agent AI Travel Advisor README 声称用 3 个 agent、4 组实时 API 服务和 ChromaDB RAG，并把 AI 限定为分析层。
- Trip Planner README 的范围是用 Google Maps places 搜索并按评分、评论数筛选，生成 CSV；它不是日程排程器。
- Wanderlust README 的产品抽象是多人共享的目的地 board，重点是共同组织计划。
- JourneyJolt README 声称根据偏好生成酒店与日程；源码使用 Gemini JSON、Google Places、Firebase，并提供路线 endpoint 封装。
- AI Travel Planner README 说明它把表单拼成 prompt，交给 Altogic 上的 GPT-3 Chat Completion，再把 Markdown 文本展示/下载。

## Architecture

| 项目 | 主抽象 | 端到端路径 | 主要外部依赖 |
|---|---|---|---|
| OpenTripPlanner | 交通网络图 + 路由请求 | GTFS/OSM/NeTEx/GBFS → GraphBuilder → 索引图 → RoutingService/Raptor → GraphQL 客户端 | Java/JVM、Maven、地图/交通数据源、实时更新 |
| AWS | 用户画像上下文 + 对话链 | user id → Redshift SQL → prompt template → Bedrock ConversationChain → Streamlit 会话 | Bedrock、Redshift Serverless、CloudFormation、EC2、Cognito、Streamlit |
| Multi-Agent Advisor | 结构化请求 + 纯 HTTP 服务 + 3 个 agent | 请求解析 → 4 组 API 并行 → RAG 知识 → itinerary compiler | Gemini/CrewAI、Amadeus、SerpApi、Booking/Airbnb、Places/Viator/Yelp、Maps/Weather/Currency/Country API、ChromaDB |
| Trip Planner CLI | Places 记录集合 | query → Google text search → 过滤 → Wikipedia 摘要 → CSV | Google Places、Wikipedia、CSV |
| Wanderlust | Trip 与 Destination 记录、评论线程 | Rails controller → ActiveRecord → 共享编辑页/邮件分享 | Rails 3.2、PostgreSQL、Devise、AngularJS、Mandrill |
| JourneyJolt | 用户表单 + 单次 LLM JSON + Firestore 文档 | 表单 → Gemini `sendMessage` → `JSON.parse` → Firestore `Trips` → 详情页 | Gemini、Google Places、Firebase/Auth0、Vite/React |
| AI Travel Planner | prompt 字符串 + Markdown 响应 | 表单 → prompt → Altogic endpoint → GPT-3 文本 → Markdown/下载 | Altogic、OpenAI GPT-3、React |

## Code Evidence

### EV-001 — OTP 把数据导入、图构建和路由查询分层
- Path: `sources/otp/GraphBuilder.java`
- Symbol: `GraphBuilder.create`, `GraphBuilder.run`
- Observation: `create` 按 OSM、GTFS、NeTEx 等数据源装配模块，并加入站点连接、换乘、连通性和一致性检查；`run` 先检查每个模块输入，再按队列执行构建。
- Meaning: OTP 的优势来自可重建、可索引的交通网络数据模型，而不是一次生成一段文本。
- Alternative explanation: 这是交通引擎的正常复杂度，不能直接说明面向游客的体验更好。
- Confidence: high

### EV-002 — OTP 的请求路径有超时、校验、预处理和路由 worker
- Path: `sources/otp/DefaultRoutingService.java`
- Symbol: `route(RouteRequest)`
- Observation: 查询入口检查超时和起终点，调用 `RequestPreProcessor`，再创建 `RoutingWorker` 执行；响应为空且无错误时还记录异常情况。
- Meaning: 它把路由可行性和失败信号放在服务层处理，可作为 Tour Pass 交通证据层的工程参考。
- Alternative explanation: 路由结果仍是“从 A 到 B 的候选路径”，不包含预算、偏好、开放时间或叙事排程。
- Confidence: high

### EV-003 — AWS 示例把用户画像直接拼进对话上下文
- Path: `sources/aws/travel_planner.py`
- Symbol: `get_user_data`, `get_bedrock_chain`
- Observation: `get_user_data` 将 user id 转为整数后查询画像和预订，轮询 Redshift Data API 直到完成；随后生成 prompt template 和 `ConversationChain`。`chatbot_app.py` 用 Streamlit session 保存链和问答。
- Meaning: 画像注入与云资源编排是其主要价值，行程事实仍由模型回答。
- Alternative explanation: 它是 AWS 博客型参考实现，链路简单有利于演示，不代表生产级事实核验。
- Confidence: high

### EV-004 — Trip Planner CLI 只生成地点数据集
- Path: `sources/adl/fetch.py`
- Symbol: `fetch_place_detail`, CLI 主流程
- Observation: 先调用 Google Places text search，再用评分/评论数和类型过滤，尝试从 Wikipedia 补摘要，最终逐行写入 CSV；没有日期、时段、路线或冲突校验。
- Meaning: 这是一个可复用的 POI 发现子系统，不能替代完整行程规划。
- Alternative explanation: CLI 用户可以在外部工具中继续排程，仓库本身没有声称完成排程。
- Confidence: high

### EV-005 — Wanderlust 的核心对象是可评论的共享 Trip
- Path: `sources/wanderlust/trip.rb`, `sources/wanderlust/destination.rb`, `sources/wanderlust/trips_controller.rb`, `sources/wanderlust/schema.rb`
- Symbol: `Trip`, `Destination`, `TripsController#create/update/share`
- Observation: Trip `has_many :destinations`、可选归属 user；Destination 保存地址、坐标、方向、URL 并可评论；controller 公开创建/编辑/更新和邮件分享；schema 只有 trips/destinations/users/comments 等记录。
- Meaning: 多人协作、讨论和分享是其产品优势，时间轴和证据不是数据模型的一部分。
- Alternative explanation: 代码年代较早，缺失功能可能只是项目范围选择。
- Confidence: high

### EV-006 — JourneyJolt 是单次模型生成后直接落库
- Path: `sources/journey-jolt/CreateTrip.jsx`, `sources/journey-jolt/AiModel.jsx`
- Symbol: `generateTrip`, `SaveTrip`, `chatSession`
- Observation: 表单限制行程 1–5 天；`sendMessage` 返回文本后直接 `JSON.parse`，随后把 `userSelection` 和 `tripData` 写入 Firestore。Gemini chat session 的历史包含一份固定 Bhopal JSON 示例；schema 要求酒店、坐标、价格、时间等字段。
- Meaning: 它的优点是低摩擦、展示完整；事实验证和模型输出治理仍在应用之外。
- Alternative explanation: `GlobalApi.jsx` 封装了 Google Places 和 route endpoint，未来可能由其他组件使用；当前抓到的核心生成路径没有把这些结果合并进 plan。
- Confidence: high

### EV-007 — JourneyJolt 有 Places 字段选择和路线封装，但耦合边界松
- Path: `sources/journey-jolt/GlobalApi.jsx`
- Symbol: `getPlaceDetails`, `getCityDetails`, `getRoute`
- Observation: Places 请求带字段掩码，路线通过后端 `/api/get-route` 查询并在异常时返回 `null`；该文件没有显示生成流程如何消费这些返回值。
- Meaning: 字段掩码是控制地图 API 成本的好做法，但“有封装”不等于“已成为行程事实来源”。
- Alternative explanation: 详情页组件或未抓取的后端项目可能会使用这些函数。
- Confidence: medium

### EV-008 — AI Travel Planner 把结构化表单压成一段 prompt
- Path: `sources/ai-travel-planner/App.js`
- Symbol: `handleSubmit`
- Observation: 表单收集目的地、预算、风格、兴趣、住宿、交通、活动、菜系、天数和语言，拼成一段字符串 POST 到 `REACT_APP_ENDPOINT_URL`；响应按 `data.choices[0].message.content` 作为文本展示，并只提供下载 txt。
- Meaning: 它适合验证需求和 UI，而不提供可验证实体、时间轴或版本化计划。
- Alternative explanation: Altogic 后端可能承担更多逻辑，但仓库公开前端没有证据证明这一点。
- Confidence: high

### EV-009 — Tour Pass 已有证据化排程和所有权层
- Path: `trip_agent/workflow.py`, `trip_agent/validation.py`, `trip_agent/plan_output.py`, `trip_agent/store.py`, `README.md`
- Symbol: `enrich_plan`, `HardValidator.validate`, route evidence assembly, store ownership checks
- Observation: Tour Pass 并行查询 POI、路线和天气，把 provider response hash 写入输出；路线缺失时标记估算并在 validator 生成 `MISSING_ROUTE_EVIDENCE`，未解析地点生成 `UNRESOLVED_ENTITY`；store 在读取 session/version 前检查 owner。
- Meaning: 它已经跨过“模型生成器”边界，形成证据、时间轴、验证、保存和权限连续链路。
- Alternative explanation: 当前仍有部分估算和未核验警告，且真实 Provider 覆盖、延迟和成本仍需评测，不能把警告写成完全可靠。
- Confidence: high

## Engineering Evidence

- OTP 仓库有 Maven 构建、GitHub Actions 的集成/性能/架构校验工作流和大量路由/导入测试；README 明确说每个合并 PR 运行 speed test。证据说明工程成熟度高，但不等于每个部署地区的数据质量高。
- AWS 通过 CloudFormation 创建 Redshift Serverless、EC2、Cognito、VPC 等资源，部署完整但组件和权限面大；`travel_planner.py` 的 Redshift 轮询以 10 秒为间隔，响应时间和失败恢复未在源码中做细粒度封装。
- Wanderlust 有 RSpec、Factory Girl 和数据库迁移，但 README 明确写的是 Rails 3.2.13，并把 Authorization 标为 None；它的协作数据模型可借鉴，基础设施不能直接照搬。
- JourneyJolt 的 README roadmap 把单元测试和更好的 API 错误处理列为未完成项；核心代码只在 JSON parse 或网络异常时显示 toast/error。
- Trip Planner CLI 和 AI Travel Planner 没有发现与路线可行性、时间冲突或事实 provenance 对应的测试/评估目录。
- Multi-Agent AI Travel Advisor README 宣称 4 组服务用 `asyncio.gather` 并由 WebSocket 报进度；本轮因 GitHub API 限流未抓到对应源码，按“官方声明/待验证”处理。

## Limitations

- OTP 是可嵌入的交通路由内核，需要数据导入、图构建、索引和实时 feed 运维；它不解决住宿、景点偏好、预算和自然语言交互。
- AWS 示例个性化上下文强，但模型回答是主要交付，缺少 POI/路线/天气证据链和确定性时间轴；云资源启动与权限成本高。
- Multi-Agent Advisor 覆盖面最接近完整旅行预订，但需要大量商业 API key，数据价格/库存和地区覆盖会成为运营瓶颈；3 次 AI 调用也带来延迟和成本。
- JourneyJolt 的模型示例本身包含固定的 Bhopal 内容，源码把生成 JSON 直接保存；README 中提到的“最佳”或“自动路线”无法作为事实质量证据。
- AI Travel Planner 只交付 Markdown 文本，用户无法在应用内修改或验证结构化计划。
- Wanderlust 的共享和评论很适合协作，但 schema 没有日程 item、时间窗、证据引用或版本快照。
- Tour Pass 自身仍受 Provider 覆盖、地图路线缺失、模型等待和预算上限影响；当前“已核验”必须限定为已有证据覆盖的实体与路线。

## Contradictions

- JourneyJolt 的 README/产品描述把“自动生成且考虑 travel time”作为卖点，但生成路径只显示一次 Gemini 调用和 Firestore 落库；路线封装存在，却没有证据表明它参与最终计划。
- Multi-Agent Advisor 把“AI only does analysis”和“all travel data comes from real APIs”作为定位，但本轮只能核验 README；不能据此断言 API 数据新鲜度或整条链路稳定。
- AWS README 把方案称为个性化 itinerary planner，代码确实读取画像和预订，但没有路线或地点事实校验；“个性化”成立，“可执行且已核验”未被证明。
- Tour Pass 当前可以交付带 warning 的降级计划，这提高可用性但也要求产品清楚区分 `verified`、`estimated` 和 `unresolved`，否则优势叙事会反噬信任。

## Open Questions

- 见 `open-questions.md`；主要未决点是竞品实测可用性、Multi-Agent Advisor 源码验证、Tour Pass 与 OTP/OSRM/高德的组合方式，以及如何用盲评证明“证据完整度”带来的用户价值。
