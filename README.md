# Tour Pass

Tour Pass 当前是一个可独立部署的旅行规划 Web 平台。用户可以通过结构化表单或自然语言提交需求，系统使用 LLM 编排行程，并调用高德地图和天气服务核验地点、路线与天气，最终保存、展示和分享结构化行程。

## 当前功能

- 结构化需求表单：城市、天数、日期、住宿区域、同行人、节奏、交通、预算、每日时段、必去地点、兴趣和补充要求。
- 自由描述与后续修改：持久化保存历史消息和上一版完整行程；重新规划时仅向模型注入近期对话、结构化约束和上一版行程摘要。
- 真实地点证据：高德 POI 搜索、地点详情、规范名称、地址、坐标和营业时间。
- 真实路线证据：步行、公交和驾车路线；仅在坐标及证据匹配时采用路线距离和时长。
- 天气证据：优先和风天气，高德天气兜底。
- 有界主 Agent 循环：默认最多 24 个模型决策步骤、48 个实际 Provider 查询和 4 次行程提交（初稿加 3 次修复）；模型可在一轮原生 Tool Calling 中并行请求独立工具，完全相同的成功请求直接复用本轮结果，不重复访问 Provider。
- 分层上下文预算：对话、上一版行程、待修复候选、POI 和路线证据分别裁剪；候选行程涉及的实体和路线优先保留，完整原始数据继续留在存储、日志与评估录制中。
- 实时进度：通过 SSE 展示模型阶段、工具调用、缓存、耗时、结构处理和保存状态。
- 结果页：逐日时间轴、住宿锚点、区域组合、交通段、地图点位、风险提示、候选区域比较和完整度报告。
- 自动保存与版本：保存会话、消息、每次成功生成的完整版本和运行事件。
- 匿名体验：首次访问无需注册，默认每天 5 次规划额度。
- 基础账号：注册、登录、退出、Argon2id 密码哈希和跨设备行程恢复；默认每天 20 次额度。
- 所有权隔离：访客和账号只能访问自己的私有行程。
- 分享与发现：访客生成不公开收录的私密链接；登录账号可把固定快照发布到发现页。
- PDF 导出：使用浏览器原生打印能力和专用打印样式。
- 持久化：本地默认 SQLite，生产环境通过 `DATABASE_URL` 使用 PostgreSQL。
- 运行观测：脱敏 JSONL 日志、请求 ID、模型和工具耗时、缓存命中及错误阶段。
- 部署：FastAPI 单容器和 Render PostgreSQL Blueprint。

## 一次完整行程生成链路

```text
浏览器初始化身份和额度
  -> 用户填写结构化表单或自由描述
  -> POST /chat/stream
  -> 校验会话、CSRF、所有权和每日额度
  -> 创建 session_id / run_id
  -> 恢复上一版行程、历史消息和版本化 PlanningContext
  -> 主 LLM 通过原生 Tool Calling 选择地点、详情、路线和天气工具
  -> Provider Cache
  -> 高德地点 / 地点详情 / 路线，和风或高德天气
  -> 工具结果以 function_call_output 回传同一 Agent 循环
  -> 主 LLM 调用 submit_itinerary 提交完整结构化行程
  -> 后端只采纳已进入 Evidence Store 的地点和路线事实
  -> Hard Validator 检查用户硬约束、实体、时间轴、路线和每日闭环
  -> 未通过时先执行不改变用户约束的确定性时间轴修复，再把结构化 ValidationReport 返回主 LLM，最多重新提交 3 次
  -> 通过后由独立 Reviewer 进行影子审查，不改写、不放宽硬门禁
  -> 保存消息、行程版本、验证报告、审查结果和运行轨迹
  -> SSE 返回最终结果
  -> 前端渲染时间轴、交通、地图、风险和完整度
```

模型只能调用公开的严格工具契约：`search_places`、`place_detail`、`route`、`weather`、`ask_user` 和 `submit_itinerary`。运行时负责并行执行独立工具、缓存、超时、限流、预算和终止条件；模型不能直接访问 Provider、数据库或任意代码执行能力。

运行时只把规范化后的地点、路线和天气字段加入模型上下文，高德原始响应保留在 Provider Cache。每轮重建紧凑 Evidence Ledger，丢弃已被证据快照取代的旧推理历史；证据收集阶段不发送完整行程提交 Schema，进入提交阶段后才暴露该契约，降低重复输入。

