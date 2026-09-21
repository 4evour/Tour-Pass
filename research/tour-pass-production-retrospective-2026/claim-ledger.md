# Claim Ledger

| ID | Type | Claim | Evidence | Confidence | Article Location |
|---|---|---|---|---|---|
| C-001 | FACT | 当前结构化请求已覆盖目的地、日期、抵返、住宿偏好、房型、预算、兴趣、预约偏好和每日时间窗 | `trip_agent/contracts.py:72-175` | high | 当前产品基础 |
| C-002 | FACT | 当前主链路以一次模型骨架为中心，仅在结构化输出损坏时做一次紧凑重试 | `trip_agent/loop.py:26-44,220-304`; `README.md:8-10` | high | 当前生产链路 |
| C-003 | FACT | 模型骨架的 stop 只有类型、名称、检索词、时段、游览规模、短理由和可选标记 | `trip_agent/model_schema.py:47-88` | high | 数据模型缺口 |
| C-004 | FACT | 高德、天气和铁路查询位于模型生成后的确定性组装阶段 | `trip_agent/workflow.py:1188-1445`; `README.md:34-42` | high | 当前生产链路 |
| C-005 | FACT | 自动生成的预约任务默认没有截止日期、购买链接和代办能力 | `trip_agent/workflow.py:2849-2882` | high | 票务问题 |
| C-006 | FACT | 餐饮候选的单人价格字段默认是空值 | `trip_agent/workflow.py:2827-2848` | high | 餐饮问题 |
| C-007 | FACT | 当前证据层能为高德 POI 和路线保存引用、响应指纹、抓取时间和陈旧标记 | `trip_agent/plan_output.py:593-805` | high | 可复用能力 |
| C-008 | FACT | README 明确把未被 Provider 证明的预约库存、票价和临时管制排除在硬门禁之外 | `README.md:65-71` | high | 校验边界 |
| C-009 | FACT | 当前前端 PDF 导出调用浏览器原生 `window.print()` | `trip_agent/static/app.js:1280-1289`; `README.md:21` | high | 出版问题 |
| C-010 | FACT | 当前反馈接口只保存 kind、run/session、500 字 detail 和事件名 | `trip_agent/contracts.py:220-227`; `trip_agent/app.py:137-152` | high | 编辑问题 |
| C-011 | FACT | 当前存储会为每次成功计划新增版本并保留发布快照 | `trip_agent/store.py:46-116,225-260` | high | 可复用能力 |
| C-012 | FACT | 当前测试文件有 125 个测试定义；铁路、预约语义、分享和高德有针对性测试，但未发现以 PDF、打印或图片命名的测试 | 静态扫描 `tests/trip_agent_test.py`，研究日 2026-09-20 | medium | 测试缺口 |
| C-013 | FACT | 本次成品使用了独立 HTML 和 Playwright 导出脚本，导出前强制展开 details、加载图片、等待解码后再生成 A4 PDF | `scripts/export_tianjin_jinan_humanities_pdf.mjs` | high | 实际生产过程 |
| C-014 | FACT | 本次实用版最终为 28 页，人文版为 30 页；两个版本被保留为独立文件 | 本地 `pdfinfo` 与文件清单，研究日 2026-09-20 | high | 实际交付 |
| C-015 | FACT | 人文版打印 CSS 已加入 A4 边距、orphans/widows 和组件级 break 规则 | `2026国庆天津济南人文旅行导览.html:737-985` | high | PDF 修复 |
| C-016 | FACT | 本次用户先后要求改变导游语气、增加夜间和餐饮、取消机械模板、补地址交通图片票务，再处理 PDF 和移动端链接 | 当前线程用户修改记录 | high | 需求演变 |
| C-016A | FACT | 用户明确纠正：Codex 一开始没有理解需求，最初采用的生产架构也不合适 | 当前线程用户纠正，2026-09-20 | high | 需求根因 |
| C-017 | INFERENCE | 早期多次返工的主要原因是没有先定义成品契约与验收维度，而非单个提示词写得不够长 | C-003、C-009、C-013、C-016 | high | 根因 |
| C-018 | INFERENCE | 48 页与大片空白由内容密度、折叠展开和过多不可拆分页规则共同造成，不是单一图片尺寸问题 | C-013、C-015 + `output/pdf-check/*contact-sheet.jpg` | medium | PDF 根因 |
| C-019 | INFERENCE | 手机 PDF 中高德链接的可靠性取决于 PDF 阅读器、内置浏览器和地图协议处理，仅提供一个可点击 URI 不足以保证可用 | 当前线程移动端反馈 + 人文版中的阅读器提示与高德 URI 生成代码 | high | 导航问题 |
| C-020 | INFERENCE | 当前 Tour Pass 的核心抽象是结构化 itinerary，而本次任务的核心抽象已变成有研究证据和出版状态的旅行项目 | C-001 至 C-015 | high | 中心论点 |
| C-021 | OPINION | Tour Pass 应保留快速规划，同时新增显式“旅行手册项目”模式 | 判断标准：低门槛、复杂需求完整性、开发成本 | high | 目标产品 |
| C-022 | OPINION | 新模式应以 Trip Brief、Fact Ledger、Route Graph、Content Dossier、Asset Manifest、Publication Model、QA Report 为核心对象 | 本次返工中反复缺失的信息类型 | high | 目标架构 |
| C-023 | OPINION | P0 应先解决事实可执行、局部修改和 PDF 交付，不应先追求自动文学写作 | 用户痛点频次、事实风险与实现依赖排序 | high | 路线图 |
| C-024 | OPEN | 预约与门票规则能否获得稳定官方网页或 API 并自动刷新 | 缺少统一数据源和服务条款评估 | low | 未决问题 |
| C-025 | OPEN | 服务端 PDF 预检的空白率、孤行和裁切阈值应如何设定 | 需要用本次和更多手册建立基准集 | low | 未决问题 |
| C-026 | OPEN | 文化写作的事实正确性与文学质量应由谁最终批准 | 需要定义编辑角色和发布责任 | low | 未决问题 |
| C-027 | FACT | Tour Pass 当前前端渲染同一基准计划后导出 21 页 A4 PDF，逐页图中存在明显大面积空白 | `output/tourpass-baseline-20260920/desktop.pdf`; `output/tourpass-baseline-20260920/contact-sheet.jpg`; `trip_agent/static/styles.css:172-178` | high | PDF 边界 |
| C-028 | FACT | 基准运行耗时 69.8 秒，调用模型 2 次、Provider 39 次，应用 21 次自动修复并最终通过 Hard Validator | `artifacts/tour-pass-tianjin-jinan-baseline/20260920T152250Z/runs/01-tianjin-jinan-national-day-handbook/summary.json` | high | 基准运行 |
| C-029 | FACT | 第一次模型输出达到 8,192 output tokens 后在 JSON 字符串中截断，系统改用紧凑提示重试 | 同目录 `events.jsonl` 的前 5 个事件；`trip_agent/loop.py:44,281-341` | high | 生成容量 |
| C-030 | FACT | 紧凑结果随后被自动删除 6 个 optional 非餐食节点，包括入住、退房、取行李、夜游与回酒店 | 同目录 `events.jsonl` 的 `plan_repair_applied`; `trip_agent/workflow.py:673-700` | high | 自动修复 |
| C-031 | FACT | 最终计划 35 个日程项中只有 8 个绑定实体，开放时间核验为 0，但完整度仍为 84 | 同目录 `summary.json`; `response.json` | high | 评估可信度 |
| C-032 | FACT | 完整度把 `opening_match=unknown` 计为开放检查通过，只要 `booking_tasks` 是 list 就把预约清单计为通过 | `trip_agent/plan_output.py:1044-1052,1120-1124` | high | 评估可信度 |
| C-033 | FACT | 当前城际模式修复把所有偏好合并后先匹配 flight，使天津到济南的高铁偏好被返程中的飞机关键词污染 | `trip_agent/workflow.py:188-201`; 基准 `response.json` 的 `transport_options.intercity` | high | 交通正确性 |
| C-034 | FACT | 基准 evaluator 没有实例化 Rail12306Provider，recording 也没有 rail 字段 | `trip_agent/evaluate.py:1019-1027,1094-1105`; 基准 `recording.json` 与 `manifest.json` | high | 评估覆盖 |
| C-035 | FACT | 12 个预约任务的 deadline、booking_url 和 evidence refs 全部为空 | 基准 `response.json` 的 `plan.booking_tasks`; `trip_agent/workflow.py:2849-2882` | high | 预约执行 |
| C-036 | INFERENCE | 当前失败链不是单一提示词问题，而是输入模型、生成容量、自动修复、Provider 覆盖和评分口径连续压缩需求 | C-029 至 C-035 | high | 中心论点 |
