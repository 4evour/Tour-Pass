# CHANGELOG

> **版本规范**: Major.架构变更 | Minor.新功能 | Patch.bug修复/数据更新
> 每次发版打对应 git tag（如 `git tag -a v2.1.0`）。

## v2.0.0 — 多Agent系统上线 (2026-06-16)

> **git tag**: `v2.0.0`
> **回退标记**: `v1.0-legacy`（单Agent版本）
>
> 核心变更：从单Agent管线迁移到 LangGraph 多Agent架构（9个专业Agent），
> 20城POI数据质量清洗，管理后台，R2图床支持，CI质量门禁。

## 2026-06-20 19:27 - 清理误提交的 Python 缓存文件

### 变更内容 — 改了什么文件，具体改了什么
- scripts/__pycache__/clean_poi_attractions.cpython-311.pyc — 从 Git 跟踪中移除误提交的 Python 字节码缓存文件。
- CHANGELOG.md — 记录本次仓库卫生清理。

### 原因 — 为什么要改
- `.pyc` 文件是 Python 自动生成的本地缓存，不包含需要维护的源码逻辑；仓库已经通过 `.gitignore` 忽略 `__pycache__/` 和 `*.pyc`，但该文件历史上已被跟踪，导致反复出现在 Git 状态中。

### 影响范围 — 改动影响了哪些功能/模块
- 仅影响 Git 仓库跟踪内容和本地缓存文件状态，不影响运行时代码、业务逻辑或线上功能。

## 2026-06-20 19:22 - 修复结构化表单代理 404 并减少默认餐厅数量

### 变更内容 — 改了什么文件，具体改了什么
- src/api.cpp — C++ 反代层新增 `POST /agent/plan-structured` 转发到 Python Agent，避免结构化表单提交在外层服务返回 404。
- scripts/verify_agent_proxy_routes.js — 新增静态回归验证，检查 C++ 代理层必须注册结构化表单规划路由。
- tools/clustering.py — 普通非美食优先行程每天默认只分配 1 个餐厅；只有美食/culinary 明确偏好时才分配 2 个餐厅。
- agents/scheduler_agent.py — 普通非美食优先行程默认只安排午餐；只有美食/culinary 明确偏好时才安排午餐和晚餐。
- tests/test_multi_agent.py — 增加普通 balanced 行程只分配/排程 1 个餐厅的回归测试，同时保留美食优先仍安排午餐和晚餐的覆盖。
- CHANGELOG.md — 记录本次结构化表单和餐厅数量修复。

### 原因 — 为什么要改
- Python Agent 已有 `/agent/plan-structured`，但线上入口通过 C++ 服务反代；C++ 代理未注册该路径时，结构化表单提交会在外层直接返回 404。
- 旧的 balanced 默认策略会每天安排午餐和晚餐两个餐厅，使普通观光行程被餐厅占比过高，弱化景点主线。

### 影响范围 — 改动影响了哪些功能/模块
- 影响线上结构化表单提交路径、C++ 到 Python Agent 的代理路由、多 Agent 聚类餐厅分配和 Scheduler 餐厅时间安排。
- 不改变 Python Agent `/agent/plan-structured` 业务接口、前端表单字段、餐厅候选质量过滤和美食优先行程的双餐安排。

## 2026-06-20 14:20 - 过滤误分类为景点的伴手礼小店

### 变更内容 — 改了什么文件，具体改了什么
- agents/poi_agent.py — 低价值 POI 过滤增加“伴手礼、纪念品、文创、冰箱贴、礼品、小店、专卖店、专营店、土特产、礼品饰品店”等单体零售小店特征；这类 POI 不再进入主景点候选，用户明确必去时仍保留。
- tests/test_multi_agent.py — 增加“哈哈Home(重庆解放碑步行街洪崖洞店)”类误分类文创伴手礼小店的回归测试，并覆盖购物兴趣下仍过滤单体小店、购物地标仍保留的场景。
- CHANGELOG.md — 记录本次 POI 质量过滤修复。

### 原因 — 为什么要改
- 重庆数据中“哈哈Home(重庆解放碑步行街洪崖洞店)”被采集为 `attraction`，但实际是文创/伴手礼小店；旧逻辑在用户有购物兴趣时会放过这类单体零售 POI，导致低质量“景点”进入行程。

### 影响范围 — 改动影响了哪些功能/模块
- 影响 PoiAgent 的景点候选过滤和多 Agent 行程的景点质量。
- 不改变原始 POI 数据、餐厅选择、夜间排程、用户明确必去 POI 的保留逻辑和前端展示结构。

## 2026-06-20 14:17 - 修复夜市抢占白天景点排程

### 变更内容 — 改了什么文件，具体改了什么
- agents/scheduler_agent.py — 新增当天景点排程顺序规则：同时存在白天景点和夜市/夜景类 POI 时，先安排白天景点，再保留 1 个夜间 POI 到当天末尾。
- tests/test_multi_agent.py — 增加夜市排在候选列表首位时仍保留白天景点的回归测试。
- CHANGELOG.md — 记录本次排程修复。

### 原因 — 为什么要改
- 夜市类 POI 固定到晚上后，如果它在候选景点顺序里排在前面，旧循环会先安排夜市并把 `current_time` 推到晚上，导致后续白天景点被当天结束时间截掉，出现一天只有餐厅和夜市的结果。

### 影响范围 — 改动影响了哪些功能/模块
- 影响多 Agent Scheduler 的当天景点排程顺序。
- 不改变餐厅数量策略、POI 数据、路线优化和前端展示结构。

## 2026-06-20 14:14 - 修复夜市夜景景点被排到早上

### 变更内容 — 改了什么文件，具体改了什么
- agents/scheduler_agent.py — 新增夜间 POI 识别规则，命中 `nightlife` 类型或名称/标签/描述/推荐语含“夜市、夜景、夜游、夜生活、酒吧”时，优先安排到 18:00 后；普通排程和必去补救注入都复用该规则。
- tests/test_multi_agent.py — 增加“洪崖洞夜市街区”普通排程和必去补救场景的回归测试。
- CHANGELOG.md — 记录本次夜间 POI 排程修复。

### 原因 — 为什么要改
- 重庆数据中“洪崖洞夜市街区”被标为 `attraction`，开放时间从 10:30 起；旧排程只按开放时间和路线顺序安排，且必去补救默认插入上午/下午，导致夜市类景点可能出现在早上。

### 影响范围 — 改动影响了哪些功能/模块
- 影响多 Agent Scheduler 对夜市、夜景、夜游、夜生活和酒吧类 POI 的时间安排。
- 不改变 POI 数据、路线优化、餐厅选择和前端展示结构。

## 2026-06-20 14:08 - 修复结构化表单点击被 CSP 拦截

