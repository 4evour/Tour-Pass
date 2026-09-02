# Grounded Planner 评估与发布方案

> 文档状态：待评审（Proposed）  
> 制定日期：2026-08-29  
> 目标：证明新链路比现有实现更可靠，而不是只展示更漂亮的案例

## 1. 评估对象

所有实验都使用同一份脱敏需求、同一城市数据快照和同一模型配置，至少比较三组：

| 组别 | 实现 | 作用 |
|---|---|---|
| Legacy | 当前生产入口（C++/旧 Agent） | 反映现状和回滚质量 |
| Direct LLM | 将同一结构化需求直接发给模型 | 判断脚手架是否真正提供了增益 |
| Grounded | 新主规划器 + typed tools + solver + validator | 目标实现 |

Direct LLM 只能作为实验对照，不能直接上线。它用来识别“本地规则是否压制模型常识”，并暴露实体、开放状态和路线幻觉。

## 2. 固定 Benchmark

### 城市和规模

首批固定长沙、青岛、重庆三个城市。每城至少 10 条需求：

- 3 条轻松节奏、2～3 天；
- 4 条标准节奏、3～4 天；
- 2 条含必去项和跨区域移动；
- 1 条包含歧义 POI、预约/闭馆风险或天气敏感活动。

总计至少 30 条；正式灰度前扩展到每城 30 条、总计 90 条。需求文件必须版本化，不能在看到结果后修改期望。

### 场景标签

每条样例附带标签：poi_ambiguity、must_visit、opening_hours、route_matrix、hotel_loop、weather、meal_window、rain_plan、cross_area、low_walking、high_density。标签用于分桶分析，不用于事后挑选样例。

### 重放方式

1. 冻结 request JSON、城市数据快照、prompt_version、模型和工具版本。
2. 记录每组的原始结构化输出、工具调用摘要、最终 ItineraryPlan 和 ValidationReport。
3. 外部服务不可用时使用录制夹具；报告中标记 replay_mode，不把离线结果当线上能力。
4. 每个结果生成稳定 hash，任何手工修改都视为新版本并重新评估。

## 3. 核心指标和门槛

### 3.1 硬指标

| 指标 | 定义 | MVP 门槛 |
|---|---|---:|
| Hard pass rate | 无硬错误且通过最终 validator 的行程数/总数 | ≥ 95% |
| Must-visit coverage | 必去项已解析且进入计划的比例 | 100%（不可行时必须显式失败） |
| Entity resolution rate | 最终地点映射到唯一实体 ID 的比例 | 100% |
| Verified route rate | 每个相邻移动段拥有指定方式真实路线证据的比例 | ≥ 98% |
| Opening evidence coverage | 需要开放判断的地点具有日期化来源的比例 | ≥ 95% |
| Hotel loop pass rate | 每天从住宿锚点出发并回到锚点的比例 | 100%（用户指定异地结束除外） |
| Time conflict rate | 到达、停留、通勤和缓冲发生重叠的比例 | 0% |
| Hallucinated POI rate | 不存在、类别错误或错误分店进入最终结果的比例 | 0% |

### 3.2 数据与证据质量指标

| 指标 | 定义 | MVP 门槛 |
|---|---|---:|
| Core POI recall | 三城市版本化核心地点与常见别名能进入候选池或明确返回不可用 | 100% |
| Alias resolution accuracy | 别名映射到正确规范实体的比例 | ≥ 95%，错误实体进入最终结果为 0 |
| Local/online attribution | 能区分本地命中、在线补查、别名失败和排序淘汰的样例比例 | 100% |
| Default-hours hard usage | 默认 `09:00-21:30` 等生成时间被当作开放硬证据的比例 | 0% |
| Route-mode verification | 标记 verified 的路线确由相同交通方式的供应商结果产生 | 100% |
| Weather provenance | 天气结果记录 QWeather（和风天气）、高德降级或 unavailable | 100% |

XHS stop 名称匹配率、高德实时搜索快照覆盖率和本地路线有向对覆盖率作为诊断指标记录，不直接作为发布门槛；这些集合包含组合描述、道路、景区子点和低价值设施，必须通过版本化核心地点清单判断真实召回质量。

### 3.3 质量指标

| 指标 | 定义 | 目标 |
|---|---|---:|
| Area coherence | 同日区域连贯度，按真实路线和跨区次数计算 | 比 Legacy 提升 ≥ 15% |
| Commute efficiency | 实际通勤分钟数相对可行解下界 | 不劣于 Direct LLM，且比 Legacy 降 ≥ 10% |
| Loop quality | 每日首尾闭环、折返和重复跨江的综合分 | 比 Legacy 提升 ≥ 20% |
| Pace fit | 与轻松/标准/紧凑偏好匹配程度 | 人工盲评 ≥ 4/5 |
| Explanation faithfulness | 文案中可核验事实与结构化结果一致 | ≥ 99% |
| User retry rate | 用户在结果后立即整单重试比例 | 灰度期不高于 Legacy + 5% |

