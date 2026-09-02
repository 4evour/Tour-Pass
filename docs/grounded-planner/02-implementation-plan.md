# Grounded Planner 实施计划

> 文档状态：实施中（Phase 0～4 首条纵向链路已完成，Phase 5/发布门槛未完成）  
> 制定日期：2026-08-29  
> 适用范围：Tour Pass 规划链路转型，不包含编辑器重做

本文档把 01-architecture-and-contracts.md 中的目标架构拆成可执行阶段。每个阶段都规定文件范围、依赖、测试和退出条件；除非退出条件满足，否则不进入下一阶段。

## 0. 执行原则

1. 先建立可复现基线，再改生产链路。
2. 每个阶段只保留一条新增主路径，旧路径只用于对照、回滚或兼容。
3. LLM 输出只能产生候选和偏好，不能直接写入最终行程。
4. 新增代码必须有 typed contract、结构化日志和回归测试。
5. 代码结构变化前后都要使用 codebase-memory-mcp；工具不可用时停止结构性实现并记录阻塞。
6. 每次仓库文件修改都在根目录 CHANGELOG.md 追加日期、原因和影响。

## 1. Phase 0：恢复图谱并建立基线

### 目标

把当前仓库状态、调用链和质量问题固定下来，避免在过期图谱或主观印象上改造。

### 文件级任务

| 任务 | 文件/目录 | 说明 |
|---|---|---|
| 恢复知识图谱 MCP | Codex/MCP 配置，不提交密钥 | 注册 codebase-memory-mcp，确认项目名为 Tour-Pass |
| 重新索引 | .codebase-memory/graph.db.zst | 使用 moderate 或 full，persistence=true |
| 记录调用链 | research/ 或 docs/grounded-planner/ | 导出 /agent/plan*、/trip/chat、/api/optimize-route、前端提交入口的调用关系 |
| 建立基准样例 | tests/fixtures/grounded-planner/ | 长沙、青岛、重庆各 5～10 个固定需求，保存脱敏输入和期望硬约束 |
| 建立运行基线 | scripts/、tests/ | 分别跑 legacy、多 Agent、direct LLM（离线录制响应）并保存指标 |
| 建立语义数据审计 | scripts/、tests/fixtures/grounded-planner/ | 区分结构完整与旅游语义完整；统计核心 POI/别名召回、默认开放时间、路线方式 verified 比例、证据 TTL 和 XHS 地点匹配 |
| 补充变更记录 | CHANGELOG.md | 记录图谱刷新、基线版本和数据来源 |

### 基线需求样例

- 2～4 天、酒店区域明确或可推荐、节奏为轻松/标准/紧凑。
- 至少包含 2 个必去景点、1 个餐饮偏好和 1 个交通偏好。
- 至少 1 个存在歧义的 POI、1 个可能闭馆或需要预约的 POI。
- 至少 1 个需要跨区域移动的日期，用于检验闭环和通勤。

### 验证命令

    npm run test:multi-agent
    npm run quality:algorithm
    npm run quality:itinerary-smoke
    npm run validate:data:all

### 退出条件

- 图谱能查询目标符号、调用方和被调用方，且索引时间晚于本次开始时间。
- 三城市样例可一键重放，输入、模型响应、工具响应和最终结果均有版本号。
- 已得到 legacy 与 direct LLM 的基线报告；若无法访问外部模型，必须使用录制响应并注明限制。
- 明确当前生产默认入口及所有前端调用方。
- 已固化 2026-08-30 数据审计基线：21 城市 9,588 个 POI、5,152 个景点全部使用默认 `09:00-21:30`、49,429 条路线边中 49,397 条为 `partial` 且只有 32 条为 `ok`；后续改造必须能复现并逐项改善这些指标。
- 每个基准城市有版本化核心地点与别名清单，能区分“本地缺失”“别名未解析”“候选已召回但排序淘汰”。

## 2. Phase 1：切换产品入口，隐藏编辑器和多轮修改