### 变更内容 — 改了什么文件，具体改了什么
- web/index.html — 移除结构化表单切换按钮和提交按钮上的 inline `onclick`。
- web/app.js — 使用 `addEventListener` 绑定自然语言/结构化表单切换和结构化提交按钮；提交前清理旧结果并显示规划状态；加载遮罩和旧结果节点缺失时跳过对应 DOM 操作，避免提交被空节点异常中断。
- scripts/verify_agent_image_carousel.js — 本地验证服务增加与线上一致的 `script-src 'self'` CSP，并加入结构化表单切换、提交和结果渲染断言。
- CHANGELOG.md — 记录本次结构化表单修复。

### 原因 — 为什么要改
- 线上 CSP 禁止 inline event handler，浏览器拦截 `onclick="switchPlanMode('form')"` ，导致点击“结构化表单”没有反应。

### 影响范围 — 改动影响了哪些功能/模块
- 影响首页 AI 规划入口的自然语言/结构化表单切换与结构化表单提交。
- 不改变 Agent 规划接口、表单字段、排程逻辑和自然语言规划按钮。

## 2026-06-20 14:00 - 显示 Agent 站点间通勤时间和距离

### 变更内容 — 改了什么文件，具体改了什么
- api_multi_agent.py — `convert_to_frontend_format` 保留每个站点的 `travel_minutes_from_previous`、`distance_meters_from_previous`、`route_source`、`transport_hint`，并保留每日 `route_segments`、`total_travel_minutes`、`route_quality`。
- web/app.js — Agent 行程卡片从第二站开始显示“从上一站通勤 X 分钟 · Y km · 数据来源”。
- web/styles.css — 增加 Agent 通勤信息条样式，复用真实路线/估算路线配色。
- scripts/verify_agent_image_carousel.js — 增加 Agent 卡片通勤时间、距离和来源的浏览器渲染断言。
- tests/test_multi_agent.py — 增加转换层保留通勤字段的回归测试。
- CHANGELOG.md — 记录本次通勤信息显示修复。

### 原因 — 为什么要改
- Scheduler 已计算站点间通勤数据，但转换给前端时丢掉了相关字段；Agent 结果页也没有渲染通勤条，导致两个景点之间的通勤时间和距离不可见。

### 影响范围 — 改动影响了哪些功能/模块
- 影响多 Agent 结果页的站点卡片和 itinerary JSON 字段。
- 不改变路线计算、排程算法、POI 数据和普通规划卡片逻辑。

## 2026-06-20 13:54 - 修复 Agent 景点图片轮播失败图兜底

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — Agent 行程卡片图片轮播记录加载失败的图片索引；当前图片加载失败时自动尝试下一张可用图片，全部失败时才显示占位图。
- scripts/verify_agent_image_carousel.js — 增加首图 404 时自动切到下一张可用图、继续点击下一张仍能切换的回归验证。
- CHANGELOG.md — 记录本次轮播修复。

### 原因 — 为什么要改
- 线上景点图片区域可能遇到某张图片加载失败，旧逻辑只显示占位图，不会自动跳过坏图；用户点击左右按钮时如果切到的图片同样不可用，视觉上像轮播无法切换。

### 影响范围 — 改动影响了哪些功能/模块
- 影响多 Agent 结果页的景点/餐厅图片轮播展示。
- 不改变 Agent 行程生成、图片数据结构、POI 数据和普通规划卡片。

## 2026-06-20 13:30 - 修复天气 key alias CI 失败

### 变更内容 — 改了什么文件，具体改了什么
- tools/weather_api.py — 和风天气 key 与 API host 改为运行时读取当前环境变量，再回退到 `agents.config` 默认值；天气、生活指数和预警请求改为通过当前 host 动态生成 URL。
- CHANGELOG.md — 记录本次 CI 修复。

### 原因 — 为什么要改
- 最新 GitHub Actions 在 `test_weather_key_accepts_hefeng_aliases` 失败。根因是 CI 先导入 `api_multi_agent` 并缓存 `agents.config.QWEATHER_KEY`，后续测试只 reload `tools.weather_api` 时无法读到新设置的 `HEFENG_WEATHER_KEY`。

### 影响范围 — 改动影响了哪些功能/模块
- 修复测试环境和运行时动态配置天气 key/host 的一致性。
- 不改变 API 响应结构，不新增依赖。

## 2026-06-20 13:22 - 增加结构化规划和多轮行程会话

### 变更内容 — 改了什么文件，具体改了什么
- api_multi_agent.py — 新增结构化规划请求模型和 `/agent/plan-structured` SSE 接口；增加 session 存储、会话续接、`/agent/chat-session` 和 `/agent/modify` 行程局部修改能力；规划结果写入 session，便于后续对话修改。
- graph.py — 新增 `create_initial_state_from_intent`，允许结构化表单绕过 IntentAgent 解析；数据采集改为先跑 PoiAgent，再并行酒店/天气/餐厅，避免酒店与餐厅读取空 POI 状态。
- web/index.html — 增加“自然语言/结构化表单”切换和城市、天数、人群、侧重点、节奏、预算、必去、酒店预算、特殊要求等表单输入。
- web/app.js — 前端发送 `session_id`，新增结构化表单提交、多轮对话面板和行程局部修改调用。
- web/styles.css — 增加结构化表单、多轮对话面板和相关交互样式。
- web/editor/src/components/AgentChat.tsx — React 编辑器聊天组件支持 session_id、上下文历史和修改动作回写。
- web/editor-dist/ — 重新构建 React 编辑器静态产物，匹配 AgentChat 会话改动。
- CHANGELOG.md — 记录本次结构化规划和多轮会话变更。

### 原因 — 为什么要改
- 用户提到之前已有结构化表单输入，需要让多 Agent 生成逻辑直接消费明确的城市、天数、节奏、偏好和必去信息，减少自然语言解析误差；同时生成后需要能继续对话修改行程，而不是每次全量重跑。

### 影响范围 — 改动影响了哪些功能/模块
- 多 Agent API 新增结构化入口和会话状态，前端可在自然语言和表单规划间切换。
- 多轮对话可基于当前行程进行局部修改，后续可继续扩展为更完整的增量重排。
- 数据采集顺序改变：POI 成为酒店/餐厅/天气等下游 agent 的稳定输入。

## 2026-06-20 13:22 - 增强和风天气接入与天气感知排程

