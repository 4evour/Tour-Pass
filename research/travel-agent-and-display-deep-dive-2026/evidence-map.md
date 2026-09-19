# Evidence Map

## Source State

版本、访问日期和本地快照见 `source-state.md`。外部仓库源码优先于 README；README 中没有对应源码或运行证据的内容标为官方声明或开放问题。

## README Reuse Map

| 项目 | reuse | adapt | verify | exclude |
|---|---|---|---|---|
| Kbhujbal Multi-Agent Advisor | 3 个 agent、4 组服务、RAG、WebSocket 进度的定位 | 真实数据先于 LLM、编排与服务分离 | API 可用性、调用次数、降级和成本 | “production quality”式宣传 |
| Vikrambhat LangGraph | LangGraph + Ollama + Streamlit 的模块化意图 | 只保留能改变结果的阶段 | 每个 agent 是否真正并行/共享状态 | agent 数量 |
| Adrit CrewAI | 专门角色覆盖研究、交通、天气、预算、日程 | 角色职责可折叠为少数确定性阶段 | 9 个任务和 7 个 agent 的实际质量 | “perfect trip plan” |
| Shaheen Taskflow | 研究 agent + 旅行 agent + reporter 的分工 | 报告生成与事实搜索分离 | tool 调用、任务链、部署运行 | “production-ready”标题 |
| Skywain Trip Planner Skill | canonical JSON、路线检查、主题渲染、self-check | 用于结果页信息架构和数据契约 | 个人使用流程、搜索许可和主题生成成本 | 国际航班/酒店产业链 |
| JourneyJolt | 表单、照片、酒店/景点卡片、低摩擦浏览 | 用于前端卡片和目的地视觉 | Gemini 输出的事实质量与路线接入 | 固定示例 JSON |

## Official Claims

- Kbhujbal README 声称“AI 只做分析，旅行数据来自真实 API”，并公开 3 个 AI 阶段：请求解析、知识 RAG、行程编译。
- Vikrambhat README 声称以 LangGraph 管理行程、天气、活动、打包、文化和聊天等多个 agent。
- Adrit README 把研究、住宿、交通、天气、日程、预算拆为多个 CrewAI agent，并由 Trip Planner 汇总。
- Shaheen README 将项目定位为多 Agent + Agentic RAG + 报告输出。
- Skywain 的 SKILL.md 把 plan JSON、路线工具、计划 lint、self-check 和主题渲染视为完整交付契约。

## Architecture

### 1. Kbhujbal: 最接近“事实先行”的 Agent 管线

`backend/crew/orchestrator.py` 明确分为四步：AI 解析用户请求；四组服务通过 `asyncio.gather` 并行取数据；RAG 知识专家；AI 编译最终行程（lines 211–355）。`schemas.py` 对航班、住宿、活动、路线、天气和请求做了统一 Pydantic 模型（lines 13–181）。WebSocket 把四个阶段暴露给前端（`websocket.py:20–25,60–109`）。

优点是边界清楚、模型不直接伪造所有外部数据、进度状态容易表达。问题是编译器最终仍返回字符串，公开代码没有显示跨字段时间轴校验、证据引用或计划版本。

### 2. Vikrambhat: 有 Graph 外形，但核心仍是单次生成

`travel_agent.py` 注册多个 LangGraph node（lines 45–63），但只有 `generate_itinerary` 设置为 entry point 并直接连到 END（line 55–56）。用户生成后，活动、链接、天气、打包和文化模块由 UI 按钮逐个触发（lines 128–184）。`generate_itinerary.py` 只用一条 prompt 调一次 Ollama（lines 5–16）。

优点是用户可以按需加载附加内容，首次生成成本低。问题是 Agent 不是一个真正的“行程规划闭环”，图结构只是模块注册，生成结果仍是 Markdown 字符串。

### 3. Adrit: 角色很多，但顺序执行和重复职责明显

`main.py` 创建 7 个 agent 和 9 个任务，并设置 `Process.sequential`（lines 23–127）。`tasks.py` 让研究、住宿、交通、天气、日程和预算分别生成，再由 Trip Planner 汇总。每个角色都有相似的自然语言目标，数据契约主要是长文本/Markdown。

优点是职责容易向非技术用户解释。问题是调用次数、等待时间和上下文重复会随角色数增长；没有源码证据证明每个角色产出的事实被统一校验。

### 4. Shaheen: “搜索—旅行—报告”三角色，适合内容报告而非日程执行

