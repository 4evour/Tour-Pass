# Evidence Map

## Source State

研究固定在 Tour Pass commit `ca54eeb14177024f9f9e7479e371399b458c7b23`；外部项目 commit、版本和访问日期见 `source-state.md`。

## README Reuse Map

| 内容 | 分类 | 处理 |
|---|---|---|
| 24 步、48 次 Provider、4 次提交预算 | reuse | 与源码和真实运行记录相符，用于描述当前循环边界 |
| 原生 Tool Calling 选择地点、路线和天气 | adapt | 说明设计意图，但结合源码指出控制权仍交给模型 |
| “运行时负责并行执行独立工具” | verify | `asyncio.gather` 成立，但 AMap Provider 全局锁使网络请求串行进入临界区 |
| “失败后确定性修复再交回模型” | adapt | 目前确定性修复只覆盖路线时间轴，其他 allowed actions 没有执行器 |
| “可信、完整、可执行”类价值判断 | exclude | 单次广州真实链路失败，不足以证明整体质量 |

## Official Claims

- LangGraph将自己定位为低层、可定制、支持确定性与 Agent 工作流组合的编排框架，提供持久执行、流式、检查点和 human-in-the-loop。
- Pydantic AI提供类型化 Agent、工具和结构化输出；其 OpenAI provider 可接收自定义 `AsyncOpenAI` 客户端和 `base_url`，并原生提供 Responses 模型。
- OpenAI Agents SDK 的 `Runner` 明确定义为“LLM → 输出 → 工具/交接 → 再调用LLM”的循环，直到最终输出或 `max_turns`。
- Google ADK 的 workflow agents 按预定义逻辑执行顺序、并行或循环，不让模型决定编排；其 2.x 同时引入图工作流。
- 上述均是项目官方声明，不独立证明 Tour Pass 迁移后性能或质量。

## Architecture

### Current Tour Pass

```text
用户输入
  -> 构造 PlanningContext
  -> 通用模型循环（最多24轮）
  -> 模型自由选择 search/detail/route/weather
  -> 模型提交完整大 JSON
  -> normalize + 少量确定性时间轴修复
  -> Hard Validator
  -> 失败报告重新交给同一模型
  -> 最多四次整份重提
  -> 通过才保存/交付，否则返回 null
```

### Recommended Boundary

```text
用户输入
  -> request normalization
  -> 一次小型 LLM 骨架规划
  -> 程序批量解析 POI
  -> 程序按区域生成必要路线矩阵
  -> 程序排时间轴/插餐饮/统一锚点
  -> hard + advisory 两级验证
  -> 程序局部修复
  -> 可选一次小型 LLM 语义补丁
  -> 保存并流式交付
```

LangGraph只承担状态、节点、条件边、并行、检查点和事件流；旅行领域规则仍保留在本地节点中。

## Code Evidence

### EV-001 — 当前模型拥有循环控制权
- Path: `trip_agent/loop.py`
- Symbol: `TripAgent.run`
- Observation: `for step in range(self.max_steps)` 内每轮调用 `llm.ainvoke`，并强制 `tool_choice="required"`；没有工具调用时又提示模型必须选择工具。
- Meaning: 模型不只是生成计划，还决定查什么、何时提交、失败后如何修复；轮数和上下文增长由模型行为驱动。
- Alternative explanation: 有界预算避免无限循环，但不能保证预算内产生价值。
- Confidence: high

### EV-002 — 验证失败导致整份候选再次交给模型
- Path: `trip_agent/loop.py`
- Symbol: `TripAgent.run` submit branch
- Observation: 校验失败后把 `candidate_plan` 与整个 `validation_report` 写入 `repair_context`；达到提交上限后返回“停止交付”。
- Meaning: 局部错误会触发整份结构化计划重写，且最终可能无用户可见计划。
- Alternative explanation: 大模型可能在一次重写中修复多项语义错误，但广州实测没有实现。
- Confidence: high

### EV-003 — allowed_actions 目前只是提示，不是动作协议
- Path: `trip_agent/loop.py`, `trip_agent/validation.py`
- Symbol: `repair_context`, `_issue`
- Observation: Validator返回 `allowed_actions`，Runtime未按 action dispatch 到确定性处理器，只把报告反馈给模型；仅 `_repair_route_timeline` 被直接执行。
- Meaning: 系统有“修复建议”的数据结构，但没有“修复执行器”。
- Alternative explanation: 模型可把 action 当指导语；这不构成确定性执行。
- Confidence: high