### 变更内容 — 改了什么文件，具体改了什么
- agent/.env.example — 增加 `QWEATHER_KEY` 和 `QWEATHER_API_HOST` 示例配置。
- agents/config.py — 统一读取和风天气 key、API host、天气预报、生活指数和灾害预警接口地址。
- tools/weather_api.py — 天气接口扩展为三类数据：每日天气、旅游/穿衣/紫外线等生活指数、灾害预警；补充安全数值转换和 21 城 location 映射。
- agents/weather_agent.py — 并发获取天气、生活指数和灾害预警；LLM 只基于真实数据生成建议，失败时使用规则兜底建议。
- agents/scheduler_agent.py — 根据降雨、紫外线、日出日落、恶劣天气和预警调整排程偏好、开始/结束时间和天气 SSE 提示。
- api_multi_agent.py — 转换前端行程时透出每日天气、天气严重程度、天气提醒和 `weather_available`。
- render.yaml — 为 Render 部署预留 `QWEATHER_KEY` secret 和 `QWEATHER_API_HOST` 默认值。
- CHANGELOG.md — 记录本次天气接入和天气感知排程变更。

### 原因 — 为什么要改
- 用户要求天气模块真实接入；原天气能力只覆盖基础预报，缺少生活指数、预警、日出日落和对排程的可解释影响。

### 影响范围 — 改动影响了哪些功能/模块
- WeatherAgent、SchedulerAgent、API 行程格式和前端可展示天气字段。
- Render 部署环境需要配置 `QWEATHER_KEY` 后才会启用真实和风天气。
- 没有配置和风天气 key 时仍返回明确占位数据，不让 LLM 编造天气。
- 高紫外线、雨天或恶劣天气会影响室内/室外 POI 排序和当天时间边界。

## 2026-06-20 00:47 - 增加 Reviewer 行程质量失败码

### 变更内容 — 改了什么文件，具体改了什么
- agents/reviewer_agent.py — hard-check 增加 `unsupported_poi`、`area_scattered`、`weak_last_day`、`meal_attraction_imbalance`、`excessive_commute_estimated`、`excessive_commute_confirmed` 等确定性失败码。
- tests/test_multi_agent.py — 新增 Reviewer 低质量 POI、跨区、长估算通勤、最后一天过空和餐厅景点失衡回归测试。
- CHANGELOG.md — 记录本次 Reviewer 失败码变更。

### 原因 — 为什么要改
- 多 Agent 回路需要稳定、可测试的质量信号，不能只依赖 LLM 审核文本；用户反馈的“小众 POI、跨区通勤、最后一天只有餐厅、景点餐厅不均衡”需要被 reviewer 明确识别。

### 影响范围 — 改动影响了哪些功能/模块
- ReviewerAgent 会在 `review_result.issues` 中输出更细粒度的质量问题。
- Scheduler 后续可继续消费这些失败码做自动补救。
- 不改变 LLM reviewer 提示格式和 API 响应结构。

## 2026-06-20 00:39 - 优化路线图高德导航展示

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — 新增高德导航 URL、路线 URL、通勤来源标签辅助函数；地图 popup、overview 小卡和详情卡支持点击高德导航；地图路线按 `amap_cached` 实线、估算段虚线展示；高德导航按钮复用统一 URL 生成逻辑。
- web/styles.css — 增加地图 popup 地址/导航、通勤来源 chip、详情卡高德链接样式。
- CHANGELOG.md — 记录本次路线图导航展示变更。

### 原因 — 为什么要改
- 用户要求导出的旅游路线图中对应景点地址可点击并能跳转高德导航，同时前端需要解释景点之间的通勤时间是否来自真实高德路径。

### 影响范围 — 改动影响了哪些功能/模块
- 行程 overview、详情页、地图 popup、打印导出和分享页中的 POI 导航链接。
- 地图路线视觉展示会区分真实缓存路径和估算路径。
- 不改变后端行程生成逻辑和 POI 数据。

## 2026-06-20 00:36 - 增加每日通勤分段来源

### 变更内容 — 改了什么文件，具体改了什么
- tools/route.py — 新增 `calculate_route_segments`，优先读取 `edges.json` 缓存路径，输出相邻 POI 的通勤分钟、路径来源、距离和交通提示，并写回后一站的通勤字段；`calculate_total_travel_time` 改为复用分段结果。
- agents/scheduler_agent.py — 每日最终 stops 排序后统一生成 `route_segments`、`total_travel_minutes` 和 `route_quality`，确保必去补救插入后的路线字段仍然准确。
- tests/test_multi_agent.py — 新增真实缓存路径优先和 Scheduler 日程路线字段回归断言。
- CHANGELOG.md — 记录本次通勤分段来源变更。

### 原因 — 为什么要改
- 用户要求行程展示景点之间的通勤时间，并明确区分是否参考高德真实路径；原逻辑只返回总通勤分钟，且未把真实/估算来源暴露给前端和 reviewer。

### 影响范围 — 改动影响了哪些功能/模块
- 多 Agent Scheduler 输出新增路线分段和路线质量统计。
- 前端可直接消费 `route_segments`、`route_source`、`distance_meters_from_previous` 展示真实/估算通勤。
- 旧调用仍可使用 `calculate_total_travel_time`，但结果会复用新的分段计算。

## 2026-06-20 00:32 - 增加 POI 主行程分层准入

### 变更内容 — 改了什么文件，具体改了什么
- tools/scoring.py — 新增 `classify_poi_tier` 和 `build_poi_evidence_sources`，将 POI 分为 `core_hotspot`、`route_supported`、`fallback_only`。
- agents/poi_agent.py — 为候选 POI 写入 `poi_tier`、`evidence_sources`、`image_missing`，并阻止 `fallback_only` 进入主行程候选。
- tests/test_multi_agent.py — 新增 POI 分层和 `PoiAgent` 主候选过滤回归测试。
- CHANGELOG.md — 记录本次 POI 分层准入变更。

### 原因 — 为什么要改
- 防止无热门证据、无真实路线证据的小众 POI 因普通评分加分进入主行程，提升多 Agent 行程真实性和稳定性。

### 影响范围 — 改动影响了哪些功能/模块
- 多 Agent POI 候选生成：主行程候选更严格。
- 调度器仍可通过 `available_pois` 访问 fallback 候选，用于必去兜底或后续替换。
- 前端和 reviewer 后续可消费 `poi_tier`、`evidence_sources`、`image_missing` 做解释和质量检查。

## 2026-06-20 00:25 - 设计多 Agent 行程质量闭环

### 变更内容 — 改了什么文件，具体改了什么
- docs/superpowers/specs/2026-06-20-agent-itinerary-quality-design.md — 新增多 Agent 行程质量设计文档，覆盖 POI 分层、节奏饱满度、同区通勤、Reviewer 失败码、旅游攻略证据接口、图片补全、前端展示和导出高德导航。
- CHANGELOG.md — 追加本次设计文档变更记录。

### 原因 — 为什么要改
- 当前多 Agent 行程仍会出现小众非景点、餐厅和景点分配不均、最后一天内容塌陷、路径可信度不足和前端解释不清的问题；需要先明确共享质量契约和后续实现边界。

