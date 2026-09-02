# Evidence Map

## Source State

Tour Pass 固定在 `f91bb5861b7d66cc072020fe1ae48fc169e72c3b`；Pi 固定在 `e86823096c5bad39e1ca282ec24bc5eb9bec745b`；DSH 固定在 `b150a551b8d465e31e418e1b2eaf5e79bbb7d28e`。研究日期为 2026-08-27，外部仓库均来自官方 GitHub。

## README Reuse Map

| Source content | Classification | Reason |
|---|---|---|
| Pi 将自身称为 minimal agent harness | adapt | 可以证明定位；“minimal”是否适合 Tour Pass 要由源码边界和项目规模判断 |
| Pi 文档中的 session tree、compaction、extensions | verify | 已用 `session-manager.ts`、`agent-loop.ts`、测试源码核对主要行为 |
| DSH 的 “Everything is a Plugin” | adapt | 插件化由 Cordis package composition 支持，但不等于所有项目都应采用该复杂度 |
| DSH README 的生产级或完整性暗示 | verify | 源码和测试覆盖广，但本次未安装依赖、未独立运行测试或 benchmark |
| 功能数量、包数量和 UI 截图 | exclude | 不能证明 Agent 质量，也不能决定 Tour Pass 的架构 |

## Official Claims

- Pi 官网和官方仓库将其定位为可嵌入、可通过 extensions/skills/tools 定制的最小 agent harness。
- Pi 官方 session 文档声明会话为 JSONL 树，支持 resume、tree navigation、fork、branch summary 和 compaction。
- DSH 官方仓库以 “Everything is a Plugin” 描述自身，代码将 agent loop、session、tools、persistence、projection、compaction、skills 和 subagent 分为独立 packages。
- 这些是项目自述，不能单独证明正确性、性能或适合 Tour Pass。

## Architecture

### Pi end-to-end path

```text
prompt
  -> AgentSession prepares system prompt, active tools and session context
  -> agent-loop.runLoop streams assistant message
  -> tool calls are validated and passed through beforeToolCall
  -> sequential/parallel execution emits updates and tool results
  -> afterToolCall may replace final visible result
  -> result enters current context and session manager appends entries
  -> prepareNextTurn may change context/model/reasoning
  -> compaction/branching later rebuilds context from the active leaf
```

### DSH end-to-end path

```text
user message
  -> durable agent/inbox/spliced event
  -> ReactLoopAgent claims input at a turn/step boundary
  -> system prompt sections + RuntimeContextProjection assemble context
  -> Session.deriveMessages() projects current surface from the event log
  -> LLM chunks and assistant message append as events
  -> tool scheduler validates, gates, approves, executes and finalizes calls
  -> tool call/result events update the surface
  -> session persistence batches the append-only tail
  -> projections fold the same events into client/domain read models
  -> resume reloads events and reconstructs the scoped agent world
```

### Tour Pass target path

```text
input/trigger -> append event -> project working context -> orchestrator decides
  -> typed tool -> append canonical result/provenance -> validate
  -> propose plan patch -> approval when required -> commit plan version
  -> editor/user outcome appends feedback -> memory candidate/eval projection
```

## Code Evidence

### EV-001 - Pi loop is small but has deliberate control points
- Path: Pi `packages/agent/src/agent-loop.ts`
- Symbol: `runLoop`, `streamAssistantResponse`, `executeToolCalls`, `prepareToolCall`, `finalizeExecutedToolCall`
- Observation: 内层循环在 assistant tool calls 与 steering message 之间推进；外层循环接收 follow-up。LLM 前可 `transformContext`，每轮后可 `prepareNextTurn` 和 `shouldStopAfterTurn`，工具前后有策略 hook。
- Meaning: Tour Pass 可以用一个 orchestrator loop 取代固定角色流，同时保留预算、暂停、审批和降级控制。
- Alternative explanation: hook 多并不自动产生可靠行为，仍需领域工具和 eval。
- Confidence: high

### EV-002 - Pi separates durable session history from active model context
- Path: Pi `packages/coding-agent/src/core/session-manager.ts`
- Symbol: `buildSessionPath`, `buildContextEntries`, `buildSessionContext`, `SessionManager._appendEntry`
- Observation: entry 通过 `parentId` 形成树；context 沿当前 leaf 回溯。最新 compaction 控制哪些旧条目进入上下文，custom state entry 不进入模型消息。
- Meaning: “记忆”不应等同于把所有历史消息回传给模型；历史、状态与上下文应分离。
- Alternative explanation: Tour Pass 的计划版本可能比通用消息树更自然。
- Confidence: high