### 目标

在不删除旧代码的前提下，让用户默认进入“一次提交、一次结果”的新产品边界。

### 文件级任务

| 任务 | 文件/目录 | 说明 |
|---|---|---|
| 保留弹性结构化输入 | web/index.html、api_multi_agent.py、planner/runtime.py | 只强制城市；空值采用透明默认并返回 assumptions；附加要求原文保留且可解析部分进入确定性约束 |
| 隐藏编辑器入口 | web/index.html、web/app.js | 移除默认导航和按钮；保留受控 feature flag 回滚入口 |
| 禁止默认多轮修改 | web/app.js、相关 API 调用 | 结果页只提供“整单重新规划”和“复制需求”，不提供自然语言 patch |
| 增加规划版本标识 | web/app.js、模板/样式 | 展示 planning_run_id、数据时间和风险提示，不展示内部推理 |
| 兼容旧接口 | api_multi_agent.py、src/api.cpp | 旧 /agent/plan* 和 /trip/chat 保留路由、标记 deprecated，默认不被新前端调用 |
| 前端回归 | tests/test_tour_ai_layout_markup.js 及相关 UI 测试 | 验证编辑器和多轮入口默认不可达，结构化提交仍可用 |

### 依赖

- Phase 0 已明确前端入口和旧接口依赖。
- `TOURPASS_GROUNDED_PLANNER_ENABLED` 默认开启新链路；设置为 `false` 恢复旧 `/agent/plan-structured`，远端回退标签可恢复整个改造前版本。

### 验证命令

    npm run editor:test
    npm run editor:build
    npm run verify:ui

### 退出条件

- 新用户路径只有结构化需求提交和结果页。
- 旧编辑器资源仍可构建，回滚 flag 能恢复旧入口。
- 未引入新的 API 断裂；旧接口的兼容测试仍通过。

## 3. Phase 2：新增 Python Grounded Planner 骨架

### 目标

建立单主规划器、显式上下文、typed tools、事件 trace 和统一响应，不改变 C++ 求解算法的核心实现。

### 推荐目录

    planner/
      __init__.py
      models.py              # Pydantic/TypedDict 合同
      context.py             # TripContext 与 prompt projection
      runtime.py             # 单次 PlanningRun 主循环
      prompts.py             # 版本化提示模板
      tools/
        registry.py
        places.py
        status.py
        routes.py
        weather.py
        solver.py
        validator.py
      evidence.py            # 证据、来源、TTL、缓存键
      trace.py               # 事件写入和脱敏
      repair.py              # 确定性 patch
      errors.py

### 文件级任务

| 任务 | 文件/目录 | 说明 |
|---|---|---|
| 定义模型 | planner/models.py | 实现 TripContext、PlanSkeleton、PlaceEvidence、RouteEvidence、ItineraryPlan、ValidationReport |
| 建立上下文投影 | planner/context.py | 固定系统规则、用户需求、工具摘要、校验错误；原始供应商响应不进 prompt |
| 建立模型适配器 | planner/runtime.py | 封装当前 OpenAI-compatible endpoint；模型、温度、超时和 prompt 版本配置化 |
| 注册 typed tools | planner/tools/registry.py | 工具白名单、输入校验、request-level 去重、超时、重试和 trace hook |
| 实现主循环 | planner/runtime.py | skeleton → evidence → solve → validate → repair；LLM 默认总预算 2、绝对上限 3，最多 3 次确定性修复 |
| 接入 FastAPI | api_multi_agent.py | 新增内部 /planner/plan；将 /agent/plan-structured 适配到同一实现 |
| 版本化提示 | planner/prompts.py | 每次请求记录 prompt_version，禁止运行时拼接未审查指令 |
| 增加单测 | tests/ | schema、工具调用顺序、超时、重试、失败分类和幂等性 |
| 解析弹性输入 | planner/runtime.py | 统一处理缺失、`null`、空字符串和别名；构建 ConstraintProfile 与 assumptions |

