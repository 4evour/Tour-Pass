# Comparison Matrix

| Dimension | Tour Pass current | OpenAI Agents SDK guidance | Anthropic current design | LangGraph production model | TravelPlanner benchmark |
|---|---|---|---|---|---|
| 主抽象 | 一次规划请求和共享 `TourState` | 可恢复的 agent run；manager、agents-as-tools 或 handoff | durable session event log + replaceable harness + tools/sandboxes | thread checkpoint + cross-thread store | 受多类约束的完整旅行计划任务 |
| 数据模型 | POI/route JSON、计划 state、30 分钟 session、保存后的 itinerary | run state、interruptions、tool calls、handoffs、traces | append-only events；上下文只是事件的可变视图 | checkpoint snapshots、namespaced memory items | query、工具环境、计划、环境/常识/硬约束 |
| 更新模型 | 一次生成；部分编辑器更新；每次规划新 graph thread | run 可暂停、审批、恢复 | harness 可崩溃重启并从事件续跑 | 每步 checkpoint；store 跨 thread 更新 | 离线任务生成与严格评估 |
| 检索与交付 | 规划前固定 BM25/XHS 查询；交付静态 itinerary | 模型按需调用工具/MCP；trace 后进入 eval | just-in-time context、progressive disclosure | state/store 可在节点中读取 | Agent 必须选择工具并持续跟踪约束 |
| 治理 | LLM 调用数上限、critical/non-critical retry；无工具审批 | input/output/tool guardrails + resumable approval | 凭据与执行 sandbox 隔离，session 独立 | interrupt/time travel/fault tolerance primitives | 主要是评估，不提供生产治理 |
| 耦合 | 业务节点直接 import Python 工具；Graph 与 API session 分裂 | SDK 管理 loop，应用拥有工具和存储 | 对稳定接口有意见，对 harness 实现保持可替换 | 框架级 runtime primitives | benchmark 代码和数据集 |
| 验证 | 152 个组件测试、2 城 smoke、C++ 算法质量检查 | structured traces + workflow eval | durable event visibility and infrastructure metrics | framework primitives，应用自行建立 eval | 约束成功率揭示 LLM 规划脆弱性 |
| 运营成本 | 当前较低；主要是 LLM、外部 API 和两套状态管理 | 更多模型/tool calls、trace storage、approval UX | session log、stateless harness、tool infra 和 sandbox | persistent DB、retention、checkpoint pruning | 离线 benchmark 成本，不是生产成本 |
| 在什么条件下更强 | 固定城市、一次性生成、低成本演示 | 有多个权限/策略边界和可恢复工具运行时 | 长时任务、基础设施故障恢复、工具隔离 | 已经使用 LangGraph 且需要最小迁移 | 需要证明旅游任务是否真的满足多约束 |

## What To Borrow

### From OpenAI Agents SDK guidance

- 借“manager owns final answer + specialists as bounded tools”的所有权设计，不必迁移 SDK。
- 把副作用审批建模为可序列化 interruption，恢复同一次 run。
- trace 记录模型、工具、guardrail、handoff 和自定义 span；再从 trace 建任务 eval。

### From Anthropic Managed Agents and context engineering

- 分开 durable session 与 model context。原始事件可恢复，上下文可按模型和任务动态裁剪。
- 让外部供应商、地图、日历和执行环境成为统一工具接口；凭据不进入模型可见环境。
- 使用按需检索和渐进披露，不把所有攻略、POI 和历史一次性塞进 prompt。

### From LangGraph

- 继续使用现有框架，但把 `MemorySaver` 换成生产 checkpointer。
- 使用 store 保存跨行程偏好、证据和学习样例；不要把这些混在 thread checkpoint。
- 使用 interrupt/resume 实现“建议 patch -> 用户批准 -> 应用 patch”。

### From TravelPlanner

- 评估完整约束成功，而不是只看路线是否生成或文本是否自然。
- 把工具选择、信息完整性、常识约束、预算/时间硬约束分别评分。
- 保持 deterministic solver；语言模型负责搜索、澄清和控制，不负责心算所有约束。

## What Not To Borrow Yet

- 不因 OpenAI/Anthropic 提供 SDK 就重写现有 LangGraph。
- 不先建设通用 sandbox；旅游场景的首批工具应是受限 API，而不是任意代码执行。
- 不先上跨组织 A2A。Tour Pass 目前没有必须由独立 Agent 服务互操作解决的问题。
- 不把 benchmark 旧模型分数当作当前模型性能，也不把框架官方说明当作 Tour Pass 的实测收益。
