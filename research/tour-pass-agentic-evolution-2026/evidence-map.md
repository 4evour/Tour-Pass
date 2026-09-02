# Evidence Map

## Source State

Research is pinned to commit `f91bb5861b7d66cc072020fe1ae48fc169e72c3b` on `codex/trip-workflow-updates`, inspected on 2026-08-27. The working tree was already dirty. External facts below use official documentation or the TravelPlanner paper/repository and include the access date in `source-state.md`.

## README Reuse Map

| README content | Classification | Reason |
|---|---|---|
| C++17 planner + Python Agent + React editor | reuse | Matches repository entry points and dependency files. |
| 21-city coverage | adapt | Data directories support this claim, but coverage does not imply equal route freshness or production quality. |
| Multi-agent planning flow | adapt | The node flow is real, but most nodes are deterministic workflow components rather than autonomous tool-using agents. |
| Real weather and optional hotel prices | verify | Weather has a live provider plus an explicit placeholder; hotel pricing remains inert unless an external provider is configured. |
| Production/deployment maturity implications | verify | Deployment exists, but the session runtime defect, in-memory graph checkpointer, and missing agent traces/evals limit stronger claims. |
| Marketing language that equates node count with intelligence | exclude | Role count is not evidence of autonomy, reliability, or user value. |

## Official Claims

- OpenAI documentation defines agents as applications that plan, call tools, collaborate across specialists, and keep enough state to complete multi-step work. It recommends adding specialists only when capability, policy, prompt, or ownership contracts truly differ.
- OpenAI documentation treats tool guardrails, resumable human approvals, structured traces, and repeatable workflow evaluation as separate production concerns.
- Anthropic distinguishes workflows, whose paths are predefined in code, from agents, where the model dynamically directs process and tool use. It recommends increasing complexity only when evaluation shows a benefit.
- Anthropic's 2025 context-engineering guidance recommends a small high-signal context, just-in-time retrieval, progressive disclosure, compaction, and persistent notes for long-horizon work.
- Anthropic's 2026 Managed Agents design separates the durable session event log, replaceable harness, and execution tools/sandboxes so each can fail and recover independently.
- LangGraph documents checkpointers as thread-scoped state and stores as cross-thread long-term memory; in-memory savers do not survive process restarts.
- TravelPlanner evaluates travel planning as tool use under environment, commonsense, and hard constraints. Its paper reports that evaluated language agents struggled with tool selection, task focus, and tracking multiple constraints; the reported GPT-4 success rate was 0.6% for the paper's 2024 setup, not a current model benchmark.

## Architecture

Current Tour Pass is a hybrid constraint-planning workflow:

```text
Structured form / natural language
  -> intent parsing
  -> fixed BM25/XHS retrieval
  -> POI selection
  -> hotel/weather/restaurant fan-out
  -> deterministic scheduling and route optimization
  -> deterministic + LLM review
  -> ticket metadata + summary
  -> frontend itinerary
  -> optional editor changes and trip save
```

The strongest component is the deterministic planning core. The main missing loop is after delivery: editor changes, trip execution events, and user outcomes do not become durable evidence that affects later planning.

End-to-end evidence path:

```text
Input
  api_multi_agent.py::StructuredPlanRequest / PlanRequest
Validation
  Pydantic request models + TripIntent validators
Transformation
  create_initial_state_from_intent -> LangGraph nodes -> SchedulerAgent
Persistence
  Redis/in-memory SessionStore (30-minute TTL) + separate in-memory MemorySaver
Retrieval
  fixed query expansion -> in-memory BM25 + XHS route loading
Delivery
  convert_to_frontend_format -> SSE/frontend/editor
Feedback
  editor command history and saved itinerary, currently not returned to planner memory/evals
```

## Code Evidence