### 影响范围 — 改动影响了哪些功能/模块
- 仅新增设计文档和变更记录，不改变运行时逻辑。
- 后续实施将影响多 Agent 生成链路、路径数据消费、前端结果页和路线图导出。

## 2026-06-18 19:54 - 忽略本地临时审计产物

### 变更内容 — 改了什么文件，具体改了什么
- .gitignore — 增加 `.qoder/`、根目录 `_debug/_fix/_test` 临时脚本、`audit_images.py`、`fix_network.bat`、本地 XHS 登录/cookie 辅助脚本、XHS 签名备份文件和本地 handoff 文档的忽略规则。
- CHANGELOG.md — 记录本次未跟踪文件审计后的忽略范围。

### 原因 — 为什么要改
- 未跟踪文件主要是生成文档、本机调试脚本、一次性补丁脚本、XHS 登录/cookie 辅助和备份文件，不属于正式多 Agent 规划质量修复；加入忽略规则可避免推送时误纳入。

### 影响范围 — 改动影响了哪些功能/模块
- 仅影响 Git 工作区清洁度和后续提交范围，不改变前端、后端、测试或运行时行为。

## 2026-06-18 19:41 - 收窄多 Agent 修复处理范围

### 变更内容 — 改了什么文件，具体改了什么
- CHANGELOG.md — 移除未跟踪交接文档对应的变更记录，只保留本次要处理的 6 个多 Agent 规划质量修复文件范围。

### 原因 — 为什么要改
- 用户明确要求先只确认/处理已完成的 6 个多 Agent 规划质量修复，后续 Tour-AI、LvBanGPT 等参考项目工作暂不处理。

### 影响范围 — 改动影响了哪些功能/模块
- 仅影响变更记录，不改变前端、后端、测试或运行时行为。

## 2026-06-18 17:28 - 优化餐饮数量、节奏解析和 XHS 排程约束

### 变更内容 — 改了什么文件，具体改了什么
- agents/intent_agent.py — 增加“紧凑/休闲”等节奏关键词解析；优化必去景点切分，避免把“颐和园/和平公园”这类含“和”的景点名拆坏。
- agents/poi_agent.py — 按节奏调整 POI 候选量，紧凑模式返回更多候选，给早上/下午/晚上安排留出足够景点池。
- tools/clustering.py — 餐厅分配从“只取 5km 内”改为近距离优先、不足时按评分和距离兜底补齐；景点分配在均衡天数时优先最近簇，远距离普通 POI 不再强行塞入无关日期。
- agents/scheduler_agent.py — 排程显式按节奏插入餐厅：休闲默认至少午餐，均衡/紧凑安排午餐和晚餐；紧凑模式锚定早上、下午、晚上景点时段；景点避开默认饭点；XHS 共现调整不再移动用户必去景点、不跨过距离阈值、不把紧凑日搬到少于 4 个景点。
- tests/test_multi_agent.py — 增加节奏解析、必去景点切分、餐厅兜底、紧凑日三时段、POI 候选量、地理聚类、XHS 必去/距离/密度保护等回归测试。
- CHANGELOG.md — 记录本次 AI 多Agent规划质量修复。

### 原因 — 为什么要改
- 用户反馈三天行程只推荐一家餐厅、紧凑/休闲诉求没有体现在排程里、明确要求的景点会漏排或被错误解析、行程会跨区混排，小红书攻略引用也需要确认是否被正确学习。排查发现根因包括：节奏未走正则 fast-path、中文“和”被简单切分、餐厅聚类缺少远距离兜底、排程把景点 `lunch` 时段误当成已吃午餐、紧凑模式候选 POI 不足，以及 XHS 共现交换过度移动景点。

### 影响范围 — 改动影响了哪些功能/模块
- AI 多Agent规划的 IntentAgent、PoiAgent、RestaurantAgent 聚类、SchedulerAgent 和 XHS 参考路线使用方式。
- 紧凑行程会更倾向早上/下午/晚上都有景点且午晚餐齐全；休闲行程减少景点数并保留基本用餐；小红书路线仍参与 POI 加权和同日微调，但不会覆盖用户必去和地理合理性。
- 不改变前端接口字段、不新增第三方依赖、不修改已预留的天气/酒店价格接口。

## 2026-06-18 17:08 - 修复 Agent 景点攻略文字裁剪

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — Agent 行程卡片的攻略文字不再用字符数判断是否显示“展开攻略”，改为渲染后根据真实 `scrollHeight`/`clientHeight` 判断文本是否被折叠，移动端换行后超高也会显示展开按钮。
- web/styles.css — Agent 攻略文字增加 `overflow-wrap` 和 `word-break`，确保长中文/混排文本在窄屏内自适应换行。
- scripts/verify_agent_image_carousel.js — 增加移动端窄屏长攻略文字回归检查，确保文字被截断时必须有展开控件。
- CHANGELOG.md — 记录本次 Agent 景点攻略文字排版修复。

### 原因 — 为什么要改
- 用户反馈景点描述文字在移动端卡片里没有自适应排版，部分文字看不到。根因是 CSS 固定 `max-height: 60px` 裁剪文本，而 JS 只按字符数大于 120 才显示展开按钮，未覆盖短文本在窄屏换行后高度超出的情况。

### 影响范围 — 改动影响了哪些功能/模块
- 首页 AI 多Agent 行程结果中的景点攻略文字展示。
- 不改变后端规划结果、图片轮播、推荐语去重或卡片数据结构。

## 2026-06-18 16:58 - 优化景点候选低价值 POI 过滤

### 变更内容 — 改了什么文件，具体改了什么
- agents/poi_agent.py — 将原先仅排除“会议中心/会展中心”的规则扩展为 `_is_low_value_poi`，普通行程过滤误标为景点的纯购物中心、培训机构、学校校区、写字楼/办公楼、产业园/科技园等低旅行价值 POI；用户明确必去时仍保留，用户有购物兴趣时保留购物类地标。
- tests/test_multi_agent.py — 增加低价值商业/教育/办公 POI 过滤、购物兴趣保留商场、必去指定保留低价值名称的回归测试。
- CHANGELOG.md — 记录本次景点筛选规则优化。

### 原因 — 为什么要改
- 用户反馈仍有不是真正景点的高分 POI 被筛入行程。排查发现数据源里不少商场、培训机构、校区、写字楼被标为 `attraction`，仅靠 type 和热度评分无法排除。

### 影响范围 — 改动影响了哪些功能/模块
- AI 多Agent规划的 PoiAgent 候选集合和后续行程景点质量。
- 默认旅游行程会更少出现纯商业/教育/办公类 POI；购物优先或用户明确必去的场所不受该过滤影响。

## 2026-06-18 16:34 - 优化模板提示词并预留第三方数据接口

