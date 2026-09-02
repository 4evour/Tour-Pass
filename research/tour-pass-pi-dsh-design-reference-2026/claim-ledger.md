# Claim Ledger

| ID | Type | Claim | Evidence | Confidence | Article Location |
|---|---|---|---|---|---|
| C-001 | FACT | Pi 的主循环支持 tool-call continuation、steering、follow-up、context transform 和 next-turn hooks。 | Pi `packages/agent/src/agent-loop.ts::runLoop` | high | Runtime |
| C-002 | FACT | Pi 在工具参数验证后、执行前运行拦截器，并可 block/terminate；执行后还可改写最终结果。 | Pi `packages/agent/src/agent-loop.ts::prepareToolCall/finalizeExecutedToolCall` | high | Tools |
| C-003 | FACT | Pi 的 coding session 以 `id/parentId` 形成树，并从活动 leaf 构建 compaction-aware context。 | Pi `packages/coding-agent/src/core/session-manager.ts::buildSessionPath/buildContextEntries/buildSessionContext` | high | Sessions |
| C-004 | FACT | Pi extension 能动态注册工具并更新 active tool/system prompt。 | Pi `packages/coding-agent/examples/extensions/dynamic-tools.ts`; `packages/coding-agent/test/agent-session-dynamic-tools.test.ts` | high | Tools |
| C-005 | FACT | DSH `Session` 是 deep-frozen、连续 seq 的 append-only event log，模型消息由 surface 派生。 | DSH `packages/core/session/src/index.ts::Session.append/deriveMessages` | high | Sessions |
| C-006 | FACT | DSH 的每次 agent step 从 inbox、system prompt assembly、runtime projection 和 session-derived messages 构建请求。 | DSH `packages/core/agent-loop/src/agent.ts::preStep/step/buildRequest` | high | Context |
| C-007 | FACT | DSH tool runtime 同时提供 schema、scope restriction、guard、pre/post policy、approval 和并发分类。 | DSH `packages/core/tools/src/index.ts::ToolRuntime` | high | Tools |
| C-008 | FACT | DSH 在缺少审批服务或 agent identity 时，将 `ask` 降级为拒绝。 | DSH `packages/core/tools/src/index.ts::resolveApproval` | high | Governance |
| C-009 | FACT | DSH projection 以 `init/apply/view/stateVersion` 折叠 session log，并支持 checkpoint + tail replay。 | DSH `packages/session/session-projection/src/index.ts::SessionProjectionRegistry` | high | Memory |
| C-010 | FACT | DSH persistence 对每个 session 串行化写入并使用 write-behind；resume 流程在发布前完成恢复和 setup。 | DSH `packages/session/session-persistence/src/coordinator.ts`; `packages/core/agent-loop/tests/resume.spec.ts` | high | Recovery |
| C-011 | FACT | DSH compaction 以 surface replacement 写入 checkpoint message，并在提交前检查选区稳定且摘要更小。 | DSH `packages/compaction/compaction-basic/src/region.ts::summarizeCompaction/assertSelectedSpanStable/commitCompactionBody` | high | Compaction |
| C-012 | FACT | DSH continuable subagent 有独立 durable child id，并可配置深度、工具过滤和前后台执行。 | DSH `packages/subagent/tool-subagent/src/index.ts::apply` | high | Multi-agent |
| C-013 | FACT | Tour Pass 当前规划顺序由静态 LangGraph 决定，且 checkpointer、API thread id 和业务 SessionStore 没有形成统一长程 session。 | Tour Pass `graph.py::build_tour_graph`; `api_multi_agent.py::_make_thread_id`; `tools/session_store.py::SessionStore` | high | Baseline |
| C-014 | FACT | Tour Pass 编辑器记录多种 itinerary 修改，但目前没有把 diff 写回 planner memory/eval。 | Tour Pass `web/editor/src/stores/historyStore.ts`; `web/editor/src/stores/editorStore.ts`; `web/editor/src/NewEditorApp.tsx` | high | Feedback |
| C-015 | INFERENCE | Tour Pass 的主要短板是 durable agent runtime，而不是旅游规划没有进一步 Agent 化空间。 | C-005 + C-006 + C-013 + C-014 | high | Thesis |
| C-016 | INFERENCE | Tour Pass 应采用 Pi-like loop 和 DSH-like event/projection contract，而不是完整移植任一框架。 | C-001 + C-003 + C-005 + C-007 + 当前项目规模 | high | Decision |
| C-017 | OPINION | 首版应限制为一个 orchestrator、6-8 个工具、3-5 个 projection 和一个持久化实现。 | 以最小可验证闭环和现有团队复杂度为准 | medium | Roadmap |
| C-018 | OPINION | 前端现阶段只需 trace、diff、approve，不应继续把复杂编辑器当作 Agent runtime 的前置条件。 | 用户目标 + C-014 + runtime 验收需要 | high | UI |
| C-019 | OPEN | editor diff 中哪些信号能可靠成为长期偏好，尚无真实用户数据证明。 | 缺少生产 telemetry/用户研究 | low | Limitations |
| C-020 | OPEN | 新 runtime 是否能提升采纳率、恢复率并控制成本，必须通过 Tour Pass 自有 eval 证明。 | 尚未实现或运行目标 runtime | low | Evaluation |

