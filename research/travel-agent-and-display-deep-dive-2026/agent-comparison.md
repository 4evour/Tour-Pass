# Agent Comparison

## What The Projects Actually Do

| 项目 | Agent 结构 | 模型调用形态 | 工具/事实 | 输出契约 | 显示形态 | 适合借鉴什么 |
|---|---|---|---|---|---|---|
| Kbhujbal | 解析器 + 知识专家 + 编译器 | 3 次主要 AI 阶段；服务并行 | 航班/住宿/活动/物流 API + ChromaDB | Pydantic 服务模型，最终字符串 | WebSocket 进度 + Markdown | 最小的“Agent + 数据服务”分层 |
| Vikrambhat | LangGraph 节点集合 | 首次生成 1 次；附加模块按按钮调用 | Serper、Ollama；天气/活动等模块 | 字符串 | Streamlit 表单 + Markdown + 右侧聊天 | 按需附加内容、低首轮成本 |
| Adrit | 7 个专门 Agent + Trip Planner | 9 个顺序任务 | 搜索/计算工具，更多内容由 Agent 生成 | 长文本/Markdown | Streamlit 结果 + 文件 | 领域职责的命名方式，不能照搬数量 |
| Shaheen | Web research + Travel + Reporter | Agent 工具绑定分散 | 航班、天气、Serper、Wikipedia、图片 | 报告型文本 | 报告/视觉元素 | 研究与写作分离 |
| Skywain | 规则化阶段 + 可选城市子 Agent | 研究阶段多次；页面阶段无 LLM 必需 | 公开数据、路线工具、浏览器深链 | `plan.geo.json` | 主题 HTML、地图/KML/清单 | 单一事实源、可重渲染、旅行手册 |
| JourneyJolt | 一个 Gemini chat session | 单次 JSON 生成 | Google Places/route 封装 | JSON 文档 | 酒店/地点卡片 | 目的地对象的视觉表达 |
| Tour Pass | 一次骨架模型 + 程序编排 + validator | 1 次主调用，必要时局部修复 | 高德 POI/路线、天气、缓存 | 结构化 plan + evidence | 时间轴、地图、证据/风险 | 已具备最简可靠底座 |

## Recommended Minimal Agent

```text
用户自然语言/表单
        ↓ 1 次 LLM
轻量 ItinerarySkeleton
        ↓ 程序并行
POI / 路线 / 天气证据
        ↓ 程序确定性组装
按天时间轴 + 休息/返程/缓冲
        ↓ 1 次可选局部修复
HardValidator + evidence status
        ↓
旅行手册式结果页
```

只保留一个“行程规划 Agent”就够了。它负责：目的地分区、顺序、取舍、行程主题、对用户的解释。程序负责：地点身份、路线时间、天气、开放时间、预算计算、时间轴和失败状态。

首轮不需要独立的天气 Agent、餐厅 Agent、酒店 Agent、文化 Agent、预算 Agent，也不需要 Agent 之间互相聊天。它们要么是数据 Provider，要么是确定性模块。

## UI Information Architecture

### Planning mode

- 页面只强调一个输入动作：目的地 + 在意的事情。
- 详细字段放在“补充条件”抽屉，不把模型选择器和内部设置放在首屏。
- 规划中显示 4 个用户语言阶段：整理需求、查找地点和路线、安排每天顺序、检查可行性。

### Result mode

- 规划完成后，输入区收起成“修改这份行程”入口；移动端直接进入结果。
- 首屏只放：目的地/天数、路线一句话、今天或第一天、当前可信状态、一个主动作。
- 统计条降为三个数字：天数、主要地点、需要确认的事项。完整度和 Provider 细节放到“依据与待确认”。
- 每天是一个旅行日卡片：日主题、路线一句话、按时间排序的活动/餐饮/交通/休息；路线证据作为行程项内的次级状态。
- 酒店、预算、预约、风险是行程后的附录模块，不和第一天时间轴争夺首屏。
- 手机只保留“今天 / 下一站 / 导航 / 回住宿”四个高频动作；桌面再展示全日和全程导航。

### Visual language

- 借鉴 Skywain 的“旅行手册”而不是“Agent 控制台”：一个封面、一句路线摘要、按日章节和可打印附录。
- 借鉴 JourneyJolt 的地点卡片：真实图片、地点名、区域、开放状态、地图入口；图片只是识别入口，证据状态仍需文字。
- 借鉴 Kbhujbal 的进度连接线，但只用于生成期间；结果页不展示 7 个 Agent 名称。
- 当前 Tour Pass 的深绿主题可以保留，但应该减少封面几何装饰和重复信息，增加目的地图像/地点对象作为第一视觉信号。