### 变更内容 — 改了什么文件，具体改了什么
- web/index.html — 聊天框 placeholder 和快捷模板提示词改为包含城市、天数、必去景点、每晚酒店预算、偏好优先级和节奏等规划要素，帮助 AI 多Agent 更稳定解析用户意图。
- web/app.js — 热门行程模板的 `msg` 同步升级为结构化自然语言提示词，点击模板后直接生成更明确的旅行需求。
- scripts/verify_prompt_templates.js — 新增模板提示词回归检查，验证首页快捷提示和热门模板都覆盖预算、优先级、必去点等关键字段。
- tools/weather_api.py — 和风天气 key 兼容 `QWEATHER_KEY`、`QWEATHER_API_KEY`、`HEFENG_WEATHER_KEY`，并提供非敏感配置状态。
- tools/hotel_price_api.py、tools/__init__.py、agents/hotel_agent.py — 新增酒店价格 provider 边界；未配置时明确跳过，配置 `HOTEL_PRICE_*` 后可从第三方/自建适配服务拉取价格并合并进酒店候选；第三方返回非法价格时跳过价格字段，避免打断规划。
- docs/third_party_integrations.md — 记录和风天气、酒店价格供应商的可行性、环境变量和酒店价格适配器契约。
- tests/test_multi_agent.py — 增加和风天气 key 别名、酒店价格未配置状态、价格报价合并的回归测试。
- CHANGELOG.md — 记录本次模板和第三方接口预留改动。

### 原因 — 为什么要改
- 用户反馈模板提示词太泛，不利于根据“城市、天数、必去景点、酒店预算、偏好优先级”等信息稳定规划；同时希望后续能便捷接入酒店实时价格和已准备好的和风天气 API。
- 参考 Tour-AI 后确认“小红书内容导入→结构化解析→可视化行程”是值得借鉴的方向；本轮先落地当前架构最直接受益的结构化输入和外部数据接口边界。

### 影响范围 — 改动影响了哪些功能/模块
- 首页 AI 多Agent规划输入、快捷模板和热门模板。
- WeatherAgent 的真实天气数据配置兼容性。
- HotelAgent 的酒店价格数据来源预留；无酒店价格 provider 时不影响现有规划。
- 不引入新的前端页面，不直接复制 Tour-AI 代码；小红书帖子导入 UI 留作后续独立增量。

## 2026-06-18 15:39 - 移除首页手动规划入口

### 变更内容 — 改了什么文件，具体改了什么
- web/index.html — 移除首页“手动规划行程”链接，以及“手动设置偏好”折叠表单板块；保留 AI 多Agent规划输入框、快捷模板、关键词和结果区域。
- web/app.js — 表单、城市卡片、酒店选择器相关启动绑定改为元素存在时才启用；热门行程模板不再写入已移除的表单字段，改为直接填充聊天框并触发 AI 规划。
- scripts/verify_agent_image_carousel.js — 增加 Playwright 回归断言，验证首页不再出现手动规划入口/偏好表单，同时 AI 多Agent入口仍存在。
- CHANGELOG.md — 记录本次手动规划入口移除，并已在改动前推送回退标签 `manual-planner-before-removal-20260618`。

### 原因 — 为什么要改
- 用户反馈手动规划行程板块维护和优化成本过高，当前产品主流程应聚焦 AI 多Agent规划；移除前保留 git 标签，方便之后需要时按标签恢复。

### 影响范围 — 改动影响了哪些功能/模块
- 首页主界面不再展示手动规划入口或手动偏好表单。
- AI 多Agent聊天规划、快捷模板、关键词追加和 Agent 行程结果展示继续保留。
- 不删除 `web/editor` 源码和后端 editor API，避免扩大到构建/历史编辑器功能的破坏性变更。

## 2026-06-18 15:29 - Agent 图片支持滑动切换

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — Agent 行程卡片多图轮播增加图片区域 pointer 滑动/拖拽手势，左滑下一张、右滑上一张；保留原有左右按钮点击切图。
- web/styles.css — 图片区域增加纵向滚动友好的 `touch-action: pan-y`、拖拽光标反馈，并禁用图片原生拖拽干扰。
- scripts/verify_agent_image_carousel.js — 增加 Playwright 回归断言，验证图片区域水平拖动可前后切换。
- CHANGELOG.md — 记录本次图片滑动交互修复。

### 原因 — 为什么要改
- 线上 Agent 多图卡片虽然有左右按钮，但移动端和触屏场景下用户无法直接在图片上左右滑动，切图不够便捷。

### 影响范围 — 改动影响了哪些功能/模块
- 首页 AI 多 Agent 行程详情中的多图景点/餐厅/酒店卡片图片交互。
- 单图卡片不受影响；不改变图片 URL 生成、后端规划结果或卡片文案展示。

## 2026-06-18 15:21 - 均衡多天景点分配

### 变更内容 — 改了什么文件，具体改了什么
- agents/poi_agent.py — 必去景点前置补充后按 POI id/name 去重，避免同一个 POI 因复制并标记 `is_must_visit` 后再次从评分结果进入候选池；常规旅游候选排除“会议中心/会展中心”等商务场馆，用户明确必去时仍保留。
- tools/clustering.py — 普通景点分配时先补齐景点数过少的日期，再按地理距离放入最近分组，避免前两天过载而后一天只剩单个景点。
- tests/test_multi_agent.py — 增加北京“故宫/长城”必去候选不重复测试、商务会议中心不应进入常规北京旅游候选测试，以及 3 天行程普通景点应优先填充过少日期的聚类回归测试。
- CHANGELOG.md — 记录本次调度质量修复。

### 原因 — 为什么要改
- 用户反馈北京 3 天行程第 3 天只安排了一个会议中心。排查发现必去景点会重复占用候选名额，且聚类算法在已有第 1/2 天中心点时会持续把普通景点塞向已有中心，导致后续日期过空；同时“会议中心”类商务 POI 会被当作普通旅游景点进入候选。

### 影响范围 — 改动影响了哪些功能/模块
- AI 多 Agent 的 POI 候选集合和分日聚类均衡性。
- 不改变 POI 评分维度、路线优化、图片展示或前端渲染逻辑。

## 2026-06-18 15:02 - 支持“要去”必去景点解析

### 变更内容 — 改了什么文件，具体改了什么
- agents/intent_agent.py — 在 `must_visit` 正则解析中补充“要去XX/想要去XX”句式，并限制触发上下文，避免把“不要去XX”识别成必去景点。
- tests/test_multi_agent.py — 增加“去北京玩三天，要去故宫和长城”的回归测试，覆盖无标点句式和“不要去故宫，要去长城”的否定边界。
- CHANGELOG.md — 记录本次意图解析修复。

### 原因 — 为什么要改
- 用户明确输入“要去故宫和长城”时，现有 regex 快速解析没有识别该自然句式，导致 `must_visit` 为空，后续 PoiAgent/SchedulerAgent 的必去补救链路无法稳定安排这两个景点。

