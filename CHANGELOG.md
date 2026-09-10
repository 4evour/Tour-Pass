# CHANGELOG

## 2026-09-09 - 行程长图式表达

### 变更内容
- `trip_agent/static/app.js`、`trip_agent/static/styles.css` - 将行程结果重组为可连续阅读的高密度旅行手册：增加关键数据总览、分日导航、主题色日程段、真实交通衔接、逐段时间轴、住宿据点、预约营业核对、天气穿着、随身清单和出发前提醒。
- 将内部枚举转换为用户可读中文；重复的开放与路线警告按类型聚合，地图坐标和质量检查等审计信息按需展开，但每个地点和交通段仍保留各自的核验状态。

### 影响范围
- 页面完全由现有结构化行程数据和 HTML/CSS 渲染，不调用或依赖 AI 生图服务；桌面、移动端和打印布局同步更新，并支持在浏览器本地导出最高 2160 像素宽的完整 PNG 长图。

## 2026-09-09 - 放宽真实规划超时

### 变更内容
- `trip_agent/llm.py`、`trip_agent/runtime.py`、`trip_agent/.env.example` - 将单次模型请求默认超时调整为 120 秒，并将完整规划请求默认超时调整为 180 秒，避免上游模型推理波动导致正常行程被过早终止。
- `trip_agent/loop.py`、`trip_agent/workflow.py`、`trip_agent/evaluate.py` - 将 Provider 逻辑请求预算从 14 放宽到 100；预算仍是上限，运行时只执行当前行程实际产生的地点、天气和路线查询。
- `trip_agent/app.py`、`trip_agent/llm.py` - 将上游模型连接失败转换为稳定的 `planning_service_unavailable` 响应，前端不再暴露内部 `RuntimeError`，并对短暂连接错误执行有限重试。
- `trip_agent/providers/amap.py`、`trip_agent/workflow.py` - 复合目的地先解析为高德城市编码；地点选择约束到当天片区，返程时间不足时压缩或移除可选活动，避免跨区误绑和返程路线时间冲突。
- `trip_agent/context.py` - 自由描述中的“公共交通为主”“不要太赶”等约束可直接进入结构化规划上下文。

### 影响范围
- 超时只扩大等待上限，不增加模型调用次数；正常完成的请求仍会立即返回。
- 三日四站行程通常约执行 29 个逻辑请求；七日行程会按实际地点与路线数量增长，但不会为凑满预算而发送无意义请求。

## 2026-09-08 - 单次骨架规划与确定性行程组装

### 变更内容
- `trip_agent/loop.py`、`trip_agent/workflow.py`、`trip_agent/model_schema.py` - 将开放式原生工具循环改为轻量骨架生成与程序化组装；正常路径只调用模型一次，随后由后端批量核验地点、天气和路线并生成完整时间轴。
- `trip_agent/contracts.py`、`trip_agent/app.py`、`trip_agent/static/` - 结构化表单直接提交类型化旅行请求，保留日期、同行人、节奏、交通方式和每日时段，不再依赖模型从拼接文本中恢复这些字段。
- `trip_agent/llm.py`、`trip_agent/cache.py`、`trip_agent/providers/amap.py` - 增加稳定提示缓存键、慢请求对冲、规范化 Provider 缓存键和限速下的并发网络请求。
- `trip_agent/validation.py`、`trip_agent/plan_output.py` - 必去地点继续执行硬门禁；可选地点、住宿首尾锚点和预算外路线无法核验时改为明确警告，并支持标记保守估算的交通段。
- `trip_agent/evaluate.py`、`tests/trip_agent_test.py` - 更新评估录制、重放和回归测试，覆盖单次骨架生成、请求预算、提示缓存、对冲请求、可选地点降级和结构化请求边界。

### 原因
- 多轮模型工具循环会放大延迟、Token 和 Provider 调用量，并把可确定化的查询、排序、时间计算和修复交给模型重复完成。
- 表单此前同时发送结构化数据和展示文本，但服务端契约字段不一致会丢失日期、同行人、交通偏好和每日时段。