### EV-001 - The graph is a fixed workflow, not a model-directed tool loop
- Path: `graph.py`
- Symbol: `build_tour_graph`
- Observation: Nodes and edges are statically declared. The only conditional branch is Reviewer -> Scheduler or Ticket, capped at two review cycles.
- Meaning: Tour Pass is correctly described as an agentic workflow, but not as an autonomous agent that chooses tools or decomposes unforeseen tasks.
- Alternative explanation: A fixed workflow is often the right architecture for itinerary generation because it is predictable and testable.
- Confidence: high

### EV-002 - Most named agents are bounded deterministic components
- Path: `graph.py`, `agents/base.py`, `agents/ticket_agent.py`, `agents/restaurant_agent.py`, `agents/scheduler_agent.py`
- Symbol: agent construction and `BaseAgent` subclasses
- Observation: POI, retrieval, restaurant, scheduler, and ticket nodes use ordinary Python logic. LLM nodes call prompt chains through `invoke_llm`; no `bind_tools`, `tool_calls`, or MCP invocation exists in the agent code.
- Meaning: Adding more role names would increase ceremony, not autonomy. The useful next step is a model-owned decision loop over a small tool contract.
- Alternative explanation: Deterministic nodes intentionally protect core route quality from LLM variability.
- Confidence: high

### EV-003 - Graph persistence and product sessions are split and do not provide durable continuation
- Path: `graph.py`, `api_multi_agent.py`, `tools/session_store.py`
- Symbol: `MemorySaver`, `_make_thread_id`, `SessionStore`
- Observation: The graph uses `MemorySaver`, while API requests generate a fresh UUID-like `thread_id`. A separate Redis/in-memory session object has a 30-minute TTL and stores serialized state and chat history.
- Meaning: The runtime cannot reliably resume the same graph run after restart, delayed approval, or a later trip phase. It also lacks cross-trip user memory.
- Alternative explanation: Fresh thread IDs correctly isolate one-shot generation requests and the Redis session is adequate for a short demo.
- Confidence: high

### EV-004 - The session migration is incomplete and a public diagnostic path fails
- Path: `api_multi_agent.py`
- Symbol: `modify_itinerary`, `list_sessions`
- Observation: These functions still reference `_chat_sessions`, which has no definition after migration to `SessionStore`. Directly invoking `list_sessions()` raises `NameError`.
- Meaning: Session lifecycle behavior is not covered end to end, and this is a concrete maturity gap around the exact area needed for a long-running agent.
- Alternative explanation: These endpoints may not be linked from the current UI, limiting user-visible blast radius.
- Confidence: high

### EV-005 - Retrieval is eager and predetermined
- Path: `agents/retrieve_agent.py`, `tools/rag.py`
- Symbol: `RetrieveAgent.execute`, `search_guides`, `search_poi_tips`
- Observation: Retrieval executes a fixed set of must-visit, interest, generic-guide, transport, timing, and crowd queries before scheduling. Results are text snippets from an in-memory BM25 corpus plus XHS route records.
- Meaning: The reviewer cannot ask targeted follow-up questions such as current closure status, an uncertain route segment, or a replacement near the user's location. This is the clearest place for just-in-time agent tools.
- Alternative explanation: Fixed retrieval is fast, cheap, deterministic, and suitable for stable local data.
- Confidence: high

### EV-006 - The quality loop can force completion without exposing the final failure contract
- Path: `graph.py`, `api_multi_agent.py`, `docs/superpowers/specs/2026-06-20-agent-itinerary-quality-design.md`
- Symbol: `route_review`, `convert_to_frontend_format`
- Observation: Missing review results, excessive non-critical errors, or reaching the cycle cap route to Ticket. The frontend conversion omits `review_result` and `quality_warnings`, although the design document says a capped repair must not silently pass.
- Meaning: The system has internal review but does not yet make uncertainty and degraded quality a first-class product state.
- Alternative explanation: Some day-level route quality and replacement fields are exposed, so the UI has partial evidence.
- Confidence: high

