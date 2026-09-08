# Claim Ledger

| ID | Type | Claim | Evidence | Confidence | Article Location |
|---|---|---|---|---|---|
| C-001 | FACT | 当前Harness最多允许24轮模型决策、48次Provider和4次完整提交 | `README.md:12`; `trip_agent/loop.py:833-864,1208-1224` | high | Current State |
| C-002 | FACT | 广州短提示真实运行使用12次planner、48次Provider、4次提交，734072ms后无计划 | `artifacts/guangzhou-three-way-comparison/20260907T141532Z/tour-pass-live/20260907T142649Z/runs/01-guangzhou-short-prompt/summary.json` | high | Failure Evidence |
| C-003 | FACT | 该运行LLM累计694017ms，占总墙钟约94.5% | 同C-002；比例为确定性计算 | high | Bottleneck |
| C-004 | FACT | 校验失败后Runtime把完整candidate和validation report反馈给模型，直到提交预算耗尽 | `trip_agent/loop.py:1192-1224` | high | Failure Mechanism |
| C-005 | FACT | Validator的allowed_actions目前没有通用确定性dispatch；直接执行的修复仅见路线时间轴修复 | `trip_agent/loop.py:1013-1029,1192-1224`; `trip_agent/validation.py` | high | Failure Mechanism |
| C-006 | FACT | AMap缓存未命中请求的等待和HTTP GET位于同一实例级asyncio.Lock中 | `trip_agent/providers/amap.py:22-66` | high | Provider Concurrency |
| C-007 | FACT | LangGraph Graph API提供条件边、并行fan-out/fan-in、Send、reducers和节点错误路由 | https://docs.langchain.com/oss/python/langgraph/use-graph-api （访问2026-09-08） | high | Framework Fit |
| C-008 | FACT | LangGraph官方提供AsyncPostgresSaver、thread_id和checkpoint state/history接口 | https://docs.langchain.com/oss/python/langgraph/add-memory （访问2026-09-08） | high | Persistence |
| C-009 | FACT | Pydantic AI支持OpenAI Responses模型、自定义AsyncOpenAI和base_url | https://ai.pydantic.dev/models/openai/ （访问2026-09-08） | high | Model Adapter |
| C-010 | FACT | OpenAI Agents SDK Runner在工具调用后重新调用LLM，超过max_turns则失败或进入配置的错误处理 | https://openai.github.io/openai-agents-python/running_agents/ （访问2026-09-08） | high | Candidate Rejection |
| C-011 | FACT | Google ADK workflow agents可按预定义顺序、并行和循环执行，不咨询模型决定编排 | https://google.github.io/adk-docs/agents/workflow-agents/ （访问2026-09-08） | high | Candidate Comparison |
| C-012 | FACT | Google ADK 2.0官方声明Agent API、event model和session schema相对1.x有breaking changes | https://pypi.org/project/google-adk/ 2.8.0元数据（访问2026-09-08） | high | Migration Risk |
| C-013 | INFERENCE | 当前主要根因是开放式模型控制流和整份重写，而不是缺少更强Validator | C-002、C-003、C-004、C-005 | high | Thesis |
| C-014 | OPINION | LangGraph Graph API是当前项目最合适的主Harness | 比较标准：显式控制流、迁移边界、streaming、checkpoint、现有栈兼容性 | high | Decision |
| C-015 | OPINION | 不应采用任何候选框架的预构建ReAct循环作为主规划器 | 当前失败机制与OpenAI Runner/Pydantic Agent默认模型循环相同 | high | Decision |
| C-016 | INFERENCE | Pydantic AI更适合作为第二阶段模型适配层，而不是主Harness | C-009及其Agent工具重试行为；当前项目已使用Pydantic 2 | medium | Migration |
| C-017 | OPEN | 自定义LLM endpoint能否无损兼容LangChain ChatOpenAI或Pydantic AI Responses流 | 尚未运行兼容性spike | low | Open Questions |
| C-018 | OPEN | 新图能否在代表性请求P95内60秒交付 | 需要固定评测集和真实provider实验 | low | Acceptance |