### 影响范围
- 默认 Provider 请求预算现为 100；正常路径单次模型调用，结构化骨架无法解析时最多补一次格式重试。
- 快速模式不再运行独立 Reviewer，也不让模型反复修改完整行程；Hard Validator 仍决定最终是否交付。
- 未核验的可选事实以警告或估算展示，不再冒充高德证据；必去地点无法解析仍阻止交付。

## 2026-09-07 - 原生工具规划循环、硬校验与可重放评估

### 变更内容
- `trip_agent/llm.py`、`trip_agent/model_schema.py`、`trip_agent/loop.py` - 将模型交互切换为 Responses 原生 Function Calling；支持同轮并发地点、详情、路线和天气调用，限制工具、步骤与提交次数，并将完整行程改为 `submit_itinerary` 专用结构化提交。
- `trip_agent/validation.py`、`trip_agent/plan_output.py` - 增加服务端 Hard Validator，校验用户约束、实体唯一性、开放风险、时间轴、真实路线和住宿闭环；校验失败只向模型返回结构化问题，最终失败则停止交付。
- `trip_agent/reviewer.py`、`trip_agent/runtime.py` - 增加独立上下文 Reviewer，默认以影子模式审查已通过硬校验的行程，不参与事实生成或放宽硬门禁。
- `trip_agent/context.py`、`trip_agent/store.py` - 将历史对话和上一版行程整理为版本化 `PlanningContext`，后续修改沿用已确认约束，同时保留会话所有权与持久化边界。
- `trip_agent/evaluate.py`、`README.md` - 增加真实模型与 Provider 评估命令、完整请求/响应录制、版本与源码哈希、耗时和 Token 汇总，以及不访问外部服务的逐调用确定性重放；重放恢复录制时的初始与最终推理强度，避免配置漂移导致请求哈希不一致。
- `trip_agent/static/app.js`、`trip_agent/static/styles.css` - 进度页新增原生工具批次、提交校验、修复和独立审查事件展示；继续只暴露系统动作，不展示模型内部推理。
- `tests/trip_agent_test.py` - 覆盖原生工具协议、并发工具执行、严格提交契约、硬校验失败与修复、会话上下文、Reviewer、录制重放和路线端点别名解析。
- `trip_agent/loop.py`、`trip_agent/model_schema.py` - 按证据收集与提交阶段裁剪工具契约，合并同批及跨轮的相同成功工具请求，并对可安全前移的活动执行确定性路线缓冲修复；住宿区域可使用已核验地标或交通站点作为路线锚点，区域同名餐厅不会再阻断锚点解析。
- `trip_agent/plan_output.py`、`trip_agent/validation.py` - 预约状态只采信 Provider 证据；住宿区域与具名路线锚点可通过相同实体 ID 或坐标闭环，避免别名造成假失败。
- `trip_agent/reviewer.py`、`trip_agent/llm.py` - Reviewer v3 使用高推理强度复核完整时间叙述与路线证据；Responses 流在服务端 `stream_read_error` 或已开始后的网络中断时执行有限重试。
- `trip_agent/context.py`、`trip_agent/loop.py`、`trip_agent/runtime.py` - 增加分层模型记忆预算：仅注入近期对话、结构化约束、上一版与待修复行程摘要，并按候选相关性限制 POI 和路线证据；预算可通过环境变量配置且限制在安全范围内。

### 原因
- 旧循环依赖模型输出自定义动作 JSON，工具查询与最终交付缺少强制边界；模型可能在没有完整实体和路线证据时直接生成结果，失败后也缺少可审计的定向修复。
- 需要用完整输入输出和外部调用记录复现一次规划，量化各阶段耗时、成本和硬门禁结果，而不是依赖人工挑选样例。
- 规划循环此前会在每轮重新注入完整历史、上一版行程、候选行程和累计证据，导致长会话输入持续膨胀，并把已持久化但当前决策不需要的数据重复发送给模型。