### 3.4 系统指标

- P95 首屏结果延迟：staging 目标 ≤ 30 秒，production 先不超过 Legacy 的 1.5 倍。
- 外部工具错误率：按 provider、错误码和城市分桶；`CUQPS_HAS_EXCEEDED_THE_LIMIT`、429、5xx、超时必须可单独告警。
- 请求级缓存命中率：实体、路线、状态和天气分别统计，命中不能掩盖过期证据。
- 单请求模型调用：默认预算不超过 2 次、绝对上限 3 次；骨架纠错、证据驱动重规划和结果解释共享预算，确定性修复不计作模型调用。
- 单请求工具调用：以请求级去重和批量路线为主，超过预算时记录 `budget_exceeded` 并降级或失败。
- 天气 provider：分别统计 QWeather（和风天气）主源成功率、高德降级率和 `weather_unavailable` 比例。
- 成本：记录 token、外部 API 次数和估算费用，不能写入任何密钥、完整 Authorization 或带 key 的 MCP URL。

## 4. 自动评估

### 4.1 Validator 评估

自动检查必须独立于模型生成逻辑，至少覆盖：

1. schema 完整性和版本；
2. 实体唯一性、类别和分店；
3. 必去覆盖；
4. 指定日期开放/预约；
5. 相邻段路线证据和交通方式；
6. 时间轴、停留时长和缓冲；
7. 酒店闭环；
8. 站点数、连续游玩、步行和每日结束时间；
9. 夜景、夜市、早餐、午餐、晚餐的时段语义；
10. 证据 TTL、来源优先级和响应 hash。

每条失败都返回稳定 error_code，例如 ENTITY_UNRESOLVED、MUST_VISIT_MISSING、ROUTE_UNVERIFIED、OPENING_UNKNOWN、TIME_OVERLAP、HOTEL_LOOP_BROKEN、PACE_EXCEEDED。

### 4.2 反事实和故障注入

对同一请求注入以下故障，确认系统拒绝伪造事实：

- POI 搜索返回空结果、多个同名分店、类别冲突，或供应商 Top 1 是错误实体；
- 本地缺少爱晚亭、第一/第二海水浴场、鹅岭二厂等核心/别名样例，但高德在线搜索可解析；
- 开放状态过期、默认时间伪装成真实时间、官方公告显示临时闭馆；
- 路线 API 超时、QPS 超限、429、返回步行和驾车方式不一致；
- 缓存边仅有 `amap_status=partial`，或公交时间由出租车时间乘系数得到；
- QWeather（和风天气）缺失、日期超出覆盖范围、高德基础天气降级也失败；
- C++ solver 无可行解；
- 模型输出非法 JSON、漏必去项、添加未检索地点；
- 缓存命中但 TTL 已过期；
- trace 存储不可用或响应超过大小限制。

期望行为是显式 warning/failure、可控重试或确定性修复，不是静默使用直线距离、猜测营业时间或让模型重新编造。

### 4.3 Direct LLM 对照分析

对 Direct LLM 结果额外标注：

- 宏观分区和主题是否更自然；
- 不存在景点、错误分店和错误开放时间；
- 是否给出真实可行的通勤时间；
- 是否每天回酒店、是否发生折返；
- 是否把“建议”误写成“已确认”。

该分析用于决定哪些能力必须留给模型，哪些能力必须由工具和 solver 接管；不能用来证明 Direct LLM 可生产。

## 5. 人工盲评

### 评审方式

由至少 2 名不参与实现的评审者，对三组结果随机打乱后评分，不显示组别和 prompt。每条结果只展示用户可见行程、通勤、风险和来源摘要。

### 评分维度

每项 1～5 分，并记录“不确定/无法判断”：

- 是否符合需求和必去项；
- 地点组合是否自然；
- 通勤是否现实、是否存在明显折返；
- 每日节奏和休息是否合理；
- 开放/预约/天气提示是否有帮助；
- 文案是否忠实、不夸大已核验事实；
- 整体是否愿意照此执行。

出现硬错误时，该条整体可执行性直接记为 1 分，并单独记录错误类型；不得用文案好看抵消硬错误。

## 6. 发布分层

### 阶段 A：本地与 CI

- 所有 schema、工具 adapter、validator、repair 单测通过；
- 三城市至少 30 条 benchmark 可重放；
- git diff --check 通过；
- 无 secret、Cookie、原始推理或大段供应商响应进入日志。

### 阶段 B：staging 全链路

