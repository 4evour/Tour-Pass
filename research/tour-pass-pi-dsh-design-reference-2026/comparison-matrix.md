# Comparison Matrix

| Dimension | Pi Coding Agent | DeepSeek Harness | Tour Pass 取舍 |
|---|---|---|---|
| 主抽象 | 一个可扩展的 agent session；薄 loop 驱动当前分支 | 插件化宿主中的 event-sourced session、agent、tool 与 projection 服务 | 核心对象应是 `TripSession/TripMission`，不是一份生成结果或一组角色 |
| Agent loop | 直接的内外循环；tool call 后继续，支持 steering、follow-up、next-turn hook | turn/step phase machine；每个请求由 session log 重建，inbox 可持久化 steer/follow-up | 首版采用 Pi 的简单 loop API，但把 DSH 的 turn/step/stop reason 写入事件 |
| 会话模型 | JSONL tree，`id/parentId` 形成分支；当前 leaf 决定上下文 | 严格 append-only typed events；surface 决定模型历史，header 单独保存 | 计划采用 append-only events + `plan_version/patch`；无需复制通用消息树 UI |
| 上下文 | 从活动路径重建；`transformContext`、custom message、branch summary 和 compaction 可插入 | system prompt sections + runtime context projection + surface-derived messages；每轮从日志派生 | 建 `WorkingContext` 投影，只放当前目标、硬约束、活跃计划、相关事实和待处理审批 |
| 压缩 | compaction entry 保存摘要、保留尾部和覆盖位置；最新压缩控制上下文 | compaction 是事务化 surface replacement；检查选区稳定、摘要确实更小，原事件仍在日志 | 借 DSH 的“不删事实、替换投影”和并发稳定性检查；实现规模保持 Pi 式小巧 |
| 工具注册 | built-in/custom/extension tools；运行时可注册并设置 active tools | scoped registry；注册、restrict、guard、pre/post、approval、并发调度、输出 schema | 做固定领域 registry + session scope；先不做通用插件加载器 |
| 权限 | `beforeToolCall`/extension `tool_call` 可 block；无 UI 时示例默认拒绝危险动作 | pre-execute 可 allow/deny/ask，缺 approval service 默认拒绝；guard 单调收紧 | 查询默认允许；费用/通知/日历/预约按风险审批；无审批通道 fail closed |
| 工具结果 | 结果作为 toolResult message 回注，支持 partial update 和 after hook | 规范 JSON value 与模型可见 content 分离；最终结果与 additional context 持久化 | 工具返回 `canonical_value + model_summary + provenance`，避免把长原始响应全塞上下文 |
| 持久化 | 本地 JSONL append；简单、可观察、适合单用户工具 | JSONL/SQLite 后端、异步 write-behind、per-session serialization、repair/resume | 首版 SQLite/Postgres 单实现；必须有 append 原子性、版本检查、flush/resume 测试 |
| 派生状态 | 主要在 SessionManager/AgentSession 内重建 | projection registry 支持版本化 checkpoint、tail replay、client view | 借 projection 思路实现少数领域 read models，不建通用注册平台 |
| 子 Agent | 以 extension/example 为主，可按独立 prompt 启动 | provider/tool 化；子会话独立，可前台、后台或 continuable，并有深度/工具过滤 | 常规规划不启用；仅复杂证据搜集或跨城市并行使用，子任务必须有独立事件与预算 |
| 分支与修改 | 消息树支持探索不同路径和 branch summary | session fork 和 surface replacement 侧重可恢复事实流 | 用 `plan_proposed -> plan_patched -> plan_accepted`，比聊天树更符合旅游领域 |
| 记忆 | session 内持久历史；skills/resources 按需进入上下文 | session log + projections + filesystem skills；长期偏好仍需领域设计 | 区分 session facts、用户长期偏好和 eval 样例，禁止把完整聊天当 memory |
| 故障恢复 | 会话文件可打开/分支；loop 有 retry、abort、auto-compaction | 显式 resume、persistence coordinator、torn-tail repair、生命周期 ownership | 先覆盖进程重启、工具超时、审批暂停、重复回调四类恢复用例 |
| 耦合与成本 | 内核小，容易嵌入；复杂治理需自行补齐 | 能力完整但包和生命周期很多，学习与运维成本高 | 架构形态 70% 参考 Pi，数据/恢复契约 30% 参考 DSH |
| 各自更强的条件 | 单产品、小团队、要快速形成可靠 tool loop | 多产品、多前端、多存储、动态插件和复杂生命周期 | Tour Pass 当前明显更接近 Pi 的适用条件 |

## Decision

不是“选择 Pi 或 DSH”，而是分层取舍：

| Layer | Recommendation | Reason |
|---|---|---|
| Loop/API | Pi-like | 简单、可读、容易评估，不把领域问题埋进框架生命周期 |
| Durable truth | DSH-like | 事件日志让恢复、审计、编辑反馈和 projection 有共同事实源 |
| Context | Hybrid | Pi 的显式 transform + DSH 的日志投影；上下文是派生物，不是数据库 |
| Tools | DSH contracts, small registry | typed output、scope、policy、approval 值得借；动态插件平台暂不需要 |
| Plan evolution | Tour Pass native | 用 plan version/patch/validation，不复制 coding conversation branch |
| UI | Minimal | trace/diff/approve 足以验证 runtime，复杂编辑器不应成为前置条件 |