### 影响范围 — 改动影响了哪些功能/模块
- AI 多 Agent 意图解析中的必去景点提取。
- 仅扩展“要去/想要去”表达，不改变景点排序、调度、POI 数据和前端展示逻辑。

## 2026-06-18 14:49 - 去除 Agent 卡片重复推荐文案

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — Agent stop 卡片渲染时规范化 `reason`、`guide_text`、`recommendation` 文本；当推荐文案与已展示的理由或攻略文本完全相同时，不再重复渲染底部提示。
- scripts/verify_agent_image_carousel.js — 增加回归断言，验证相同推荐文案只在卡片中显示一次。
- CHANGELOG.md — 记录本次重复文案修复。

### 原因 — 为什么要改
- 线上部分景点会把同一段推荐语同时放在 `reason` 和 `recommendation` 中，前端按字段逐个展示后造成用户看到重复文字。

### 影响范围 — 改动影响了哪些功能/模块
- 首页 AI 多 Agent 行程详情中的 stop 卡片文案展示。
- 不改变后端规划结果、不改景点排序或去重逻辑；不同内容的推荐语仍会正常显示。

## 2026-06-18 14:28 - Agent 景点图片支持左右切换

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — Agent 行程卡片从 `image_url` 和 `images` 数组收集图片地址并去重；多图时显示上一张/下一张按钮，点击后在当前卡片内切换图片。
- web/styles.css — 增加 Agent 景点图片左右切换按钮样式，按钮居中贴边显示，避开顶部时间和类型标签。
- scripts/verify_agent_image_carousel.js — 新增 Playwright 回归脚本，验证多图景点会渲染左右按钮并能前后切换。
- CHANGELOG.md — 记录本次图片切换实现。

### 原因 — 为什么要改
- 线上多 Agent 行程的景点数据已经可能带有 `images` 多图数组，但前端只读取 `image_url`，用户无法查看同一景点的其他图片。

### 影响范围 — 改动影响了哪些功能/模块
- 首页 AI 多 Agent 行程详情中的景点/餐厅/酒店等 stop 卡片图片展示。
- 单图卡片保持原样，不显示左右切换按钮；不改后端规划、图片 URL 生成和景点去重逻辑。

## 2026-06-18 14:07 - 修复 Agent 行程重复景点

### 变更内容 — 改了什么文件，具体改了什么
- tools/clustering.py — 在景点分日聚类前增加同一物理景区去重：同 ID 只保留一次；规范化后同景区名且距离很近的 POI 只保留更匹配必去项/热度更高的一个，并在 must_visit 补救后再次排除重复景区。
- agents/intent_agent.py — 补充“必须去/务必去XX”的必去景点正则解析。
- tests/test_multi_agent.py — 增加“沙面/沙面岛/沙面公园”近似重复回归测试，以及“必须去沙面”解析回归测试。
- CHANGELOG.md — 记录本次重复景点修复。

### 原因 — 为什么要改
- 线上多 Agent 行程会把同一个景区重复安排，例如 `沙面` 和 `沙面岛` 两个重叠必去词会让同一个 `沙面岛` 跨天重复出现，同时还可能把近距离同景区的 `沙面公园` 作为独立景点加入。
- “必须去沙面”此前不会进入 regex 快速解析的 `must_visit`，会让必去补救链路无法稳定启动。

### 影响范围 — 改动影响了哪些功能/模块
- AI 多 Agent 分日聚类：减少同一景区、子景点或别名 POI 在行程中重复出现。
- 必去景点解析：支持用户自然输入“必须去XX/务必去XX”。
- 不改 POI 数据文件，不影响餐厅跨日去重和 C++ 路线算法。

## 2026-06-18 13:39 - 修复 R2 景点图片被 CSP 拦截

### 变更内容 — 改了什么文件，具体改了什么
- src/api.cpp — 将默认 CSP 生成集中到 `contentSecurityPolicy`，并从 `ASSET_BASE_URL`/`TOURPASS_ASSET_BASE_URL` 提取图片源 origin 加入 `img-src`。
- include/tourpass/api.h — 暴露 CSP 生成 helper，供回归测试直接校验。
- tests/test_main.cpp — 增加 R2 图床 origin 必须出现在 `img-src` 的回归测试。
- CHANGELOG.md — 记录本次图片显示修复。

### 原因 — 为什么要改
- 线上 Agent 返回的景点 `image_url` 是 R2 URL，图片本身可访问，但页面响应头 `Content-Security-Policy` 的 `img-src` 没允许 R2 域名，浏览器拦截加载后前端只能显示占位图标。

### 影响范围 — 改动影响了哪些功能/模块
- 首页和分享页的图片加载安全策略：允许当前配置的 R2/资产域名显示景点、酒店等图片。
- 不改变图片 URL 生成逻辑，也不放宽脚本或接口连接策略。

## 2026-06-18 12:20 - 修复 Render Agent 反代 502

### 变更内容 — 改了什么文件，具体改了什么
- src/api.cpp — Linux/Render 的 `/agent/*` 反代从手写 raw socket 读取改为复用项目已有 `httplib::Client`，并补齐 query string 转发；Agent 不可达时返回结构化 `AGENT_PROXY_ERROR` 和底层错误原因。
- tools/rag.py — 新增单城市 RAG 初始化能力，避免首个规划请求一次加载 21 个城市的攻略/知识数据。
- agents/retrieve_agent.py — RetrieveAgent 改为只按当前请求城市懒加载 RAG。
- tests/test_multi_agent.py — 增加城市级 RAG 初始化回归测试，确认请求北京不会顺带索引上海。
- scripts/container_smoke.js — Agent health 失败时输出响应体片段，避免 CI 只显示 `HTTP 502` 而丢失代理错误细节。
- src/api.cpp — 修复 Agent 代理 handler 对 `agentPort` 的悬空引用，确保 Linux/Render 运行时实际连接 `AGENT_PORT` 指定端口。
- CHANGELOG.md — 记录本次 502 根因调查和修复范围。

### 原因 — 为什么要改
- 最新 GitHub Actions Docker smoke 和线上 `https://tour-pass.onrender.com/agent/health` 都返回 502，响应体为 `{"error":"Agent no response"}`。
- CI 容器日志显示 FastAPI Agent 已经完成 startup 并监听 `127.0.0.1:8090`，但 Python 侧没有收到 `/agent/health` 请求；失败点集中在 C++ Linux raw socket 反代实现，而不是 Agent 健康检查自身。
- Render 免费实例 521MB 内存限制可能仍会影响首个规划请求的 graph/RAG 懒加载，但 `/agent/health` 不触发这些重资源加载，当前可复现 502 需要先修反代可达性。
- 首个 `/agent/plan` 仍可能在免费实例中受内存限制影响，原 RetrieveAgent 会在请求期全量 `init_rag("data")`，需要改成城市级懒加载降低峰值内存。

