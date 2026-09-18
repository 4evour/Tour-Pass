# Source State

- Repository: Tour Pass
- Local path: `D:/Tour Pass`
- Remote URL: 本地仓库未在本轮依赖远程提交；外部项目均使用 GitHub 官方仓库快照
- Branch/tag: `main`
- Commit: `4a41e26108d9946f7d2a4dcc9deb5b57b2d347e3`
- Research date: 2026-09-18 (Asia/Shanghai)
- Primary language: Python / FastAPI；前端为原生 HTML/CSS/JavaScript
- Requested audience: Tour Pass 产品与技术决策者
- Research question: GitHub 上开源旅游规划项目分别解决了哪些系统层问题？它们的优点、证据边界和运营成本是什么？Tour Pass 可以在哪些条件下形成可验证的优势？
- Explicit non-goals: 不做 stars 排名；不把 README 宣称当作运行结果；不评估商业闭源产品；不把外部项目的宣传性路线、价格或坐标当作已核验事实；本轮不修改生产代码。
- Local materials inspected: `README.md`、`trip_agent/workflow.py`、`trip_agent/validation.py`、`trip_agent/plan_output.py`、`trip_agent/store.py`、`research/tour-pass-agent-harness-reuse/`
- Official docs inspected: 各项目 GitHub README、架构文档、源码文件、测试/CI 目录（访问日期均为 2026-09-18）
- Competitors inspected:
  - OpenTripPlanner: `https://github.com/opentripplanner/OpenTripPlanner` @ `1b1177b7dc44cc2c5f89f18ad04076e99d608d23`
  - AWS personalized travel itinerary planner: `https://github.com/aws-samples/personalized-travel-itinerary-planner` @ `606f4839d27c20842ce97a6683d6cb43081a73d1`
  - Trip Planner CLI: `https://github.com/adl1995/trip-planner` @ `25ad2a88c0c108e4460bfec253bf17c8471c30d8`
  - Wanderlust: `https://github.com/danecjensen/mywanderlust` @ `ad6bf8372a94ea7548d51a771416354cc6a94ef8`
  - JourneyJolt: `https://github.com/satendra03/Journey-Jolt` @ `44c76d9cadb5de9bde003d0f79fa327b8a02c1b1`
  - AI Travel Planner: `https://github.com/zinedkaloc/ai-travel-planner` @ `0f2c9a94f6d61ad434815cdb329c397b92f92407`
  - Multi-Agent AI Travel Advisor v2: `https://github.com/kbhujbal/Multi-Agent-AI-Travel-Advisor` @ `235edddcefeb9200ba9aa5a716fcc1158fb19b61`

外部快照与关键源码摘录保存在本目录的 `sources/`、`*-README.md` 与 `*-tree.txt`，用于复核；快照通过 GitHub 官方 API 获取。GitHub stars 仅作为访问日的检索线索，未用于技术结论。