### 影响范围
- 默认主链路允许最多 24 个模型步骤、48 次实际外部查询和 4 次结构化提交；模型调用次数由任务实际需要决定，但所有循环均受预算限制，相同成功工具请求不重复消耗 Provider 配额。
- 只有通过 Hard Validator 的行程才能交付；Reviewer 影子结论不会改变交付结果。未经 Provider 核验的开放时间仍以警告展示，不冒充已确认事实。
- 评估产物包含完整模型上下文与第三方结果并被 Git 忽略；结构化日志继续脱敏。知识图谱已按当前工作区以 `moderate`、`persistence=true` 刷新。
- 完整行程、历史和 Provider 原始结果仍保留在数据库、日志与评估录制中；裁剪只影响模型可见上下文。评估清单记录实际记忆预算，重放沿用同一预算以保持确定性。

## 2026-09-04 - 降低规划循环延迟并约束模型输出

### 变更内容
- `trip_agent/loop.py` - 将每轮变化的证据计数移到模型请求末尾，保持系统提示、工具契约和既有历史的稳定前缀，避免状态数字变化使整段上下文失去缓存。
- `trip_agent/loop.py` - 地点详情与路线结果只向模型传递规划必需字段；高德原始响应继续用于服务端证据处理，但不再反复拼入模型上下文。
- `trip_agent/llm.py`、`trip_agent/.env.example` - 工具决策默认使用 `low` 推理强度，最终规划使用 `medium`，避免简单决策和结构整理消耗 `high` 推理预算。
- `trip_agent/model_schema.py`、`trip_agent/llm.py` - 通过 Responses `text.format` 启用严格 JSON Schema；不同阶段只允许对应动作、工具参数和完整行程字段。
- `trip_agent/loop.py` - JSON 解析失败时记录输出哈希、长度、错误位置和括号状态，不记录模型正文或用户内容。
- `tests/trip_agent_test.py` - 增加稳定请求前缀、解析诊断、工具证据压缩和严格 Schema 回归测试。

### 原因
- 线上一次一日游规划在最终模型请求中输入 31,414 token 且缓存归零，并产生 11,599 output token；动态系统提示和原始工具载荷放大了传输、推理与流式响应耗时。

### 影响范围
- 不改变当前模型调用上限或路线选择逻辑；模型输出新增 `decision` 根字段并由运行时解包，连续规划步骤更容易复用稳定前缀，模型可见工具上下文显著缩小。


## 2026-09-03 - 增加轻量账号、分享与公开行程

### 变更内容
- `trip_agent/db.py`、`trip_agent/models.py`、`trip_agent/store.py` - 使用同一套 SQLAlchemy 数据模型兼容本地 SQLite 与生产 PostgreSQL，为行程增加访客或账号所有权，并保留每次生成的版本。
- `trip_agent/auth.py`、`trip_agent/app.py` - 增加匿名浏览器会话、每日 5 次访客额度、账号注册登录登出、Argon2 密码哈希、HttpOnly 会话 Cookie、CSRF 校验和账号升级后的行程归属迁移。
- `trip_agent/static/` - 增加剩余额度、登录注册、私密分享、账号公开发布、公开行程浏览筛选，以及调用浏览器打印对话框的 PDF 导出入口。
- `Dockerfile`、`render.yaml`、`.dockerignore` - 增加 Render Web Service 与 PostgreSQL 的最小部署配置。
- `README.md` - 汇总当前平台能力、一次完整规划调用链和校验边界；本轮明确不加入硬校验器，完整度报告继续作为透明提示而非交付门禁。
- `.env`、`trip_agent/.env.example` 与生产环境 - 统一使用 `ztoken.zlux.top` 的 Responses 流式接口和 `gpt-5.6-luna`，规划与最终整理阶段均使用 `high` 推理强度；修正 Docker `--env-file` 将引号计入密钥导致的 401。

### 原因
- 允许首次访问者无需注册即可体验，同时让后续用户跨设备保留行程，并在不引入 OAuth、Redis、任务队列或独立 PDF 服务的前提下形成可分享的公开内容。

### 影响范围
- 访客行程只对当前浏览器会话可见，登录或注册后会归入该账号；访客分享默认是不进入发现页的私密链接，账号分享才会进入公开列表。
- 生产环境通过 `DATABASE_URL` 使用 PostgreSQL；未配置时继续使用被 Git 忽略的本地 SQLite。PDF 使用浏览器原生“打印为 PDF”，不增加服务端渲染依赖。

