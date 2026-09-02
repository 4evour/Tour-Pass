# Source State

- Repository: Tour Pass
- Local path: `D:\Tour Pass`
- Remote URL: `git@github.com:4evour/Tour-Pass.git`
- Branch/tag: `codex/trip-workflow-updates`
- Commit: `f91bb5861b7d66cc072020fe1ae48fc169e72c3b`
- Research date: 2026-08-27 (Asia/Shanghai)
- Working tree: dirty before research; pre-existing edits in `CHANGELOG.md`, `web/index.html`, and `tests/test_tour_ai_layout_markup.js` were preserved.
- Primary language: C++17 core planner, Python FastAPI/LangGraph agent service, TypeScript/React editor, static JavaScript frontend
- Requested audience: Tour Pass maintainer deciding whether and how to make the product more agentic
- Research question: Tour Pass is already a multi-agent travel planner, but why does it still feel like a toy, and which current agent-system designs can materially raise its product and engineering ceiling?
- Explicit non-goals: no agent-framework migration, no business-code change, no claim that more agents automatically improve quality, no booking-provider selection, and no production-readiness certification.
- Codebase graph status: the repository requires `codebase-memory-mcp`, but its graph tools were not exposed in this session. Source and tests were read directly. The existing graph artifact was not treated as current evidence and was not refreshed because no code structure changed.
- Official docs inspected (accessed 2026-08-27):
  - OpenAI Agents SDK overview: https://developers.openai.com/api/docs/guides/agents
  - OpenAI orchestration and handoffs: https://developers.openai.com/api/docs/guides/agents/orchestration
  - OpenAI guardrails and human review: https://developers.openai.com/api/docs/guides/agents/guardrails-approvals
  - OpenAI integrations and observability: https://developers.openai.com/api/docs/guides/agents/integrations-observability
  - OpenAI agent workflow evaluation: https://developers.openai.com/api/docs/guides/agent-evals
  - Anthropic, Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
  - Anthropic, Effective context engineering for AI agents: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
  - Anthropic, Scaling Managed Agents: Decoupling the brain from the hands: https://www.anthropic.com/engineering/managed-agents
  - LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
  - LangGraph memory overview: https://docs.langchain.com/oss/python/concepts/memory
- Competitors and benchmarks inspected (accessed 2026-08-27):
  - TravelPlanner paper: https://arxiv.org/abs/2402.01622
  - TravelPlanner repository: https://github.com/OSU-NLP-Group/TravelPlanner

## Repository Entry Points

- Python workflow construction: `graph.py::build_tour_graph`
- Python API adapter: `api_multi_agent.py`
- Shared workflow state: `agents/state.py::TourState`
- Deterministic planner node: `agents/scheduler_agent.py::SchedulerAgent`
- Quality review node: `agents/reviewer_agent.py::ReviewerAgent`
- Retrieval: `agents/retrieve_agent.py`, `tools/rag.py`
- Session storage: `tools/session_store.py::SessionStore`
- C++ planning engine: `src/`, `include/tourpass/`
- Editor interaction history: `web/editor/src/stores/historyStore.ts`, `web/editor/src/stores/editorStore.ts`
- Main regression suite: `tests/test_multi_agent.py`

## Verification Performed

- `npm run test:multi-agent`: PASS, 152 tests in 3.792s.
- `npm run quality:itinerary-smoke`: PASS for Qingdao and Chongqing.
- `py -3 -X utf8 -c "import asyncio, api_multi_agent as a; print(asyncio.run(a.list_sessions()))"`: FAIL with `NameError: _chat_sessions is not defined`, confirming an uncovered session-runtime defect.
