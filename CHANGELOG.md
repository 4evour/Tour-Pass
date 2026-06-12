## 2026-06-11 23:30 - 多Agent架构重构初始化

### 变更内容
- 保存当前工作进度到 main 分支
- 创建 v1.0-legacy Tag 标记旧架构版本
- 创建 feat/multi-agent-refactor 分支
- 实现 LangGraph 多Agent协作架构

### 新增文件
- `agents/state.py`: 共享状态定义（TourState、数据模型）
- `agents/base.py`: Agent 基类
- `agents/intent_agent.py`: 意图解析 Agent
- `agents/poi_agent.py`: 景点推荐 Agent
- `agents/hotel_agent.py`: 酒店选择 Agent
- `agents/weather_agent.py`: 天气查询 Agent
- `agents/restaurant_agent.py`: 餐厅推荐 Agent（本地数据）
- `agents/scheduler_agent.py`: 行程规划 Agent
- `agents/reviewer_agent.py`: 约束审查 Agent
- `agents/ticket_agent.py`: 门票信息 Agent
- `graph.py`: 主图构建
- `main_multi_agent.py`: 入口文件
- `requirements-multi-agent.txt`: 新依赖

### 原因
旧架构（单Agent评分系统）存在三大问题：
1. 评分固化：冷门景点反复推荐
2. LLM不听指令：必去景点被忽略
3. 约束难维护：5层保护链过于复杂

### 影响范围
- 新架构与旧架构并存，可通过分支切换
- main 分支保留旧代码
- feat/multi-agent-refactor 分支开发新架构
- 后续可接入大众点评和抖音团购

### Git 操作
- 提交当前修改到 main: a26b328
- 创建 Tag: v1.0-legacy
- 创建分支: feat/multi-agent-refactor
- 首次提交: e878b6e

## 2026-06-12 16:00 - 前端集成 + 景点评分优化

### 变更内容
- **vite.config.ts**: 移除 /editor 代理（与 ase: '/editor/' 冲突），新增 /agent 代理转发到 8001 端口
- **AgentChat.tsx**: 修复 SSE 事件类型匹配，后端发送 itinerary 前端现可正确识别
- **AgentToolStatus.tsx**: 新增多 agent 事件图标（pois_found, schedule_created, weather_checked, restaurant_found 等）
- **tools/scoring.py**: 新增购物降权逻辑，非购物行程中商场类景点降权 -35 分

### 原因
- Vite /editor 代理与 base path 冲突导致 500 错误
- 后端发送 	ype: "itinerary" 但前端只识别 itinerary_complete
- 太古汇/正佳广场等商场因 popularity=4.9 排在广州塔/白云山前面

### 影响范围
- 前端开发服务器正常启动
- AI 聊天窗口可正确生成并展示行程
- 景点推荐从商场变为真正的旅游景点（广州博物馆、花城广场、中山纪念堂等）
