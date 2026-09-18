# Open Questions

| ID | Question | Why It Matters | Missing Evidence | Next Check |
|---|---|---|---|---|
| OQ-001 | Multi-Agent AI Travel Advisor 当前 commit 是否真的按 README 以 2–3 次 AI 调用完成 4 组 API 并行？ | 它是最接近 Tour Pass 的公开架构参照 | 本轮 GitHub API 限流，只有 README/tree | 获取源码快照，运行无 key 的 mock contract，检查 `asyncio.gather`、失败降级和 agent 调用次数 |
| OQ-002 | Tour Pass 与 OTP/OSRM/高德路线 Provider 的组合，哪个在目标中国城市的路线覆盖和延迟更好？ | 决定是否值得引入独立路由内核 | 没有同模型、同城市、同请求集的路线基准 | 固定 20 个城市/跨区路线，比较成功率、P95、端点一致性和缓存命中 |
| OQ-003 | 证据标签和完整度报告是否改变用户选择或信任？ | 这是产品优势而非单纯工程特性 | 没有用户实验 | 做 A/B：普通行程 vs 带 evidence/status/risk UI，测修改率、接受率和事实纠错率 |
| OQ-004 | Tour Pass 的 warning 降级是否比整单失败更有用？ | 决定预算耗尽时的产品策略 | 目前主要是代码与已有评测记录 | 注入 POI/route/weather 失败，盲评“继续使用计划”与“重新规划”偏好 |
| OQ-005 | 高德、天气和模型调用的成本能否按用户、城市和运行归因？ | 证据化链路可能显著增加运营成本 | 现有日志有耗时/token，但缺统一 cost ledger | 为 Provider response 与模型 usage 增加价格版本和 run-level cost 汇总 |
| OQ-006 | Tour Pass 的上下文记忆、版本和共享快照是否比 Wanderlust/Firestore 文档更适合多人共同修改？ | 决定协作功能的下一步 | 尚未做并发编辑和冲突策略研究 | 定义 itinerary item/version/participant 数据模型，做双人并发编辑与回滚实验 |
| OQ-007 | JourneyJolt 的 Places/route 封装是否由未抓取后端真正接入主计划？ | 避免低估竞品实现 | 公开快照中的生成路径没有引用这些函数 | 获取完整部署/后端仓库或运行网络请求，确认最终 UI 的实体来源 |
| OQ-008 | 公开项目的默认部署是否会带来明显安全问题（前端 key、默认数据库凭据、宽权限）？ | 影响哪些模式可借鉴 | 目前仅做静态扫描 | 对候选仓库做 secret/config/permission review；仅记录可复核的配置风险，不复制凭据 |