### EV-003 - Pi tools can change without rebuilding the loop
- Path: Pi `packages/coding-agent/src/core/extensions/runner.ts`, `packages/coding-agent/examples/extensions/dynamic-tools.ts`, `packages/coding-agent/test/agent-session-dynamic-tools.test.ts`
- Symbol: `ExtensionRunner.bindCore`, `registerEchoTool`, dynamic tool registration test
- Observation: extension 可以在 session start 后注册工具，runtime 暴露 `get/setActiveTools` 与 `refreshTools`；测试断言新工具同步进入 registry、active tools 和 system prompt。
- Meaning: Tour Pass 可按城市、数据可用性、用户权限和任务阶段缩小工具集。
- Alternative explanation: 动态工具变化会破坏 prompt/KV cache 稳定性，首版应只做少量阶段性裁剪。
- Confidence: high

### EV-004 - Pi permission behavior is an extension policy, not hard-coded in each tool
- Path: Pi `packages/agent/src/agent-loop.ts`, `packages/coding-agent/examples/extensions/permission-gate.ts`
- Symbol: `prepareToolCall`, `tool_call` handler
- Observation: 参数验证后、实际执行前调用 `beforeToolCall`；策略可 block/terminate。示例在无 UI 时默认拒绝危险命令。
- Meaning: Tour Pass 的预订、付费、通知和日历写入应在统一策略层审批。
- Alternative explanation: 示例不是完整权限系统，没有账户 ACL、幂等或审计语义。
- Confidence: high

### EV-005 - DSH session is the durable source of truth, not an in-memory transcript
- Path: DSH `packages/core/session/src/index.ts`
- Symbol: `Session.append`, `Session.surface`, `Session.deriveMessages`
- Observation: `Session` 保存连续 seq 的 deep-frozen append-only typed events；每个消息事件声明 surface operation，模型历史由 surface 投影而来。compaction replacement 改变 surface，但不删除原日志。
- Meaning: Trip facts、plan versions、审批和 editor diff 可以共享一个可审计事实源，同时各自投影不同视图。
- Alternative explanation: 对小型一次性请求，事件溯源比直接存 JSON 更复杂。
- Confidence: high

### EV-006 - DSH context is rebuilt at each step from session and scoped prompt sections
- Path: DSH `packages/core/agent-loop/src/agent.ts`, `packages/core/agent-loop/src/runtime-context.ts`
- Symbol: `ReactLoopAgent.preStep`, `ReactLoopAgent.step`, `RuntimeContextProjection`
- Observation: 每个 step 先 claim inbox，assemble system prompt sections，再用 runtime context projection 和 `session.deriveMessages()` 构建请求。注释明确说明 every request is derived from the session log。
- Meaning: Tour Pass 可以在每次工具结果后重新投影活跃事实，避免一个可变大 state object 成为隐式真相。
- Alternative explanation: 每步重建需要缓存和稳定前缀设计，否则增加延迟与 token 成本。
- Confidence: high

### EV-007 - DSH tools combine visibility, policy, approval and execution semantics
- Path: DSH `packages/core/tools/src/index.ts`
- Symbol: `ToolRuntime.register`, `restrict`, `guard`, `prepare`, `execute`, `resolveApproval`, `applyPostPolicy`
- Observation: 工具有输入/输出 schema、scope restriction、并发分类、pre/post waterfall 和 monotonic guards；`ask` 在没有 approval service 或 agent identity 时拒绝。
- Meaning: 旅游工具必须区分 read、compute、write、transaction，且权限不应散落在 adapter 中。
- Alternative explanation: DSH 完整工具 runtime 对 Tour Pass 首版过重，可实现其最小合同而非移植代码。
- Confidence: high

### EV-008 - DSH persistence decouples synchronous append from I/O and supports resume
- Path: DSH `packages/session/session-persistence/src/coordinator.ts`, `packages/session/session-persistence/src/write-behind.ts`, `packages/core/agent-loop/tests/resume.spec.ts`
- Symbol: `PersistenceCoordinator`, `SessionWriteBehind`, resume tests
- Observation: live append 同步进入内存日志，持久化按 session 串行、批量异步写；resume 在发布 session/agent 前先加载并完成 scoped setup，失败可回滚。
- Meaning: 审批暂停、进程重启和工具超时后继续同一旅行任务需要类似的恢复边界。
- Alternative explanation: 首版可用数据库事务同步写，未必需要 write-behind 和 repair coordinator。
- Confidence: high

### EV-009 - DSH projections are versioned read models derived from the log
- Path: DSH `packages/session/session-projection/src/index.ts`
- Symbol: `SessionProjectionRegistry.register`, `snapshot`, `checkpoint`, `restore`, `drive`
- Observation: 每个 projection 定义 `init/apply/view/stateVersion`；checkpoint 带 watermark，恢复时可从 tail replay，版本不匹配则回退全量 fold。
- Meaning: Tour Pass 的 plan、facts、approval、trace 和记忆候选不需要混在 agent state 中，可独立重建和升级。
- Alternative explanation: 只有 projection 计算昂贵或客户端很多时，通用 checkpoint registry 才值得实现。
- Confidence: high

