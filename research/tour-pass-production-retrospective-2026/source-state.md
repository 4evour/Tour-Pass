# Source State

- Repository: Tour Pass
- Local path: `D:/Tour Pass`
- Remote URL: `git@github.com:4evour/Tour-Pass.git`
- Branch/tag: `main`
- Commit: `92389b47f58819ffdf6b1180457bf53579afecdc`
- Research date: 2026-09-20
- Primary language: Python、JavaScript、HTML/CSS；FastAPI、Pydantic、Playwright
- Requested audience: Tour Pass 产品与工程负责人
- Research question: 这次天津、济南旅行导览为何在 Codex 中经历多轮手工研究、编辑与制版，现有 Tour Pass 哪些能力可以复用，哪些生产环节需要补成正式产品能力
- Explicit non-goals: 不修改业务代码；不重新核验旅行事实；不评价模型品牌；不把本次旅行导览内容重写一遍
- Official docs inspected: 本次复盘以当前仓库源码、测试、成品和对话过程为主，不新增外部产品事实
- Competitors inspected: 本次不做竞品比较；比较对象为 Codex 实际生产流程、当前 Tour Pass、建议流程

## Local Evidence Inspected

- `README.md`
- `trip_agent/contracts.py`
- `trip_agent/context.py`
- `trip_agent/model_schema.py`
- `trip_agent/loop.py`
- `trip_agent/workflow.py`
- `trip_agent/plan_output.py`
- `trip_agent/validation.py`
- `trip_agent/providers/amap.py`
- `trip_agent/providers/rail.py`
- `trip_agent/store.py`
- `trip_agent/app.py`
- `trip_agent/static/app.js`
- `trip_agent/static/styles.css`
- `tests/trip_agent_test.py`
- `2026国庆天津济南手机导览.html`
- `2026国庆天津济南旅行导览.pdf`
- `2026国庆天津济南人文旅行导览.html`
- `2026国庆天津济南人文旅行导览.pdf`
- `2026国庆天津济南真人导游手册.md`
- `scripts/export_tianjin_jinan_pdf.mjs`
- `scripts/export_tianjin_jinan_humanities_pdf.mjs`
- `output/pdf-check/compact-contact-sheet.jpg`
- `output/pdf-check/final-contact-sheet.jpg`
- `output/humanities-pdf-check/contact-sheet.jpg`
- `artifacts/tour-pass-tianjin-jinan-baseline/20260920T152250Z/`
- `output/tourpass-baseline-20260920/desktop.pdf`
- `output/tourpass-baseline-20260920/contact-sheet.jpg`

## Conversation Evidence

本次复盘还使用了当前线程中的用户修改记录。它能证明需求如何变化，但不能替代外部事实来源。主要节点包括：

1. 从三人跨城、住宿、返程和节奏等基础约束开始。
2. 用户指出初稿过度强调“未核实”、行程偏少、夜间利用不足且缺少特色餐饮。
3. 用户要求每天按实际情况安排，不机械套用同一模板。
4. 用户要求景点讲解更丰富、更像真人导游，并增强文学性。
5. 用户要求每个地址、逐段交通时间、高德导航与高质量真实照片。
6. 用户要求把地址表改成纵向路线，并让每个地点直接打开高德。
7. 用户要求查清所有预约、价格、开售时间、抢票节点与行李事项。
8. HTML 转 PDF 后，用户发现折叠内容、移动端链接、48 页篇幅、大片空白和难看断页等问题。
9. 用户继续补充新华路 31 号的天津站旧址、大明湖、《潜伏》剧情线和购票直达链接。
10. 最终形成实用版与人文增强版两个成品，而非覆盖同一文件。

## Reuse / Adapt / Verify / Exclude

| README claim | Decision | Reason |
|---|---|---|
| 结构化输入、多轮历史、版本保存 | reuse | 当前源码可直接证明，且是新流程的基础设施 |
| 高德 POI、路线、天气、12306 时刻核验 | reuse | 适合继续承担确定性事实层，但不能外推到门票、库存和酒店实时价格 |
| 单次模型生成完整轻量骨架 | adapt | 适合快速初稿，不适合承载研究、长篇文化写作和出版状态 |
| Hard Validator | adapt | 可保留硬约束校验，并扩展为事实、资产、出版三类门禁 |
| 浏览器打印即 PDF 导出 | adapt | 已用本次基准计划实测为 21 页并观察到多页大面积空白；应调整 day 分页规则并建立出版 QA |
| 完整度报告 | adapt | 应升级为可操作的 QA Report，而不只是结果页提示 |
| 未接入的预约库存、票价和临时管制 | exclude as capability | README 已明确不是硬门禁，不能当作当前产品已有能力 |

## Tour Pass Baseline Run

同一份需求已在 commit `92389b47f58819ffdf6b1180457bf53579afecdc` 上通过 `python -m trip_agent.evaluate live` 实跑，并将最终 `response.json` 注入当前前端 `renderPlan()` 生成桌面、手机截图和 21 页 A4 PDF。完整指标、命令和失败点见 `baseline-run-report.md`。

## Evidence Limits

- 线程记录不是机器生成的变更日志，无法准确统计每轮耗时和每个中间版本的所有字段变化。
- 当前成品是未跟踪文件，Git 无法提供逐次 diff；本复盘只能根据对话、现有文件和导出目录还原过程。
- Tour Pass 基准 PDF 使用真实 Agent 输出和当前前端渲染，但注入过程由研究脚本完成，不等同于从产品 UI 点击生成；它足以评价 `renderPlan()` 与打印 CSS，不证明完整 UI 工作流无问题。
- 票务、开放时间和价格是旅行内容事实，本轮没有重新联网核验，因此复盘只评价它们的生产方式，不重复背书其有效性。
- 当前测试数量通过静态扫描得到 125 个测试定义；本轮尚未将其等同于全部通过。
