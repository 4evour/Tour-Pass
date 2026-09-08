# Open Questions

| ID | Question | Why It Matters | Missing Evidence | Next Check |
|---|---|---|---|---|
| OQ-001 | 当前自定义Responses endpoint是否完整兼容Pydantic AI `OpenAIResponsesModel`的流式文本、工具调用、usage和错误事件？ | 决定能否删除自写 `trip_agent/llm.py` | 对真实endpoint的协议测试 | 用现有录制输入运行20个固定case，比较文本、tool calls、usage和终止状态 |
| OQ-002 | LangGraph checkpoint还是现有Trip/Run表应成为工作流状态真相源？ | 双写会制造恢复冲突和更多维护成本 | 数据所有权设计与崩溃注入实验 | 先定义checkpoint只存运行中state、Trip表只存已交付版本；模拟节点间进程退出 |
| OQ-003 | 哪些Validator code属于hard、warning、auto-fix？ | 决定交付率和可信边界 | 基于产品风险的分类表 | 对全部现有code逐项分类；每个hard code写出会真实伤害用户的反例 |
| OQ-004 | Provider上限20是否覆盖单城3日游？ | 防止新图仍因证据扩张而失控 | 多城市固定基准分布 | 用广州、长沙、青岛、重庆及复杂约束case统计唯一POI与必要边 |
| OQ-005 | 是否真的需要耐久恢复？ | 若所有请求目标低于60秒，完整checkpoint可能不是首要收益 | 生产请求中断、刷新、重试数据 | 首个迁移切片先用内存checkpointer；证明有恢复需求再启用PostgresSaver |
| OQ-006 | 单次骨架模型能否稳定返回可排程的区域和POI列表？ | 决定模型调用能否固定到1+1 | 新 `ItinerarySkeleton` schema和评测 | 用录制模型跑同一输入多次，测城市/天数/必去点/区域一致性，不先接Provider |
| OQ-007 | 现有SSE事件能否直接映射LangGraph stream modes而不改变前端协议？ | 决定迁移是否局部 | 事件字段映射和前端契约测试 | 建立旧事件→graph event映射表，跑一个影子endpoint |