### 主循环伪代码

    budget = LlmBudget(default_total=2, absolute_total=3)
    ctx = build_trip_context(request)
    skeleton = llm.plan_skeleton(ctx, budget)
    evidence = collect_evidence(skeleton, ctx)
    candidate = solve_itinerary(ctx, skeleton, evidence)
    report = validate_itinerary(candidate, ctx, evidence)
    for _ in range(3):
        if report.hard_pass:
            break
        if not report.repairable:
            return fail_with_reasons(report)
        candidate = apply_deterministic_patch(candidate, report, evidence)
        report = validate_itinerary(candidate, ctx, evidence)
    if not report.hard_pass:
        return fail_with_reasons(report)
    return explain_fixed_result_or_template(candidate, report, budget)

### 退出条件

- 新接口能在不依赖旧多 Agent graph 的情况下完成端到端 dry-run。
- 任何未解析地点、无来源路线或未知开放状态都不能进入 ItineraryPlan。
- 每次运行都有可查询的 planning_run_id 和阶段事件。
- 旧接口适配后，响应字段保持向后兼容或明确返回迁移错误。
- 只提供城市、其余字段为空的请求仍能进入规划；响应明确列出日期、交通、预算和住宿采用的假设。
- “少走路、每天最多 N 站、预留午餐、住某区域、不去某类地点”等附加要求有契约测试，并影响 Solver/Validator，不只进入 prompt。

## 4. Phase 3：接入实体、开放状态、路线和天气证据

### 目标

把真实数据放到求解之前；解决“模型知道景点但不知道是否存在、是否开放、怎么走”的核心问题。

### 实施顺序

1. 候选召回：合并用户必去项、LLM 骨架地点以及按每日区域/主题/旅行角色扩展的工具候选；本地数据只作低延迟召回和缓存，不要求预先包含模型提到的全部地点。
2. 实体消歧：先匹配本地规范名、别名和 `source_id`；未命中、歧义、过期、必去项或分店查询再调用高德关键词与详情搜索，按城市、类别、区域和分店确定性消歧，不盲取 Top 1。
3. 开放状态：先查官方公告/官方开放时间，再查地图状态；节假日和指定日期必须复核。当前默认 `09:00-21:30` 不得作为硬证据。
4. 路线矩阵：按实际交通方式批量请求相邻候选和酒店锚点，记录距离、时长、provider、采集时间和验证状态；`partial` 边、推导公交、距离估算不得标记为 verified。
5. 天气：继续复用和风天气（QWeather）客户端作为主 provider，高德基础天气作降级；天气只影响软排序或触发确定性替换，不允许模型自行编写天气事实。
6. 缓存和降级：按实体、日期、方式、城市和 provider 生成稳定键；缓存命中仍检查 TTL，过期或缺失要显式标记。

### 文件级任务

| 任务 | 文件/目录 | 说明 |
|---|---|---|
| 外部客户端 | planner/tools/ 或现有 service client | 定义 Tour Pass provider 接口，复用现有鉴权、限流、批量 HTTP 和重试，不把 key 写入代码 |
| 高德 provider | planner/tools/places.py、routes.py 或现有客户端 | 核心查询优先复用高德 Web API；官方 MCP 作为可替换 adapter、专属地图/导航能力或受控验证，不改变 typed tool 合同 |
| 天气 provider | planner/tools/weather.py、tools/weather_api.py | 明确 QWeather 即和风天气，保留为主源；高德天气仅基础降级，不引入未确认维护责任的第三方天气 MCP |
| 证据模型 | planner/evidence.py | provider、source_url、retrieved_at、valid_until、confidence、raw_hash、verification_status |
| 数据适配 | data/、scripts/ | 本地数据改为召回/缓存/benchmark；补规范名、别名、旅行角色和语义审计，不把一次性抓取结果当永久事实 |
| 高德代理 | src/api.cpp 或现有代理层 | 统一 allowlist、QPS、超时和错误码；带 key 的 MCP URL、原始响应和凭据不得进入模型或普通 trace |
| 缓存 | 现有存储层或独立 cache adapter | 先使用已有存储能力，避免引入新基础设施 |
| 测试夹具 | tests/fixtures/grounded-planner/ | 固定实体别名、Top 1 错配、闭馆、路线 `partial`、QPS 超限、和风天气缺失及高德降级响应 |

