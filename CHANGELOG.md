# CHANGELOG

## 2026-09-03 - 增加轻量账号、分享与公开行程

### 变更内容
- `trip_agent/db.py`、`trip_agent/models.py`、`trip_agent/store.py` - 使用同一套 SQLAlchemy 数据模型兼容本地 SQLite 与生产 PostgreSQL，为行程增加访客或账号所有权，并保留每次生成的版本。
- `trip_agent/auth.py`、`trip_agent/app.py` - 增加匿名浏览器会话、每日 5 次访客额度、账号注册登录登出、Argon2 密码哈希、HttpOnly 会话 Cookie、CSRF 校验和账号升级后的行程归属迁移。
- `trip_agent/static/` - 增加剩余额度、登录注册、私密分享、账号公开发布、公开行程浏览筛选，以及调用浏览器打印对话框的 PDF 导出入口。
- `Dockerfile`、`render.yaml`、`.dockerignore` - 增加 Render Web Service 与 PostgreSQL 的最小部署配置。
- `README.md` - 汇总当前平台能力、一次完整规划调用链和校验边界；本轮明确不加入硬校验器，完整度报告继续作为透明提示而非交付门禁。

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