### 影响范围 — 改动影响了哪些功能/模块
- Render/Docker Linux 环境：`/agent/ping`、`/agent/health`、`/agent/plan`、`/agent/plan-sync`、`/agent/plan-multi`、`/agent/chat` 等 C++ 到 Python Agent 的代理路径。
- Windows 本地 API smoke：不改 WinHTTP 反代分支。
- 前端 AI 多 Agent 规划：恢复 C++ 服务对 Python Agent 的可达性；SSE 响应经 `httplib::Client` 缓冲返回，后续如需优化实时流式可单独处理。
- 首个规划请求：RAG 只加载当前城市，减少 Render 免费实例上的内存峰值；跨城市请求会按城市逐步追加索引。
- CI Docker smoke：后续 Agent 502 会显示响应体和 C++ 代理错误日志，便于区分连接失败、读取失败和 Agent 业务失败。
- Docker/Render Agent 代理：端口捕获改为按值保存，避免 handler 注册后局部端口变量失效导致连接 `port=0`。

## 2026-06-17 21:36 - 修复广州样本数据 CI 校验规则

### 变更内容 — 改了什么文件，具体改了什么
- package.json — 将 `validate:data` 改为使用 `--allow-transit-schedule-defaults --allow-disconnected --required-types attraction,restaurant,hotel`，让默认广州样本校验与全城市真实数据校验规则保持一致。
- api_multi_agent.py — 取消 Agent 启动期预初始化 LLM 和 LangGraph，改为首个规划请求时懒加载；RAG 仍在启动时初始化。
- CHANGELOG.md — 记录本次 CI 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions `CI` 在 `Validate sample data` 步骤执行 `npm run validate:data` 失败。
- 失败原因是默认校验目标已从长沙改为 `data/guangzhou/pois.json`，但默认规则仍强制要求 `nightlife` 类型并要求 transit POI 必须有 `open_time`、`close_time`、`visit_duration_minutes`。当前广州真实数据没有 `nightlife`，且 5 个 transit POI 只有旧字段 `visit_duration`，导致 16 个数据校验错误。
- 不直接改广州 POI 数据，是为了避免人为补造 nightlife 或交通点时间字段污染真实数据。
- 线上游客登录后 `/agent/plan` 返回 502 `Agent no response`，同时 `/agent/health` 也返回同样错误，说明 C++ 主服务正常但 Python Agent 未能稳定提供服务；减少 Agent 启动期 LLM/Graph 预热，避免 Render 实例启动时因重初始化过重导致 Agent 不可用。

### 影响范围 — 改动影响了哪些功能/模块
- CI 数据校验：`validate:data` 不再因为真实城市数据缺少 nightlife 或 transit 时间字段失败；`validate:data:all` 和全城市数据门禁规则保持一致。
- Agent 运行时：`/agent/health` 可更早返回；首个 AI 规划请求会承担 LLM/Graph 懒加载耗时。

## 2026-06-17 21:56 - 修复 Multi-Agent CI 测试缺失文件

### 变更内容 — 改了什么文件，具体改了什么
- tests/test_multi_agent.py — 将 `test:multi-agent` 使用的 Python 回归测试文件纳入版本控制。
- requirements-multi-agent.txt — 补充 `fastapi`、`httpx`、`python-dotenv`、`redis`，使 CI 测试依赖与 Agent/Docker 运行依赖保持一致。
- CHANGELOG.md — 记录二次 CI 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions 新 run `27693832302` 已通过 `Validate sample data`，但在 `Multi-Agent tests` 步骤失败。
- 失败原因是干净 checkout 中没有 `tests/test_multi_agent.py`，而 `package.json` 的 `test:multi-agent` 正在执行该路径；本地能通过是因为该文件只存在于未跟踪工作区。
- 测试会导入 `api_multi_agent.py`，因此 CI 也需要安装 API 导入依赖，否则补上测试文件后会继续因缺依赖失败。

### 影响范围 — 改动影响了哪些功能/模块
- CI 多 Agent 测试：干净 GitHub runner 可找到并执行测试文件。
- Python Agent 依赖：`requirements-multi-agent.txt` 可覆盖测试和运行时导入所需的轻量 API 依赖。

## 2026-06-17 22:02 - 修复 Windows API smoke 城市参数

### 变更内容 — 改了什么文件，具体改了什么
- scripts/api_smoke.ps1 — 路线 smoke 使用 `docs/sample_candidate_request.json` 中的城市作为 `/route/shortest` 的 `city` 参数。
- CHANGELOG.md — 记录 Windows API smoke 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions run `27694240231` 中 Ubuntu 已全部通过，Windows 在最后的 `API smoke` 步骤失败。
- 失败原因是 smoke 从根 `data/edges.json` 读取长沙边 `amap_f3d362be -> amap_b011c2`，但请求 `/route/shortest` 时没有显式传 `city`，服务会使用当前默认城市，导致用非长沙图查询长沙 POI 并返回 `NOT_FOUND`。

### 影响范围 — 改动影响了哪些功能/模块
- CI Windows API smoke：路线检查与样例候选请求城市保持一致，不受服务默认城市变化影响。
- 运行时接口：只影响测试脚本，不改变 `/route/shortest` 接口行为。

## 2026-06-17 22:09 - 修复 API smoke 路线样本来源

### 变更内容 — 改了什么文件，具体改了什么
- scripts/api_smoke.ps1 — 路线 smoke 改为从 `data/guangzhou/edges.json` 取样，并显式传 `city=广州`。
- CHANGELOG.md — 记录第三层 Windows API smoke 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions run `27694712668` 仍在 Windows `API smoke` 的 `/route/shortest` 检查失败。
- 失败原因是 `data/changsha/edges.json` 当前为空；服务按城市目录加载“长沙”，而 smoke 之前从根 `data/edges.json` 读取旧长沙边，导致路线样本和服务实际加载的城市图不一致。
- 广州是当前默认数据校验目标，且 `data/guangzhou/edges.json` 有有效边数据，用它做 smoke 样本更贴近当前 CI 数据入口。

### 影响范围 — 改动影响了哪些功能/模块
- CI Windows API smoke：路线检查使用真实已加载且有边的城市图。
- 运行时接口：只影响测试脚本，不改变服务行为。

## 2026-06-17 22:26 - 修复 Agent 健康检查启动阻塞

### 变更内容 — 改了什么文件，具体改了什么
- api_multi_agent.py — Agent 启动期不再全量执行 `rag_module.init_rag("data")`，RAG 与 LLM/Graph 一样改为首个检索/规划请求懒加载。
- scripts/container_smoke.js — 将 `/agent/health` 从非致命警告改为 Docker smoke 的硬性门禁。
- CHANGELOG.md — 记录线上 `/agent/health` 502 与 CI Docker smoke 漏检的原因和修复方式。