## 2026-09-03 - 新增结构化行程需求表单

### 变更内容
- `trip_agent/static/index.html`、`trip_agent/static/styles.css` - 在默认入口增加结构化行程表单，覆盖目的地、日期天数、住宿区域、同行人、节奏、交通、预算、每日时段、必去地点、兴趣和补充要求，并保留自由描述入口。
- `trip_agent/static/app.js` - 将表单字段确定性整理为单条完整需求，复用现有 SSE 规划链路；提交后自动进入同一会话，可继续通过对话修改。

### 原因
- 单一聊天框要求用户自行组织全部约束，首次使用成本高且容易遗漏日期、住宿锚点、节奏和必去项。

### 影响范围
- 新行程默认显示“快速填写”，仅目的地为必填项；已保存行程仍直接恢复到自由描述模式，不改变后端接口和持久化格式。

## 2026-09-03 - 规划诊断日志与持久化行程

### 变更内容
- `trip_agent/observability.py`、`trip_agent/llm.py`、`trip_agent/loop.py` - 增加脱敏 JSONL 运行日志，记录 `run_id`、阶段、模型请求输入字符数、推理强度、连接/首事件/首文本/总耗时、精简 token 用量、工具耗时、结构修正和持久化耗时；最终行程生成默认使用 `medium` 推理强度。
- `trip_agent/store.py`、`trip_agent/runtime.py`、`trip_agent/app.py`、`trip_agent/contracts.py` - 使用独立 SQLite 保存会话消息、每次生成版本、完整行程和运行轨迹；新增历史行程列表与详情接口。
- `trip_agent/static/` - 增加“新行程”和“已保存行程”入口，重启后自动恢复最后打开的行程，并允许在原对话中提交修改；实时轨迹补充模型连接、首事件、首文本、重试、结构检查和自动保存状态。
- `tests/trip_agent_test.py` - 覆盖日志脱敏及 token 摘要、存储重开、历史行程恢复、原会话修改上下文和流式诊断里程碑。

### 原因
- 原链路只能看到整个模型阶段耗时，无法区分连接等待、隐藏推理、首段正文和输出传输，也无法在服务重启后恢复行程并继续修改。

### 影响范围
- 行程默认保存到被 Git 忽略的 `trip_agent/trips.sqlite`，日志默认写入 `trip_agent/logs/planning.jsonl` 并按 10 MiB 轮转保留 5 份。
- 已保存行程会作为后续修改的显式上下文；若修改消息没有重复天数，证据预算沿用原行程天数，不再误按三天重新查询。

## 2026-09-03 - 实时展示完整规划进度

### 变更内容
- `trip_agent/loop.py`、`trip_agent/app.py`、`trip_agent/contracts.py` - 为一次规划运行发布带耗时的模型阶段、工具调用、结构修正和完成事件；新增 `POST /chat/stream` SSE 接口，并以心跳保持长耗时连接。
- `trip_agent/static/` - 提交后在右侧实时展示六阶段流程、当前工作、累计耗时、模型轮次、事实查询数和逐事件轨迹；行程完成后保留可展开的完整生成轨迹。
- `tests/trip_agent_test.py` - 覆盖运行中事件发布、SSE 先返回进度再返回结果以及类型化超时错误。

### 原因
- 原页面在完整 JSON 返回前没有任何可见进度，用户无法区分模型生成、地点核验、路线查询或结果解析耗时。

### 影响范围
- 浏览器规划请求由同步 `POST /chat` 切换到 `POST /chat/stream`；原接口继续保留兼容。进度只展示系统动作和外部工具状态，不暴露模型内部推理。

## 2026-09-03 - 切换 Responses 中转模型