`web_research_agent.py` 绑定网页、Wikipedia、文章和图片工具；`travel_agent.py` 只绑定航班和天气工具；`reporter_agent.py` 不绑定工具，只负责写报告。它把“找到资料”和“写成可读内容”分开，但公开源码没有行程 schema、路线闭环或时间轴验证。

### 5. Skywain: Agent 负责研究，程序负责数据和页面

SKILL.md 和 `references/output-template.md` 把 `plan.geo.json` 设为唯一事实源，包含 `days[].timeline`、`stops`、`verify`、`map`、预算、清单和 brief。`phase-6-assemble.md` 要求先做 closure scan、时间链检查、价格来源、语言一致性和 self-check，再渲染主题页面。它不是传统多 Agent App，但在“如何把规划结果交付给人”这一层证据最完整。

### 6. Tour Pass: 最小且正确的骨架已经存在

Tour Pass 当前链路是：一次轻量骨架模型调用 → 程序批量查 POI/路线/天气 → 确定性时间轴 → HardValidator → 保存/流式交付。模型不拥有 Provider，也不反复修改完整计划。相比多 Agent 项目，复杂度更低；相比单次 Markdown 生成器，事实边界更清楚。

## Code Evidence

### EV-001 — 真实 Agent 项目的最小有效结构是“解析—取证—编排”
- Path: `../open-source-travel-planners-2026/sources/kbhujbal/orchestrator.py`
- Symbol: `run_travel_pipeline`
- Observation: 解析请求、并行服务、RAG 知识和最终编译分成四步，且服务查询不由 AI 逐个选择。
- Meaning: 这已经足够表达“Agent 的价值”，不需要为天气、住宿、预算各自建一个人格 Agent。
- Alternative explanation: 该项目 README/代码没有给出完整运行评估；分层设计不等于质量已证实。
- Confidence: high

### EV-002 — LangGraph 项目未必真的需要图
- Path: `../open-source-travel-planners-2026/sources/vikrambhat2/travel_agent.py`, `generate_itinerary.py`
- Symbol: `workflow`, `generate_itinerary`
- Observation: graph 注册了多个节点，但只有生成节点在首条路径上；其余节点由按钮触发，生成函数是单次 Ollama 调用并返回字符串。
- Meaning: “用了 LangGraph”不能证明存在复杂 Agent 协作；如果产品只有固定步骤，普通异步函数更直观。
- Alternative explanation: 其它脚本可能被未来条件边接入，但当前 commit 没有证据。
- Confidence: high

### EV-003 — CrewAI 角色数量带来调用和上下文成本
- Path: `../open-source-travel-planners-2026/sources/adrit/main.py`, `agents.py`, `tasks.py`
- Symbol: `TripCrew.run`, `TravelAgents`, task factory methods
- Observation: 7 个 agent、9 个任务按顺序执行，最终 Trip Planner 需要读取前面长文本结果。
- Meaning: 对只做行程规划的产品，这套角色划分会增加延迟和失败面，且不自动增加事实可靠性。
- Alternative explanation: 教学项目可能故意展示 CrewAI 能力，不能代表作者要优化生产成本。
- Confidence: high

### EV-004 — 进度 UI 应该显示“用户能理解的阶段”，而非内部 agent 名称
- Path: `../open-source-travel-planners-2026/sources/kbhujbal/websocket.py`, `AgentProgress.jsx`
- Symbol: `AGENT_STEPS`, `progress_callback`, `AgentProgress`
- Observation: WebSocket 推送四个阶段，前端用图标、连接线和 running/completed 状态显示；但标题仍是 Travel Planning Manager、Knowledge Expert 等内部角色。
- Meaning: 进度形式值得借鉴，命名应换成“整理需求 / 查找地点和路线 / 组合每日安排 / 检查结果”。
- Alternative explanation: 对开发者用户，agent 名称可能是有用的调试信息。
- Confidence: high

### EV-005 — 轻量结果页常见模式是原文卡片或 Markdown
- Path: `../open-source-travel-planners-2026/sources/kbhujbal/ItineraryDisplay.jsx`, `sources/vikrambhat2/travel_agent.py`
- Symbol: `ItineraryDisplay`, Streamlit `st.markdown`
- Observation: Kbhujbal 把请求和最终字符串分别放在蓝色请求框、白色 Markdown 卡片；Vikrambhat 在宽列中渲染 Markdown，右侧单独聊天。
- Meaning: 这种实现快，但长文阅读、定位当天路线和比较证据都弱，不适合 Tour Pass 已有的结构化结果。
- Alternative explanation: 它们优先演示 Agent，而不是做旅行手册。
- Confidence: high

