<div align="center">

# 🧭 Tour Pass

### 让 LLM 生成的行程，更好读、更好查

![Python 3.12](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)

</div>

> **项目方向**：Tour Pass 从旅行规划原型出发。实践中发现，专用旅游规划 Agent 的规划能力不如直接借助 Codex 等通用工具，因此项目不再重复造轮子：保留可运行的第一版，后续重点转向把 LLM 行程合理、美观地展示出来，方便阅读与查询。

---
## 🗺️ 导航

[快速开始](#-快速开始) · [第一版能力](#-第一版能力规划原型) · [生成流程](#-生成流程) · [校验边界](#-校验边界) · [API](#-主要-api) · [评测与重放](#-评测与确定性重放) · [部署](#-部署)

## ⚡ 快速开始

**环境：** Python 3.12+，以及一个兼容的 LLM API Key。高德地图与和风天气 Key 可选；配置后启用真实地点、路线和天气核验。

```bash
python -m pip install -r trip_agent/requirements.txt
```

```powershell
Copy-Item trip_agent/.env.example .env
```

在 `.env` 中填写 `TRIP_AGENT_LLM_KEY`，然后启动：

```bash
python -m trip_agent.app
```

打开 <http://127.0.0.1:8123> 开始使用。服务默认使用本地 SQLite；生产部署可通过 `DATABASE_URL` 接入 PostgreSQL。**不要把 `.env`、运行日志或评测录制文件提交到仓库。**

## ✨ 第一版能力（规划原型）

| 规划体验 | 可靠性与交付 |
|---|---|
| 📝 结构化表单与自然语言输入 | 🗺️ 高德 POI、路线及天气核验 |
| 💬 结合历史对话继续修改行程 | 🧩 确定性时间轴组装与硬约束校验 |
| 🕒 逐日时间轴、交通和地图点位 | 📊 风险提示与行程完整度报告 |
| 💾 自动保存会话与行程版本 | 🔐 匿名/账号隔离及跨设备恢复 |
| 🔗 私密分享或发布到发现页 | 🖨️ 浏览器打印与 PDF 导出 |
| ⚡ SSE 实时展示规划进度 | 🐘 SQLite 本地存储 / PostgreSQL 生产存储 |

匿名访客默认每天可规划 5 次；登录账号默认每天 20 次。系统使用 Argon2id 保存密码哈希，并按所有权隔离私有行程。

## 🧠 生成流程

```text
提交结构化需求或自然语言
          │
          ▼
校验身份、会话、所有权与每日额度
          │
          ▼
LLM 生成轻量行程骨架 JSON
          │
          ▼
并行查询 POI、路线与天气 ── 持久化缓存复用相同请求
          │
          ▼
确定性组装时间轴、通勤与缓冲
          │
          ▼
Hard Validator 检查约束与证据
       ┌──┴──┐
       ▼     ▼
    保存版本  返回具体冲突
       │
       ▼
SSE 推送结果，前端展示行程与风险
```

模型负责路线骨架、片区组合、取舍和自然语言说明；不生成坐标、路线耗时或开放状态，也不持有 Provider 工具。正常路径只调用主模型一次；仅骨架无法解析时最多追加一次格式重试，不通过反复调用模型修改整份行程。

程序负责类型化请求解析、POI 选择、路线和天气查询、去重、午餐补齐、时间计算、结构归一化与硬校验。单次运行默认最多发起 100 个 Provider 逻辑请求；达到实时请求预算时优先保留住宿、必去地点和活动间路线，并明确标记未执行的低优先级核验，不伪造外部事实。

稳定的系统提示与 JSON Schema 使用显式 `prompt_cache_key`。对话和上一版行程摘要按预算裁剪；完整原始计划、Provider 响应与运行事件仍保留在存储、缓存和评测录制中。SSE 与脱敏 JSONL 日志记录模型/工具耗时、缓存命中、Token 用量和错误阶段。

## ✅ 校验边界

Hard Validator 确定性检查以下项目，并区分硬失败与警告：

- 城市、天数、开始日期及每日时段符合用户输入；必去地点进入日程。
- 景点与餐饮实体保留 ID、坐标和来源；未绑定实体或重复 POI 会产生警告。
- 活动时间有效且不重叠；已知开放时间冲突会提示，无法确认时明确标注。
- 路线端点、路线证据与时间轴一致；缺少真实路线时产生警告，必要时使用明确标注的保守估算。
- 每日行程以住宿锚点闭环；锚点无法解析时，明确提示首尾路线尚未核验。

**当前不作为硬门禁：** 节奏（轻松/标准/紧凑）的量化阈值、总步行强度、预算与主观体验质量，以及 Provider 无法证明的预约库存、票价和临时管制。这些内容会通过完整度报告与风险提示展示，不覆盖硬校验结论。

## 🔌 主要 API

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 服务、Provider、缓存和数据库状态 |
| `GET` | `/api/auth/session` | 获取或创建浏览器身份 |
| `POST` | `/api/auth/register` · `/api/auth/login` · `/api/auth/logout` | 注册、登录与退出 |
| `GET` | `/api/sessions` | 当前身份的已保存行程 |
| `GET` | `/api/sessions/{session_id}` | 行程消息与最新版本 |
| `POST` / `DELETE` | `/api/sessions/{session_id}/publish` | 发布或取消分享 |
| `GET` | `/api/public/itineraries` | 查询公开行程 |
| `GET` | `/api/public/itineraries/{slug}` | 读取公开快照 |
| `POST` | `/chat` | 非流式规划 |
| `POST` | `/chat/stream` | SSE 流式规划主入口 |

## 🧪 评测与确定性重放

运行真实模型与 Provider 链路（默认请求覆盖长沙、青岛和重庆；铁路换城段也会调用 12306）：

```bash
python -m trip_agent.evaluate live --model deepseek-flash --wire-api chat_completions
```

评测会把模型、高德、天气和铁路请求统一录制到 `artifacts/trip-agent-eval/<UTC 时间>/`，包括输入输出、运行事件、验证报告、最终行程、耗时、Token 和缓存指标。录制内容可能包含完整上下文，目录已加入 Git 忽略规则，**请勿公开上传**。

离线重放指定行程（不访问模型或外部 Provider）：

```bash
python -m trip_agent.evaluate replay artifacts/trip-agent-eval/<UTC 时间>/runs/<行程目录>
```

重放器校验请求哈希、调用顺序、记录消费情况和最终语义结果哈希；上下文、契约或执行顺序发生漂移时会失败。

## 🚀 部署

项目提供 FastAPI 单容器与 Render PostgreSQL Blueprint：

- `Dockerfile`：Python 3.12 容器镜像。
- `render.yaml`：Web 服务、PostgreSQL 数据库及必要环境变量模板。
- `trip_agent/.env.example`：本地环境变量示例。生产环境密钥应通过托管平台的 Secret/Environment 配置，不要写入仓库。

本地模型调用默认超时为 300 秒，整次规划默认超时为 420 秒；可分别通过 `TRIP_AGENT_LLM_TIMEOUT_SECONDS`（最大 600）和 `TRIP_AGENT_RUN_TIMEOUT_SECONDS`（最大 900）调整。调整时也需确认反向代理或托管平台的请求时限。临时过载或并发限制最多重试 3 次，共用模型等待预算；永久配额错误不会重试。

模型可见记忆默认保留最近 4 条对话（单条最多 800 字符）、最多 7 天且每天 8 个行程项，以及各 24 条 POI 和路线证据。可通过以下环境变量调整，运行时会将值限制在安全范围内：

`TRIP_AGENT_MEMORY_HISTORY_MESSAGES` · `TRIP_AGENT_MEMORY_MESSAGE_CHARS` · `TRIP_AGENT_MEMORY_PLAN_DAYS` · `TRIP_AGENT_MEMORY_ITEMS_PER_DAY` · `TRIP_AGENT_MEMORY_EVIDENCE_PLACES` · `TRIP_AGENT_MEMORY_EVIDENCE_ROUTES`

---

<div align="center">

**Tour Pass** · 让每段行程都有依据，也留有余地。

</div>