- 使用真实配置但隔离数据和配额；
- 执行模型、地图、天气、solver 全部故障演练；
- 结果页能展示来源、时间戳和风险；
- 影子运行同时记录 legacy 和 grounded，用户只看到受控版本；
- 连续 2 个工作日无 P0/P1 缺陷。

### 阶段 C：production 影子运行

- 100% 请求异步运行 grounded，但不改变用户结果；
- 比较 hard pass、实体、路线、延迟、成本和失败原因；
- 影子运行不得阻塞主请求，超时自动丢弃并计数；
- 至少积累 100 条真实但脱敏的请求或 7 天数据，再决定灰度。

### 阶段 D：小流量灰度

建议 5% → 25% → 50% → 100% 四档，每档至少观察 24～48 小时。任一档出现停止条件，立即切回旧实现并冻结扩大流量。

## 7. 停止条件、回滚和降级

### 立即回滚

- 任意已展示结果含幻觉 POI、明显错误分店或虚构路线；
- Hard pass rate 低于 90%，或连续 2 个小时低于 95%；
- 外部地图/模型错误导致大量请求无结果；
- 出现密钥、Authorization、Cookie 或用户隐私进入日志；
- P95 延迟超过预算 2 倍并持续 30 分钟；
- 用户投诉集中指向闭馆、走错地点或酒店闭环错误。

### 降级顺序

1. 关闭可选解释 LLM，使用模板解释固定结构；
2. 启用未过期路线/状态缓存；
3. 缩小候选集和日期范围，减少外部调用；
4. 对非关键天气信息降级为“未获取”；
5. 回滚到 legacy，但保留 grounded trace 供诊断。

降级不得把未知事实标成已确认，也不得绕过硬校验。

## 8. 监控和数据保留

### 必须监控的事件

- planning_started / skeleton_created / evidence_collected / solved / validated / repaired / completed / failed；
- 每个工具的 provider、cache_hit、latency_ms、retry_count、error_code；
- hard_fail_code、repair_count、最终 plan hash、prompt/model/tool/solver 版本；
- feature flag、城市、日期范围和交通方式。

### 脱敏和保留

- trace 默认只保留结构化摘要、哈希和来源元数据；原始响应按最短诊断周期加密保存或不保存。
- 用户偏好和行程属于个人数据，按现有存储和删除策略处理；benchmark 必须脱敏。
- 任何用于评估的人工改判都保存 reviewer、时间、依据和版本，避免不可解释的“手工修正”。

## 9. 最终发布清单

### 质量

- [ ] 三城市 benchmark 达到门槛，且 Direct LLM、Legacy、Grounded 对照报告已归档。
- [ ] 版本化核心地点和别名清单达到召回/消歧门槛；能区分本地缺失、别名失败和排序淘汰。
- [ ] 所有最终地点有唯一实体 ID；路线和开放状态均有证据，默认开放时间与 `partial` 未验证方式未通过硬门禁。
- [ ] QWeather（和风天气）主源、高德天气降级和天气完全不可用三条路径均已验证并展示真实 provider 状态。
- [ ] 必去、时间轴、酒店闭环和节奏硬校验通过。
- [ ] 故障注入不会产生伪造事实。

### 工程

- [ ] 新接口、旧兼容接口和前端 payload 一致。
- [ ] planning_run_id 可定位一次请求，trace 已脱敏。
- [ ] 超时、请求级去重、QPS/并发限制、重试、缓存、健康检查和 feature flag 已验证。
- [ ] `npm run test:multi-agent`、`npm run quality:algorithm`、`npm run quality:itinerary-smoke`、`npm run validate:data:all`、语义数据审计、相关前端测试、容器 smoke 和 `git diff --check` 已实际执行并记录结果。
- [ ] 代码结构变化后 codebase-memory-mcp 已对当前 `D:/Tour Pass` 工作区使用 `persistence=true` 刷新图谱。

### 运营

- [ ] Render 环境变量、配额和告警联系人已确认。
- [ ] 一键回滚步骤已在 staging 演练。
- [ ] 灰度期间每日检查硬错误、成本、延迟和用户重试。
- [ ] 计划保留 7～14 天遗留观察窗口，再决定是否删除旧编辑器、多 Agent 和通用 RAG。

## 10. 简历项目叙事

当且仅当上述门槛真实达成后，简历可以将项目描述为：

> 设计并落地一个 grounded itinerary planner：由单主 LLM 生成路线骨架，接入 POI 实体消歧、开放状态、真实路线和天气工具，以 C++ 时间窗求解器和硬校验器保证可执行性；通过 legacy/direct-LLM/grounded 三组 benchmark、故障注入、trace 和灰度回滚验证质量与可靠性。

不要写“多 Agent 自动协作”或“完全避免幻觉”等无法由指标和 trace 证明的表述。
