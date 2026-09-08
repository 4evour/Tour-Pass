# Source State

- Repository: Tour Pass
- Local path: `D:/Tour Pass`
- Remote URL: 未核查；本次不需要远端仓库信息
- Branch/tag: `main`
- Commit: `ca54eeb14177024f9f9e7479e371399b458c7b23`
- Research date: 2026-09-08
- Primary language: Python；FastAPI、Pydantic 2、SQLAlchemy、httpx
- Requested audience: Tour Pass 技术与产品决策者
- Research question: 是否应直接复用成熟 Agent Harness，以及哪个框架最适合把当前开放式 ReAct 循环改成低延迟、可验证、可降级的旅行规划工作流
- Explicit non-goals: 不修改生产代码；不证明任何框架能自动提高行程质量；不以 GitHub stars 排名；不评估前端、认证、分享和 PDF 功能

## Local Evidence Inspected

- `README.md`
- `trip_agent/loop.py`
- `trip_agent/llm.py`
- `trip_agent/providers/amap.py`
- `trip_agent/validation.py`
- `trip_agent/requirements.txt`
- `artifacts/guangzhou-three-way-comparison/20260907T141532Z/tour-pass-live/20260907T142649Z/runs/01-guangzhou-short-prompt/summary.json`
- `artifacts/guangzhou-three-way-comparison/20260907T141532Z/comparison.json`

## Official Sources Inspected

访问日期均为 2026-09-08。

### LangGraph

- Docs: https://docs.langchain.com/oss/python/langgraph/overview
- Graph API: https://docs.langchain.com/oss/python/langgraph/use-graph-api
- Durable execution: https://docs.langchain.com/oss/python/langgraph/durable-execution
- Persistence: https://docs.langchain.com/oss/python/langgraph/add-memory
- Interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- Streaming: https://docs.langchain.com/oss/python/langgraph/streaming
- Repository: https://github.com/langchain-ai/langgraph
- Inspected main commit: `81bf17b23123e4ef8b9d5f49fa09a0122fc2edd1`
- PyPI observed version: `1.2.11`
- License: MIT

### Pydantic AI

- Agents: https://ai.pydantic.dev/agents/
- Graph: https://ai.pydantic.dev/graph/
- OpenAI models/provider: https://ai.pydantic.dev/models/openai/
- Structured output: https://ai.pydantic.dev/output/
- Tool retry behavior: https://ai.pydantic.dev/tools-advanced/
- Durable execution: https://ai.pydantic.dev/durable_execution/overview/
- Repository: https://github.com/pydantic/pydantic-ai
- Inspected main commit: `a1a42986ca10f5693cf83c9c414e1b57d01f837e`
- PyPI observed version: `2.40.0`
- License: MIT

### OpenAI Agents SDK

- Running agents: https://openai.github.io/openai-agents-python/running_agents/
- Models: https://openai.github.io/openai-agents-python/models/
- Sessions: https://openai.github.io/openai-agents-python/sessions/
- Repository: https://github.com/openai/openai-agents-python
- Inspected main commit: `17e108245a7de01d45c1b4349c0497bd3a5186e0`
- PyPI observed version: `0.22.0`
- License: MIT

### Google ADK

- Workflow agents: https://google.github.io/adk-docs/agents/workflow-agents/
- Model integration: https://google.github.io/adk-docs/agents/models/
- Repository: https://github.com/google/adk-python
- Inspected main commit: `7db3610d76c67d9ef7bcf08e30d951f136a93dda`
- PyPI observed version: `2.8.0`
- License: Apache-2.0

### Additional Candidates

- Microsoft Agent Framework repository: https://github.com/microsoft/agent-framework ; inspected main commit `709a7fb8b920f4a1cacfe7a8b0e38a6f241e161b`
- CrewAI repository/docs: https://github.com/crewAIInc/crewAI and https://docs.crewai.com/en/concepts/flows

## Competitors Inspected

LangGraph、Pydantic AI/Pydantic Graph、OpenAI Agents SDK、Google ADK、Microsoft Agent Framework、CrewAI。Temporal/DBOS 仅作为耐久执行后端边界参考，不作为本次主 Harness 候选。
