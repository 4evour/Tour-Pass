# Open Questions

| ID | Question | Why It Matters | Missing Evidence | Next Check |
|---|---|---|---|---|
| OQ-001 | TripSession 首版应落在 SQLite、现有业务数据库还是独立 event store？ | 决定事务、恢复、部署和 C++/Python 边界 | 当前部署数据库与写入吞吐约束 | 盘点存储层与生产拓扑，做一次重启恢复 spike |
| OQ-002 | 哪些事件是永久事实，哪些只保留为短期 trace？ | 影响隐私、成本、删除权和上下文质量 | 数据分类与保留政策 | 为每种 `TripEvent` 标注 retention、PII 和可删除性 |
| OQ-003 | plan patch 的最小 schema 是什么？ | patch 是验证、审批、diff UI 和编辑反馈的共同合同 | 现有 editor command 与后端 itinerary schema 的完整映射 | 用 20 个真实编辑操作做 schema 反推 |
| OQ-004 | 首批 6-8 个工具如何分 read/compute/write/transaction？ | 决定审批、并发、重试和幂等策略 | 外部供应商能力与可靠性 | 先为现有 C++ solver、route、weather、RAG 建 tool contract 表 |
| OQ-005 | 哪些上下文必须常驻，哪些按需检索？ | 决定 token、缓存和工具选择正确率 | 真实长会话 trace | 建 context breakdown telemetry 并比较 eager/JIT 两组 eval |
| OQ-006 | 什么条件才值得创建子 Agent？ | 防止再次用角色数量掩盖单 loop 能力 | 跨城市/跨来源并行任务数据 | 只在独立上下文、并行收益和可合并输出三项都满足时实验 |
| OQ-007 | 如何验证跨重启、审批暂停和重复回调的一致性？ | 这是持续 Agent 与一次性 API 的关键差异 | failure-injection suite | 加进程 kill、timeout、duplicate delivery、stale patch 四类用例 |
| OQ-008 | 哪些 editor diff 能晋升为长期偏好？ | 错误记忆会持续污染推荐 | 用户确认与多次行为数据 | 先生成 memory candidate，要求重复证据或用户确认后再写入 |
| OQ-009 | codebase-memory 图谱何时刷新？ | 项目规则要求代码结构变化后重新索引 | 当前会话没有对应 MCP 工具；本次仅文档变更 | 实施 runtime 代码后用 `moderate` 索引并持久化 |

