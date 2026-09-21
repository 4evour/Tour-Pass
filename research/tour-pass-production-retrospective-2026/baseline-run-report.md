# Tour Pass 天津—济南基准运行报告

## 结论先行

这次不是拿最终页面倒推产品问题，而是把同一份天津—济南需求真正送进 Tour Pass。系统成功返回结果，Hard Validator 通过，完整度显示 84 分；但它仍不能直接作为这次旅行的交付手册。

最主要的问题不是“模型不会写”，而是长篇需求进入当前单次骨架后连续发生了四次压缩：结构化请求不能表达分组返程，模型输出触顶后进入紧凑重试，自动修复继续删除可选节点，完整度指标又把“已标成 unknown”算作通过。最终页面看似完整，实际丢失了接送、入住、行李、夜游、双交通方案、预约执行信息和《潜伏》深度内容。

## 复跑输入

- 人类可读提示词：`baseline-prompt.md`
- Tour Pass 结构化请求：`baseline-request.json`
- 运行 commit：`92389b47f58819ffdf6b1180457bf53579afecdc`
- 运行日期：2026-09-20
- 模式：`live`
- 模型：`deepseek-flash`
- Wire API：`chat_completions`
- Reasoning effort：`low`

运行命令：

```powershell
python -m trip_agent.evaluate live `
  --requests research/tour-pass-production-retrospective-2026/baseline-request.json `
  --output artifacts/tour-pass-tianjin-jinan-baseline `
  --model deepseek-flash `
  --wire-api chat_completions `
  --reasoning-effort low
