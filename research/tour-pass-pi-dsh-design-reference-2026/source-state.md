# Source State

- Repository: Tour Pass
- Local path: `D:\Tour Pass`
- Remote URL: 当前工作区未查询远程地址；本次研究不依赖远程仓库状态。
- Branch/tag: `codex/trip-workflow-updates`
- Commit: `f91bb5861b7d66cc072020fe1ae48fc169e72c3b`
- Research date: 2026-08-27
- Primary language: C++ 17、Python、TypeScript
- Requested audience: Tour Pass 项目维护者
- Research question: Pi Coding Agent 与 DeepSeek Harness 的 agent loop、会话、上下文、工具、压缩、权限和子 Agent 设计中，哪些值得 Tour Pass 借鉴？
- Explicit non-goals: 不评价通用 coding benchmark，不重写 Tour Pass，不设计复杂编辑器，不把角色数量当作 Agent 能力。
- Official docs inspected: [Pi 官网](https://pi.dev)、[Pi 官方仓库](https://github.com/earendil-works/pi)、[DeepSeek Harness 官方仓库](https://github.com/deepseek-ai/deepseek-harness)（访问日期均为 2026-08-27）。
- Competitors inspected: Pi Coding Agent、DeepSeek Harness（DSH）。

## Pinned External Sources

| Project | Branch | Commit | Commit time | Local checkout |
|---|---|---|---|---|
| Pi Coding Agent | `main` | `e86823096c5bad39e1ca282ec24bc5eb9bec745b` | 2026-08-26T17:40:36+02:00 | `C:\Users\Lenovo\AppData\Local\Temp\tourpass-agent-reference-20260827\pi` |
| DeepSeek Harness | `master` | `b150a551b8d465e31e418e1b2eaf5e79bbb7d28e` | 2026-08-21T20:03:37+08:00 | `C:\Users\Lenovo\AppData\Local\Temp\tourpass-agent-reference-20260827\deepseek-harness` |

## Scope

重点检查：

- 从用户输入到 LLM、工具调用、结果回注和停止条件的运行链路；
- 会话事件如何持久化、恢复、分支和投影为模型上下文；
- 上下文压缩是否保留原始事实与可重建性；
- 工具如何注册、裁剪、并发、拦截和审批；
- 子 Agent 是否拥有独立会话，以及父子上下文如何隔离；
- 这些机制映射到旅游规划后是否产生可测量的产品价值。

未安装两个外部仓库的依赖，因此没有把其测试源码的存在写成“本地测试已通过”。结论以 pinned commit 的源码、测试契约和官方文档交叉支持。
