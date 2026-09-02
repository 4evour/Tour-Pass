# Thesis

## Central Thesis

Tour Pass 不应继续扩充“景点 Agent、酒店 Agent、餐厅 Agent”的固定流水线，也不应直接复制 DSH 的通用插件平台。最合适的目标是一个 **Pi 风格的小型 Trip Agent 内核，加上 DSH 风格的事件化 TripSession 和可重建投影**：模型在有界循环中动态选择领域工具，所有输入、工具事实、计划版本、用户编辑和审批都先进入追加式事件日志；每一轮只从日志投影出任务所需上下文，C++ 求解器继续负责确定性约束。

这个判断可证伪：若在多轮规划、局部重规划和中断恢复评估中，新 runtime 不能降低用户编辑距离、提高硬约束成功率或恢复成功率，那么应保留当前固定工作流，而不是为了架构先进性扩大系统。

## Common Misreading

一个常见理解是：Pi 强在工具循环，DSH 强在插件数量，所以 Tour Pass 应接更多工具并增加更多 Agent。这个理解漏掉了二者真正解决的问题：Pi 让每轮模型决策、工具执行和会话分支保持简单可见；DSH 则让持久事实、派生状态和运行时插件可以独立演进与恢复。工具或角色数量只是表象。

## Supporting Evidence

1. Pi 的 `runLoop` 只有少量稳定边界：构建 LLM 上下文、流式响应、执行工具、注入 steering/follow-up、准备下一轮和停止；`beforeToolCall`、`afterToolCall`、`prepareNextTurn` 与 `transformContext` 允许领域策略扩展，而不改循环主体。
2. Pi 的 session 不是简单消息数组：JSONL entry 以 `id/parentId` 形成树，`buildSessionContext` 从当前 leaf 重建活动分支，并以 compaction/branch summary 控制模型可见上下文。会话历史与当前上下文因此不是同一个对象。
3. DSH 明确把 `Session` 实现为不可改写的事件日志；LLM history、inbox、统计和领域状态都可由 surface/projection 折叠得到，持久层异步批量写入并支持恢复。这比“把聊天记录塞回 prompt”更适合 Trip Mission。
4. DSH 的工具层把 schema、作用域可见性、并发分类、pre/post policy、单调 guard、审批和最终模型可见结果放在统一执行管线中；这正对应旅游场景里的查询、重算、写日历、预约等不同风险级别。
5. Tour Pass 当前是固定 LangGraph 节点图，Graph `MemorySaver`、每请求新 `thread_id` 和短 TTL 业务 session 没有形成一个可跨请求、跨重启、跨审批恢复的任务事实源；编辑器 diff 也没有回流。

## Counterargument

DSH 的事件溯源、projection registry、插件生命周期、持久化协调器和 scoped tool runtime 解决的是通用宿主平台问题。Tour Pass 当前团队规模和领域边界都更小，复制这套层次会制造大量抽象、迁移和运维成本。旅行规划的约束也适合固定工作流，过多模型决策可能降低稳定性。

这个反论点是成立的，因此建议借用 **契约** 而不是移植框架：首版只实现一种持久化、一个 orchestrator、约 6-8 个 typed tools、3-5 个 projection 和一套审批规则。只有出现第二种存储、第二类 runtime 或第三方领域扩展后，才引入完整插件装载器。

## Conditions

判断成立的条件：

- 产品目标从一次性路线扩展到多轮规划、行前变更或行中重规划；
- 能定义至少两类会变化的外部事实，并对数据时间与来源负责；
- 使用统一 `trip_session_id` 贯穿 API、运行时、计划版本和编辑反馈；
- 建立可重复的 trace/eval，证明动态工具选择带来收益。

判断失效的条件：

- 项目只需展示 C++ 路线算法和一次性结果；
- 没有可靠外部工具，也没有用户回访或持续任务；
- 持久 runtime 的成本明显高于编辑后重生成，并且评估没有质量提升。

## Recommended Runtime

```text
TripSession append-only event log
  ├─ facts projection: 用户约束、确认过的地点事实、数据时效
  ├─ plan projection: 当前 plan_version、patch 链、验证状态
  ├─ approval projection: 待批准/已批准/拒绝的动作
  ├─ memory candidates: 从用户显式确认和编辑 diff 提取，尚未直接写长期记忆
  └─ trace projection: 决策、工具、耗时、失败和降级
          ↓
Context Builder（预算化、按需、可解释）
          ↓
Trip Orchestrator loop
          ↓
Typed domain tools
  search_evidence / check_place / check_route / solve_itinerary
  validate_plan / propose_patch / request_approval / apply_action
          ↓
C++ Solver + deterministic validators + external adapters
          ↓
events: tool_result / plan_proposed / validation_failed / approval_requested
```

### 最小内核

1. `TripEventStore`：追加、读取、乐观版本检查、按 `trip_session_id` 恢复。
2. `TripProjector`：从事件计算 `WorkingContext`，不让模型直接消费完整日志。
3. `TripAgentLoop`：最多 N 轮，支持 tool call、steer、cancel、resume 和结构化停止原因。
4. `ToolRegistry`：typed input/output、只读/变更分类、超时、幂等键、pre/post policy、审批。
5. `CompactionPolicy`：压缩的是模型上下文，不删除事实日志；摘要带覆盖范围和来源事件 ID。
6. `EvalTrace`：每个 plan version 记录输入事实、工具选择、验证、成本、延迟和最终编辑 diff。

### 前端暂缓后的最小界面

不继续做自由画布式编辑器，只提供三个可验收表面：

- `Trace`：Agent 为什么查这个工具、哪些事实过期或失败；
- `Diff`：旧计划与 `plan_patch` 的增删改及影响；
- `Approve`：对写日历、通知、预约等副作用逐项批准或拒绝。

## Do Not Copy

- 不复制 DSH 的通用动态插件市场、跨语言 Code Mode、复杂 host/client runtime 和所有 projection 基础设施。
- 不照搬 Pi 的 coding-specific bash/file 权限与分支 UI；旅游计划通常需要 plan version + patch，而不是任意消息树编辑。
- 不把所有历史摘要成“长期记忆”；稳定偏好必须可编辑、有来源、有时间，并由用户行为或确认支持。
- 不把 Reviewer、Scheduler 再包装成自治子 Agent；优先作为 typed tools，只有独立上下文和并行价值明确时才创建子 Agent。
- 不让 LLM 直接覆盖完整行程；每次变化生成 patch，先验证再提交。

## Unproven

- Pi 与 DSH 的公开测试在本机未执行，尚未独立验证其实现正确性和性能。
- 哪些用户编辑可以稳定推断长期偏好，尚无 Tour Pass 真实数据支持。
- 当前模型在 6-8 个旅游工具上的选择正确率、恢复一致性和成本尚未测量。
- append-only log 的存储规模、保留周期和隐私删除策略尚未设计。

