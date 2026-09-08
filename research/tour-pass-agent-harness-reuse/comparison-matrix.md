# Comparison Matrix

## Decision

**首选：LangGraph 1.2.x Graph API。**

使用范围：工作流状态、条件分支、批量并行、节点重试/错误路由、流式事件和可选PostgreSQL检查点。

**不要使用：LangGraph预构建ReAct Agent。** 否则只会把当前循环换一个实现。

**第二阶段候选：Pydantic AI 2.40的模型/provider层。** 只有在自定义Responses endpoint兼容性测试通过后，再考虑替换 `trip_agent/llm.py`；首轮迁移先保留当前LLM adapter，避免同时改变编排和协议。

## Framework Comparison

| 候选 | 主抽象 | 确定性工作流 | 持久/恢复 | 自定义模型适配 | 与当前项目贴合度 | 主要风险 | 决策 |
|---|---|---|---|---|---|---|---|
| LangGraph 1.2.11 | 状态图、节点、边、superstep | 强；条件边、`Send`、fan-out/fan-in、显式循环 | 强；内存及Postgres等checkpointer、thread/checkpoint历史 | 中；可保留当前adapter，也可接LangChain模型 | **最高**；正面解决手写循环和状态机 | 学习成本；state schema与现有DB可能重复 | **采用Graph API** |
| Pydantic AI 2.40 | 类型化Agent、工具、输出；另有Pydantic Graph | 中到强；Graph可表达，但Agent默认仍是模型循环 | 中；耐久执行主要通过Temporal、DBOS、Prefect等集成 | **强**；Responses、AsyncOpenAI、base_url、模型profile | 高；现有项目已用Pydantic 2 | 若直接用Agent仍可能重复12轮；引入外部耐久引擎过重 | **作为模型层候选，不做主Harness** |
| OpenAI Agents SDK 0.22 | Agent、Runner、Tools、Handoffs | 弱到中；核心Runner是模型循环 | 中；sessions内建，长任务依赖Dapr/Temporal/DBOS等 | 强于OpenAI；兼容模型可走provider/AnyLLM | 中；可删除部分tool/trace样板 | 官方循环就是“工具后再次调用LLM”；不能解决当前根因 | **不采用为主Harness** |
| Google ADK 2.8 | Agent + Workflow/Graph | 强；顺序、并行、循环按预定义逻辑 | 强；runtime/session/event生态完整 | 中；模型无关但Gemini最顺，其他模型常经LiteLLM | 中 | 2.0有明确breaking changes；依赖面大；Google生态偏重 | **暂不采用** |
| Microsoft Agent Framework | Agent + graph workflow | 强，覆盖checkpoint、workflow、middleware | 强 | 中到强 | 中 | 框架面广、迁移和概念成本高；本次未做endpoint实测 | **保留备选** |
| CrewAI Flows | Crew/Agent/Flow | 中；Flow支持事件和状态 | 中 | 中 | 低 | 多Agent角色和委派不是本问题；容易增加模型调用 | **排除** |
| 普通async Python流水线 | 函数、数据类、队列 | 强且最直白 | 弱到中；需要自己做恢复和事件 | 保留现状 | 中到高 | 会继续自建检查点、分支、SSE映射和恢复 | 仅适合进一步缩小产品范围 |

## System-Level Comparison

| 维度 | LangGraph | Pydantic AI | OpenAI Agents SDK | Google ADK |
|---|---|---|---|---|
| 状态模型 | 用户定义TypedDict/Pydantic state，节点增量更新 | 类型化deps/messages/output；Graph另有state | RunState、消息、session | Session/Event/Workflow state |
| 更新模型 | reducers与superstep；条件边控制下一节点 | Agent轮次或Graph节点推进 | Runner循环追加items | 预定义workflow或graph推进 |
| 工具控制 | 可完全由节点代码控制，也可用ToolNode | Agent通常由模型选工具；普通函数/Graph可确定性控制 | 模型决定工具调用 | Workflow可确定性编排，LLM Agent可选工具 |
| 并行 | 原生fan-out/fan-in与`Send` | Python并发或耐久引擎；Agent支持并行工具 | 同轮函数工具并发可配置 | ParallelAgent/graph fan-out |
| 失败隔离 | 节点重试、错误处理、条件路由、checkpoint | 每工具/输出重试；其他异常传播；耐久需集成 | max_turns、tool/model错误处理 | workflow重试和事件处理 |
| 流式交付 | messages/updates/custom/debug等模式 | event stream和UI协议 | run streamed events | event stream |
| 运维成本 | 新增Python包；Postgres saver可选 | 核心较轻；耐久引擎会增大运维 | 核心较轻；耐久另接引擎 | 依赖和生态面更大 |
| 框架耦合 | 图state/edge/checkpoint API | Agent/model/message API | OpenAI风格Agent/Runner | ADK Runtime/Session/Agent生态 |

## Why LangGraph Wins Here

1. Tour Pass的问题是**控制流错误**，不是缺少更多Agent能力。
2. LangGraph允许所有Provider调用留在普通Python节点中，不要求模型看见或选择这些工具。
3. 现有SSE可以映射graph streaming，不必让用户等待终态。
4. `AsyncPostgresSaver`与现有PostgreSQL方向一致；本地可先用内存/SQLite级测试，生产再启用Postgres。
5. 迁移可以只替换 `trip_agent/loop.py`，暂时保留Provider、validator、schema、store和当前LLM适配器。

## Recommended Graph

```text
START
  -> normalize_request
  -> draft_skeleton_llm             # 模型调用1，小schema
  -> resolve_places                 # 程序批量查POI
  -> [fetch_routes || fetch_weather]# 并行程序节点
  -> build_timeline                 # 程序排程、午餐、缓冲
  -> normalize_entities             # place_id是身份，名称只是展示
  -> validate
       hard semantic issue -> targeted_patch_llm  # 最多模型调用2
       auto-fixable issue  -> apply_repairs
       warnings only       -> finalize
  -> finalize
  -> persist
  -> END
```

### 强制预算

- `draft_skeleton_llm`: 恰好1次；
- `targeted_patch_llm`: 0或1次；只返回JSON Patch/局部字段，不返回整份计划；
- Provider: 按唯一POI和必要跨区边去重，默认上限20；
- hard validation: 一次主验证，一次修复后验证；
- 任何未知开放时间、临时票务、普通市区路线缺证据：warning，不阻断交付；
- 任何预算耗尽：交付已形成的降级计划，并明确标注未核验项，不返回 `plan=null`。

## Migration Boundary

保留：

- `TripRequest` / `PlanningContext` / `ItineraryPlan` Pydantic模型；
- AMap、weather、cache和store；
- 登录、额度、SSE API、分享、版本和PDF；
- Validator中真正的用户硬约束。

替换或删除：

- `TripAgent.run`中的24步通用Tool Calling循环；
- `submit_itinerary`终端工具；
- 把整份candidate与report再次送给模型的修复循环；
- 模型自主决定逐条路线查询；
- `allowed_actions`只有字符串而没有处理器的协议。

新增：

- `TripPlanningState`；
- 明确图节点和条件边；
- `RepairRegistry[code -> deterministic handler]`；
- canonical entity key（优先Provider `place_id`）；
- hard/warning/auto-fix三级结果；
- 小型 `ItinerarySkeleton` 和 `PlanPatch` 输出类型。
