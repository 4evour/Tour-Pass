# Evidence Map

## Source State

版本、研究范围和本地证据清单见 `source-state.md`。本次已让 Tour Pass 生成基准计划，并用当前 `renderPlan()` 与打印 CSS 导出页面和 PDF；Codex 独立成品与 Tour Pass 基准产物继续严格分开。

## README Reuse Map

| Capability | Decision | Boundary |
|---|---|---|
| 结构化请求和多轮版本 | reuse | 作为 Trip Brief 和项目历史的基础 |
| 单次模型行程骨架 | adapt | 保留快速模式，深度模式增加后续研究与编辑阶段 |
| 高德、天气、12306 | reuse | 只支持各自能证明的地点、路线、天气与时刻事实 |
| Hard Validator | adapt | 扩展事实、资产和出版门禁，但不让规则代替人工编辑 |
| 浏览器打印 | adapt | Tour Pass 基准 PDF 已实测为 21 页，并出现由 day 分页规则造成的明显空白；这与 Codex 独立 PDF 的 48 页问题是两套证据 |
| 预约库存、门票与临时管制 | exclude as current capability | README 已明确尚未成为硬门禁 |

## Official Claims

- README 将当前产品定义为结构化输入、单次模型骨架、Provider 核验、确定性时间轴、Hard Validator、保存、分享和浏览器打印组成的旅行规划平台。
- README 明确说明模型不负责声称坐标、路线耗时、开放状态等外部事实已经核验。
- README 明确说明预约库存、票价、临时管制、预算和主观体验质量尚未成为硬门禁。

## Architecture

当前主架构是 `ChatRequest -> PlanningContext -> skeleton -> deterministic assembly -> normalization/evidence -> validation -> store -> render`。建议保留这条快速规划链路，并在深度手册模式中增加 Fact Ledger、Route Graph、Content Dossier、Theme Thread、Asset Manifest、Publication Model 和 QA Report。详细阶段见 `retrospective.md`。

## Code Evidence

| Area | Current evidence | What it proves | What it does not prove |
|---|---|---|---|
| 输入契约 | `trip_agent/contracts.py:72-175` | 多城市、日期、抵返、房型、预算、兴趣、预约偏好和时间窗已有类型化输入 | 不能表达同一旅行中不同人的分流返程、票务执行状态和出版偏好 |
| 多轮上下文 | `trip_agent/loop.py:148-170`; `trip_agent/context.py:505-930` | 会恢复上一版计划、近期消息并合并新要求 | 没有结构化批注、字段级变更意图和冲突审阅界面 |
| 模型骨架 | `trip_agent/model_schema.py:47-145`; `trip_agent/loop.py:26-44` | 模型负责行程意图、地点、顺序和短说明，外部事实留给程序 | 不承载深度景点文章、影视关系、图片和出版信息 |
| 确定性组装 | `trip_agent/workflow.py:1188-1445`; `trip_agent/workflow.py:2790-2999` | 可查询 POI、路线、天气、铁路并生成执行结构 | 高德地点证据不能证明门票规则、库存、餐饮价格或酒店房价 |
| 票务任务 | `trip_agent/workflow.py:2849-2882` | 会识别需要预约或待核实的景点 | `deadline`、`booking_url` 与证据默认空，不能直接执行购票 |
| 证据追踪 | `trip_agent/plan_output.py:593-805` | POI、路线等可绑定 evidence refs、响应指纹和抓取时间 | 没有声明级文化资料、图片许可和规则有效期模型 |
| 硬校验 | `trip_agent/validation.py:86-260`; `README.md:53-71` | 检查城市、天数、日期、必去点、时间轴、路线和部分行动负荷 | 文风、图片质量、移动端链接、PDF 断页不在门禁内 |
| 版本与分享 | `trip_agent/store.py:46-116,137-145,225-260` | 成功计划会保存版本，也可发布快照 | 缺少区块级 diff、批准状态和成品资产版本关系 |
| 产品反馈 | `trip_agent/contracts.py:220-227`; `trip_agent/app.py:137-152` | 能记录简单 outcome signal | 不能把用户批注锚定到具体日期、景点、页面或 PDF 坐标后形成编辑任务 |
| 前端输出 | `trip_agent/static/app.js:648-731,800-865,1193-1289`; `output/tourpass-baseline-20260920/render-report.json` | 能展示待办、证据、长图并调用浏览器打印；基准桌面与手机页面无横向溢出或 page error | 没有服务端 PDF、逐页预检、移动端阅读器兼容策略 |
| 打印样式 | `trip_agent/static/styles.css:172-178`; `output/tourpass-baseline-20260920/contact-sheet.jpg` | 21 页基准 PDF 出现多页大面积空白；day 同时使用 `break-inside: avoid-page` 与相邻 day `break-before: page` | 单一样本不足以确定通用空白率阈值 |
| 基准 Agent 运行 | `artifacts/tour-pass-tianjin-jinan-baseline/20260920T152250Z/runs/01-tianjin-jinan-national-day-handbook/summary.json` | 69.8 秒、2 次 LLM、39 次 Provider、21 次修复；35 项中 8 项绑定实体，开放核验为 0，最终硬校验仍通过且完整度为 84 | 单次运行不能代表所有模型与目的地 |
| 城际偏好修复 | `trip_agent/workflow.py:188-201`; 基准 `response.json` | 不同 leg 的偏好被全局拼接，返程中的“飞机”使天津到济南被修成 flight | 尚未验证修复后的 traveller-group 数据模型 |
| 紧凑重试 | `trip_agent/loop.py:44,281-341`; 基准 `events.jsonl` | 首轮 8,192 output tokens 截断后，重试限制每日最多 4 stop、reason 45 字 | 不能证明所有 8 天请求都会截断 |
| 评估 Provider | `trip_agent/evaluate.py:1019-1027,1094-1105`; 基准 `manifest.json` 与 `recording.json` | live/replay evaluator 未接入 rail；本次只有 AMap 与 weather | 生产 `TripRuntime` 仍有铁路 Provider，不能据此说产品完全没有铁路能力 |
| 本次导出 | `scripts/export_tianjin_jinan_humanities_pdf.mjs` | 导出前展开折叠、触发懒加载、等待解码并生成 tagged PDF | 只针对一个文件，未成为产品通用管线 |
| 本次排版 | `2026国庆天津济南人文旅行导览.html:737-985` | 已用 A4 边距、orphans/widows、局部 break 规则修正断页 | 规则仍依赖内容长度，缺少自动空白率和裁切检测 |
| 本次成品 | 人文 PDF 30 页、实用 PDF 28 页；导出检查目录中的 contact sheet | 证明通过多轮调整可以得到可读成品 | 不证明同一规则能泛化到其他目的地和篇幅 |