`submit_itinerary` 只是提交候选，不代表交付。Schema 保证字段、类型与枚举；Hard Validator 再执行跨字段和证据语义校验。失败报告通过同一个 `call_id` 返回模型，模型只能在剩余提交预算内修复。

## 当前校验边界

当前后端已确定性执行以下硬门禁：

- 行程城市、天数、开始日期、每日可用时段与用户输入一致。
- 必去地点全部进入日程。
- 每个景点和餐饮绑定本次运行中已核验的唯一 Provider 实体；同一 POI 不重复安排。
- 活动时间有效、不重叠，声明停留时长与起止时间一致。
- 已知开放时间冲突时拒绝交付；开放时间无法确认时保留明确警告。
- 相邻实体及已解析住宿锚点之间存在真实路线证据，且通勤时长能放入时间间隔。
- 每天起终点与住宿锚点一致；用户明确指定住宿区域时，锚点必须解析到可核验坐标。

尚未成为硬门禁的内容：

- 轻松、标准、紧凑等节奏的定量阈值。
- 总步行强度、预算和主观体验质量。
- 未能由 Provider 证明的预约库存、票价和临时管制。

这些内容由完整度报告、风险提示和独立影子 Reviewer 透明展示，不得覆盖 Hard Validator 的结论。

## 主要接口

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/health` | 服务、Provider、缓存和数据库状态 |
| `GET` | `/api/auth/session` | 获取或创建浏览器身份 |
| `POST` | `/api/auth/register` | 注册账号 |
| `POST` | `/api/auth/login` | 登录 |
| `POST` | `/api/auth/logout` | 退出登录 |
| `GET` | `/api/sessions` | 当前身份的已保存行程 |
| `GET` | `/api/sessions/{session_id}` | 行程消息和最新版本 |
| `POST` | `/api/sessions/{session_id}/publish` | 分享或公开行程 |
| `DELETE` | `/api/sessions/{session_id}/publish` | 取消分享 |
| `GET` | `/api/public/itineraries` | 查询公开行程 |
| `GET` | `/api/public/itineraries/{slug}` | 读取公开快照 |
| `POST` | `/chat` | 非流式规划接口 |
| `POST` | `/chat/stream` | SSE 流式规划主入口 |

## 本地运行

```bash
python -m pip install -r trip_agent/requirements.txt
python -m trip_agent.app
```

复制 `trip_agent/.env.example` 为 `.env`，至少配置 LLM Key；启用真实地点和天气能力时再配置高德与和风天气 Key。运行状态数据库、Provider 缓存、日志和 `.env` 均已加入 Git 忽略规则。

模型可见记忆默认保留最近 4 条对话（单条最多 800 字符）、最多 7 天且每天 8 个行程项，以及各 24 条 POI 和路线证据。可通过 `TRIP_AGENT_MEMORY_HISTORY_MESSAGES`、`TRIP_AGENT_MEMORY_MESSAGE_CHARS`、`TRIP_AGENT_MEMORY_PLAN_DAYS`、`TRIP_AGENT_MEMORY_ITEMS_PER_DAY`、`TRIP_AGENT_MEMORY_EVIDENCE_PLACES` 和 `TRIP_AGENT_MEMORY_EVIDENCE_ROUTES` 调整；运行时会把配置限制在安全范围内。

## 真实链路评估与确定性重放

使用默认的长沙、青岛、重庆请求运行真实模型与 Provider 链路：

```bash
python -m trip_agent.evaluate live --model gpt-5.6-luna
```

每次运行会在 `artifacts/trip-agent-eval/<UTC 时间>/` 保存请求、版本清单、完整模型输入输出、工具输入输出、运行事件、验证报告、最终行程、耗时、Token、缓存和汇总指标。该目录包含完整上下文，已加入 Git 忽略规则，不应公开上传。

不访问模型或外部 Provider，按记录逐调用校验并重放某个行程：

```bash
python -m trip_agent.evaluate replay artifacts/trip-agent-eval/<UTC 时间>/runs/<行程目录>
```

重放器会检查每次模型及工具请求的哈希、调用顺序、记录消费情况和最终语义结果哈希；任何上下文、契约或执行顺序漂移都会使重放失败。