### EV-006 — 卡片式酒店/地点展示提供了视觉入口，但不应承载事实真相
- Path: `../open-source-travel-planners-2026/sources/journey-jolt/Hotelcard.jsx`, `Placescard.jsx`, `Hotels.jsx`, `Places.jsx`
- Symbol: `Hotelcard`, `Placescard`
- Observation: JourneyJolt 把酒店和地点拆成独立 section/card，配图片、rating、价格和地图入口；数据来自 Gemini 计划再由 Places API 补详情。
- Meaning: Tour Pass 可以借鉴“先看到目的地对象，再看时间轴”的视觉语言，但卡片必须显示来源状态，不能把模型文本直接当事实。
- Alternative explanation: 卡片细节可能在未抓取的组件中继续校验。
- Confidence: medium

### EV-007 — Skywain 用“规划数据”和“显示主题”解耦
- Path: `../open-source-travel-planners-2026/sources/skywain/output-template.md`, `phase-6-assemble.md`
- Symbol: `plan.geo.json`, `render_theme2.py`, `plan_lint.py` contract
- Observation: 同一 plan JSON 生成普通 HTML、主题页面、地图链接、KML 和清单；页面顺序固定为 overview → decisions → checklist → legs → day cards → hotels → budget → brief。
- Meaning: 视觉重做可以只改 renderer，不改 Agent/Provider 数据；这比把 HTML 字符串散落在规划函数里更稳。
- Alternative explanation: Skywain 面向个人导出，不直接解决 Tour Pass 的交互式会话。
- Confidence: high

### EV-008 — Tour Pass 当前结果页存在“信息都对，但首屏层级不对”
- Path: `trip_agent/static/index.html`, `trip_agent/static/styles.css`, `output/playwright/tour-pass-comparison-1365.png`, `output/playwright/tour-pass-comparison-390.png`
- Symbol: `.workspace`, `.assistant-panel`, `.guide-cover`, `.trip-statbar`, `.decision-modules`
- Observation: 桌面同时展示固定输入侧栏和完整结果；结果首屏依次出现长标题、完整度徽章、动作按钮、证据说明、统计条、行动负荷，再进入逐日内容。手机则把输入工作台和结果垂直串联，用户生成后要滚过大块输入区域才能看到行程。
- Meaning: 问题是产品模式没有切换：规划前是工作台，规划后应该是旅行手册/当天操作页；当前仍把两者同时当主内容。
- Alternative explanation: 保留输入侧栏方便修改，但移动端尤其不适合固定占屏。
- Confidence: high

## Engineering Evidence

- Kbhujbal 的 AgentProgress、WebSocket 和四阶段状态是可借鉴的“处理中”体验，但完成后仍应隐藏内部 Agent 细节。
- Vikrambhat 的按需按钮证明“天气/活动/打包”可以作为结果页的附加模块，而不是首轮规划必经 Agent；Tour Pass 可以保留核心行程为一个结果，附加内容放入折叠区。
- Adrit 的 7 Agent/9 Task 体系展示了最常见的过度工程风险：角色职责相互重叠、顺序等待、长文本交接、缺少统一 schema。
- Skywain 的 self-check 和 theme renderer 说明显示效果的关键不是堆装饰，而是稳定的数据层、固定交付顺序和可重复渲染。

## Limitations

- 本轮主要依据 GitHub 当前 commit 的源码、README、树和本地截图，没有对每个项目做真实 API 运行复现；外部 key、模型和服务可用性未独立验证。
- Skywain 的主题页面非常成熟，但它是个人使用的导出式 Agent Skill，不能直接当作 Tour Pass 的实时 Web App 架构。
- JourneyJolt 的卡片表现受真实远程数据和图片服务影响，不能仅凭组件名称判断事实质量。
- 本地参考图没有出现在当前工作区；本轮以已有 Tour Pass 截图和公开源码的可见结构作比较，没有声称复刻那张图。

## Contradictions

- 多个项目把“multi-agent”写成卖点，但实际能改变行程质量的往往是外部数据、结构化 schema 和最终编译，而不是角色数量。
- Kbhujbal 的“AI only analysis”分层很有价值，但最终仍交付字符串，缺少 Tour Pass 已有的证据状态和硬校验表达。
- Skywain 的显示效果远好于普通 Markdown，但其流程包含航班、酒店、签证、图片和多主题渲染，直接移植会违背“只做行程规划”的范围。

## Open Questions

- 见 `open-questions.md`。
