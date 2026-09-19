# Claim Ledger

| ID | Type | Claim | Evidence | Confidence | Article Location |
|---|---|---|---|---|---|
| C-001 | FACT | Kbhujbal 管线把请求解析、并行外部服务、RAG 知识和最终行程编译分为四个步骤。 | `../open-source-travel-planners-2026/sources/kbhujbal/orchestrator.py:211-355` | high | Agent comparison |
| C-002 | FACT | Kbhujbal 的服务模型用 Pydantic 统一航班、住宿、活动、路线、天气和请求字段。 | `../open-source-travel-planners-2026/sources/kbhujbal/schemas.py:13-181` | high | Agent comparison |
| C-003 | FACT | Kbhujbal 前端通过 WebSocket 将四个内部阶段映射为进度事件和 AgentProgress 连接线。 | `../open-source-travel-planners-2026/sources/kbhujbal/websocket.py:20-25,60-109`; `../open-source-travel-planners-2026/sources/kbhujbal/AgentProgress.jsx:28-99` | high | Display comparison |
| C-004 | FACT | Vikrambhat 的 LangGraph 只有 generate_itinerary 在首条图路径上，其余节点由 UI 按钮单独调用。 | `../open-source-travel-planners-2026/sources/vikrambhat2/travel_agent.py:45-63,128-184` | high | Agent comparison |
| C-005 | FACT | Vikrambhat 的主行程函数使用一次 Ollama 调用并返回字符串。 | `../open-source-travel-planners-2026/sources/vikrambhat2/generate_itinerary.py:5-16` | high | Agent comparison |
| C-006 | FACT | Adrit CrewAI 在 `Process.sequential` 中创建 7 个 agent 和 9 个任务，最终由 Trip Planner 汇总。 | `../open-source-travel-planners-2026/sources/adrit/main.py:11-130`; `../open-source-travel-planners-2026/sources/adrit/agents.py:69-176` | high | Agent comparison |
| C-007 | FACT | Shaheen 的公开 agent 代码把网页/文章/图片研究、航班/天气工具和无工具的报告 Agent 分开。 | `../open-source-travel-planners-2026/sources/shaheen/web_research_agent.py:12-26`; `travel_agent.py:11-24`; `reporter_agent.py:7-20` | high | Agent comparison |
| C-008 | FACT | Skywain 把 plan JSON 作为渲染、地图链接、KML 和清单的共同输入，并要求在交付前执行自检和 lint。 | `../open-source-travel-planners-2026/sources/skywain/output-template.md:9-46,364-424`; `phase-6-assemble.md:31-108` | high | Display comparison |
| C-009 | FACT | JourneyJolt 把酒店和地点作为带图片/评分/价格/地图入口的独立视觉模块。 | `../open-source-travel-planners-2026/sources/journey-jolt/Hotelcard.jsx`; `Placescard.jsx`; `Hotels.jsx`; `Places.jsx` | medium | Display comparison |
| C-010 | FACT | Tour Pass 已有一次轻量骨架模型调用、Provider enrichment、确定性时间轴和 HardValidator。 | `trip_agent/loop.py`; `trip_agent/workflow.py`; `trip_agent/validation.py`; `README.md:26-51` | high | Tour Pass |
| C-011 | FACT | 当前 Tour Pass 桌面截图同时显示输入侧栏和完整结果，手机截图将输入工作台排在结果之前。 | `output/playwright/tour-pass-comparison-1365.png`; `output/playwright/tour-pass-comparison-390.png`; `trip_agent/static/index.html:14-138` | high | Display diagnosis |
| C-012 | INFERENCE | 只做行程规划时，一个规划 Agent + 程序化证据/排程比多角色 Crew 更符合范围和稳定性要求。 | C-001 + C-004 + C-006 + C-010 | medium | Thesis |
| C-013 | INFERENCE | Tour Pass 当前最需要的是“规划模式 → 旅行手册模式”的界面切换，而不是继续堆叠 Agent 状态和完整度信息。 | C-003 + C-008 + C-009 + C-011 | medium | Display diagnosis |
| C-014 | OPINION | 结果首屏只应优先显示目的地、路线摘要、当天/第一天、下一步动作和可信状态；证据、预算、预约放到可展开附录。 | usability criteria: scanability, actionability, trust | medium | Display plan |
| C-015 | OPEN | 单 Agent 与多 Agent 在相同模型、Provider 和测试集下的质量/延迟差异尚未实测。 | `open-questions.md:OQ-001` | low | Limitations |
| C-016 | OPEN | 当前参考图片的确切尺寸、字体、图片比例和布局规则不在本地快照中。 | `open-questions.md:OQ-004` | low | Limitations |