### 变更内容
- `trip_agent/llm.py` - 增加 OpenAI Responses 流式协议、`/responses` SSE 增量解析和输出文本聚合，同时保留 Chat Completions 兼容能力；流开始后发生中断时禁止重复提交同一生成请求。
- `trip_agent/runtime.py`、`trip_agent/.env.example` - 将默认中转地址和模型更新为 `https://ztoken.zlux.top`、`gpt-5.6-luna`，推理强度设为 `high`，整单运行上限提高到 600 秒。
- `tests/trip_agent_test.py` - 增加 Responses 请求结构、响应解析及读取超时不重试的回归测试。

### 原因
- 原 DeepSeek 配置使用失效密钥，请求返回 HTTP 401；切换后仍使用同步 Responses 请求，无法产生首字时间，高推理生成又超过原 90 秒读取上限，自动重试造成多个仍在上游执行的重复请求并最终触发整单超时。

### 影响范围
- 本地 Trip Agent 改用 Responses SSE 流式协议，允许中转站持续返回增量事件；单次高推理生成读取上限 480 秒，整单最多 600 秒。真实密钥只保存在被 Git 忽略的 `.env` 中。


## 2026-09-03 - 独立 Trip Agent 成为主线

### 变更内容
- 主线只保留独立 `trip_agent/` 应用、对应测试和持久化代码知识图谱。
- 移除旧 C++ 服务、多 Agent、旧 RAG、旧 Web/编辑器、历史数据及其构建部署配置。
- 旧版本由 `legacy/tour-pass-before-trip-agent` 分支和 `grounded-planner-before-migration-20260830` 标签保留。

### 原因
- 当前产品方向已经切换为单一、对话式 Trip Agent；继续保留旧系统会污染代码检索、运行入口和后续开发判断。

### 影响范围
- 默认开发与运行对象改为 `python -m trip_agent.app`。
- 旧接口、旧前端和旧部署配置不再存在于主线；需要查看或恢复时切换到归档分支或标签。

## 2026-09-03 - 完整行程输出与证据边界

### 变更内容
- `trip_agent/loop.py`、`trip_agent/prompts.py`、`trip_agent/plan_output.py` - 将模型输出升级为逐日时间轴、住宿闭环、区域比较、风险和叙事完整契约；增加分阶段批量工具调用、重复查询拦截、模型 JSON 重试及事实归一化。
- `trip_agent/llm.py`、`trip_agent/runtime.py`、`trip_agent/.env.example` - 扩大长行程输出与运行预算，并为临时模型传输错误增加有限重试。
- `trip_agent/static/` - 重做行程工作台，展示每日时段、地点证据、交通段、地图坐标、风险来源、候选区域和完整度检查。
- `tests/trip_agent_test.py` - 覆盖批量查询、重复调用、长 JSON 重试、地点证据清洗、路线端点绑定、天气来源绑定、住宿闭环及重复 POI 合并。

### 原因
- 原预览仅能返回简化景点列表，无法承载可直接执行的多日行程；同时必须防止模型生成的坐标、开放时间或路线数字被误标为外部已核验事实。

### 影响范围
- 模型负责路线取舍和表达，高德与天气 Provider 负责外部事实。
- 未与请求端点和响应哈希匹配的路线不展示精确时间或距离，而是明确标为待核验；模型建议与已核验事实分开展示。

## 2026-09-02 - 新增独立对话式 Trip Agent

### 变更内容
- `trip_agent/` - 新增独立 FastAPI 对话入口、OpenAI-compatible 模型适配器、有限工具循环、高德地点/路线/天气查询、和风天气优先策略、SQLite 原始响应缓存与单页界面。
- `tests/trip_agent_test.py` - 覆盖模型 JSON 提取、未核验地点拒绝、地点简称规范化、工具预算和冷/热缓存行为。
- `trip_agent/.env.example`、`.gitignore` - 补充环境变量示例及本地缓存忽略规则。

### 原因
- 在不复制旧多 Agent 编排和旧规划数据链路的前提下，验证由单一对话 Agent 按需获取实时证据并生成结构化行程的完整闭环。

### 影响范围
- 独立入口默认监听 `127.0.0.1:8123`。
- 最终行程地点必须匹配本轮高德查询证据；工具调用有界，外部响应按 TTL 缓存在本地 SQLite。
