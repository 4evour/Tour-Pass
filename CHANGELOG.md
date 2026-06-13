# CHANGELOG

## 2026-06-13 - 管理后台 POI 数据管理

### 变更内容
- include/tourpass/graph.h + src/graph.cpp — PoiGraph 新增 indMutablePoi(id) 方法，返回可变 POI 指针
- include/tourpass/models.h + src/models.cpp — 新增 poiToJson() 序列化函数，将 Poi 对象转为完整 JSON
- include/tourpass/data_loader.h + src/data_loader.cpp — 新增 savePois(path, pois) 函数，将 POI 数据写回 JSON 文件并保留原始 JSON 中的额外字段（source, source_id, _angle 等）
- include/tourpass/api.h — CityBundle 新增 poisPath 字段，记录城市 POI 数据文件路径
- src/main.cpp — 加载城市数据时设置 undle->poisPath
- src/api.cpp — 新增 4 个管理员 API 端点：
  - GET /admin/pois — 分页列表，支持城市/类型/关键词筛选
  - GET /admin/pois/:id — 单个 POI 详情
  - PUT /admin/pois/:id — 更新 POI 所有字段并写回磁盘
  - PUT /admin/pois/:id/image — 快捷设置主图
- web/admin.html — 新增「🏔️ 景点管理」tab，包含 POI 列表、编辑弹窗、图片挑选器，以及配套 CSS 样式
- web/admin.js — 新增 POI 管理逻辑：城市切换、分页、搜索筛选、全字段编辑表单（含标签输入）、3 张高德图片对比挑选

### 原因
需要一个管理员页面来管理所有城市的景点 POI 数据，特别是从每张景点的 3 张高德爬取图片中挑选最适合展示的主图。

### 影响范围
- C++ 后端：PoiGraph、models、data_loader、api 四个模块均有改动，需重新编译
- 前端：admin.html 和 admin.js 新增大量代码，不影响现有用户端功能
- 数据安全：POI 修改后直接写回对应城市的 pois.json 文件，保留原始 JSON 中的额外字段
## 2026-06-13 16:35 - 高德照片批量下载（多 Key 轮换）

### 变更内容
- 修改 scripts/download_amap_photos.js：支持多 API Key 轮换、多城市批量爬取、按 POI 类型优先级排序
- 新增 API Key: 64ca7624c4f373ec3b123b2298b81019

### 原因
原脚本只支持单 Key + 单城市（广州），无法高效覆盖 20 个城市的 9154 个待爬 POI。多 Key 轮换可将日限额从 5000 提升到 10000。

### 影响范围
- data/*/pois.json：各城市 POI 将被补充 image_url 和 images 字段
- data/*/images/：新增照片文件
- output/amap-detail-cache/：API 响应缓存

## 2026-06-13 17:15 - 高德照片全量爬取完成

### 变更内容
- 20 个城市共 2354/8519 个 POI 成功获取照片（27.6% 成功率）
- 耗时 14 分钟（并发 5，双 Key 轮换）
- 各城市 data/{city}/pois.json 的 image_url 和 images 字段已更新
- 照片存储在 data/{city}/images/{poi_id}/ 下

### 原因
补充 POI 视觉数据，提升前端展示和用户体验。

### 影响范围
- 20 个城市 pois.json 已更新（约 28% 的 POI 获得照片）
- 剩余 72% 的 POI 在高德 Detail API 中无照片数据
## 2026-06-13 17:37 - 小红书旅游路线爬虫与提取工具

### 变更内容
- scripts/crawl_xhs_routes.js — 新增 API 方式路线爬虫，通过小红书搜索 API 搜索完整行程路线笔记，LLM 提取结构化路线数据，输出到 data/{city}/xhs_routes.json
- scripts/crawl_xhs_routes_browser.js — 新增 Playwright 浏览器方式路线爬虫，自动处理 cookie/鉴权，搜索路线相关笔记并提取内容
- scripts/extract_routes.py — 新增 Python 路线提取脚本，从已有 XHS 笔记数据中用 LLM 提取结构化行程路线，支持多城市批量处理
- data/guangzhou/xhs_routes.json — 从已有 191 条广州笔记中提取出 14 条完整路线

### 原因
当前打分机制限制了 agent 路线规划的合理性，需要真实的小红书行程路线数据作为大模型学习路线规划的训练样本。新工具聚焦于提取完整的多日行程路线（而非单景点 tips）。

### 影响范围
- 新增 scripts/ 下 3 个脚本，不影响现有功能
- data/guangzhou/xhs_routes.json 为新数据文件
- 现有 XHS cookie 已过期，API 方式爬虫需要刷新 cookie 才能使用
- 浏览器方式爬虫可自动处理鉴权，但需要 Playwright 环境