### 失败策略

- 实体无法唯一确认：该候选淘汰；若为必去项，返回需要用户澄清或整单不可规划。不得因供应商 Top 1 有结果就视为唯一实体。
- 重要景点开放状态未知：默认阻止进入最终行程；非关键候选可降级为 warning。默认开放时间不能消除未知状态。
- 路线查询失败：不得使用直线距离替代；尝试未过期的已验证缓存，仍失败则整段标记不可验证并阻止硬通过。推导公交时间只能用于粗筛。
- 和风天气失败：降级查询高德基础天气；仍失败不阻止基础规划，但去掉“根据天气已优化”的文案，并降低软评分。

### 退出条件

- 三城市基准中所有最终地点都有唯一实体 ID；核心地点与常见别名的召回、解析错误和淘汰原因可分别统计。
- 展示的通勤时间 100% 带指定交通方式的真实路线证据；无直线距离、`partial` 未验证方式或推导公交冒充。
- 指定日期的关键开放状态有来源和时间戳；默认时间的硬证据使用率为 0。
- QWeather（和风天气）主源与高德天气降级均有录制夹具，结果明确记录实际 provider。
- 外部服务超时、QPS 超限、限流和空结果均可测试、可观测、可降级。

## 5. Phase 4：接入 C++ 求解器、硬校验和确定性修复

### 目标

让路线质量由确定性约束决定，而不是由 LLM 或 Reviewer 的主观评分决定。

### 文件级任务

| 任务 | 文件/目录 | 说明 |
|---|---|---|
| 扩展 solver 输入 | include/tourpass/、src/ | 增加实体 ID、时间窗、停留时长、酒店锚点、路线矩阵和证据状态 |
| 复用路线接口 | src/api.cpp、现有规划模块 | 将 /api/optimize-route 作为内部 typed tool，统一错误语义 |
| 实现 validator | planner/tools/validator.py 或 C++ 等价模块 | 按文档规定顺序执行硬门禁，输出稳定错误码 |
| 实现 repair | planner/repair.py | 仅允许局部 patch，记录 patch 前后 hash |
| 补回归测试 | tests/ | 必去遗漏、闭环断裂、闭馆、重叠、跨城、过度步行、时段错误 |
| 更新数据校验 | scripts/ | 确保新字段不会破坏旧城市数据和路线图 |

### 优化顺序

1. 先满足硬约束并找可行解；
2. 在可行解集合内最大化必去覆盖、兴趣匹配和区域连贯；
3. 再最小化总通勤、折返、步行和重复跨江；
4. 最后优化餐饮、天气匹配、主题完整性和多日多样性。

### 退出条件

- 硬约束失败不会被软分数掩盖。
- 确定性 patch 在三轮内收敛；无法修复时返回明确原因和缺失证据。
- C++ 旧算法测试与新 planner 集成测试同时通过。
- 新旧结果可通过同一份 ValidationReport 比较。

## 6. Phase 5：结果页、trace、健康检查和灰度

### 目标

让结果可解释、可审计、可回滚，并以小流量证明真实质量提升。

### 文件级任务

