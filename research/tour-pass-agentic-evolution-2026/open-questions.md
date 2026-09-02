# Open Questions

| ID | Question | Why It Matters | Missing Evidence | Next Check |
|---|---|---|---|---|
| OQ-001 | 目标是作品集技术深度，还是可持续使用的旅行产品？ | 决定优先做 trace/eval 还是行中服务和供应商集成。 | 产品目标和用户访谈 | 选一个北极星指标并写 10 个目标用户任务。 |
| OQ-002 | 用户生成后最常做哪些编辑？ | 编辑 diff 可能是最强偏好信号。 | 线上匿名事件数据 | 记录 remove/reorder/move/time-change 的聚合统计，不记录敏感文本。 |
| OQ-003 | 同一用户是否重复规划多个城市或多次出行？ | 决定长期记忆是否有真实价值。 | 用户回访和登录数据 | 测量 30/90 天重复规划率。 |
| OQ-004 | 哪些实时事件最常使计划失效？ | 决定先接天气、闭馆、票务还是交通延误。 | 失败反馈和供应商可用性 | 对 20 次真实旅行做事件日志和事后访谈。 |
| OQ-005 | 可靠票务/酒店/营业状态 API 是否可获得？ | 没有可信工具，自治只会放大幻觉。 | 合同、许可、成本、SLA | 对两个候选供应商做 adapter spike 和数据新鲜度审计。 |
| OQ-006 | 哪些动作允许自动执行？ | 日历写入、预订和取消需要不同审批。 | 权限模型和用户研究 | 建 read/propose/write 三层工具权限矩阵。 |
| OQ-007 | 如何统一 `session_id`、LangGraph `thread_id`、用户和已保存 trip？ | 这是恢复、审计和反馈归因的基础。 | 数据模型决策 | 设计 `TripSession`, `PlanVersion`, `TripEvent`, `Approval` schema。 |
| OQ-008 | 当前模型的工具选择和 patch 能力如何？ | 决定自治边界，而不是凭框架功能猜测。 | Tour Pass task eval | 建 50 个任务，比较 fixed workflow、orchestrator+tools、fully autonomous 三种基线。 |
| OQ-009 | Reviewer 失败在真实数据上有多常见，返修是否改善？ | 决定保留 LLM reviewer 还是更多依赖 deterministic validators。 | trace 和 before/after 指标 | 记录每轮失败码、patch、最终约束得分和成本。 |
| OQ-010 | 如何处理相互冲突或过期的用户记忆？ | 错误长期记忆会持续污染计划。 | 记忆治理策略 | 每条记忆保存 source、observed_at、confidence、expires_at，并允许用户编辑/删除。 |
| OQ-011 | MCP adapter 是否优于普通 Python provider interface？ | 只有在多供应商或跨 runtime 时才可能回本。 | 第二个真实 provider 和复用需求 | 先实现两个同合同 adapter，再比较 MCP 的维护收益。 |
| OQ-012 | `codebase-memory-mcp` 为什么未暴露？ | 项目规则要求修改前用图谱检查。 | 当前 Codex/MCP 配置 | 后续任务恢复该 MCP 后补做 `search_graph`/`trace_path`，代码变更时再索引。 |