### EV-004 — 工具并发被 Provider 全局锁部分抵消
- Path: `trip_agent/loop.py`, `trip_agent/providers/amap.py`
- Symbol: `asyncio.gather`, `AmapProvider._request`
- Observation: Runtime使用 `asyncio.gather` 执行同轮外部调用，但 AMap `_request` 在缓存未命中后把限流等待和 HTTP GET 全部置于同一 `asyncio.Lock`。
- Meaning: 对高德的多个独立请求不会形成真实 HTTP 并发；Provider elapsed 可与墙钟重叠，但吞吐受单锁限制。
- Alternative explanation: 该锁可能是为了保护配额和限流；问题是粒度，而不是需要完全删除限流。
- Confidence: high

### EV-005 — 真实失败以模型时间为主
- Path: `artifacts/.../runs/01-guangzhou-short-prompt/summary.json`
- Observation: 734072ms 总耗时；12次 planner 调用；694017ms LLM耗时；48次 Provider；4次提交；最终无计划。
- Meaning: 主要收益来自减少模型轮次和整份重写，不是仅更换异步库。
- Alternative explanation: 这是单次运行，不代表分布总体。
- Confidence: high

### EV-006 — LangGraph提供所需的确定性结构
- Source: https://docs.langchain.com/oss/python/langgraph/use-graph-api
- Observation: Graph API有显式 state schema、reducers、条件边、`Send` map-reduce、fan-out/fan-in、`Command` 和节点错误处理；平行 superstep 配合 checkpointer 可在恢复时避免重做已成功节点。
- Meaning: Tour Pass可把“骨架、POI、路线、排程、验证、局部修复”建成显式节点，而不是继续维护手写通用 ReAct 循环。
- Alternative explanation: 框架不会自动提供旅行领域排程器或正确的硬/软规则。
- Confidence: high

### EV-007 — LangGraph可直接对接现有PostgreSQL方向
- Source: https://docs.langchain.com/oss/python/langgraph/add-memory
- Observation: 官方给出 `AsyncPostgresSaver`、`thread_id`、状态历史和检查点恢复；生产使用数据库-backed checkpointer。
- Meaning: 可复用检查点/恢复，而无需在 `planning.jsonl`、运行事件和数据库之间再造一套工作流状态机。
- Alternative explanation: 与现有 session/version 表的归属仍需设计，不能同时让两套存储成为真相源。
- Confidence: high

### EV-008 — Pydantic AI最适合做模型适配层候选
- Source: https://ai.pydantic.dev/models/openai/
- Observation: `OpenAIResponsesModel`支持 Responses API；`OpenAIProvider`接受自定义 `AsyncOpenAI` 与 `base_url`；支持结构化输出、工具参数校验和显式重试预算。
- Meaning: 若当前自定义 endpoint 兼容性验证通过，可减少 `trip_agent/llm.py` 中流式、响应解析和工具调用适配代码。
- Alternative explanation: 第三方“OpenAI兼容”实现可能缺字段或流事件，必须做录制回放兼容测试。
- Confidence: high

## Engineering Evidence

- 当前依赖已使用 Pydantic 2、FastAPI、SQLAlchemy、PostgreSQL，LangGraph 1.2.x和Pydantic AI 2.40均满足Python/Pydantic方向。
- LangGraph PyPI元数据标注 Production/Stable，官方提供Postgres checkpointer；这证明公开稳定性定位和可用接口，不证明本项目迁移零风险。
- Pydantic AI PyPI元数据标注 Production/Stable；OpenAI Agents SDK当前PyPI主版本仍为0.x；Google ADK 2.0官方明确包含与1.x不兼容的breaking changes。
- LangGraph、Pydantic AI、OpenAI Agents SDK为MIT；Google ADK为Apache-2.0，均允许项目内复用，仍需保留许可要求。

## Limitations

- 任何通用框架都不会自动解决“北京路住宿区”和“北京路步行街”实体身份不一致。
- LangGraph不自带旅行规划器；领域调度、证据分级和降级策略仍需项目实现。
- 一次广州运行只能证明当前链路存在严重失败案例，不能估计全量成功率。
- 尚未用项目自定义 LLM endpoint 真实运行 LangGraph `ChatOpenAI` 或 Pydantic AI provider。
- LangGraph检查点若与现有版本表重复存储，可能增加而不是减少复杂度。

## Contradictions

- README称运行时并行执行独立工具；代码层确实 `gather`，但同一 AMap provider 的 HTTP 请求被全局锁串行化。两者只有在“任务并发、Provider串行限流”的限定下同时成立。
- 当前系统强调硬校验提高可信度；广州案例中五条末轮路线失败属于锚点证据身份关联，证明严格度没有转化为同等准确的错误分类。
- 换成 OpenAI Agents SDK 或 Pydantic AI `Agent` 默认循环可减少样板代码，但仍保留“工具调用后再调用模型”的核心循环，不能自动解决12轮问题。

## Open Questions

见 `open-questions.md`。最高优先级是自定义 Responses endpoint 兼容性、LangGraph检查点与现有存储的单一真相源、以及新图在固定评测集上的延迟/交付率。