### 原因 — 为什么要改
- 最新 CI 虽然通过，但 Docker smoke 日志显示 `/agent/health` 实际返回 502，只是脚本把它标记为 non-fatal；线上 `https://tour-pass.onrender.com/agent/health` 和游客规划 `/agent/plan` 同样返回 502。
- 失败原因是 FastAPI lifespan 仍在启动期同步全量加载 RAG，读取 21 个城市的攻略和 POI 知识后才会响应健康检查；Render/Docker 中 C++ 反代在 Agent 未完成启动前只能返回 `Agent no response`。
- Agent 健康检查不应依赖 RAG 已完成索引，RAG 可由 `RetrieveAgent` 在首个规划请求中懒加载。

### 影响范围 — 改动影响了哪些功能/模块
- Agent 启动：`/agent/health` 可先返回，避免主服务健康但 Agent 反代一直 502。
- CI Docker smoke：后续若 Agent health 不可用，CI 会失败而不是放过问题。
- 首个 AI 规划请求：会承担 RAG 懒加载耗时。

### 2026-06-15 22:19 — 收紧质量门禁和交付边界

#### 变更内容
- .github/workflows/ci.yml、package.json、web/editor/package.json、scripts/run_python_test.js — CI 显式开启 `TOURPASS_BUILD_TESTS=ON`，增加全城市数据校验、数据校验回归测试、Python 多 Agent 测试、React editor Vitest 和 editor build；补充对应 npm scripts 和跨平台 Python 测试 runner。
- scripts/validate_data.js、tests/test_validate_data_all_cities.js — 新增 `--all-cities` 与 `--data-dir`，逐个校验根数据和城市目录中的 `pois.json/edges.json`；新增回归测试确认坏城市数据会让全量校验失败。
- web/editor/src/core/commands/__tests__/*、web/editor-dist/index.html、web/editor-dist/assets/index-hlZKmOB9.js — 修正 command 测试 fixture 与实际 `setDays` store API 一致；刷新已跟踪的 editor build 产物入口。
- src/api.cpp、api_multi_agent.py — C++ 和 Agent CORS 改为环境变量白名单；C++ `/images` 与 Agent `/data/{city}/images/...` 只允许图片扩展名并限制在数据图片目录内，不再公开整个 data 目录。
- Dockerfile、.dockerignore — 运行镜像不再复制 `scripts/`；Docker build context 排除采集脚本、XHS 会话/路线中间数据和大图片目录。

#### 影响范围
- CI：PR/Push 会运行更多测试和构建，耗时增加但能提前发现测试空跑、Agent 回归、editor 编译和多城市数据问题。
- 运行时安全：跨域访问必须通过 `TOURPASS_ALLOWED_ORIGINS` 或 `AGENT_ALLOWED_ORIGINS` 显式配置；非图片数据不再能通过图片静态路径访问。
- Docker：生产镜像体积和敏感采集中间文件暴露面降低。

### 2026-06-15 17:18 — 多Agent上线入口与 R2 图片准备

#### 变更内容
- Dockerfile、entrypoint.sh、.dockerignore — 默认使用 `AGENT_IMPL=multi` 启动 `api_multi_agent:app`，保留 `AGENT_IMPL=legacy` 回滚入口；镜像复制多 Agent 根文件、agents/tools 目录和 requirements，并排除 `data/*/images/`。
- src/api.cpp、include/tourpass/models.h、src/models.cpp、src/search.cpp、web/admin.js、api_multi_agent.py — 新增/接入图片 URL 解析逻辑，`ASSET_BASE_URL` 或 `TOURPASS_ASSET_BASE_URL` 存在时将相对图片路径解析为 CDN/R2 URL，绝对 URL 原样返回，避免 `/https://...`。
- src/api.cpp、api_multi_agent.py — C++ proxy 增加 `/agent/plan-multi`；修复参数名；`/agent/health` 和 `/agent/stats` 返回 RAG 与 XHS 加载统计。
- tools/xhs_loader.py、tools/route.py、agents/retrieve_agent.py、agents/scheduler_agent.py、agents/state.py、graph.py — 修复中文城市名读取、edges 字段读取；将 XHS 路线转为 POI 频次、同日共现、参考路线摘要并注入多 Agent 规划上下文。
- scripts/upload_r2_assets.js — 新增 R2 上传脚本，支持 `--dry-run`、`--city`、`--only-amap`。
- scripts/multi_agent_regression.py — 新增 21 城 `/agent/plan-sync` 回归脚本。

#### 影响范围
- 部署：Render Docker 运行 C++ 后端 + Python 多 Agent 双进程，旧单 Agent 通过环境变量回滚。
- 图片：生产环境配置 CDN base 后，行程、搜索、POI 浏览和管理页展示可直接使用 CDN 图片 URL。
- 多 Agent：Retrieve/Poi/Scheduler 可利用 XHS 路线信号。

### 2026-06-13 17:37 — 小红书旅游路线爬虫与提取工具

#### 变更内容
- scripts/crawl_xhs_routes.js — 新增 API 方式路线爬虫
- scripts/crawl_xhs_routes_browser.js — 新增 Playwright 浏览器方式路线爬虫
- scripts/extract_routes.py — 新增 Python 路线提取脚本
- data/guangzhou/xhs_routes.json — 从已有 191 条广州笔记中提取出 14 条完整路线

### 2026-06-13 17:15 — 高德照片全量爬取完成

#### 变更内容
- 20 个城市共 2354/8519 个 POI 成功获取照片（27.6% 成功率）
- 各城市 data/{city}/pois.json 的 image_url 和 images 字段已更新
- 照片存储在 data/{city}/images/{poi_id}/ 下

### 2026-06-13 16:35 — 高德照片批量下载（多 Key 轮换）

#### 变更内容
- 修改 scripts/download_amap_photos.js：支持多 API Key 轮换、多城市批量爬取

### 2026-06-13 — 管理后台 POI 数据管理

#### 变更内容
- include/tourpass/graph.h + src/graph.cpp — PoiGraph 新增 findMutablePoi(id) 方法
- include/tourpass/models.h + src/models.cpp — 新增 poiToJson() 序列化函数
- include/tourpass/data_loader.h + src/data_loader.cpp — 新增 savePois() 写回 JSON
- include/tourpass/api.h — CityBundle 新增 poisPath 字段
- src/api.cpp — 新增 4 个管理员 API 端点（GET/PUT /admin/pois）
- web/admin.html — 新增「景点管理」tab
- web/admin.js — POI 管理逻辑：城市切换、分页、搜索筛选、编辑表单