### EV-010 - DSH subagents are isolated conversations with explicit scheduling and limits
- Path: DSH `packages/subagent/tool-subagent/src/index.ts`
- Symbol: `resolveDelegationRun`, `apply`
- Observation: 子 Agent 工具区分 foreground、background 和 continuable；可限制深度与工具，默认提示明确子 Agent 是否继承父上下文。continuable 子任务拥有 durable child id。
- Meaning: 真正多 Agent 的关键是独立上下文、生命周期、预算和回收，不是把函数命名为 Agent。
- Alternative explanation: Tour Pass 常规城市行程不需要这一复杂度。
- Confidence: high

### EV-011 - Tour Pass currently lacks a unified durable mission runtime
- Path: Tour Pass `graph.py`, `api_multi_agent.py`, `tools/session_store.py`
- Symbol: `build_tour_graph`, `MemorySaver`, `_make_thread_id`, `SessionStore`
- Observation: LangGraph 路径固定；每次规划创建新 thread id；Graph checkpointer 与短 TTL 业务 session 分离。已有研究还确认两个接口残留未定义 `_chat_sessions`。
- Meaning: 当前“一次性 API 调用”的观感来自核心对象和会话契约，而非旅游领域没有 Agent 空间。
- Alternative explanation: 对 demo 和一次性生成，这个设计更便宜、更确定。
- Confidence: high

### EV-012 - Tour Pass already produces the feedback needed for domain memory
- Path: Tour Pass `web/editor/src/stores/historyStore.ts`, `web/editor/src/stores/editorStore.ts`, `web/editor/src/NewEditorApp.tsx`
- Symbol: editor commands and saved-trip update flow
- Observation: 删除、添加、换序、跨天移动和改时间已被记录用于 undo/redo，但没有进入 planner session、偏好候选或 eval。
- Meaning: 最有价值的“记忆”来源可能是用户接受/拒绝的 plan patch，而不是聊天摘要。
- Alternative explanation: 一次编辑可能由临时情况引起，不能直接推断长期偏好。
- Confidence: high

## Engineering Evidence

- Pi 有针对 session context、branching、compaction、retry、dynamic tools 和 extension hooks 的测试源码；关键示例不是只有文档描述。
- DSH 有 agent loop、resume、session property、JSONL/SQLite persistence、projection、compaction、tool policy、subagent 和 web lifecycle 测试源码。
- 外部仓库本地 checkout 均没有 `node_modules`，本次没有安装依赖或运行测试，因此不声明测试通过。
- Tour Pass 既有研究已运行 `npm run test:multi-agent`（152 tests PASS）和 `npm run quality:itinerary-smoke`（青岛、重庆 PASS）；这些证明当前算法/工作流基线，不证明持续 Agent runtime。

## Limitations

- Pi 与 DSH 都是 coding-agent-oriented harness；旅游领域的外部事实时效、供应商交易、隐私删除和用户偏好需要另行设计。
- 没有基于同一任务集测量 Pi/DSH 的 token、延迟、恢复或工具选择质量，不能做性能排名。
- DSH 当前版本为 `0.1.1-rc.2`，包边界仍可能快速变化。
- Pi 的 JSONL session 主要面向本地单用户工具，不直接提供 Tour Pass 所需租户、ACL 和数据删除合同。
- 本次没有用户访谈或生产 telemetry，无法证明“行中陪伴”比“一次性规划”更有需求。
- 当前会话没有暴露 `codebase-memory-mcp` 的 `search_graph`、`trace_path`、`get_code_snippet` 或 `index_repository`，项目图谱不能作为本次验证来源。

## Contradictions

- Tour Pass 名称上是多 Agent，运行时却主要由固定代码决定节点顺序；Pi/DSH 的关键恰好是模型可在受控边界内决定下一步。
- Tour Pass 有 `MemorySaver` 和 SessionStore，但没有一个稳定 ID 与持久事件源贯穿请求、审批和编辑。
- DSH 的全插件化很先进，但对 Tour Pass 全量照搬会违反“为实际复杂度付费”的工程原则。
- Pi 的 session tree 很适合探索对话分支，但旅游产品更需要 plan version、patch 和审批状态，不能直接复制其 UI 模型。

## Open Questions

- `TripSession` 首版使用 SQLite 还是现有服务数据库，如何与 C++ 服务事务边界衔接？
- 哪些 editor diff 只属于本次旅行，哪些可以晋升为长期用户偏好？
- 首批工具中哪些拥有足够可靠、合法且带时间戳的数据来源？
- 计划 patch 的 schema 如何表达跨天移动、时间窗口调整、酒店更换和局部路线重算？
- 恢复评估如何模拟进程重启、重复 webhook、审批超时和外部服务部分失败？