## End-to-End Trace

```text
ChatRequest
  -> POST /chat/stream
  -> TripAgent.run
  -> build_planning_context(previous_plan, message, history, structured_request)
  -> LLM + itinerary_skeleton_output_format
  -> repair_skeleton
  -> ItineraryAssembler.assemble
     -> AMap place search / route
     -> weather
     -> 12306 timetable when applicable
     -> deterministic timeline and booking placeholders
  -> normalize_plan + add_traceability
  -> HardValidator.validate
  -> TripStore.save_exchange
  -> SSE result
  -> renderPlan
  -> window.print or exportPlanImage
```

本次已跑通从结构化请求到 `renderPlan` 和打印的基准链路。它证明 Tour Pass 当前能生成和渲染计划，也直接暴露了长输出截断、自动裁剪、城际 mode 串扰、rail 评估缺口、完整度误判和打印空白。Codex 独立成品的 48 页问题仍只属于独立导出链路，不能与 Tour Pass 的 21 页基准混写。

## Engineering Evidence

- `StructuredTripRequest` 证明需求字段已经相当丰富，但这次首轮失败说明“字段齐全”不等于“产品目标理解正确”。
- `booking_tasks` 已有可扩展骨架，最短路径是在其上增加开窗、截止、渠道、URL、证件、行李与有效期，不必另建一套无关系统。
- 现有 evidence refs、抓取时间和 stale 状态可以推广到票务规则、文化事实和图片来源。
- 版本存储可以继续复用，但需要增加字段级 patch、区块批注和发布包版本关系。
- 本次独立导出脚本提供了图片等待、折叠展开和 contact sheet 的实现经验；是否迁入 Tour Pass，应由基准导出结果决定。
- 基准导出已证明 contact sheet 值得迁入产品 QA；当前 Tour Pass PDF 的日级强制分页确实会制造大块空白。

## Limitations

- 本次只运行了一个固定模型、一个复杂行程样本，结论适用于发现具体缺口，不用于宣称总体成功率。
- 对话是需求演变证据，不是完整的机器变更日志。
- 成品未纳入 Git，无法精确还原每一版差异。
- 本轮没有重新联网核验旅行门票、价格、开放时间和预约规则。
- 125 个测试定义是静态计数，本轮尚未据此声称全部通过。

## Contradictions

- 用户首轮已经给出多人分流、国庆、文化与《潜伏》等信号，Codex 仍按普通攻略生产；问题不能全部归因于“需求后来才增加”。
- Tour Pass 基准 PDF 已出现大面积空白，但页数和成因与 Codex 独立 48 页 PDF 不同；两者都需要出版 QA，不能互相替代证据。
- Hard Validator 通过且完整度为 84，与 22.86% 实体绑定、0% 开放核验、预约 URL 全空同时成立，说明当前“通过”口径与用户可执行性矛盾。
- 现有系统强调事实核验，却把预约链接和截止日期留空；“知道需要核对”和“用户可以直接执行”仍是两种产品状态。
- 现有系统保存完整版本，但用户的局部反馈仍会触发完整替代方案；版本存在不等于编辑过程可控。

## Open Questions

见 `open-questions.md`。当前最先应回答的是：修正 traveller-group、leg 级交通偏好与完整度门槛后，同一基准请求能否稳定通过新的可交付标准。