```

运行目录：

```text
artifacts/tour-pass-tianjin-jinan-baseline/20260920T152250Z/
```

## 运行概况

| Metric | Result | Interpretation |
|---|---:|---|
| 总耗时 | 69.8 秒 | 单请求可接受，但首轮失败造成第二次模型调用 |
| 模型调用 | 2 次 | 首次 JSON 被截断，紧凑重试成功 |
| 输入 / 输出 token | 4,601 / 11,236 | 第一次输出独占 8,192 tokens |
| Provider 调用 | 39 次 | 37 次高德、2 次天气，没有铁路调用 |
| 自动修复 | 21 次 | 包含 6 次删除行程节点 |
| 日程项 | 35 个 | 餐食占比较高，多个关键执行节点被删 |
| 实体绑定 | 8 / 35 | 22.86%，27 项未解析 |
| 已核验路线 | 13 段 | 时间轴预计需要 28 段，覆盖不足一半 |
| 开放时间核验 | 0 | 所有景点开放信息均未完成核验 |
| 预约任务 | 12 个 | 全部没有 deadline 和 booking URL |
| 必去点覆盖 | 12 / 12 | 名称保留，但不代表地点、开放和内容已核验 |
| Hard Validator | pass | 说明硬约束门槛过松，不说明成品可交付 |
| 完整度 | 84 / 100 | 与实际可执行度明显不一致 |

## Agent 全流程与重新出问题的位置

### 1. 原始需求进入结构化请求

`baseline-prompt.md` 已把日期、三人会合、两组返程、住宿、房型预算、节奏、博物馆、大明湖、新华路 31 号、《潜伏》专题、餐饮、逐段交通、预约、图片与 PDF 全部写清。`baseline-request.json` 也尽量映射到现有 `StructuredTripRequest`。

问题在此阶段已经出现：`travellers` 是一段字符串，`intercity_preferences` 也是无归属的字符串数组。系统没有 traveller group，也没有把交通偏好绑定到具体 leg 的结构，所以“10 月 3 日天津到济南优先高铁”和“10 月 6 日北京/广州分别比较高铁与飞机”只能挤在同一层。

### 2. 单次模型生成完整骨架

第一次输出 20,525 字符、8,192 output tokens，在 JSON 字符串中间终止，错误为：

```text
Unterminated string starting at: line 585 column 16 (char 20508)
```

这不是随机内容错误，而是当前“8 天计划一次性生成”的容量风险。随后系统使用 `COMPACT_RETRY_PROMPT` 重试；它要求每日最多 4 个 stop、每个 reason 不超过 45 个汉字。重试能恢复合法 JSON，却天然削弱了人文讲解、专题叙事和完整执行节点。

### 3. 自动修复骨架

系统一共应用 21 个修复，其中 6 个 `trim_relaxed_stop` 删除了：

- 海河沿岸夜景
- 海光寺入住与休整
- 回酒店休息
- 解放北路金融街
- 退房与去天津站
- 取行李去车站机场

因此 D1 最终只剩早餐、午餐、晚餐；D8 删除了取行李和去车站/机场。这里的根因是 relaxed 行程超过 3 个 stop 时优先删 optional 非餐食节点。系统把“可弹性调整”和“可从成品删除”混成了同一语义。

### 4. 修复城际交通

模型在第一次输出中明确给了天津到济南“高铁”，最终计划却变成：

```json
{
  "from": "天津",
  "to": "济南",
  "mode": "flight"
}
```

`preferred_intercity_mode()` 将所有跨城偏好拼接后，按固定顺序先查“飞机”，再查“高铁”。由于 10 月 6 日返程偏好中含飞机，10 月 3 日天津到济南也被修成 flight。返程又被压成单个“济南 → 北京/广州，mode unknown”，无法表达一人去北京、两人去广州。

### 5. Provider 核验

实跑只有高德和天气，没有铁路。`trip_agent.evaluate live` 构造 `TripAgent` 时未传入 `Rail12306Provider`，manifest 的 provider availability 也只有 amap、qweather。即使生产 `TripRuntime` 支持铁路，当前评估链路仍无法覆盖这一能力。

地点核验也暴露了输入粒度问题。济南住宿建议是“泉城路或趵突泉周边”，实际查询关键词却只有“济南”，最终绑定成泛化的“济南住宿区”和参考坐标，导致多段往返路线从错误住宿锚点出发。用户要求每段同时给公共交通与打车，当前只保存了单一 mode 的已选路线。

### 6. 预约与内容生成

12 个预约任务全部只有“出发前核对是否需要预约”，`deadline`、`booking_url`、evidence refs 为空。当前任务模型无法容纳预约开窗、价格、证件、退改、行李和失败备选。

景点 `reason` 只能承载一两句短说明，紧凑重试又限制为 45 个汉字。新华路 31 号最终只有“对照《潜伏》剧情空间看外立面，注意区分取景与历史背景”，没有剧情、人物、镜头、证据等级或来源。图片也没有进入数据模型和渲染结果。

### 7. 完整度与 Hard Validator

完整度 84 的主要误导来自两个判定：

- `opening_match` 只要是 `matched`、`unknown` 或 `risk` 就通过，因此 0 个开放时间被核验仍显示 pass。
- `booking_tasks` 只要是 list 就通过，因此 12 个任务都没有 deadline 和 URL 仍显示 pass。

Hard Validator 适合阻止日期、天数和必去点等结构性错误，但当前不应被解释为“旅行手册可执行”。

### 8. 前端和 PDF

把真实 `response.json` 注入当前 `renderPlan()` 后，桌面和手机页面均无横向溢出、无 page error。但 5 个 `details` 默认全部关闭，页面只有约 10 个可用的地点导航实体，没有购票链接和图片。

Tour Pass 自身打印输出为 A4、21 页、约 2.2 MB。逐页 contact sheet 确认第 6、9、12 页附近存在明显大片空白。打印样式同时设置：

```css
.guide-day { break-inside: avoid-page; }
.guide-day + .guide-day { break-before: page; }
```

每天强制另起页，并尽量不在页内拆分整天内容，长短不一时会制造半页或整页空白。这次可以明确算作 Tour Pass 自身的基准结果，与此前 Codex 独立 PDF 的 48 页问题不再混淆。

渲染产物位于：

```text
output/tourpass-baseline-20260920/
├── desktop.png
├── mobile.png
├── desktop.pdf
├── contact-sheet.jpg
├── pdf-pages/
└── render-report.json
```

## 应回灌到 Tour Pass 的改造

### P0：先修正确性和评估可信度

1. 用 `TravellerGroup`、`JourneyLeg` 和 `LegPreference` 表达分批抵达、分流返程与每段交通偏好，禁止全局关键词决定某一段 mode。
2. 修复 `preferred_intercity_mode()` 的全局串扰；交通偏好必须按日期、起终点和 traveller group 匹配。
3. 紧凑重试只压缩措辞，不删除 transport、check-in/out、luggage、return-to-hotel 和用户明确要求的夜游节点。
4. 将完整度拆为需求保真、实体绑定、路线覆盖、开放核验、预约可执行、内容与出版六类分数。`unknown` 不能算开放核验通过，空列表或空 URL 不能算预约通过。
5. 给 evaluator 接入 Rail12306Provider，并把 rail 纳入 recording、replay 和 provider availability。
6. 修正打印分页契约：每天可以跨页，短组件避免拆分；导出后固定生成页图和 contact sheet，检测高空白率、裁切、图片失败和链接数量。

### P1：把“旅行手册”建成正式模式

1. Booking Task 增加开窗、截止、价格、官方渠道、URL/小程序路径、证件、退改、行李、有效期、来源和 fallback。
2. 增加 Content Dossier 与 Theme Thread，让《潜伏》线能保存剧情、人物、地点关系、证据等级、来源、剧透级别和长短文案。
3. 增加 Asset Manifest，保存图片来源、作者、许可、尺寸、焦点和裁切策略。
4. 增加 Publication Model，把同一份批准内容编译为网页、手机简版和 A4 PDF，而不是让网页组件直接承担出版版式。
5. 需求阶段先产出 Trip Brief 和一天完整样张，经确认后再批量生成余下日期。

## 建议的回归门槛

同一基准请求再次运行时，至少满足：

- 10 月 3 日天津 → 济南仍为 rail；10 月 6 日北京、广州分成两个 traveller-group legs。
- 入住、退房、取行李、去车站/机场等执行节点不被自动裁剪。
- 必去地点实体绑定率达到 100%，全部日程地点绑定率不低于 90%。
- 连续地点的路线覆盖率达到 100%，每段至少有公共交通与打车两案，明确节假日缓冲。
- 所有预约任务要么有可执行入口与截止，要么带来源、复核日期和明确替代方案；不能只写“出发前核对”。
- 完整度不得在开放核验为 0 或分流返程不可表达时超过 60。
- PDF 无整页异常空白、无图片裁切、无标题孤悬；手机端保留 HTTPS、可复制地址与二维码三种导航降级。

## 证据索引

- 运行摘要：`artifacts/tour-pass-tianjin-jinan-baseline/20260920T152250Z/runs/01-tianjin-jinan-national-day-handbook/summary.json`
- 最终计划：同目录 `response.json`
- 模型与 Provider 录制：同目录 `recording.json`
- 全事件链：同目录 `events.jsonl`
- 汇总 manifest：`artifacts/tour-pass-tianjin-jinan-baseline/20260920T152250Z/manifest.json`
- 页面/PDF 检查：`output/tourpass-baseline-20260920/render-report.json` 与 `contact-sheet.jpg`
