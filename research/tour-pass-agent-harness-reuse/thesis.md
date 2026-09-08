# Thesis

## Central Thesis

Tour Pass应当复用 **LangGraph 1.2.x Graph API作为工作流内核**，但不应复用其预构建ReAct Agent：把当前开放式工具循环改成显式的“骨架规划→批量证据→确定性排程→分级校验→局部修复→交付”状态图，才能同时减少模型轮次并保留现有证据、存储和产品能力。

## Common Misreading

“换成成熟Agent SDK就会自动从12次模型调用降到1次”是不完整的理解。OpenAI Agents SDK、Pydantic AI `Agent`及多数预构建Agent默认仍会在工具结果后再次调用模型；如果继续让模型决定查询、提交和修复，框架只会替换循环实现，不会改变复杂度。

## Supporting Evidence

1. `trip_agent/loop.py`把工具选择、提交时机和校验修复都置于最多24轮的模型循环；广州实测用了12轮、48次Provider和4次整份提交，最终没有行程。
2. `trip_agent/validation.py`返回修复动作，但除路线时间轴外Runtime没有动作执行器；锚点身份错误和一个零时长活动最终导致整份计划拒绝。
3. LangGraph官方Graph API提供显式状态、条件边、并行fan-out/fan-in、`Send`、节点错误处理、streaming和PostgreSQL checkpointer，正好覆盖当前手写Harness重复实现的通用编排能力。
4. Pydantic AI官方provider对Responses API、自定义`AsyncOpenAI`、`base_url`和结构化输出支持较强，适合作为后续模型适配层候选，但其默认Agent工具重试仍然会回到模型。

## Counterargument

Tour Pass的目标流程只有约七个固定阶段，直接写普通异步Python流水线可能比引入LangGraph更简单，也避免框架状态语义和数据库检查点。这个反论点在“不需要中断恢复、不需要分支、不会继续扩展工作流”的条件下成立。

采用LangGraph的理由不是“Agent项目必须用框架”，而是现有产品已经有SSE、会话、版本、重放、分支校验、并行外部调用和未来追问恢复需求；这些横切能力已超过一条简单函数链。如果首个迁移切片不能明显删除现有loop和事件样板，应该停止迁移而不是双轨叠加。

## Conditions

论点成立需要：

- 不使用 `create_react_agent` 或等价预构建循环；
- 模型调用上限在图结构中固定，而不是仅配置 `max_steps`；
- Provider查询由程序依据骨架批量生成，不由模型逐轮探索；
- 验证分为 hard failure、advisory warning、auto repair；
- LangGraph state与现有Trip版本存储明确单一真相源；
- 迁移采用单条广州基准影子验证后再切流。

论点在以下条件下失效：

- 产品决定退化成一次纯文本生成，不再保存结构化地图和证据；此时普通两段Python函数即可；
- 自定义模型endpoint与选定模型适配器不兼容；
- 引入图后仍把整个计划作为每个节点的大型消息反复发送。

## Unproven

- 尚未证明LangGraph迁移后一定达到60秒；这取决于模型首Token和总生成时延。
- 尚未证明Pydantic AI能无损解析当前自定义Responses SSE事件；需要录制兼容性测试。
- 尚未证明所有旅行请求可两次模型调用完成；复杂多城市、多人约束可能需要显式升级路径。
- 尚未量化LangGraph检查点对现有数据库和SSE实现能删除多少代码。
