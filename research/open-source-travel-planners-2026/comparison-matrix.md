# Comparison Matrix

## Decision

Tour Pass 应把竞争边界放在“证据化约束规划”这一交叉层：借鉴 OTP 的路由/数据模型纪律，借鉴 Wanderlust 的共享对象，借鉴 Kbhujbal 的 API 分层和进度交付，但保留自己的中国本地 Provider、确定性时间轴、硬校验、降级和版本/所有权闭环。

## System-Level Comparison

| 项目 | 主抽象 | 数据模型 | 更新模型 | 检索与交付 | 治理/版本 | 耦合 | 验证证据 | 运营成本 | 在什么条件下更强 |
|---|---|---|---|---|---|---|---|---|---|
| OpenTripPlanner | 交通网络图、RouteRequest | GTFS/OSM/NeTEx/GBFS 图、Raptor 路径、实时告警 | 构图 + 实时更新、快照读 | GraphQL 查询候选路线 | 运营方配置；图快照；非游客协作 | JVM 服务 + 数据 feed | 大量单测、CI、性能测试、超时/错误 | 数据 feed、图构建、内存和实时更新 | 公共交通、多模态 A→B 路由准确且可扩展 |
| AWS personalized planner | 画像上下文 + 对话链 | Redshift 用户/预订记录、prompt history | 查询时读取；ConversationBufferMemory | Streamlit 聊天文本 | Cognito/云资源；未见行程版本模型 | AWS 强耦合 | 参考架构；未见 itinerary 质量评测 | Redshift/EC2/Cognito/Bedrock/VPC | 已有 AWS 数据资产、重视画像问答 |
| Multi-Agent AI Travel Advisor | 结构化请求 + API 服务 + agents | Pydantic normalized models、ChromaDB RAG、外部 API 响应 | 请求时并行查询；RAG 重索引 | REST/WebSocket、日程编译器 | README 未说明所有权/版本 | CrewAI + 11 类 API | README 声称 2–3 calls；本轮未独立复现 | 大量 API key、额度、失败/延迟面 | 需要航班/酒店/活动/物流一体化并接受高运营复杂度 |
| Trip Planner CLI | POI 集合 | Places JSON → CSV 行 + Wikipedia 摘要 | 一次性抓取 | 文件导出 | 无用户/版本/ACL | Python CLI + Google/Wikipedia | 无路线/日程测试证据 | 低，但受 Places/Wikipedia API 影响 | 快速发现和筛选景点数据 |
| Wanderlust | 共享 Trip + Destination board | trips/destinations/users/comments | CRUD；无时间有效模型 | Rails HTML/JSON、邮件分享 | Devise 登录；README 标明无授权 | Rails/Postgres/AngularJS | RSpec、Factory Girl；旧技术栈 | 低到中；维护旧栈 | 多人共同收集地点、评论和分享 |
| JourneyJolt | 表单 + 单次 LLM JSON | Firestore 文档：userSelection + tripData | 生成时写入；本地 storage 缓存 | React 页面、酒店/地点卡片 | Auth0/Google 登录、Firestore；版本语义未见 | Gemini/Google/Firebase/Vite | README roadmap 仍有测试/错误处理待办 | 中；前端 key、多个 SaaS | 快速做出视觉完整的个人行程产品 |
| AI Travel Planner | prompt 字符串 + Markdown | React state、远端文本响应 | 单次请求；无计划版本 | Markdown 展示、txt 下载 | 无公开 ACL/版本 | Altogic + OpenAI + React | 无结构/事实验证证据 | 低，但依赖托管 endpoint | 验证表单到 LLM 的最小产品路径 |
| Tour Pass | PlanningContext + evidence-backed itinerary | 类型化请求、POI/route/weather evidence、版本、运行事件、owner | 缓存 + 并行 Provider；版本化保存；warning/降级 | SSE 阶段事件、时间轴、地图、风险、完整度、分享/PDF | owner 隔离、账号/访客、公开快照、额度 | FastAPI + AMap/天气 + 可替换 LLM + SQLite/Postgres | HardValidator、回归测试、JSONL 观测、录制/replay | Provider 配额、模型等待、证据缓存和超时设计 | 需要可执行、可解释、可追溯的中国本地化日程 |

## Competitor Strengths to Reuse

| 竞品 | 可借鉴的具体优点 | 借鉴边界 |
|---|---|---|
| OTP | 数据导入与路由服务分层；图/快照思维；请求超时和空结果错误；性能回归 | 不直接引入完整 OTP，先吸收 route evidence contract、缓存/快照和数据质量报告 |
| Kbhujbal | API 服务与 AI agent 分开；并行拉取；WebSocket/进度；RAG 知识库 | 先证实源码和供应商可用性；避免 11 个 API 同时成为故障面 |
| Wanderlust | Trip/成员/目的地/评论共享对象；邮件分享 | 用现代 owner/ACL/版本模型重做，补齐权限与冲突处理 |
| JourneyJolt | 低摩擦表单、地图搜索、酒店/地点卡片和移动端呈现 | 生成结果必须经过实体绑定和时间轴验证，API key 不应依赖不受控的浏览器暴露 |
| AWS | 画像与已订行程注入；CloudFormation 一键部署思路 | 不把云资源复杂度带入默认部署；画像必须最小化、可解释并与行程版本关联 |
| Trip Planner CLI | 用评分/评论数筛选和 CSV 导出，适合做候选地点池 | 候选地点不能直接变成行程；需要开放时间、路线和去重校验 |

## Tour Pass Advantage Hypotheses

1. **可信交付**：每个地点、路线、天气和风险都能标记 `verified`、`estimated` 或 `unresolved`，让用户知道计划哪里可靠。
2. **硬约束优先**：必去点、日期、每日时段、住宿起终点和路线端点由程序校验，模型负责取舍和叙事。
3. **中国本地执行性**：高德 POI/路线和天气 Provider 直接进入编排；相较只展示全球 Google/商业 API 的项目，更适合中国城市和中文用户。
4. **失败仍可解释**：Provider 缺失或预算耗尽时保留已形成的计划并展示缺口，不把估算伪装为核验结果。
5. **可持续迭代**：行程版本、运行事件、缓存、SSE 和 replay 能支持问题定位与回归，而轻量竞品主要停留在一次生成。

## Risks to the Advantage

- 证据完整度若没有可量化评测，只是产品叙事；需要固定 case、事实抽检、时间轴可行性和用户盲评。
- Provider 质量或覆盖不足会把“可信”变成大量 warning；需要按城市和供应商建立 coverage dashboard。
- 事实验证带来的延迟必须由缓存、并发、阶段性 SSE 和可选深度模式控制。
