# Source State

- Repository under comparison: Tour Pass at `D:/Tour Pass`
- Commit: `4a41e26108d9946f7d2a4dcc9deb5b57b2d347e3`
- Research date: 2026-09-18 (Asia/Shanghai)
- Question: 旅游规划 Agent 项目到底怎样组织模型、工具和结果页面？哪些做法适合一个只做“旅游行程规划”的轻量产品？
- Explicit non-goals: 不建设航班/库存/预订产业链；不按 Agent 数量排名；不把 README 的“实时/production-ready”当作运行证据；不复制复杂的多 Agent 角色体系。
- GitHub projects inspected at pinned commits:
  - `kbhujbal/Multi-Agent-AI-Travel-Advisor` @ `235edddcefeb9200ba9aa5a716fcc1158fb19b61`
  - `vikrambhat2/MultiAgents-with-Langgraph-TravelItineraryPlanner` @ `dbab3f1a27afc30345a7eb8d082797522fa5ff43`
  - `AdritPal08/TravelPlanner-CrewAi-Agents-Streamlit` @ `fdf9f319ddf87317af49623c184587ac948d59b4`
  - `shaheennabi/Production-Ready-TripPlanner-Multi-AI-Agents-Project` @ `34625670fa5388d44c4b93fd608bd629f345703d`
  - `skywain/trip-planner-skill` @ `45832aeeed1b43625375644aab4635be81a016f4`
  - `satendra03/Journey-Jolt` @ `44c76d9cadb5de9bde003d0f79fa327b8a02c1b1`
  - `zinedkaloc/ai-travel-planner` @ `0f2c9a94f6d61ad434815cdb329c397b92f92407`
- Existing local evidence inspected: `trip_agent/workflow.py`, `trip_agent/loop.py`, `trip_agent/validation.py`, `trip_agent/plan_output.py`, `trip_agent/static/index.html`, `trip_agent/static/styles.css`, `trip_agent/static/app.js`, and screenshots under `output/playwright/`.
- Source snapshots reused from `../open-source-travel-planners-2026/`; additional Agent/frontend files are under that directory's `sources/`.
