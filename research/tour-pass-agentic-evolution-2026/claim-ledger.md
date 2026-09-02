# Claim Ledger

| ID | Type | Claim | Evidence | Confidence | Article Location |
|---|---|---|---|---|---|
| C-001 | FACT | Tour Pass 的主多 Agent 图是静态节点和边组成的 LangGraph 工作流。 | `graph.py::build_tour_graph` | high | Architecture |
| C-002 | FACT | 当前 Agent 代码没有模型工具调用循环；LLM 通过 prompt chain 或直接 `ainvoke` 调用。 | `agents/base.py::invoke_llm`; `rg "bind_tools|tool_calls" agents tools api_multi_agent.py` 无结果 | high | Code Evidence |
| C-003 | FACT | 图使用进程内 `MemorySaver`，而 API 为每次规划生成新的 `thread_id`。 | `graph.py:22,239`; `api_multi_agent.py::_make_thread_id` and planning endpoints | high | Persistence |
| C-004 | FACT | 产品会话默认 TTL 为 1800 秒，并在 Redis 不可用时退回进程内字典。 | `tools/session_store.py:17-25,40-105` | high | Persistence |
| C-005 | FACT | `list_sessions()` 和 `modify_itinerary()` 引用未定义的 `_chat_sessions`。 | `api_multi_agent.py:908,1121-1124`; direct command reproduced `NameError` | high | Limitations |
| C-006 | FACT | 检索节点在排程前执行预定义 BM25/XHS 查询，而不是由模型按需选择查询。 | `agents/retrieve_agent.py:27-139`; `tools/rag.py` | high | Retrieval |
| C-007 | FACT | Reviewer 达到轮次上限、缺少结果或错误过多时会路由到 Ticket；前端转换不返回 review result。 | `graph.py::route_review`; `api_multi_agent.py::convert_to_frontend_format` | high | Quality Loop |
| C-008 | FACT | 项目质量设计要求达到返修上限后返回 `quality_warnings`。 | `docs/superpowers/specs/2026-06-20-agent-itinerary-quality-design.md:227` | high | Contradictions |
| C-009 | FACT | 编辑器记录增删、重排、跨天移动和改时间，并能保存更新后的行程。 | `web/editor/src/stores/historyStore.ts`; `web/editor/src/stores/editorStore.ts`; `web/editor/src/NewEditorApp.tsx` | high | Feedback |
| C-010 | FACT | 当前多 Agent 回归套件通过 152 个测试；质量 smoke 的青岛和重庆场景通过。 | Commands run on 2026-08-27; see `source-state.md` | high | Engineering Evidence |
| C-011 | FACT | 当前测试没有发现 `_chat_sessions` 运行时缺陷，因为 API 测试覆盖导入、模型和格式转换，但未调用会话列表端点。 | `tests/test_multi_agent.py::TestAPIModule`; direct diagnostic failure | high | Test Gaps |
| C-012 | FACT | OpenAI 官方文档建议只在工具、政策、所有权或 prompt 合同真正变化时增加 specialist，并区分 handoff 与 agents-as-tools。 | https://developers.openai.com/api/docs/guides/agents/orchestration (accessed 2026-08-27) | high | Comparison |
| C-013 | FACT | OpenAI 官方文档把可恢复审批、工具护栏、trace 和 workflow eval 作为 Agent 运行时能力。 | https://developers.openai.com/api/docs/guides/agents/guardrails-approvals ; https://developers.openai.com/api/docs/guides/agents/integrations-observability ; https://developers.openai.com/api/docs/guides/agent-evals (accessed 2026-08-27) | high | Comparison |
| C-014 | FACT | Anthropic 2026 Managed Agents 将 session、harness 和 sandbox/tool 解耦，使用持久事件日志恢复无状态 harness。 | https://www.anthropic.com/engineering/managed-agents (accessed 2026-08-27) | high | Comparison |
| C-015 | FACT | Anthropic 2025 context engineering 建议按需检索、渐进披露、压缩和外部持久笔记。 | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents (accessed 2026-08-27) | high | Comparison |
| C-016 | FACT | LangGraph 区分 thread-scoped checkpointer 与 cross-thread store，并明确 in-memory saver 不跨进程重启。 | https://docs.langchain.com/oss/python/langgraph/persistence ; https://docs.langchain.com/oss/python/concepts/memory (accessed 2026-08-27) | high | Comparison |
| C-017 | FACT | TravelPlanner 将旅游规划评估为工具使用和多约束规划；其 2024 论文报告的 GPT-4 success rate 为 0.6%。 | https://arxiv.org/abs/2402.01622 (accessed 2026-08-27) | high | Benchmark |
| C-018 | INFERENCE | Tour Pass 的“玩具感”主要来自一次性交付、非持久会话、缺少动作与反馈闭环，而不是规划算法过于简单。 | C-001 through C-011 | high | Thesis |
| C-019 | INFERENCE | 最适合 Tour Pass 的架构是一个 Trip Orchestrator 把 C++ Solver、Reviewer 和外部数据源当作有界工具，而不是继续增加平级角色。 | C-002 + C-012 + C-017 | high | Recommendation |
| C-020 | INFERENCE | 编辑 diff 是项目当前最独特、成本最低的个性化和 eval 数据源。 | C-009 + absence of feedback ingestion | medium | Recommendation |
| C-021 | OPINION | 在会话、trace、eval 和审批完成前，MCP/A2A 或自主预订不应成为优先级。 | stated criteria: user value, failure isolation, and operational risk | medium | Roadmap |
| C-022 | OPEN | 行中主动重规划能否提高用户留存或行程采纳率。 | No production telemetry or user study available | low | Open Questions |
| C-023 | OPEN | 当前模型在真实 Tour Pass 工具选择和多轮约束任务上的成功率。 | No agent-task evaluation dataset exists | low | Open Questions |
