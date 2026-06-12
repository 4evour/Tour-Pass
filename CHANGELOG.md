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

## 2026-06-12 20:30 - POI数据质量清理 + 广州图片升级

### 变更内容
- 20个城市POI数据清理: 删除子景点、购物中心、教育机构、酒店/度假区、电视台、全国连锁餐厅
- nightlife类型全部清除: 酒店删除, 餐厅/酒吧合并到restaurant类型
- 删除popularity=0和无source_id的低质量POI
- 广州图片升级: 删除180张旧小红书水印PNG, 下载600张高德官方JPG(200 POI x 3张)
- 交通POI精简: 1717个→134个, 每城市保留核心机场+火车站
- 新增脚本: download_amap_photos.js, filter_all_cities.py, filter_transit.py, clean_poi_data.py

### 原因
- 旧POI数据混入大量非旅游景点(商场、学校、连锁快餐), 影响推荐质量
- 广州图片来自小红书爬取, 有水印侵权风险且匹配不精准
- 交通POI过于碎片化(地铁站、公交站、进站口), 影响行程规划

### 影响范围
- data/*/pois.json: 所有20个城市的POI数据
- data/guangzhou/images/: 图片文件替换
- scripts/: 新增4个数据处理脚本