| 任务 | 文件/目录 | 说明 |
|---|---|---|
| 统一响应渲染 | web/app.js、web/index.html | 展示每日路线、真实通勤、开放/预约提示、风险和数据更新时间 |
| 运行追踪 | planner/trace.py、存储层 | 保存阶段、耗时、cache hit、provider、错误码和版本，不保存密钥/原始推理 |
| 健康检查 | src/api.cpp、api_multi_agent.py、entrypoint.sh | 增加模型、地图、天气、solver、缓存依赖的可用性检查 |
| 影子运行 | api_multi_agent.py 或网关 | 对同一请求异步跑 legacy 与 grounded，只返回 grounded 或按 flag 返回 |
| 灰度开关 | render.yaml、配置模板 | 按环境、用户或百分比切换；默认可回滚 |
| 监控告警 | scripts/、部署配置 | P95 延迟、工具错误率、硬失败率、降级率、成本和用户重试率 |

### 退出条件

- staging 可完成端到端演练，包含外部服务失败和回滚。
- production 灰度期间可按 planning_run_id 定位单次结果。
- 发现硬约束回归、外部 API 大面积失败或成本超阈值时，能在 5 分钟内切回 legacy。

## 7. Phase 6：稳定后清理旧链路

### 触发条件

至少连续 7～14 天满足 03-evaluation-and-release.md 的生产门槛，且没有未解决的高优先级数据或路线错误。

### 文件级任务

- 删除前端编辑器默认资源和无调用的编辑器构建产物；保留可恢复 tag 或归档分支。
- 删除 agents/ 中不再被新 planner 使用的角色式 Agent、旧 graph 编排和重复 schema。
- 将旧 /agent/plan*、/trip/chat 标记 sunset，先返回迁移提示，再按版本计划移除。
- 清理通用 RAG 的无来源数据入口，仅保留垂直证据适配器。
- 删除对应测试和配置前，先确认图谱查询没有调用方，再刷新知识图谱。
- 在 CHANGELOG.md 记录删除范围、替代路径和回滚方式。

### 退出条件

- rg、知识图谱和运行日志均显示旧链路无生产调用。
- 构建、数据校验、容器 smoke 和 UI 回归均通过。
- 文档、README、部署配置与实际入口一致。

## 8. 建议开发顺序与并行边界

### 必须串行

Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6。

原因是每一步都改变下一步的输入契约：没有基线不能评估，没有证据不能求解，没有求解器门禁不能灰度。

### 可并行

- Phase 2 中 models/context/trace 与旧接口适配可以并行，但必须先冻结 schema。
- Phase 3 中实体、状态、路线三个工具可以并行开发，统一在 registry 汇合。
- Phase 5 中结果页与监控可以并行，均依赖最终 ItineraryResponse。

### 每日交付节奏

1. 上午：实现一个小契约或工具；
2. 下午：补一个失败场景测试并跑最小验证；
3. 收尾：更新 CHANGELOG.md、图谱（如代码结构变化）和 benchmark 结果；
4. 不在同一提交/变更中同时重写前端、Agent 编排和数据采集。

## 9. 风险与停止线

| 风险 | 观测信号 | 停止/处理 |
|---|---|---|
| 地图 API 不稳定、QPS 超限或超配额 | 超时、`CUQPS_HAS_EXCEEDED_THE_LIMIT`、429、缓存命中率下降 | request-level 去重、并发信号量、批量路线和带时间戳缓存；降低灰度，不可验证则不硬通过 |
| POI 数据缺失、别名错配或类别偏差 | 核心地点召回下降、供应商 Top 1 错实体、道路/校园/社区体验被漏掉 | 扩大旅行角色映射和在线消歧；暂停受影响城市上线，不靠放宽 Validator 掩盖 |
| solver 过度限制 | 可行解率下降且 direct LLM 更自然 | 只放宽软目标，不放宽硬门禁；回看输入候选质量 |
| LLM 输出格式漂移 | schema 解析失败 | 固定 JSON schema、版本化 prompt、限制模型重试次数 |
| 延迟或成本过高 | P95、token、工具调用数超阈值 | 优先缓存和批量路线；关闭可选解释调用 |
| 旧入口暗中被调用 | trace 仍出现 legacy route | 延长兼容期，查调用方后再删除 |

任何“为了通过测试而放宽必去、开放、路线或闭环规则”的改动都属于停止线，必须回到架构评审。
