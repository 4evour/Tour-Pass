# Thesis

## Central Thesis

GitHub 上的旅游规划开源项目各自把一个系统层做深：OTP 做交通网络路由，Trip Planner 做 POI 发现，Wanderlust 做多人共享，JourneyJolt/AI Travel Planner 做低摩擦的 LLM 生成，AWS/Kbhujbal 做画像或多 API 编排；目前没有被本轮证据证明同时完成“用户硬约束、真实地点/路线证据、可行时间轴、失败分级和可复核交付”的项目。Tour Pass 的可验证优势应定位为**证据化的约束规划产品**，而不是“更会聊天的旅游 Agent”。

## Common Misreading

看到竞品使用 Gemini、Claude、CrewAI 或 LangChain，容易把多 Agent 数量和工具数量当成旅游规划质量。源码对比显示，模型调用多并不自动产生路线事实、开放时间和预算可行性；OTP 的强路由也不会自动解决住宿、偏好和日程叙事。

## Supporting Evidence

1. OTP 的 `GraphBuilder` 和 `DefaultRoutingService` 证明了成熟的网络数据导入、索引、超时和路由 worker，但其核心对象是交通图和 A→B 路由，不是游客的完整日程（EV-001、EV-002）。
2. JourneyJolt 的公开生成路径在 `CreateTrip.generateTrip` 中只调用一次 Gemini、解析 JSON 后写入 Firestore；Google Places/route 封装没有证据表明已参与该计划（EV-006、EV-007）。
3. AI Travel Planner 把多字段表单拼成 prompt，交付 `data.choices[0].message.content` 的文本和下载文件，没有公开的实体、路线、时间冲突或 provenance 层（EV-008）。
4. Tour Pass 已在 `workflow.py` 中并行获取 POI、路线和天气，在 `plan_output.py` 绑定 evidence hash，并由 `HardValidator` 把未解析实体、开放时间和路线缺失区分为 warning；`store.py` 同时执行 owner 检查（EV-009）。
5. AWS 和 Multi-Agent Advisor 说明画像注入、外部服务编排和 RAG 可以提高上下文覆盖，但 AWS 源码仍以 ConversationChain 生成回答；Multi-Agent Advisor 的完整实现本轮仅有 README 证据，不能把“真实 API”宣传升级为已验证质量（EV-003 与 Engineering Evidence）。

## Counterargument

Tour Pass 的证据化链路可能牺牲生成速度、覆盖范围和体验灵活性。一个轻量的 Gemini/Claude 生成器可以在几秒内给出可读建议，而完整的地点解析、路线查询、天气和校验会引入供应商配额、延迟和降级分支；如果用户只是寻找灵感，验证成本未必值得。OTP 或 Multi-Agent Advisor 也可能在真实部署中已经解决了部分问题，只是公开仓库证据没有覆盖。

## Conditions

- 论点成立的条件：Tour Pass 对每个交付项清楚显示证据来源和状态；硬约束失败有可解释错误；路线和天气查询有预算、缓存和降级；至少用固定城市/需求集盲评可行性、必去点覆盖和事实可追溯性。
- 论点失效的条件：Provider 覆盖不足导致多数行程只能估算；用户无法理解 warning；实际延迟明显高于轻量生成器；或竞品在源码/运行证据中证明拥有同等的证据—验证—交付闭环。

## Unproven

- 本轮没有证明 Tour Pass 的最终行程质量、事实正确率、成本或速度优于任何竞品。
- 没有证明 Multi-Agent AI Travel Advisor 的 11 个 API 在当前 commit 上全部可运行，也没有独立复现其“2–3 次 AI 调用”。
- 没有证明 OTP 的实时数据在中国城市可用，或把 OTP 作为 Tour Pass 依赖一定比现有高德 Provider 更好。
- 没有证明证据引用会提高留存、转化或用户满意度；这需要产品实验。