### EV-007 - User edits are captured but not converted into learning signals
- Path: `web/editor/src/stores/historyStore.ts`, `web/editor/src/stores/editorStore.ts`, `web/editor/src/NewEditorApp.tsx`
- Symbol: command execution, `markChanged`, saved-trip update
- Observation: The editor records reorder, remove, add, move-between-days, and time-change operations and can save the resulting trip. No path converts those diffs into preference memory, evaluation labels, or planner updates.
- Meaning: Tour Pass is discarding its most domain-specific feedback signal. Learning from edits is likely more valuable than adding a generic conversational agent.
- Alternative explanation: Local undo/redo history was designed for editor UX, not model training or personalization.
- Confidence: high

### EV-008 - External action capability is mostly read-only or estimated
- Path: `agents/weather_agent.py`, `tools/weather_api.py`, `tools/hotel_price_api.py`, `agents/ticket_agent.py`
- Symbol: weather fetch, hotel price provider boundary, `TicketAgent.execute`
- Observation: Weather can call QWeather, hotel prices require a configured provider, and tickets are local price-level estimates with tips. There is no reservation, availability check, calendar write, navigation launch, or delayed approval workflow in the Python agent runtime.
- Meaning: The product generates a document but does not yet carry a travel task through preparation and execution.
- Alternative explanation: Avoiding transactions is appropriate until supplier contracts, identity, payment, and approval controls exist.
- Confidence: high

## Engineering Evidence

- `npm run test:multi-agent` passed 152 tests, covering intent parsing, scoring, clustering, scheduling, reviewer hard checks, RAG, cache, route metrics, and graph construction.
- `npm run quality:itinerary-smoke` passed Qingdao and Chongqing with zero estimated segments in those scenarios.
- The suite contains strong component-level quality checks, but no dataset of multi-turn trip tasks, no tool-selection scoring, no trace-level grading, no recovery test across process restart, and no evaluation derived from user edits.
- The failed `list_sessions()` diagnostic demonstrates that import tests and graph compilation tests do not establish working session endpoints.
- The project already has a C++ algorithm benchmark and route-quality checks. These should remain separate from agent workflow evaluation so planner quality and orchestration quality can be diagnosed independently.

## Limitations

- No live production traffic, user interviews, or editor telemetry were available, so the ranking of product opportunities is an engineering judgment rather than measured demand.
- No external hotel/ticket supplier was configured or called.
- The TravelPlanner 0.6% figure belongs to its 2024 experimental setup and must not be presented as the performance of current frontier models.
- Official framework documents describe capabilities and design guidance; they do not prove that adopting a framework improves Tour Pass.
- `codebase-memory-mcp` was unavailable, so required graph search and trace operations could not be performed.

## Contradictions

- The repository calls the system multi-agent, but code behavior is mostly a fixed workflow of deterministic components plus several isolated LLM calls.
- `MemorySaver` is present, but fresh thread IDs and process-local storage prevent it from functioning as durable conversational memory.
- The quality design requires visible warnings after capped repair, while the runtime can force-route onward and the frontend response omits the review result.
- The session store abstraction exists, but two endpoints still depend on the removed `_chat_sessions` global.
- The editor captures behavioral feedback, while the planner has no feedback ingestion or long-term preference store.

## Open Questions

- Which product target matters most: portfolio differentiation, daily active use, trip conversion, or technical depth? The optimal first milestone differs.
- Can the project legally and commercially obtain reliable availability, ticket, hotel, transit, and reservation APIs?
- Is the user willing to grant calendar, map, notification, or booking permissions, and which actions require explicit approval?
- What percentage of generated trips are edited, and which edit types recur by user or traveler segment?
- Can current session IDs be reconciled with authenticated user IDs and saved trip IDs without breaking API contracts?
- Which 50-200 realistic multi-turn tasks should become the first agent evaluation dataset?
