# CHANGELOG

> **版本规范**: Major.架构变更 | Minor.新功能 | Patch.bug修复/数据更新
> 每次发版打对应 git tag（如 `git tag -a v2.1.0`）。

## 2026-07-02 14:15 - 补充架构图表版

### 变更内容 — 改了什么文件，具体改了什么
- docs/architecture-diagram.svg — 新增可直接打开和预览的 SVG 分层架构图，展示前端、C++ 主服务、Python 多 Agent、数据存储、外部服务和部署调用关系。
- docs/architecture-diagram.md — 在文档顶部嵌入 SVG 图表，并说明下方 Mermaid 作为可编辑源码保留。
- CHANGELOG.md — 追加本次文档变更记录。

### 原因 — 为什么要改
- 用户反馈原先输出不是图表形式；Mermaid 代码块在部分查看环境不会渲染，需要提供真正可视化的图表文件。

### 影响范围 — 改动影响了哪些功能/模块
- 仅影响架构文档展示方式，不影响 C++ 服务、Python Agent、前端页面、数据脚本、测试或部署行为。

## 2026-07-02 13:59 - 生成项目架构图

### 变更内容 — 改了什么文件，具体改了什么
- docs/architecture-diagram.md — 新增项目架构图文档，包含系统总览、核心请求链路、Python 多 Agent 工作流、C++ 主服务内部模块、数据生产消费和部署形态。
- CHANGELOG.md — 追加本次文档变更记录。

### 原因 — 为什么要改
- 用户要求生成该项目的架构图，需要基于当前代码入口和默认部署链路形成可查看、可维护的 Markdown/Mermaid 文档。

### 影响范围 — 改动影响了哪些功能/模块
- 仅影响项目文档，不影响 C++ 服务、Python Agent、前端页面、数据脚本、测试或部署行为。

## 2026-06-24 17:01 - 支持小红书截图 OCR 解析

### 变更内容 — 改了什么文件，具体改了什么
- web/index.html、web/app.js、web/styles.css — 将小红书解析入口改为“帖子全文 + 笔记截图”，新增多图上传、压缩预览、移除图片和 data URL 图集展示。
- api_multi_agent.py — `/api/xhs/parse` 支持 `imageDataUrls`，对上传截图调用百度 OCR，并把 OCR 文本并入后续 DeepSeek 结构化分析。
- tests/test_xhs_image_upload_markup.js、tests/xhs_upload_ocr_test.py、tests/test_xhs_markup.js — 增加上传控件、前端钩子、后端 OCR 输入校验和入口文案回归测试。

### 原因 — 为什么要改
- 当前接入的 DeepSeek 不具备识图能力，需要先用 OCR 把小红书截图中的路线文字提取出来，再交给 DeepSeek 做结构化解析。
- 直接解析小红书链接受登录态和平台限制影响较大，全文和截图输入更稳定，也不需要接触用户小红书 Cookie。

### 影响范围 — 改动影响了哪些功能/模块
- 影响侧栏“小红书解析”的输入方式、截图 OCR、结果图库展示和解析错误提示。
- 不改变用户登录、行程保存、编辑器导入、主 AI 规划流程，也不新增小红书账号登录态采集。

## 2026-06-24 16:19 - 支持小红书正文后备解析

### 变更内容 — 改了什么文件，具体改了什么
- tools/xhs_parser.py — 在没有可抓取小红书链接时，支持把输入内容作为粘贴的笔记正文返回给后续 AI 分析流程；当“正文 + 链接”里的链接不可读时，会回退使用正文。
- api_multi_agent.py — 将小红书解析输入限制放宽到 5000 字，并把提示改为支持链接或分享文案。
- web/index.html、web/app.js — 将小红书输入框和前端校验放宽到 5000 字，空输入提示改为“链接或分享文案”。
- tests/test_xhs_parser.py、tests/test_xhs_markup.js — 增加正文后备解析和输入长度回归测试。

### 原因 — 为什么要改
- 部分小红书笔记链接格式正确，但公开网页会返回“当前笔记暂时无法浏览”，无登录服务端无法读取正文。
- 页面已经提示用户可粘贴分享文案，但后端此前仍强制要求链接，导致后备路径不可用。

### 影响范围 — 改动影响了哪些功能/模块
- 影响“小红书解析”的输入解析和错误后的可恢复路径。
- 不改变图片抓取、行程保存、编辑器导入和主 AI 规划流程。

## 2026-06-24 15:48 - 修复小红书解析错误反馈与网关代理

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — 新增 `xhsErrorMessage`，把 FastAPI/Pydantic 对象型错误转换成可读文本，并用于解析和分析接口错误提示。
- src/api.cpp — 给 C++ 主服务补充 `/api/xhs/parse`、`/api/xhs/analyze`、`/api/xhs/proxy` 到 Python Agent 的代理路由。
- tools/xhs_parser.py — 识别“小红书 - 你访问的页面不见了”或无正文的公开页回退结果，返回明确的不可读取提示。
- tests/test_xhs_frontend_error_message.js、tests/test_xhs_agent_proxy_routes.js、tests/test_xhs_parser.py — 增加回归测试覆盖错误展示、网关代理和不可读取笔记提示。

### 原因 — 为什么要改
- 小红书解析失败时前端会把对象型错误直接显示为 `[object Object]`，用户无法判断是链接问题还是服务问题。
- 生产入口只暴露 C++ 主服务，XHS Python 接口没有经过主服务代理会导致解析请求无法稳定到达 Agent。
- 部分小红书链接格式正确但公开 SSR 页面拿不到正文，需要给用户明确反馈，而不是继续进入 LLM 分析。

### 影响范围 — 改动影响了哪些功能/模块
- 影响侧栏“小红书解析”的接口调用、错误提示和图片代理访问。
- 不改变行程保存结构、AI 规划主流程或已有 `/agent/*` 代理接口。

## 2026-06-24 14:54 - 修复侧栏路由面板首屏空白

### 变更内容 — 改了什么文件，具体改了什么
- web/index.html — 调整 `planPanel` 与 `.workspace` 的闭合位置，让“我的行程”“行程编辑器”“小红书解析”“个人中心”“联系我们”等路由面板都渲染在共享工作区内。
- tests/test_sidebar_hash_routing.js — 新增断言，检查侧栏切换后的目标面板位于 `.workspace` 内，并且顶部出现在首屏视口内。

### 原因 — 为什么要改
- 侧栏路由状态已切换成功，但非 AI 助手面板被错误放在 `.workspace` 外，导致内容被前面的工作区高度挤到首屏下方，看起来像空白页面。

### 影响范围 — 改动影响了哪些功能/模块
- 影响侧栏进入“我的行程”“行程编辑器”“小红书解析”“个人中心”“联系我们”等页面的首屏展示位置。
- 不改变小红书笔记解析、行程保存、编辑器 iframe 加载或 AI 规划业务逻辑。

## 2026-06-23 21:50 - 接入小红书解析侧边栏

### 变更内容 — 改了什么文件，具体改了什么
- web/index.html — 将 `xhsPanel` 占位页替换为完整小红书解析工作台 DOM，补齐输入区、步骤条、结果区、图库、时间线、编辑弹窗、灯箱和保存/编辑按钮。
- web/app.js — 新增 XHS 保存转换逻辑、解析按钮绑定、OCR 入口、地点编辑后的重绘修复，以及保存到主行程库和跳转编辑器的闭环。
- web/styles.css — 为 XHS 面板补充 OCR 选项样式，保持现有 `.xhs-*` 视觉体系一致。
- api_multi_agent.py — 给 `/api/xhs/parse`、`/api/xhs/analyze`、`/api/xhs/proxy` 补上 OCR 字段、输入限制、OCR 文本注入和图片 URL 校验。
- tools/xhs_parser.py — 强化小红书链接提取与 host allowlist 校验，防止非小红书地址进入解析流程。
- web/editor/src/NewEditorApp.tsx — 支持通过 `?tripId=` 直接导入已保存行程，方便从 XHS 结果页继续编辑。
- tests/test_xhs_markup.js、tests/test_xhs_save_transform.js、tests/test_xhs_parser.py、tests/test_editor_trip_deeplink.js — 新增/更新回归测试，覆盖 XHS 面板 DOM、保存转换、URL 校验和编辑器深链导入。

### 原因 — 为什么要改
- 原来的 `#/xhs` 只是占位页，实际的小红书解析 JS 已经存在但没有接上 DOM。
- 需要把解析结果真正纳入现有主行程库，才能在“我的行程/个人中心”里继续管理和分享。
- 小红书笔记输入和图片代理都属于外部输入，必须补上边界校验。

### 影响范围 — 改动影响了哪些功能/模块
- 影响侧边栏“小红书解析”入口、解析展示、地点编辑、保存和继续编辑流程。
- 影响 `/api/xhs/*` 解析链路与图片代理安全边界。
- 影响编辑器从保存行程导入的入口，但不改现有行程数据库结构。

## 2026-06-23 22:16 - 收紧小红书解析输出与代理

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — 将 XHS 类型统计卡片中的类型文本改为转义后输出。
- api_multi_agent.py — 收紧 `/api/xhs/proxy` 图片代理域名，只允许小红书 CDN 图片域名，不再放行泛小红书站点域名。

### 原因 — 为什么要改
- 解析结果来自外部内容，前端展示必须避免未转义文本进入 HTML。
- 图片代理只应该服务图片资源域名，避免代理范围过宽。

### 影响范围 — 改动影响了哪些功能/模块
- 影响小红书解析结果类型统计展示。
- 影响 `/api/xhs/proxy` 对非 CDN 小红书域名图片 URL 的拦截。

## 2026-06-23 22:21 - 保持小红书代理错误码

### 变更内容 — 改了什么文件，具体改了什么
- api_multi_agent.py — 让 `/api/xhs/proxy` 内部主动抛出的 `HTTPException` 原样返回，不再被通用异常处理包装成 502。
- tests/test_xhs_parser.py — 增加小红书图片代理 URL allowlist 覆盖，验证 CDN 放行、内网和普通页面域名拒绝。

### 原因 — 为什么要改
- 非法 URL 或禁止重定向属于客户端请求错误，应保留明确的 400 错误。

### 影响范围 — 改动影响了哪些功能/模块
- 影响小红书图片代理的错误响应状态码，不影响合法图片代理流程。
- 影响 XHS 解析安全边界的回归测试覆盖。

## v2.0.0 — 多Agent系统上线 (2026-06-16)

> **git tag**: `v2.0.0`
> **回退标记**: `v1.0-legacy`（单Agent版本）
>
> 核心变更：从单Agent管线迁移到 LangGraph 多Agent架构（9个专业Agent），
> 20城POI数据质量清洗，管理后台，R2图床支持，CI质量门禁。

## 2026-06-23 14:46 - 修复结构化表单城市默认选中

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — 结构化表单城市卡再次点击已选城市时会取消选择并清空 `formCity`；旧版城市卡默认城市逻辑不再作用于 `#formCityGrid`。
- tests/test_structured_form_city_selection.js — 新增浏览器回归测试，验证结构化表单不会默认选中长沙，且已选城市可再次点击取消。

### 原因 — 为什么要改
- `/cities` 返回默认城市长沙后，旧版城市卡初始化逻辑会给结构化表单里的长沙卡片加 `.active`，造成 UI 上默认必须选长沙。
- 结构化表单自身点击逻辑只支持选中，不支持反选，用户无法取消已选城市。

### 影响范围 — 改动影响了哪些功能/模块
- 影响 AI 智能规划页的结构化表单目的地城市选择。
- 不改变自然语言规划、后端 `/cities` 接口、城市数据或提交 payload 结构。

## 2026-06-23 14:32 - 修复行程图片初始切换失灵

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — 行程站点图片轮播在加载图片时记录当前目标 URL，延迟到达的旧图片 `load/error` 事件不再影响用户已切换到的新图片。
- web/styles.css — 将 `.agent-stop-noimg` 占位层固定覆盖在图片区域内，并禁用 pointer events，避免占位层遮挡左右切换按钮。
- tests/test_agent_stop_carousel_initial_click.js — 新增浏览器回归测试，模拟首图失败事件晚于用户首次点击“下一张”到达的竞态。

### 原因 — 为什么要改
- 用户刚进入行程结果、首张图片还在加载时点击左右切换，旧图片失败事件可能晚到并按当前索引处理，把新图误标为失败或显示占位，表现为首次切换失灵。

### 影响范围 — 改动影响了哪些功能/模块
- 影响行程结果页站点卡片图片轮播的初始点击、左右按钮和滑动切换。
- 不改变行程数据结构、图片 URL 来源、小红书解析 lightbox 或后端接口。

## 2026-06-23 14:18 - 清理长沙低价值景点 POI

### 变更内容 — 改了什么文件，具体改了什么
- data/changsha/pois.json — 移除 `浏阳河婚庆文化园`、`湖南省中医药研究院` 两个被标为景点的低旅游价值 POI。
- data/pois.json — 同步移除根目录长沙样例数据里的同名 POI，保持 C++ 演示数据与多 Agent 城市数据一致。
- data/changsha/edges.json、data/edges.json — 移除指向上述已删除 POI 的通勤边，避免数据校验出现悬空边。
- scripts/clean_pois.js — 将 `婚庆` 加入名称黑名单；已有 `研究院` 规则保持不变。
- tests/test_changsha_poi_quality.js — 新增长沙 POI 质量回归测试，阻止景点/夜游数据再次出现 `研究院`、`研究所`、`婚庆` 名称条目。

### 原因 — 为什么要改
- 当前长沙景点仍混入科研机构和婚庆园区，会降低路线规划结果质量。
- `湖南省中医药研究院` 已命中现有清洗规则但数据未被清掉；`浏阳河婚庆文化园` 需要补充名称黑名单防止后续导入回流。

### 影响范围 — 改动影响了哪些功能/模块
- 影响长沙 POI 候选集、POI 搜索、行程规划中的景点选择。
- 影响长沙 POI 图中与被删除地点相连的通勤边。
- 不改变评分算法、前端展示逻辑、后端接口结构或其他城市数据。

## 2026-06-23 14:00 - 修复侧栏 Hash 路由空白页

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — 将分享链接、个人中心加载并入统一 `applyRoute()` hash 路由流程，移除旧 `handleRoute()` 监听器对 `mainApp` 的额外显隐控制。
- tests/test_sidebar_hash_routing.js — 新增 Playwright 回归测试，覆盖左侧导航 `AI 助手`、`我的行程`、`路线规划`、`笔记解析`、`个人中心`、`联系我们` 的 panel 切换。

### 原因 — 为什么要改
- 旧 `handleRoute()` 仍把 `#/profile` 当作独立页面处理，会在统一 panel 路由已经切换到个人中心后隐藏主应用 shell，导致侧栏导航点击后出现空白页。
- 需要用浏览器级测试固定所有侧栏入口的 hash 路由行为，防止后续再次引入双路由冲突。

### 影响范围 — 改动影响了哪些功能/模块
- 影响主应用左侧侧栏的 hash 跳转、个人中心 panel 加载、分享链接加载。
- 不改变后端接口、鉴权逻辑、编辑器 iframe 地址或页面视觉样式。

## 2026-06-23 12:42 - 修复侧栏导航与编辑器嵌入

### 变更内容 — 改了什么文件，具体改了什么
- src/api.cpp — 将 `/editor` 路径响应的 `X-Frame-Options` 从全局 `DENY` 调整为 `SAMEORIGIN`，其余路径保持 `DENY`。
- web/app.js — 统一 `navigateTo` 路由函数，支持无前缀 route、带查询参数 route 和 `#/` hash，并让 `getRoute` 解析 hash 查询参数前的 route 名。

### 原因 — 为什么要改
- 生产环境点击侧栏“路线规划”后，编辑器 iframe 被 `X-Frame-Options: deny` 拦截，页面看起来没有正确跳转。
- 后续重复定义的 `navigateTo` 覆盖了前面的实现，导致 `editor?tripId=...` 这类程序化跳转不会自动补 `#/`，路由解析也不能识别带查询参数的编辑器页面。

### 影响范围 — 改动影响了哪些功能/模块
- 影响主应用左侧导航中的“路线规划”编辑器嵌入，以及“我的行程”进入编辑器、笔记解析导出到编辑器等同源内部跳转。
- 不放开外站嵌入权限；非 `/editor` 页面继续使用 `X-Frame-Options: DENY`。

## 2026-06-22 15:21 - 审阅同步后端改动并收敛必去匹配口径

### 变更内容 — 改了什么文件，具体改了什么
- tools/matching.py — 新增/整理必去景点匹配工具，使用精确名称、ID、受限长度的短词包含匹配。
- agents/poi_agent.py、agents/reviewer_agent.py、agents/scheduler_agent.py、agents/summary_agent.py、tools/scoring.py、tools/clustering.py — 将必去景点覆盖、补救、评分、聚类和总结报告改为统一匹配口径，避免短词误命中过长店铺名。
- api_multi_agent.py — 修复 `/agent/chat` 中 session 清理和 session 获取未 `await` 的问题。
- tools/weather_api.py、agents/weather_agent.py — 支持 7 天游天气接口、HTTP 状态检查和缺失天气数值兜底，避免 `None` 温度在 fallback 建议中触发比较错误。
- agents/constants.py — 城市数据目录不存在时输出非阻断 warning，便于定位不支持城市或目录映射问题。
- tests/test_multi_agent.py — 增加洪崖洞短词误匹配、天气缺失数值 fallback 的回归测试。

### 原因 — 为什么要改
- 外部同步改动已经引入了更严格的必去景点匹配和天气接口改进，但仍有后置调度、聚类、评分、总结层保留旧的 `mv in name` 逻辑，可能让“洪崖洞”继续误匹配到特产店/核雕店。
- `/agent/chat` 使用异步 session store 时必须 await，否则运行时会拿到 coroutine 对象。
- 天气接口允许真实 API 字段缺失后，下游 fallback 需要接受 `None` 数值。

### 影响范围 — 改动影响了哪些功能/模块
- 影响必去景点保留、缺失必去补救、行程审核、总结中的必去覆盖报告，以及 POI 评分与聚类。
- 影响聊天修改行程接口的 session 获取路径。
- 影响真实天气数据解析和天气建议 fallback；不改变天气 API 对外字段结构。

## 2026-06-22 15:21 - 前端行程状态改为本地 7 天保留

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — 将生成后的候选行程、当前方案索引、表单 payload、当前阶段、保存状态从 `sessionStorage` 改为 `localStorage`，并记录 `tp_trip_ts`。
- web/app.js — 恢复行程时检查 7 天 TTL，过期则清理本地行程状态。

### 原因 — 为什么要改
- 用户刷新页面或关闭浏览器后，游客行程需要在本机短期保留，避免结构化表单生成后页面状态丢失。

### 影响范围 — 改动影响了哪些功能/模块
- 影响前端行程恢复和游客本地状态保留；登录 token 与 agent session id 仍沿用原有存储方式。

## 2026-06-22 14:31 - 提升 21 城真实高德路线边到生产数据

### 变更内容 — 改了什么文件，具体改了什么
- data/*/edges.json — 将 `output/data-routes-staging` 中已审计通过的 21 城路线边复制到生产 `data/`，覆盖原先低 AMap 覆盖率的生产边文件。
- docs/itinerary_quality_completion_plan.md、docs/real_route_planning_plan.md — 更新状态，记录生产 `data/{city}/edges.json` 已替换为 staging 验证后的 100% AMap 覆盖路线边，并记录默认 `data/` 口径的 Qingdao/Chongqing deterministic smoke 与 live API smoke 已通过。
- CHANGELOG.md — 记录本次生产数据提升。

### 原因 — 为什么要改
- Docker/Render 部署只复制 `data/`，不会复制 `.gitignore` 和 `.dockerignore` 中排除的 `output/`；如果不提升生产数据，线上仍会读取旧的低覆盖率 `data/{city}/edges.json`。
- 本地 staging 路线审计、确定性 Qingdao/Chongqing 行程 smoke、Qingdao/Chongqing live API staging smoke 和浏览器回归均已通过，可以进入生产数据文件。

### 影响范围 — 改动影响了哪些功能/模块
- 影响线上和本地默认数据根 `data/` 下的路线时间、距离、来源和调度可行性判断。
- 不改变 POI、图片、酒店、餐厅数据；不改变 API 字段结构。
- 部署后无需额外设置 `TOUR_PASS_DATA_DIR` 即可使用新的真实高德边。

## 2026-06-22 14:15 - 修复酒店区域匹配和酒店往返通勤门禁

### 变更内容 — 改了什么文件，具体改了什么
- agents/hotel_agent.py — 酒店区域过滤从只匹配 `area` 扩展为匹配酒店 `area/name/address/description/recommendation/tags`，使“解放碑”等商圈偏好能命中名称或标签中包含该商圈的酒店。
- agents/scheduler_agent.py — 新增酒店到首站、末站回酒店的通勤可行性过滤；真实边存在时优先使用真实时间，缺少酒店腿真实边时用估算距离兜底，超过节奏通勤阈值的可选首末站会进入 `replacement_pool`，必去点仍保留。
- agents/scheduler_agent.py — 当远距首末站过滤后某一天变为空白时，会从酒店附近可行候选中补入一个景点作为种子，再继续使用真实边补充相邻景点。
- scripts/smoke_itinerary_quality.py — 确定性 smoke 的酒店选择支持 `hotel_area`，重庆默认 smoke 场景使用“解放碑”作为酒店区域，避免测试脚本绕过 HotelAgent 商圈逻辑选到远区酒店。
- tests/test_multi_agent.py — 增加酒店商圈匹配回归测试，酒店到首站/回酒店远距可选点进入替换池的调度回归测试，空白天从酒店附近补点的回归测试，以及 smoke 脚本酒店区域选择回归测试。
- docs/itinerary_quality_completion_plan.md、docs/real_route_planning_plan.md — 更新当前验证状态，记录 Qingdao/Chongqing deterministic staging smoke、新的 Qingdao/Chongqing live API staging smoke、酒店区域/酒店往返通勤门禁和空白天补点状态。

### 原因 — 为什么要改
- 重庆 live API staging smoke 发现用户填写“解放碑”后仍选到秀山火车站酒店，根因是酒店数据的 `area` 多为行政区，商圈只存在于名称、标签或描述中。
- 同一 smoke 发现奉节县白帝城可作为单点行程绕过景点间路线检查，根因是系统只计算同一天景点之间的边，没有检查酒店出发和返程通勤。
- 首轮酒店通勤门禁修复后，重庆 live API staging smoke 进一步发现远距点被移除后会留下空白天，需要围绕酒店附近重新补入可行景点，避免行程过空。
- 确定性 itinerary smoke 使用自己的酒店选择逻辑，原本按全城热度选酒店，会绕过商圈偏好并复现远区酒店问题。
- 计划文档中的 smoke 结果和未完成项已经落后于当前验证状态，需要同步真实证据，避免后续按旧状态推进。

### 影响范围 — 改动影响了哪些功能/模块
- 影响 HotelAgent 的候选酒店过滤，用户填写商圈/片区时会更优先选择对应商圈酒店；未填写区域时行为不变。
- 影响 Scheduler 在有选定酒店时的首末站保留规则，减少跨区远点单点行程进入主行程；酒店腿缺真实边但估算距离很近的点仍可保留。
- 影响 Scheduler 的补点策略：空白天会优先从酒店附近候选恢复基本景点密度，后续相邻补点仍受真实路线边和通勤阈值约束。
- 影响 `quality:itinerary-smoke` 的重庆默认验证输入，使其更接近结构化表单里填写酒店区域后的真实规划路径。
- 影响项目计划文档的状态描述，不改变运行时代码行为。
- 不改变 API 响应字段结构，仍通过既有 `replacement_pool` 暴露被移除的可替换 POI。

## 2026-06-21 23:20 - 允许 API 使用 staging 路线数据

### 变更内容 — 改了什么文件，具体改了什么
- graph.py — `create_initial_state` 和 `create_initial_state_from_intent` 支持传入自定义 `data_dir`，默认仍为 `data`。
- api_multi_agent.py — API 读取 `TOUR_PASS_DATA_DIR` 或 `DATA_DIR` 环境变量作为路线/POI 数据根，并在普通流式规划、同步规划、结构化规划和多候选规划入口都传入初始 graph state。
- agents/state.py — 在 LangGraph 共享 `TourState` schema 中声明 `data_dir`，避免 graph 执行时丢弃自定义数据根。
- agents/poi_agent.py — 模糊必去词只保护非低质量 POI；用户写“洪崖洞”时，不再保留名称同含洪崖洞的特产店、礼品店、商业店铺等误分类景点，精确点名的 POI 仍保留。
- agents/scheduler_agent.py — 补点逻辑支持在晚间锚点前插入有真实高德边且时间可容纳的白天景点；补点候选即使描述含“夜景”，也可按白天时间插入，避免夜市/夜景单独占满整天。
- web/app.js — 旧版 `logoutBtn` 不存在时不再直接调用 `addEventListener`；反馈组件不存在时跳过 `initFeedback`；旧版 `serviceStatus` 和 `userBadge` 节点不存在时跳过对应写入，避免页面初始化在旧 DOM 绑定阶段中断。
- scripts/verify_agent_image_carousel.js — 结构化表单验证从旧 `<select id="formCity">` 操作改为点击当前城市卡片 UI；替换列表验证同步写入 `sessionStorage` 中的 session id，并等待 `/agent/modify` 响应，匹配真实会话恢复逻辑。
- tests/test_multi_agent.py — 增加 graph 初始状态自定义 `data_dir` 的回归测试，验证 `TourState` schema 声明 `data_dir`，验证多候选规划入口会把配置的数据根传入初始 state；覆盖晚间锚点前可补入真实边白天景点，以及模糊必去不保护低质量洪崖洞店铺。
- docs/itinerary_quality_completion_plan.md、docs/real_route_planning_plan.md — 记录 API 本地 smoke 可通过 `TOUR_PASS_DATA_DIR=output/data-routes-staging` 使用 staging 高德路线数据，并区分 API health smoke、mock 浏览器回归和后续完整 itinerary-generation smoke。

### 原因 — 为什么要改
- staging 路线数据已经达到 100% AMap 覆盖，但 API 初始 state 仍可能保留默认 `data`，导致调度器不能稳定读取 staging 路线边进行可行性判断。
- live API staging smoke 发现 `data_dir` 未声明在 `TourState` 中会被 LangGraph 丢弃，Scheduler 实际回退到默认 `data`，因此仍可能输出 `geo_estimated` 段。
- 重庆 live API staging smoke 发现洪崖洞夜间锚点可能独占一天，暴露“景点不够充分”的质量缺口。
- 重庆 live API staging smoke 发现“洪崖洞”作为 must_visit 会误保留洪崖洞特产店、核雕店、美食街等商业 POI。
- 需要先用 staging 数据验证 API/browser 效果，再决定是否替换生产 `data/{city}/edges.json`。
- 浏览器 smoke 发现首页早期初始化会因为缺失旧 `logoutBtn`、反馈组件、`serviceStatus` 和 `userBadge` 节点抛错，导致 `#mainApp` 一直隐藏，结构化表单和轮播验证无法进入。
- 前端验证脚本仍按旧结构化城市 select 操作，无法覆盖当前真实表单 UI。

### 影响范围 — 改动影响了哪些功能/模块
- 影响多 Agent API 的普通规划、结构化规划、同步规划和多候选规划入口；未设置环境变量时仍使用生产 `data`。
- 影响 Web 首页初始化稳定性；现有 `sidebarLogoutBtn` 退出逻辑不变。
- 不直接修改生产路线数据，不改变前端 API 响应结构。

## 2026-06-21 15:25 - 修复路线缓存隔离和高德批量缓存复用

### 变更内容 — 改了什么文件，具体改了什么
- tools/route.py — 将 `edges.json` 缓存 key 从单独城市名改为 `data_dir + city`，避免不同临时数据目录或不同数据根下的同名城市复用旧路线边。
- scripts/build_commute_edges.js — driving distance 批量请求在调用高德前先读取已有 `distance-{destination}-{offset}.json` 缓存，避免重跑城市刷新时重复请求同一批路线。
- scripts/promote_route_edges.js — 新增批量 staging promotion 工具，支持从 `data/` 和 `output/amap-{city}-routes-v2` 合并全城路线边，写入指定 staging 数据目录，支持 dry-run 和 aggregate manifest。
- scripts/audit_route_quality.js — 新增路线质量审计命令，按城市统计 AMap 覆盖、估算边数量、最长边列表，并支持 `--min-amap-ratio` 与 `--max-long-edge-minutes` 失败门槛。
- scripts/smoke_itinerary_quality.py — 新增确定性行程质量烟测命令，不调用 LLM，串起 PoiAgent、RestaurantAgent、SchedulerAgent 和 Reviewer hard checks，用 staging 路线数据验证真实行程是否仍含 estimated 段或高严重度问题。
- scripts/build_commute_edges.js — 修复模块被 `require` 时会抢先处理 `--help` 并退出的问题，避免 `fetch_real_route_pairs.js --help` 显示错误脚本说明。
- agents/scheduler_agent.py — 显式 `data_dir` 规划状态下，将缺少预计算真实路线边的相邻站点视为不可行；可选站点自动移入 `replacement_pool`，必去点会优先通过移除前一个可选点避免 estimated 段，并从 `available_pois` 里补入有真实高德边且不过通勤门槛的候选景点。
- graph.py — 初始 graph state 增加 `data_dir: "data"`，让线上结构化规划和普通规划的 Scheduler 能使用同一路线数据根。
- package.json — 新增 `real:promote-routes`、`real:audit-routes` 和 `quality:itinerary-smoke` 脚本入口。
- tests/test_multi_agent.py — 新增 Scheduler 回归测试，覆盖缺真实边的可选点进入替换池、必去点通过移除前置可选点避免 estimated 段、删除缺边点后可补入真实边候选，以及 smoke 脚本可在 staging-like fixture 上通过；新增 graph 初始状态携带 `data_dir` 的断言。
- tests/test_amap_pipeline.js — 新增离线回归测试，验证 driving distance 缓存存在时不会触发网络请求；新增批量 staging promotion 测试，验证 dry-run 不写边文件、正式运行会复制 POI 并写入合并后的 AMap 边；新增默认城市发现会忽略 `chromadb` 等非城市目录的测试；新增路线质量审计测试和 `fetch_real_route_pairs.js --help` 回归测试。
- docs/itinerary_quality_completion_plan.md、docs/real_route_planning_plan.md — 更新多城市 routes-v2 刷新和 staging promotion 状态：21 个支持城市均已生成 driving 高德边，合计 49,417 条刷新边；staging 合并后 49,450 条边，其中替换 17,287 条、插入 32,130 条；定向补采大理 1 条剩余 estimated 边后，staging 21 城 AMap 覆盖达到 100%，生产 `data/` 未覆盖。
- docs/itinerary_quality_completion_plan.md、docs/real_route_planning_plan.md — 记录确定性 Qingdao/Chongqing staging 行程烟测结果：两城均为 0 estimated 段、0 高严重度阻塞问题；同时保留生产数据尚未覆盖、部署 URL 尚未验证的待办。
- output/amap-changsha-routes-v2、output/amap-dali-routes-v2、output/amap-kunming-routes-v2、output/amap-lijiang-routes-v2、output/amap-sanya-routes-v2、output/amap-zhangjiajie-routes-v2 — 补齐剩余城市真实 driving 边刷新输出，不覆盖生产 `data/`。
- output/route_promotion_dry_run_manifest.json、output/route_promotion_manifest.json、output/data-routes-staging — 生成 21 城路线边 dry-run 和 staging 合并结果，不改变生产 `data/`。
- output/dali_route_pair_patch_pairs.json、output/dali_route_pair_patch_edges.json、output/dali_route_pair_patch_manifest.json、output/dali_route_pair_patch_merge_manifest.json — 定向补采并合并大理 `小河淌水温泉水世界乐园 -> 文华公园` driving 高德边，替换 staging 中最后 1 条 `geo_estimated` 边。
- output/route_quality_audit_staging.json — 生成 staging 路线质量审计报告，21 城最低 AMap 覆盖 100%，staging `output/data-routes-staging` 不再包含 estimated 路线边。
- output/itinerary_quality_smoke_staging.json — 生成 Qingdao/Chongqing staging 行程烟测报告，Qingdao 7 个站点、4 条 AMap 段、0 条 estimated 段、3 个替换候选；Chongqing 5 个站点、2 条 AMap 段、0 条 estimated 段、5 个替换候选。

### 原因 — 为什么要改
- 完整 Python 回归测试中，前一个测试加载了 `metriccity` 的 5 分钟路线边，后一个测试使用另一个临时 `data_dir` 下同名城市的 9 分钟高德边时仍读到旧缓存，导致真实路线判断不稳定。
- 多城市真实边刷新过程中出现 QPS 限流；脚本原本只给 walking batch 做缓存读取，driving batch 重跑会重复打高德，拖慢补采并增加限流概率。
- 用户要求继续昨天未完成任务；多城市真实路线数据是后续判断行程是否可行的基础。
- 刷新数据进入生产前需要可审计的 staging 合并和质量门槛，不能直接覆盖 `data/`。
- Qingdao/Chongqing staging 烟测显示仅补齐路线边还不够；调度器必须把“没有真实高德边”当作不可行条件，否则仍会在规划时使用 estimated 路段。
- 大理 staging 审计仍有 1 条 estimated 边，会阻碍生产 promotion 前的 100% 真实路线覆盖门槛。

### 影响范围 — 改动影响了哪些功能/模块
- 影响 `load_edges_cache`、`get_route_metric`、`calculate_route_segments` 和所有依赖 `edges.json` 的路线时间读取。
- 影响 `build_commute_edges.js` 的 driving route refresh 重跑行为；不改变路线边文件格式，只减少重复网络请求。
- 影响 Scheduler 在显式路线数据根下的站点保留规则：缺真实边的可选站点会从 active stops 移到 replacement pool；同一天可用的真实边候选会被补入 active stops。
- 影响 graph 初始状态，新增 `data_dir` 字段用于让调度器读取正确路线数据根。
- 新增和更新的 `output/` 刷新产物与 staging 数据仍为离线准备数据，不会直接改变线上规划，直到后续显式替换生产 `data/`。

## 2026-06-21 00:50 - 接入夜间审核门禁和前端替换列表

### 变更内容 — 改了什么文件，具体改了什么
- agents/reviewer_agent.py — 新增夜间 POI 识别规则，夜市、夜景、夜游、夜生活、酒吧类 POI 如果被排到 18:00 前，会产生 `evening_poi_too_early` 高严重度问题；新增全天通勤预算门禁，超过 150 分钟会产生 `excessive_day_commute` 高严重度问题。
- api_multi_agent.py — `/agent/modify` 在替换、删除、重排和改时间后重新计算当天 `route_segments`、`total_travel_minutes` 和 `route_quality`，并保留 `data_dir` 以便会话修改继续使用同一数据目录。
- tests/test_multi_agent.py — 新增 Reviewer 回归测试，覆盖早上安排夜市会被拦截、晚上安排夜市不会误报，以及全天通勤 160 分钟会被标记、90 分钟不会误报；新增 API 回归测试，验证替换景点后会按真实边刷新通勤指标。
- web/app.js — Agent 行程卡片接入 `replacement_pool`，每个可替换站点显示替换按钮和候选列表；存在 session 时点击候选会调用 `/agent/modify` 并渲染服务端返回的重算路线，没有 session 时才本地预览。
- web/styles.css — 新增 Agent 替换按钮和候选列表样式。
- scripts/verify_agent_image_carousel.js — 新增浏览器验证，覆盖替换池候选渲染、点击替换后服务端返回高德通勤、图片轮播、结构化表单和通勤展示。
- docs/itinerary_quality_completion_plan.md、docs/real_route_planning_plan.md — 同步记录 Reviewer 夜间门禁、前端替换列表、南京、武汉、桂林和厦门真实边完成状态。

### 原因 — 为什么要改
- 用户反馈夜市仍会排到早上，并要求前端接入可替换景点列表。
- 后端已经生成 day-level `replacement_pool`，但页面没有暴露，用户无法看到被自动移除的可替换 POI。

### 影响范围 — 改动影响了哪些功能/模块
- 影响多 Agent Reviewer 的确定性审核结果。
- 影响静态前端 Agent 行程卡片展示和替换景点交互；替换后会使用服务端重算后的通勤时间、距离和来源。
- 新增前端浏览器验证覆盖替换列表，不改变生产路线数据。
- 多城市真实边继续产出：南京 2257 条、武汉 2315 条、桂林 2857 条、厦门 2711 条，四城 AMap 覆盖均为 100%；并发期间出现 QPS 等待，后续爬取应控制请求密度。

## 2026-06-21 00:27 - 增加路线边合并脚本并继续多城市爬取

### 变更内容 — 改了什么文件，具体改了什么
- scripts/merge_route_edges.js — 新增路线边合并脚本，支持将刷新后的 AMap 边合并到现有 edges 副本，优先用 `provider=amap` 替换 `geo_estimated`，并输出 manifest。
- package.json — 新增 `real:merge-edges` 脚本入口。
- tests/test_amap_pipeline.js — 增加 merge route edges 回归测试，验证同一 pair 的估算边会被 AMap 边替换，并记录 replaced/inserted/edge_count。
- docs/itinerary_quality_completion_plan.md — 更新真实边爬取进度，记录上海、广州、杭州、西安已完成试爬，并记录大 batch 不稳定时使用 `--batch-size 25` 重试。
- docs/real_route_planning_plan.md — 更新 route edge merge workflow 和多城市爬取任务状态。
- output/amap-shanghai-routes-v2、output/amap-guangzhou-routes-v2、output/amap-hangzhou-routes-v2、output/amap-xian-routes-v2 — 运行产物：继续试爬四城真实 driving 边，不覆盖生产数据。

### 原因 — 为什么要改
- 刷新后的真实高德边需要安全合并/提升为可用数据源，不能手工覆盖生产 `data/*/edges.json`。
- 用户要求在爬取数据时同步更新项目，因此继续推进多城市真实边试爬。

### 影响范围 — 改动影响了哪些功能/模块
- 影响真实路线数据工具链和 AMap pipeline 测试；不改变当前生产数据、不部署。
- 上海试爬产物：536 POI、2730 条 driving 边、AMap 覆盖 100%。
- 广州试爬产物：492 POI、2512 条 driving 边、AMap 覆盖 100%。
- 杭州试爬产物：478 POI、2425 条 driving 边、AMap 覆盖 100%。
- 西安试爬产物：494 POI、2567 条 driving 边、AMap 覆盖 100%。

## 2026-06-21 00:08 - 新增完整行程质量完成计划

### 变更内容 — 改了什么文件，具体改了什么
- docs/itinerary_quality_completion_plan.md — 新增完整行程质量完成计划，将此前反馈的图片轮播、结构化表单、真实路线、夜市时间、餐厅比例、低质量 POI、替换列表、多城市真实边和上线验证纳入同一目标。
- docs/real_route_planning_plan.md — 更新已完成/部分完成状态，避免继续把已经落地的 route metric、replacement_pool 和部分多城市爬取标记为未开始。
- CHANGELOG.md — 记录本次计划文档更新。

### 原因 — 为什么要改
- 用户明确指出不止景点之间路径会影响生成质量，要求阅读之前反馈并制定完整可行方案，持续完成。
- 原路线计划文档覆盖面过窄，需要新增上层质量计划作为持续推进依据。

### 影响范围 — 改动影响了哪些功能/模块
- 仅影响项目文档和后续执行计划，不改变运行时代码或数据。

## 2026-06-20 23:59 - 接入可选景点替换池与继续多城市真实边试爬

### 变更内容 — 改了什么文件，具体改了什么
- agents/scheduler_agent.py — 新增真实路线可行性过滤：可选 stop 超过按节奏配置的真实打车/估算通勤阈值时，会从当天 stops 移入 `replacement_pool`；用户必去 stop 即使很远也会保留。
- agents/scheduler_agent.py — `execute` 接入 `replacement_pool`，并支持从 state 读取 `data_dir`，方便后续使用刷新后的真实高德边数据。
- api_multi_agent.py — `convert_to_frontend_format` 透传每天的 `replacement_pool`，为前端景点切换列表提供数据入口。
- tests/test_multi_agent.py — 增加 Scheduler 可选远点移入替换池、必去远点保留、完整 execute 输出替换池、API 透传替换池的回归测试。
- output/amap-chengdu-routes-v2、output/amap-beijing-routes-v2 — 运行产物：使用 `neighbors=8` 和 `mode=driving` 继续试爬成都、北京真实高德边，不覆盖生产 `data/*/edges.json`。

### 原因 — 为什么要改
- 用户确认超限可选景点应自动移除，但要保存在景点切换列表里供用户替换。
- 真实路线时间不能只展示在前端，需要进入 Scheduler 的可行性判断。
- 用户允许爬取数据时同步更新项目，因此继续用多城市真实高德边验证近邻 8 稀疏图方案。

### 影响范围 — 改动影响了哪些功能/模块
- 影响 SchedulerAgent 的日程生成输出、API 前端格式转换和后续前端可替换景点列表数据。
- 不改变当前生产 `data/chengdu/edges.json`、`data/beijing/edges.json`，不自动部署。
- 成都试爬产物：444 POI、2298 条 driving 边、AMap 覆盖 100%。
- 北京试爬产物：428 POI、2179 条 driving 边、AMap 覆盖 100%。

## 2026-06-20 23:44 - 接入默认打车路线指标并试爬双城真实边

### 变更内容 — 改了什么文件，具体改了什么
- tools/route.py — 新增 `get_route_metric`，统一返回单段路线的分钟数、距离、来源、置信度和交通提示；真实高德边按默认打车优先读取 `taxi_minutes`。
- tools/route.py — `calculate_route_segments` 改为复用 `get_route_metric`，默认模式从步行估算切换为打车/驾车，避免前端继续展示公交或步行优先时间。
- tools/__init__.py — 导出 `get_route_metric`，供后续 Scheduler/Reviewer 接入路线可行性门禁。
- tests/test_multi_agent.py — 增加路线指标回归测试，覆盖真实高德打车边优先、缺边时标记 estimated、route segment 默认使用打车时间。
- output/amap-qingdao-routes-v2、output/amap-chongqing-routes-v2 — 运行产物：使用 `neighbors=8` 和 `mode=driving` 试爬青岛、重庆真实高德边，不覆盖生产 `data/*/edges.json`。

### 原因 — 为什么要改
- 用户确认默认交通方式按打车判断；现有 route segment 展示会优先使用 `transit_minutes`，与产品策略不一致。
- 后续 Scheduler/Reviewer 需要统一路线指标，不能各自读取不同字段或继续依赖地理估算。
- 用户同意先爬取真实数据看覆盖率，因此先用青岛、重庆验证近邻 8 稀疏边方案的实际命中情况。

### 影响范围 — 改动影响了哪些功能/模块
- 影响路线工具函数和前端展示所依赖的 `route_segments` 时间来源；后续计划会继续把该指标接入调度和审核。
- 不改变当前生产 `data/qingdao/edges.json`、`data/chongqing/edges.json`，不自动部署。
- 青岛试爬产物：473 POI、2467 条 driving 边、AMap 覆盖 100%。
- 重庆试爬产物：483 POI、2535 条 driving 边、AMap 覆盖 100%。

## 2026-06-20 23:32 - 确认替换列表与多城市爬取策略

### 变更内容 — 改了什么文件，具体改了什么
- docs/real_route_planning_plan.md — 确认前端需要接入景点替换列表，超限移除的可选 POI 仍进入替换池供用户切换。
- docs/real_route_planning_plan.md — 确认多城市真实高德边默认使用近邻数 8，小城市或 API 额度受限时可降到 6。
- docs/real_route_planning_plan.md — 将多城市上线门槛改为先爬取并输出每城 manifest，再按真实覆盖率决定是否补充 targeted route-pair patch。
- docs/real_route_planning_plan.md — 补充当前本地城市边覆盖基线：多数城市 AMap 边覆盖约 3%-8%，重庆、成都、北京等相对更高但仍需刷新。

### 原因 — 为什么要改
- 用户确认替换列表需要接前端，并接受近邻数建议。
- 用户指出全面爬取后如果仍然覆盖率不高，需要先看实际爬取结果再决定补救策略。

### 影响范围 — 改动影响了哪些功能/模块
- 仅影响真实路线规划文档，不改变当前运行逻辑、数据文件或部署行为。

## 2026-06-20 23:14 - 增加规划关键路线真实时间抓取工具

### 变更内容 — 改了什么文件，具体改了什么
- scripts/fetch_real_route_pairs.js — 新增显式 POI pair 的高德真实路线抓取工具，支持 driving/walking/mixed、mock 测试、缓存、manifest、`--require-all` 门禁，并输出可合并到 `edges.json` 的真实边补丁。
- scripts/build_commute_edges.js — 修复 mock 模式下没有读取单 pair 路线 fixture 的问题，使现有 AMap pipeline 测试可以真实验证路线 fixture 命中。
- tests/test_amap_pipeline.js — 增加显式 route pair 抓取的离线回归测试，验证 driving/walking 分钟、`source=amap` 和 `route_confidence=real`。
- package.json — 新增 `real:route-pairs` 脚本入口。
- output/qingdao-critical-route-pairs.json、output/qingdao-critical-route-edges.json — 运行产物：对青岛三条问题路线进行 live 高德试抓，不覆盖生产数据。

### 原因 — 为什么要改
- 当前规划阶段缺少真实路线时间闭环，导致无缓存边使用步行估算，无法可靠判断当天路线是否可行。需要先能低成本抓取“酒店、候选景点、相邻 stop、餐厅插入”这些规划关键 pair 的真实 ETA。

### 影响范围 — 改动影响了哪些功能/模块
- 影响真实路线数据采集工具链和 AMap pipeline 测试；不改变线上规划运行逻辑、不覆盖现有 `data/*/edges.json`。
- 为后续把真实路线时间接入 Scheduler/Reviewer 的硬门禁提供数据输入。

## 2026-06-20 19:47 - 限制跨区远餐厅进入当天行程

### 变更内容 — 改了什么文件，具体改了什么
- agents/restaurant_agent.py — 餐厅候选不再只返回全城评分前 `days * 5`，会在全城高分候选之外补充每个区域的代表餐厅，避免胶州等远区本地餐厅被市区高分餐厅挤出候选池。
- tools/clustering.py — 餐厅和 nightlife 分配增加按节奏区分的距离上限，balanced 默认 12km；超过上限的远餐厅不再为了填补用餐槽被强行放入当天。
- tests/test_multi_agent.py — 增加区域代表餐厅候选回归测试，以及跨区远餐厅不能硬塞进当天的聚类回归测试；调整“5km 外 fallback”测试为合理距离内 fallback。
- CHANGELOG.md — 记录本次跨区远餐厅修复。

### 原因 — 为什么要改
- 青岛行程中胶州当天会把城阳区“吕家庄夜市”和胶州市“李家河夜市”拼到一起，导致 32km 被估算为 386 分钟通勤。根因是餐厅候选池只看全城评分，胶州本地餐厅排名靠后未进入候选；聚类 fallback 又没有距离上限。

### 影响范围 — 改动影响了哪些功能/模块
- 影响 RestaurantAgent 的候选覆盖范围、Clustering 的餐厅/夜生活分配距离约束，以及多 Agent 行程中的餐厅就近选择。
- 不改变原始 POI 数据、景点打分、用户必去景点保留逻辑和前端通勤展示格式。

## 2026-06-20 19:41 - 修复夜市餐厅进入午餐时段

### 变更内容 — 改了什么文件，具体改了什么
- agents/scheduler_agent.py — 新增餐厅与用餐时段匹配逻辑，`_meal_period=dinner` 或名称/标签/描述命中夜市、夜景、夜生活等晚间特征的餐厅不再匹配午餐；美食优先且存在晚餐槽时仍可安排到晚餐。
- tests/test_multi_agent.py — 新增回归测试，覆盖普通行程不把“吕家庄夜市”安排到午餐，以及美食优先行程把普通餐厅放午餐、夜市放晚餐。
- CHANGELOG.md — 记录本次夜市餐厅排程修复。

### 原因 — 为什么要改
- “吕家庄夜市”在数据中属于 `restaurant`，不是 `nightlife`；旧的夜市晚间逻辑只覆盖景点排序，餐厅插入午餐时没有检查晚间属性，导致夜市仍可能出现在早上/午餐时段。

### 影响范围 — 改动影响了哪些功能/模块
- 影响 SchedulerAgent 的餐厅排程选择，尤其是夜市、夜生活、夜景类餐饮 POI 的午餐/晚餐分配。
- 不改变原始 POI 数据、RestaurantAgent 候选评分、景点排序和普通餐厅午餐安排。

## 2026-06-20 19:27 - 清理误提交的 Python 缓存文件

### 变更内容 — 改了什么文件，具体改了什么
- scripts/__pycache__/clean_poi_attractions.cpython-311.pyc — 从 Git 跟踪中移除误提交的 Python 字节码缓存文件。
- CHANGELOG.md — 记录本次仓库卫生清理。

### 原因 — 为什么要改
- `.pyc` 文件是 Python 自动生成的本地缓存，不包含需要维护的源码逻辑；仓库已经通过 `.gitignore` 忽略 `__pycache__/` 和 `*.pyc`，但该文件历史上已被跟踪，导致反复出现在 Git 状态中。

### 影响范围 — 改动影响了哪些功能/模块
- 仅影响 Git 仓库跟踪内容和本地缓存文件状态，不影响运行时代码、业务逻辑或线上功能。

## 2026-06-20 19:22 - 修复结构化表单代理 404 并减少默认餐厅数量

### 变更内容 — 改了什么文件，具体改了什么
- src/api.cpp — C++ 反代层新增 `POST /agent/plan-structured` 转发到 Python Agent，避免结构化表单提交在外层服务返回 404。
- scripts/verify_agent_proxy_routes.js — 新增静态回归验证，检查 C++ 代理层必须注册结构化表单规划路由。
- tools/clustering.py — 普通非美食优先行程每天默认只分配 1 个餐厅；只有美食/culinary 明确偏好时才分配 2 个餐厅。
- agents/scheduler_agent.py — 普通非美食优先行程默认只安排午餐；只有美食/culinary 明确偏好时才安排午餐和晚餐。
- tests/test_multi_agent.py — 增加普通 balanced 行程只分配/排程 1 个餐厅的回归测试，同时保留美食优先仍安排午餐和晚餐的覆盖。
- CHANGELOG.md — 记录本次结构化表单和餐厅数量修复。

### 原因 — 为什么要改
- Python Agent 已有 `/agent/plan-structured`，但线上入口通过 C++ 服务反代；C++ 代理未注册该路径时，结构化表单提交会在外层直接返回 404。
- 旧的 balanced 默认策略会每天安排午餐和晚餐两个餐厅，使普通观光行程被餐厅占比过高，弱化景点主线。

### 影响范围 — 改动影响了哪些功能/模块
- 影响线上结构化表单提交路径、C++ 到 Python Agent 的代理路由、多 Agent 聚类餐厅分配和 Scheduler 餐厅时间安排。
- 不改变 Python Agent `/agent/plan-structured` 业务接口、前端表单字段、餐厅候选质量过滤和美食优先行程的双餐安排。

## 2026-06-20 14:20 - 过滤误分类为景点的伴手礼小店

### 变更内容 — 改了什么文件，具体改了什么
- agents/poi_agent.py — 低价值 POI 过滤增加“伴手礼、纪念品、文创、冰箱贴、礼品、小店、专卖店、专营店、土特产、礼品饰品店”等单体零售小店特征；这类 POI 不再进入主景点候选，用户明确必去时仍保留。
- tests/test_multi_agent.py — 增加“哈哈Home(重庆解放碑步行街洪崖洞店)”类误分类文创伴手礼小店的回归测试，并覆盖购物兴趣下仍过滤单体小店、购物地标仍保留的场景。
- CHANGELOG.md — 记录本次 POI 质量过滤修复。

### 原因 — 为什么要改
- 重庆数据中“哈哈Home(重庆解放碑步行街洪崖洞店)”被采集为 `attraction`，但实际是文创/伴手礼小店；旧逻辑在用户有购物兴趣时会放过这类单体零售 POI，导致低质量“景点”进入行程。

### 影响范围 — 改动影响了哪些功能/模块
- 影响 PoiAgent 的景点候选过滤和多 Agent 行程的景点质量。
- 不改变原始 POI 数据、餐厅选择、夜间排程、用户明确必去 POI 的保留逻辑和前端展示结构。

## 2026-06-20 14:17 - 修复夜市抢占白天景点排程

### 变更内容 — 改了什么文件，具体改了什么
- agents/scheduler_agent.py — 新增当天景点排程顺序规则：同时存在白天景点和夜市/夜景类 POI 时，先安排白天景点，再保留 1 个夜间 POI 到当天末尾。
- tests/test_multi_agent.py — 增加夜市排在候选列表首位时仍保留白天景点的回归测试。
- CHANGELOG.md — 记录本次排程修复。

### 原因 — 为什么要改
- 夜市类 POI 固定到晚上后，如果它在候选景点顺序里排在前面，旧循环会先安排夜市并把 `current_time` 推到晚上，导致后续白天景点被当天结束时间截掉，出现一天只有餐厅和夜市的结果。

### 影响范围 — 改动影响了哪些功能/模块
- 影响多 Agent Scheduler 的当天景点排程顺序。
- 不改变餐厅数量策略、POI 数据、路线优化和前端展示结构。

## 2026-06-20 14:14 - 修复夜市夜景景点被排到早上

### 变更内容 — 改了什么文件，具体改了什么
- agents/scheduler_agent.py — 新增夜间 POI 识别规则，命中 `nightlife` 类型或名称/标签/描述/推荐语含“夜市、夜景、夜游、夜生活、酒吧”时，优先安排到 18:00 后；普通排程和必去补救注入都复用该规则。
- tests/test_multi_agent.py — 增加“洪崖洞夜市街区”普通排程和必去补救场景的回归测试。
- CHANGELOG.md — 记录本次夜间 POI 排程修复。

### 原因 — 为什么要改
- 重庆数据中“洪崖洞夜市街区”被标为 `attraction`，开放时间从 10:30 起；旧排程只按开放时间和路线顺序安排，且必去补救默认插入上午/下午，导致夜市类景点可能出现在早上。

### 影响范围 — 改动影响了哪些功能/模块
- 影响多 Agent Scheduler 对夜市、夜景、夜游、夜生活和酒吧类 POI 的时间安排。
- 不改变 POI 数据、路线优化、餐厅选择和前端展示结构。

## 2026-06-20 14:08 - 修复结构化表单点击被 CSP 拦截

### 变更内容 — 改了什么文件，具体改了什么
- web/index.html — 移除结构化表单切换按钮和提交按钮上的 inline `onclick`。
- web/app.js — 使用 `addEventListener` 绑定自然语言/结构化表单切换和结构化提交按钮；提交前清理旧结果并显示规划状态；加载遮罩和旧结果节点缺失时跳过对应 DOM 操作，避免提交被空节点异常中断。
- scripts/verify_agent_image_carousel.js — 本地验证服务增加与线上一致的 `script-src 'self'` CSP，并加入结构化表单切换、提交和结果渲染断言。
- CHANGELOG.md — 记录本次结构化表单修复。

### 原因 — 为什么要改
- 线上 CSP 禁止 inline event handler，浏览器拦截 `onclick="switchPlanMode('form')"` ，导致点击“结构化表单”没有反应。

### 影响范围 — 改动影响了哪些功能/模块
- 影响首页 AI 规划入口的自然语言/结构化表单切换与结构化表单提交。
- 不改变 Agent 规划接口、表单字段、排程逻辑和自然语言规划按钮。

## 2026-06-20 14:00 - 显示 Agent 站点间通勤时间和距离

### 变更内容 — 改了什么文件，具体改了什么
- api_multi_agent.py — `convert_to_frontend_format` 保留每个站点的 `travel_minutes_from_previous`、`distance_meters_from_previous`、`route_source`、`transport_hint`，并保留每日 `route_segments`、`total_travel_minutes`、`route_quality`。
- web/app.js — Agent 行程卡片从第二站开始显示“从上一站通勤 X 分钟 · Y km · 数据来源”。
- web/styles.css — 增加 Agent 通勤信息条样式，复用真实路线/估算路线配色。
- scripts/verify_agent_image_carousel.js — 增加 Agent 卡片通勤时间、距离和来源的浏览器渲染断言。
- tests/test_multi_agent.py — 增加转换层保留通勤字段的回归测试。
- CHANGELOG.md — 记录本次通勤信息显示修复。

### 原因 — 为什么要改
- Scheduler 已计算站点间通勤数据，但转换给前端时丢掉了相关字段；Agent 结果页也没有渲染通勤条，导致两个景点之间的通勤时间和距离不可见。

### 影响范围 — 改动影响了哪些功能/模块
- 影响多 Agent 结果页的站点卡片和 itinerary JSON 字段。
- 不改变路线计算、排程算法、POI 数据和普通规划卡片逻辑。

## 2026-06-20 13:54 - 修复 Agent 景点图片轮播失败图兜底

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — Agent 行程卡片图片轮播记录加载失败的图片索引；当前图片加载失败时自动尝试下一张可用图片，全部失败时才显示占位图。
- scripts/verify_agent_image_carousel.js — 增加首图 404 时自动切到下一张可用图、继续点击下一张仍能切换的回归验证。
- CHANGELOG.md — 记录本次轮播修复。

### 原因 — 为什么要改
- 线上景点图片区域可能遇到某张图片加载失败，旧逻辑只显示占位图，不会自动跳过坏图；用户点击左右按钮时如果切到的图片同样不可用，视觉上像轮播无法切换。

### 影响范围 — 改动影响了哪些功能/模块
- 影响多 Agent 结果页的景点/餐厅图片轮播展示。
- 不改变 Agent 行程生成、图片数据结构、POI 数据和普通规划卡片。

## 2026-06-20 13:30 - 修复天气 key alias CI 失败

### 变更内容 — 改了什么文件，具体改了什么
- tools/weather_api.py — 和风天气 key 与 API host 改为运行时读取当前环境变量，再回退到 `agents.config` 默认值；天气、生活指数和预警请求改为通过当前 host 动态生成 URL。
- CHANGELOG.md — 记录本次 CI 修复。

### 原因 — 为什么要改
- 最新 GitHub Actions 在 `test_weather_key_accepts_hefeng_aliases` 失败。根因是 CI 先导入 `api_multi_agent` 并缓存 `agents.config.QWEATHER_KEY`，后续测试只 reload `tools.weather_api` 时无法读到新设置的 `HEFENG_WEATHER_KEY`。

### 影响范围 — 改动影响了哪些功能/模块
- 修复测试环境和运行时动态配置天气 key/host 的一致性。
- 不改变 API 响应结构，不新增依赖。

## 2026-06-20 13:22 - 增加结构化规划和多轮行程会话

### 变更内容 — 改了什么文件，具体改了什么
- api_multi_agent.py — 新增结构化规划请求模型和 `/agent/plan-structured` SSE 接口；增加 session 存储、会话续接、`/agent/chat-session` 和 `/agent/modify` 行程局部修改能力；规划结果写入 session，便于后续对话修改。
- graph.py — 新增 `create_initial_state_from_intent`，允许结构化表单绕过 IntentAgent 解析；数据采集改为先跑 PoiAgent，再并行酒店/天气/餐厅，避免酒店与餐厅读取空 POI 状态。
- web/index.html — 增加“自然语言/结构化表单”切换和城市、天数、人群、侧重点、节奏、预算、必去、酒店预算、特殊要求等表单输入。
- web/app.js — 前端发送 `session_id`，新增结构化表单提交、多轮对话面板和行程局部修改调用。
- web/styles.css — 增加结构化表单、多轮对话面板和相关交互样式。
- web/editor/src/components/AgentChat.tsx — React 编辑器聊天组件支持 session_id、上下文历史和修改动作回写。
- web/editor-dist/ — 重新构建 React 编辑器静态产物，匹配 AgentChat 会话改动。
- CHANGELOG.md — 记录本次结构化规划和多轮会话变更。

### 原因 — 为什么要改
- 用户提到之前已有结构化表单输入，需要让多 Agent 生成逻辑直接消费明确的城市、天数、节奏、偏好和必去信息，减少自然语言解析误差；同时生成后需要能继续对话修改行程，而不是每次全量重跑。

### 影响范围 — 改动影响了哪些功能/模块
- 多 Agent API 新增结构化入口和会话状态，前端可在自然语言和表单规划间切换。
- 多轮对话可基于当前行程进行局部修改，后续可继续扩展为更完整的增量重排。
- 数据采集顺序改变：POI 成为酒店/餐厅/天气等下游 agent 的稳定输入。

## 2026-06-20 13:22 - 增强和风天气接入与天气感知排程

### 变更内容 — 改了什么文件，具体改了什么
- agent/.env.example — 增加 `QWEATHER_KEY` 和 `QWEATHER_API_HOST` 示例配置。
- agents/config.py — 统一读取和风天气 key、API host、天气预报、生活指数和灾害预警接口地址。
- tools/weather_api.py — 天气接口扩展为三类数据：每日天气、旅游/穿衣/紫外线等生活指数、灾害预警；补充安全数值转换和 21 城 location 映射。
- agents/weather_agent.py — 并发获取天气、生活指数和灾害预警；LLM 只基于真实数据生成建议，失败时使用规则兜底建议。
- agents/scheduler_agent.py — 根据降雨、紫外线、日出日落、恶劣天气和预警调整排程偏好、开始/结束时间和天气 SSE 提示。
- api_multi_agent.py — 转换前端行程时透出每日天气、天气严重程度、天气提醒和 `weather_available`。
- render.yaml — 为 Render 部署预留 `QWEATHER_KEY` secret 和 `QWEATHER_API_HOST` 默认值。
- CHANGELOG.md — 记录本次天气接入和天气感知排程变更。

### 原因 — 为什么要改
- 用户要求天气模块真实接入；原天气能力只覆盖基础预报，缺少生活指数、预警、日出日落和对排程的可解释影响。

### 影响范围 — 改动影响了哪些功能/模块
- WeatherAgent、SchedulerAgent、API 行程格式和前端可展示天气字段。
- Render 部署环境需要配置 `QWEATHER_KEY` 后才会启用真实和风天气。
- 没有配置和风天气 key 时仍返回明确占位数据，不让 LLM 编造天气。
- 高紫外线、雨天或恶劣天气会影响室内/室外 POI 排序和当天时间边界。

## 2026-06-20 00:47 - 增加 Reviewer 行程质量失败码

### 变更内容 — 改了什么文件，具体改了什么
- agents/reviewer_agent.py — hard-check 增加 `unsupported_poi`、`area_scattered`、`weak_last_day`、`meal_attraction_imbalance`、`excessive_commute_estimated`、`excessive_commute_confirmed` 等确定性失败码。
- tests/test_multi_agent.py — 新增 Reviewer 低质量 POI、跨区、长估算通勤、最后一天过空和餐厅景点失衡回归测试。
- CHANGELOG.md — 记录本次 Reviewer 失败码变更。

### 原因 — 为什么要改
- 多 Agent 回路需要稳定、可测试的质量信号，不能只依赖 LLM 审核文本；用户反馈的“小众 POI、跨区通勤、最后一天只有餐厅、景点餐厅不均衡”需要被 reviewer 明确识别。

### 影响范围 — 改动影响了哪些功能/模块
- ReviewerAgent 会在 `review_result.issues` 中输出更细粒度的质量问题。
- Scheduler 后续可继续消费这些失败码做自动补救。
- 不改变 LLM reviewer 提示格式和 API 响应结构。

## 2026-06-20 00:39 - 优化路线图高德导航展示

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — 新增高德导航 URL、路线 URL、通勤来源标签辅助函数；地图 popup、overview 小卡和详情卡支持点击高德导航；地图路线按 `amap_cached` 实线、估算段虚线展示；高德导航按钮复用统一 URL 生成逻辑。
- web/styles.css — 增加地图 popup 地址/导航、通勤来源 chip、详情卡高德链接样式。
- CHANGELOG.md — 记录本次路线图导航展示变更。

### 原因 — 为什么要改
- 用户要求导出的旅游路线图中对应景点地址可点击并能跳转高德导航，同时前端需要解释景点之间的通勤时间是否来自真实高德路径。

### 影响范围 — 改动影响了哪些功能/模块
- 行程 overview、详情页、地图 popup、打印导出和分享页中的 POI 导航链接。
- 地图路线视觉展示会区分真实缓存路径和估算路径。
- 不改变后端行程生成逻辑和 POI 数据。

## 2026-06-20 00:36 - 增加每日通勤分段来源

### 变更内容 — 改了什么文件，具体改了什么
- tools/route.py — 新增 `calculate_route_segments`，优先读取 `edges.json` 缓存路径，输出相邻 POI 的通勤分钟、路径来源、距离和交通提示，并写回后一站的通勤字段；`calculate_total_travel_time` 改为复用分段结果。
- agents/scheduler_agent.py — 每日最终 stops 排序后统一生成 `route_segments`、`total_travel_minutes` 和 `route_quality`，确保必去补救插入后的路线字段仍然准确。
- tests/test_multi_agent.py — 新增真实缓存路径优先和 Scheduler 日程路线字段回归断言。
- CHANGELOG.md — 记录本次通勤分段来源变更。

### 原因 — 为什么要改
- 用户要求行程展示景点之间的通勤时间，并明确区分是否参考高德真实路径；原逻辑只返回总通勤分钟，且未把真实/估算来源暴露给前端和 reviewer。

### 影响范围 — 改动影响了哪些功能/模块
- 多 Agent Scheduler 输出新增路线分段和路线质量统计。
- 前端可直接消费 `route_segments`、`route_source`、`distance_meters_from_previous` 展示真实/估算通勤。
- 旧调用仍可使用 `calculate_total_travel_time`，但结果会复用新的分段计算。

## 2026-06-20 00:32 - 增加 POI 主行程分层准入

### 变更内容 — 改了什么文件，具体改了什么
- tools/scoring.py — 新增 `classify_poi_tier` 和 `build_poi_evidence_sources`，将 POI 分为 `core_hotspot`、`route_supported`、`fallback_only`。
- agents/poi_agent.py — 为候选 POI 写入 `poi_tier`、`evidence_sources`、`image_missing`，并阻止 `fallback_only` 进入主行程候选。
- tests/test_multi_agent.py — 新增 POI 分层和 `PoiAgent` 主候选过滤回归测试。
- CHANGELOG.md — 记录本次 POI 分层准入变更。

### 原因 — 为什么要改
- 防止无热门证据、无真实路线证据的小众 POI 因普通评分加分进入主行程，提升多 Agent 行程真实性和稳定性。

### 影响范围 — 改动影响了哪些功能/模块
- 多 Agent POI 候选生成：主行程候选更严格。
- 调度器仍可通过 `available_pois` 访问 fallback 候选，用于必去兜底或后续替换。
- 前端和 reviewer 后续可消费 `poi_tier`、`evidence_sources`、`image_missing` 做解释和质量检查。

## 2026-06-20 00:25 - 设计多 Agent 行程质量闭环

### 变更内容 — 改了什么文件，具体改了什么
- docs/superpowers/specs/2026-06-20-agent-itinerary-quality-design.md — 新增多 Agent 行程质量设计文档，覆盖 POI 分层、节奏饱满度、同区通勤、Reviewer 失败码、旅游攻略证据接口、图片补全、前端展示和导出高德导航。
- CHANGELOG.md — 追加本次设计文档变更记录。

### 原因 — 为什么要改
- 当前多 Agent 行程仍会出现小众非景点、餐厅和景点分配不均、最后一天内容塌陷、路径可信度不足和前端解释不清的问题；需要先明确共享质量契约和后续实现边界。

### 影响范围 — 改动影响了哪些功能/模块
- 仅新增设计文档和变更记录，不改变运行时逻辑。
- 后续实施将影响多 Agent 生成链路、路径数据消费、前端结果页和路线图导出。

## 2026-06-18 19:54 - 忽略本地临时审计产物

### 变更内容 — 改了什么文件，具体改了什么
- .gitignore — 增加 `.qoder/`、根目录 `_debug/_fix/_test` 临时脚本、`audit_images.py`、`fix_network.bat`、本地 XHS 登录/cookie 辅助脚本、XHS 签名备份文件和本地 handoff 文档的忽略规则。
- CHANGELOG.md — 记录本次未跟踪文件审计后的忽略范围。

### 原因 — 为什么要改
- 未跟踪文件主要是生成文档、本机调试脚本、一次性补丁脚本、XHS 登录/cookie 辅助和备份文件，不属于正式多 Agent 规划质量修复；加入忽略规则可避免推送时误纳入。

### 影响范围 — 改动影响了哪些功能/模块
- 仅影响 Git 工作区清洁度和后续提交范围，不改变前端、后端、测试或运行时行为。

## 2026-06-18 19:41 - 收窄多 Agent 修复处理范围

### 变更内容 — 改了什么文件，具体改了什么
- CHANGELOG.md — 移除未跟踪交接文档对应的变更记录，只保留本次要处理的 6 个多 Agent 规划质量修复文件范围。

### 原因 — 为什么要改
- 用户明确要求先只确认/处理已完成的 6 个多 Agent 规划质量修复，后续 Tour-AI、LvBanGPT 等参考项目工作暂不处理。

### 影响范围 — 改动影响了哪些功能/模块
- 仅影响变更记录，不改变前端、后端、测试或运行时行为。

## 2026-06-18 17:28 - 优化餐饮数量、节奏解析和 XHS 排程约束

### 变更内容 — 改了什么文件，具体改了什么
- agents/intent_agent.py — 增加“紧凑/休闲”等节奏关键词解析；优化必去景点切分，避免把“颐和园/和平公园”这类含“和”的景点名拆坏。
- agents/poi_agent.py — 按节奏调整 POI 候选量，紧凑模式返回更多候选，给早上/下午/晚上安排留出足够景点池。
- tools/clustering.py — 餐厅分配从“只取 5km 内”改为近距离优先、不足时按评分和距离兜底补齐；景点分配在均衡天数时优先最近簇，远距离普通 POI 不再强行塞入无关日期。
- agents/scheduler_agent.py — 排程显式按节奏插入餐厅：休闲默认至少午餐，均衡/紧凑安排午餐和晚餐；紧凑模式锚定早上、下午、晚上景点时段；景点避开默认饭点；XHS 共现调整不再移动用户必去景点、不跨过距离阈值、不把紧凑日搬到少于 4 个景点。
- tests/test_multi_agent.py — 增加节奏解析、必去景点切分、餐厅兜底、紧凑日三时段、POI 候选量、地理聚类、XHS 必去/距离/密度保护等回归测试。
- CHANGELOG.md — 记录本次 AI 多Agent规划质量修复。

### 原因 — 为什么要改
- 用户反馈三天行程只推荐一家餐厅、紧凑/休闲诉求没有体现在排程里、明确要求的景点会漏排或被错误解析、行程会跨区混排，小红书攻略引用也需要确认是否被正确学习。排查发现根因包括：节奏未走正则 fast-path、中文“和”被简单切分、餐厅聚类缺少远距离兜底、排程把景点 `lunch` 时段误当成已吃午餐、紧凑模式候选 POI 不足，以及 XHS 共现交换过度移动景点。

### 影响范围 — 改动影响了哪些功能/模块
- AI 多Agent规划的 IntentAgent、PoiAgent、RestaurantAgent 聚类、SchedulerAgent 和 XHS 参考路线使用方式。
- 紧凑行程会更倾向早上/下午/晚上都有景点且午晚餐齐全；休闲行程减少景点数并保留基本用餐；小红书路线仍参与 POI 加权和同日微调，但不会覆盖用户必去和地理合理性。
- 不改变前端接口字段、不新增第三方依赖、不修改已预留的天气/酒店价格接口。

## 2026-06-18 17:08 - 修复 Agent 景点攻略文字裁剪

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — Agent 行程卡片的攻略文字不再用字符数判断是否显示“展开攻略”，改为渲染后根据真实 `scrollHeight`/`clientHeight` 判断文本是否被折叠，移动端换行后超高也会显示展开按钮。
- web/styles.css — Agent 攻略文字增加 `overflow-wrap` 和 `word-break`，确保长中文/混排文本在窄屏内自适应换行。
- scripts/verify_agent_image_carousel.js — 增加移动端窄屏长攻略文字回归检查，确保文字被截断时必须有展开控件。
- CHANGELOG.md — 记录本次 Agent 景点攻略文字排版修复。

### 原因 — 为什么要改
- 用户反馈景点描述文字在移动端卡片里没有自适应排版，部分文字看不到。根因是 CSS 固定 `max-height: 60px` 裁剪文本，而 JS 只按字符数大于 120 才显示展开按钮，未覆盖短文本在窄屏换行后高度超出的情况。

### 影响范围 — 改动影响了哪些功能/模块
- 首页 AI 多Agent 行程结果中的景点攻略文字展示。
- 不改变后端规划结果、图片轮播、推荐语去重或卡片数据结构。

## 2026-06-18 16:58 - 优化景点候选低价值 POI 过滤

### 变更内容 — 改了什么文件，具体改了什么
- agents/poi_agent.py — 将原先仅排除“会议中心/会展中心”的规则扩展为 `_is_low_value_poi`，普通行程过滤误标为景点的纯购物中心、培训机构、学校校区、写字楼/办公楼、产业园/科技园等低旅行价值 POI；用户明确必去时仍保留，用户有购物兴趣时保留购物类地标。
- tests/test_multi_agent.py — 增加低价值商业/教育/办公 POI 过滤、购物兴趣保留商场、必去指定保留低价值名称的回归测试。
- CHANGELOG.md — 记录本次景点筛选规则优化。

### 原因 — 为什么要改
- 用户反馈仍有不是真正景点的高分 POI 被筛入行程。排查发现数据源里不少商场、培训机构、校区、写字楼被标为 `attraction`，仅靠 type 和热度评分无法排除。

### 影响范围 — 改动影响了哪些功能/模块
- AI 多Agent规划的 PoiAgent 候选集合和后续行程景点质量。
- 默认旅游行程会更少出现纯商业/教育/办公类 POI；购物优先或用户明确必去的场所不受该过滤影响。

## 2026-06-18 16:34 - 优化模板提示词并预留第三方数据接口

### 变更内容 — 改了什么文件，具体改了什么
- web/index.html — 聊天框 placeholder 和快捷模板提示词改为包含城市、天数、必去景点、每晚酒店预算、偏好优先级和节奏等规划要素，帮助 AI 多Agent 更稳定解析用户意图。
- web/app.js — 热门行程模板的 `msg` 同步升级为结构化自然语言提示词，点击模板后直接生成更明确的旅行需求。
- scripts/verify_prompt_templates.js — 新增模板提示词回归检查，验证首页快捷提示和热门模板都覆盖预算、优先级、必去点等关键字段。
- tools/weather_api.py — 和风天气 key 兼容 `QWEATHER_KEY`、`QWEATHER_API_KEY`、`HEFENG_WEATHER_KEY`，并提供非敏感配置状态。
- tools/hotel_price_api.py、tools/__init__.py、agents/hotel_agent.py — 新增酒店价格 provider 边界；未配置时明确跳过，配置 `HOTEL_PRICE_*` 后可从第三方/自建适配服务拉取价格并合并进酒店候选；第三方返回非法价格时跳过价格字段，避免打断规划。
- docs/third_party_integrations.md — 记录和风天气、酒店价格供应商的可行性、环境变量和酒店价格适配器契约。
- tests/test_multi_agent.py — 增加和风天气 key 别名、酒店价格未配置状态、价格报价合并的回归测试。
- CHANGELOG.md — 记录本次模板和第三方接口预留改动。

### 原因 — 为什么要改
- 用户反馈模板提示词太泛，不利于根据“城市、天数、必去景点、酒店预算、偏好优先级”等信息稳定规划；同时希望后续能便捷接入酒店实时价格和已准备好的和风天气 API。
- 参考 Tour-AI 后确认“小红书内容导入→结构化解析→可视化行程”是值得借鉴的方向；本轮先落地当前架构最直接受益的结构化输入和外部数据接口边界。

### 影响范围 — 改动影响了哪些功能/模块
- 首页 AI 多Agent规划输入、快捷模板和热门模板。
- WeatherAgent 的真实天气数据配置兼容性。
- HotelAgent 的酒店价格数据来源预留；无酒店价格 provider 时不影响现有规划。
- 不引入新的前端页面，不直接复制 Tour-AI 代码；小红书帖子导入 UI 留作后续独立增量。

## 2026-06-18 15:39 - 移除首页手动规划入口

### 变更内容 — 改了什么文件，具体改了什么
- web/index.html — 移除首页“手动规划行程”链接，以及“手动设置偏好”折叠表单板块；保留 AI 多Agent规划输入框、快捷模板、关键词和结果区域。
- web/app.js — 表单、城市卡片、酒店选择器相关启动绑定改为元素存在时才启用；热门行程模板不再写入已移除的表单字段，改为直接填充聊天框并触发 AI 规划。
- scripts/verify_agent_image_carousel.js — 增加 Playwright 回归断言，验证首页不再出现手动规划入口/偏好表单，同时 AI 多Agent入口仍存在。
- CHANGELOG.md — 记录本次手动规划入口移除，并已在改动前推送回退标签 `manual-planner-before-removal-20260618`。

### 原因 — 为什么要改
- 用户反馈手动规划行程板块维护和优化成本过高，当前产品主流程应聚焦 AI 多Agent规划；移除前保留 git 标签，方便之后需要时按标签恢复。

### 影响范围 — 改动影响了哪些功能/模块
- 首页主界面不再展示手动规划入口或手动偏好表单。
- AI 多Agent聊天规划、快捷模板、关键词追加和 Agent 行程结果展示继续保留。
- 不删除 `web/editor` 源码和后端 editor API，避免扩大到构建/历史编辑器功能的破坏性变更。

## 2026-06-18 15:29 - Agent 图片支持滑动切换

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — Agent 行程卡片多图轮播增加图片区域 pointer 滑动/拖拽手势，左滑下一张、右滑上一张；保留原有左右按钮点击切图。
- web/styles.css — 图片区域增加纵向滚动友好的 `touch-action: pan-y`、拖拽光标反馈，并禁用图片原生拖拽干扰。
- scripts/verify_agent_image_carousel.js — 增加 Playwright 回归断言，验证图片区域水平拖动可前后切换。
- CHANGELOG.md — 记录本次图片滑动交互修复。

### 原因 — 为什么要改
- 线上 Agent 多图卡片虽然有左右按钮，但移动端和触屏场景下用户无法直接在图片上左右滑动，切图不够便捷。

### 影响范围 — 改动影响了哪些功能/模块
- 首页 AI 多 Agent 行程详情中的多图景点/餐厅/酒店卡片图片交互。
- 单图卡片不受影响；不改变图片 URL 生成、后端规划结果或卡片文案展示。

## 2026-06-18 15:21 - 均衡多天景点分配

### 变更内容 — 改了什么文件，具体改了什么
- agents/poi_agent.py — 必去景点前置补充后按 POI id/name 去重，避免同一个 POI 因复制并标记 `is_must_visit` 后再次从评分结果进入候选池；常规旅游候选排除“会议中心/会展中心”等商务场馆，用户明确必去时仍保留。
- tools/clustering.py — 普通景点分配时先补齐景点数过少的日期，再按地理距离放入最近分组，避免前两天过载而后一天只剩单个景点。
- tests/test_multi_agent.py — 增加北京“故宫/长城”必去候选不重复测试、商务会议中心不应进入常规北京旅游候选测试，以及 3 天行程普通景点应优先填充过少日期的聚类回归测试。
- CHANGELOG.md — 记录本次调度质量修复。

### 原因 — 为什么要改
- 用户反馈北京 3 天行程第 3 天只安排了一个会议中心。排查发现必去景点会重复占用候选名额，且聚类算法在已有第 1/2 天中心点时会持续把普通景点塞向已有中心，导致后续日期过空；同时“会议中心”类商务 POI 会被当作普通旅游景点进入候选。

### 影响范围 — 改动影响了哪些功能/模块
- AI 多 Agent 的 POI 候选集合和分日聚类均衡性。
- 不改变 POI 评分维度、路线优化、图片展示或前端渲染逻辑。

## 2026-06-18 15:02 - 支持“要去”必去景点解析

### 变更内容 — 改了什么文件，具体改了什么
- agents/intent_agent.py — 在 `must_visit` 正则解析中补充“要去XX/想要去XX”句式，并限制触发上下文，避免把“不要去XX”识别成必去景点。
- tests/test_multi_agent.py — 增加“去北京玩三天，要去故宫和长城”的回归测试，覆盖无标点句式和“不要去故宫，要去长城”的否定边界。
- CHANGELOG.md — 记录本次意图解析修复。

### 原因 — 为什么要改
- 用户明确输入“要去故宫和长城”时，现有 regex 快速解析没有识别该自然句式，导致 `must_visit` 为空，后续 PoiAgent/SchedulerAgent 的必去补救链路无法稳定安排这两个景点。

### 影响范围 — 改动影响了哪些功能/模块
- AI 多 Agent 意图解析中的必去景点提取。
- 仅扩展“要去/想要去”表达，不改变景点排序、调度、POI 数据和前端展示逻辑。

## 2026-06-18 14:49 - 去除 Agent 卡片重复推荐文案

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — Agent stop 卡片渲染时规范化 `reason`、`guide_text`、`recommendation` 文本；当推荐文案与已展示的理由或攻略文本完全相同时，不再重复渲染底部提示。
- scripts/verify_agent_image_carousel.js — 增加回归断言，验证相同推荐文案只在卡片中显示一次。
- CHANGELOG.md — 记录本次重复文案修复。

### 原因 — 为什么要改
- 线上部分景点会把同一段推荐语同时放在 `reason` 和 `recommendation` 中，前端按字段逐个展示后造成用户看到重复文字。

### 影响范围 — 改动影响了哪些功能/模块
- 首页 AI 多 Agent 行程详情中的 stop 卡片文案展示。
- 不改变后端规划结果、不改景点排序或去重逻辑；不同内容的推荐语仍会正常显示。

## 2026-06-18 14:28 - Agent 景点图片支持左右切换

### 变更内容 — 改了什么文件，具体改了什么
- web/app.js — Agent 行程卡片从 `image_url` 和 `images` 数组收集图片地址并去重；多图时显示上一张/下一张按钮，点击后在当前卡片内切换图片。
- web/styles.css — 增加 Agent 景点图片左右切换按钮样式，按钮居中贴边显示，避开顶部时间和类型标签。
- scripts/verify_agent_image_carousel.js — 新增 Playwright 回归脚本，验证多图景点会渲染左右按钮并能前后切换。
- CHANGELOG.md — 记录本次图片切换实现。

### 原因 — 为什么要改
- 线上多 Agent 行程的景点数据已经可能带有 `images` 多图数组，但前端只读取 `image_url`，用户无法查看同一景点的其他图片。

### 影响范围 — 改动影响了哪些功能/模块
- 首页 AI 多 Agent 行程详情中的景点/餐厅/酒店等 stop 卡片图片展示。
- 单图卡片保持原样，不显示左右切换按钮；不改后端规划、图片 URL 生成和景点去重逻辑。

## 2026-06-18 14:07 - 修复 Agent 行程重复景点

### 变更内容 — 改了什么文件，具体改了什么
- tools/clustering.py — 在景点分日聚类前增加同一物理景区去重：同 ID 只保留一次；规范化后同景区名且距离很近的 POI 只保留更匹配必去项/热度更高的一个，并在 must_visit 补救后再次排除重复景区。
- agents/intent_agent.py — 补充“必须去/务必去XX”的必去景点正则解析。
- tests/test_multi_agent.py — 增加“沙面/沙面岛/沙面公园”近似重复回归测试，以及“必须去沙面”解析回归测试。
- CHANGELOG.md — 记录本次重复景点修复。

### 原因 — 为什么要改
- 线上多 Agent 行程会把同一个景区重复安排，例如 `沙面` 和 `沙面岛` 两个重叠必去词会让同一个 `沙面岛` 跨天重复出现，同时还可能把近距离同景区的 `沙面公园` 作为独立景点加入。
- “必须去沙面”此前不会进入 regex 快速解析的 `must_visit`，会让必去补救链路无法稳定启动。

### 影响范围 — 改动影响了哪些功能/模块
- AI 多 Agent 分日聚类：减少同一景区、子景点或别名 POI 在行程中重复出现。
- 必去景点解析：支持用户自然输入“必须去XX/务必去XX”。
- 不改 POI 数据文件，不影响餐厅跨日去重和 C++ 路线算法。

## 2026-06-18 13:39 - 修复 R2 景点图片被 CSP 拦截

### 变更内容 — 改了什么文件，具体改了什么
- src/api.cpp — 将默认 CSP 生成集中到 `contentSecurityPolicy`，并从 `ASSET_BASE_URL`/`TOURPASS_ASSET_BASE_URL` 提取图片源 origin 加入 `img-src`。
- include/tourpass/api.h — 暴露 CSP 生成 helper，供回归测试直接校验。
- tests/test_main.cpp — 增加 R2 图床 origin 必须出现在 `img-src` 的回归测试。
- CHANGELOG.md — 记录本次图片显示修复。

### 原因 — 为什么要改
- 线上 Agent 返回的景点 `image_url` 是 R2 URL，图片本身可访问，但页面响应头 `Content-Security-Policy` 的 `img-src` 没允许 R2 域名，浏览器拦截加载后前端只能显示占位图标。

### 影响范围 — 改动影响了哪些功能/模块
- 首页和分享页的图片加载安全策略：允许当前配置的 R2/资产域名显示景点、酒店等图片。
- 不改变图片 URL 生成逻辑，也不放宽脚本或接口连接策略。

## 2026-06-18 12:20 - 修复 Render Agent 反代 502

### 变更内容 — 改了什么文件，具体改了什么
- src/api.cpp — Linux/Render 的 `/agent/*` 反代从手写 raw socket 读取改为复用项目已有 `httplib::Client`，并补齐 query string 转发；Agent 不可达时返回结构化 `AGENT_PROXY_ERROR` 和底层错误原因。
- tools/rag.py — 新增单城市 RAG 初始化能力，避免首个规划请求一次加载 21 个城市的攻略/知识数据。
- agents/retrieve_agent.py — RetrieveAgent 改为只按当前请求城市懒加载 RAG。
- tests/test_multi_agent.py — 增加城市级 RAG 初始化回归测试，确认请求北京不会顺带索引上海。
- scripts/container_smoke.js — Agent health 失败时输出响应体片段，避免 CI 只显示 `HTTP 502` 而丢失代理错误细节。
- src/api.cpp — 修复 Agent 代理 handler 对 `agentPort` 的悬空引用，确保 Linux/Render 运行时实际连接 `AGENT_PORT` 指定端口。
- CHANGELOG.md — 记录本次 502 根因调查和修复范围。

### 原因 — 为什么要改
- 最新 GitHub Actions Docker smoke 和线上 `https://tour-pass.onrender.com/agent/health` 都返回 502，响应体为 `{"error":"Agent no response"}`。
- CI 容器日志显示 FastAPI Agent 已经完成 startup 并监听 `127.0.0.1:8090`，但 Python 侧没有收到 `/agent/health` 请求；失败点集中在 C++ Linux raw socket 反代实现，而不是 Agent 健康检查自身。
- Render 免费实例 521MB 内存限制可能仍会影响首个规划请求的 graph/RAG 懒加载，但 `/agent/health` 不触发这些重资源加载，当前可复现 502 需要先修反代可达性。
- 首个 `/agent/plan` 仍可能在免费实例中受内存限制影响，原 RetrieveAgent 会在请求期全量 `init_rag("data")`，需要改成城市级懒加载降低峰值内存。

### 影响范围 — 改动影响了哪些功能/模块
- Render/Docker Linux 环境：`/agent/ping`、`/agent/health`、`/agent/plan`、`/agent/plan-sync`、`/agent/plan-multi`、`/agent/chat` 等 C++ 到 Python Agent 的代理路径。
- Windows 本地 API smoke：不改 WinHTTP 反代分支。
- 前端 AI 多 Agent 规划：恢复 C++ 服务对 Python Agent 的可达性；SSE 响应经 `httplib::Client` 缓冲返回，后续如需优化实时流式可单独处理。
- 首个规划请求：RAG 只加载当前城市，减少 Render 免费实例上的内存峰值；跨城市请求会按城市逐步追加索引。
- CI Docker smoke：后续 Agent 502 会显示响应体和 C++ 代理错误日志，便于区分连接失败、读取失败和 Agent 业务失败。
- Docker/Render Agent 代理：端口捕获改为按值保存，避免 handler 注册后局部端口变量失效导致连接 `port=0`。

## 2026-06-17 21:36 - 修复广州样本数据 CI 校验规则

### 变更内容 — 改了什么文件，具体改了什么
- package.json — 将 `validate:data` 改为使用 `--allow-transit-schedule-defaults --allow-disconnected --required-types attraction,restaurant,hotel`，让默认广州样本校验与全城市真实数据校验规则保持一致。
- api_multi_agent.py — 取消 Agent 启动期预初始化 LLM 和 LangGraph，改为首个规划请求时懒加载；RAG 仍在启动时初始化。
- CHANGELOG.md — 记录本次 CI 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions `CI` 在 `Validate sample data` 步骤执行 `npm run validate:data` 失败。
- 失败原因是默认校验目标已从长沙改为 `data/guangzhou/pois.json`，但默认规则仍强制要求 `nightlife` 类型并要求 transit POI 必须有 `open_time`、`close_time`、`visit_duration_minutes`。当前广州真实数据没有 `nightlife`，且 5 个 transit POI 只有旧字段 `visit_duration`，导致 16 个数据校验错误。
- 不直接改广州 POI 数据，是为了避免人为补造 nightlife 或交通点时间字段污染真实数据。
- 线上游客登录后 `/agent/plan` 返回 502 `Agent no response`，同时 `/agent/health` 也返回同样错误，说明 C++ 主服务正常但 Python Agent 未能稳定提供服务；减少 Agent 启动期 LLM/Graph 预热，避免 Render 实例启动时因重初始化过重导致 Agent 不可用。

### 影响范围 — 改动影响了哪些功能/模块
- CI 数据校验：`validate:data` 不再因为真实城市数据缺少 nightlife 或 transit 时间字段失败；`validate:data:all` 和全城市数据门禁规则保持一致。
- Agent 运行时：`/agent/health` 可更早返回；首个 AI 规划请求会承担 LLM/Graph 懒加载耗时。

## 2026-06-17 21:56 - 修复 Multi-Agent CI 测试缺失文件

### 变更内容 — 改了什么文件，具体改了什么
- tests/test_multi_agent.py — 将 `test:multi-agent` 使用的 Python 回归测试文件纳入版本控制。
- requirements-multi-agent.txt — 补充 `fastapi`、`httpx`、`python-dotenv`、`redis`，使 CI 测试依赖与 Agent/Docker 运行依赖保持一致。
- CHANGELOG.md — 记录二次 CI 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions 新 run `27693832302` 已通过 `Validate sample data`，但在 `Multi-Agent tests` 步骤失败。
- 失败原因是干净 checkout 中没有 `tests/test_multi_agent.py`，而 `package.json` 的 `test:multi-agent` 正在执行该路径；本地能通过是因为该文件只存在于未跟踪工作区。
- 测试会导入 `api_multi_agent.py`，因此 CI 也需要安装 API 导入依赖，否则补上测试文件后会继续因缺依赖失败。

### 影响范围 — 改动影响了哪些功能/模块
- CI 多 Agent 测试：干净 GitHub runner 可找到并执行测试文件。
- Python Agent 依赖：`requirements-multi-agent.txt` 可覆盖测试和运行时导入所需的轻量 API 依赖。

## 2026-06-17 22:02 - 修复 Windows API smoke 城市参数

### 变更内容 — 改了什么文件，具体改了什么
- scripts/api_smoke.ps1 — 路线 smoke 使用 `docs/sample_candidate_request.json` 中的城市作为 `/route/shortest` 的 `city` 参数。
- CHANGELOG.md — 记录 Windows API smoke 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions run `27694240231` 中 Ubuntu 已全部通过，Windows 在最后的 `API smoke` 步骤失败。
- 失败原因是 smoke 从根 `data/edges.json` 读取长沙边 `amap_f3d362be -> amap_b011c2`，但请求 `/route/shortest` 时没有显式传 `city`，服务会使用当前默认城市，导致用非长沙图查询长沙 POI 并返回 `NOT_FOUND`。

### 影响范围 — 改动影响了哪些功能/模块
- CI Windows API smoke：路线检查与样例候选请求城市保持一致，不受服务默认城市变化影响。
- 运行时接口：只影响测试脚本，不改变 `/route/shortest` 接口行为。

## 2026-06-17 22:09 - 修复 API smoke 路线样本来源

### 变更内容 — 改了什么文件，具体改了什么
- scripts/api_smoke.ps1 — 路线 smoke 改为从 `data/guangzhou/edges.json` 取样，并显式传 `city=广州`。
- CHANGELOG.md — 记录第三层 Windows API smoke 失败原因和修复方式。

### 原因 — 为什么要改
- GitHub Actions run `27694712668` 仍在 Windows `API smoke` 的 `/route/shortest` 检查失败。
- 失败原因是 `data/changsha/edges.json` 当前为空；服务按城市目录加载“长沙”，而 smoke 之前从根 `data/edges.json` 读取旧长沙边，导致路线样本和服务实际加载的城市图不一致。
- 广州是当前默认数据校验目标，且 `data/guangzhou/edges.json` 有有效边数据，用它做 smoke 样本更贴近当前 CI 数据入口。

### 影响范围 — 改动影响了哪些功能/模块
- CI Windows API smoke：路线检查使用真实已加载且有边的城市图。
- 运行时接口：只影响测试脚本，不改变服务行为。

## 2026-06-17 22:26 - 修复 Agent 健康检查启动阻塞

### 变更内容 — 改了什么文件，具体改了什么
- api_multi_agent.py — Agent 启动期不再全量执行 `rag_module.init_rag("data")`，RAG 与 LLM/Graph 一样改为首个检索/规划请求懒加载。
- scripts/container_smoke.js — 将 `/agent/health` 从非致命警告改为 Docker smoke 的硬性门禁。
- CHANGELOG.md — 记录线上 `/agent/health` 502 与 CI Docker smoke 漏检的原因和修复方式。

### 原因 — 为什么要改
- 最新 CI 虽然通过，但 Docker smoke 日志显示 `/agent/health` 实际返回 502，只是脚本把它标记为 non-fatal；线上 `https://tour-pass.onrender.com/agent/health` 和游客规划 `/agent/plan` 同样返回 502。
- 失败原因是 FastAPI lifespan 仍在启动期同步全量加载 RAG，读取 21 个城市的攻略和 POI 知识后才会响应健康检查；Render/Docker 中 C++ 反代在 Agent 未完成启动前只能返回 `Agent no response`。
- Agent 健康检查不应依赖 RAG 已完成索引，RAG 可由 `RetrieveAgent` 在首个规划请求中懒加载。

### 影响范围 — 改动影响了哪些功能/模块
- Agent 启动：`/agent/health` 可先返回，避免主服务健康但 Agent 反代一直 502。
- CI Docker smoke：后续若 Agent health 不可用，CI 会失败而不是放过问题。
- 首个 AI 规划请求：会承担 RAG 懒加载耗时。

### 2026-06-15 22:19 — 收紧质量门禁和交付边界

#### 变更内容
- .github/workflows/ci.yml、package.json、web/editor/package.json、scripts/run_python_test.js — CI 显式开启 `TOURPASS_BUILD_TESTS=ON`，增加全城市数据校验、数据校验回归测试、Python 多 Agent 测试、React editor Vitest 和 editor build；补充对应 npm scripts 和跨平台 Python 测试 runner。
- scripts/validate_data.js、tests/test_validate_data_all_cities.js — 新增 `--all-cities` 与 `--data-dir`，逐个校验根数据和城市目录中的 `pois.json/edges.json`；新增回归测试确认坏城市数据会让全量校验失败。
- web/editor/src/core/commands/__tests__/*、web/editor-dist/index.html、web/editor-dist/assets/index-hlZKmOB9.js — 修正 command 测试 fixture 与实际 `setDays` store API 一致；刷新已跟踪的 editor build 产物入口。
- src/api.cpp、api_multi_agent.py — C++ 和 Agent CORS 改为环境变量白名单；C++ `/images` 与 Agent `/data/{city}/images/...` 只允许图片扩展名并限制在数据图片目录内，不再公开整个 data 目录。
- Dockerfile、.dockerignore — 运行镜像不再复制 `scripts/`；Docker build context 排除采集脚本、XHS 会话/路线中间数据和大图片目录。

#### 影响范围
- CI：PR/Push 会运行更多测试和构建，耗时增加但能提前发现测试空跑、Agent 回归、editor 编译和多城市数据问题。
- 运行时安全：跨域访问必须通过 `TOURPASS_ALLOWED_ORIGINS` 或 `AGENT_ALLOWED_ORIGINS` 显式配置；非图片数据不再能通过图片静态路径访问。
- Docker：生产镜像体积和敏感采集中间文件暴露面降低。

### 2026-06-15 17:18 — 多Agent上线入口与 R2 图片准备

#### 变更内容
- Dockerfile、entrypoint.sh、.dockerignore — 默认使用 `AGENT_IMPL=multi` 启动 `api_multi_agent:app`，保留 `AGENT_IMPL=legacy` 回滚入口；镜像复制多 Agent 根文件、agents/tools 目录和 requirements，并排除 `data/*/images/`。
- src/api.cpp、include/tourpass/models.h、src/models.cpp、src/search.cpp、web/admin.js、api_multi_agent.py — 新增/接入图片 URL 解析逻辑，`ASSET_BASE_URL` 或 `TOURPASS_ASSET_BASE_URL` 存在时将相对图片路径解析为 CDN/R2 URL，绝对 URL 原样返回，避免 `/https://...`。
- src/api.cpp、api_multi_agent.py — C++ proxy 增加 `/agent/plan-multi`；修复参数名；`/agent/health` 和 `/agent/stats` 返回 RAG 与 XHS 加载统计。
- tools/xhs_loader.py、tools/route.py、agents/retrieve_agent.py、agents/scheduler_agent.py、agents/state.py、graph.py — 修复中文城市名读取、edges 字段读取；将 XHS 路线转为 POI 频次、同日共现、参考路线摘要并注入多 Agent 规划上下文。
- scripts/upload_r2_assets.js — 新增 R2 上传脚本，支持 `--dry-run`、`--city`、`--only-amap`。
- scripts/multi_agent_regression.py — 新增 21 城 `/agent/plan-sync` 回归脚本。

#### 影响范围
- 部署：Render Docker 运行 C++ 后端 + Python 多 Agent 双进程，旧单 Agent 通过环境变量回滚。
- 图片：生产环境配置 CDN base 后，行程、搜索、POI 浏览和管理页展示可直接使用 CDN 图片 URL。
- 多 Agent：Retrieve/Poi/Scheduler 可利用 XHS 路线信号。

### 2026-06-13 17:37 — 小红书旅游路线爬虫与提取工具

#### 变更内容
- scripts/crawl_xhs_routes.js — 新增 API 方式路线爬虫
- scripts/crawl_xhs_routes_browser.js — 新增 Playwright 浏览器方式路线爬虫
- scripts/extract_routes.py — 新增 Python 路线提取脚本
- data/guangzhou/xhs_routes.json — 从已有 191 条广州笔记中提取出 14 条完整路线

### 2026-06-13 17:15 — 高德照片全量爬取完成

#### 变更内容
- 20 个城市共 2354/8519 个 POI 成功获取照片（27.6% 成功率）
- 各城市 data/{city}/pois.json 的 image_url 和 images 字段已更新
- 照片存储在 data/{city}/images/{poi_id}/ 下

### 2026-06-13 16:35 — 高德照片批量下载（多 Key 轮换）

#### 变更内容
- 修改 scripts/download_amap_photos.js：支持多 API Key 轮换、多城市批量爬取

### 2026-06-13 — 管理后台 POI 数据管理

#### 变更内容
- include/tourpass/graph.h + src/graph.cpp — PoiGraph 新增 findMutablePoi(id) 方法
- include/tourpass/models.h + src/models.cpp — 新增 poiToJson() 序列化函数
- include/tourpass/data_loader.h + src/data_loader.cpp — 新增 savePois() 写回 JSON
- include/tourpass/api.h — CityBundle 新增 poisPath 字段
- src/api.cpp — 新增 4 个管理员 API 端点（GET/PUT /admin/pois）
- web/admin.html — 新增「景点管理」tab
- web/admin.js — POI 管理逻辑：城市切换、分页、搜索筛选、编辑表单
## 2026-06-20 23:20 - 记录真实路线规划优化计划

### 变更内容
- 新增 `docs/real_route_planning_plan.md`，记录此前用户反馈的长通勤、夜市早排、餐厅过多、低质量 POI 等问题，以及真实路线抓取结果、架构决策、分阶段实施任务、验收标准和真实效果测试方法。
- 在计划书中明确下一步实现顺序：先建立统一路线指标，再接入 Scheduler/Reviewer 的可行性门禁，最后做 POI 覆盖与生产验证。

### 原因
- 用户要求继续下一步，并要求记录之前规划、列出完整计划书，同时对后续问题进行核实。
- 真实路线数据只能解决“时间是否真实”，还需要规划层硬约束判断“是否应该安排”，因此需要先形成可审核计划。

### 影响范围
- 仅影响项目文档，不改变当前调度、路线计算、前端展示或部署行为。
## 2026-06-20 23:27 - 补充真实路线规划决策

### 变更内容
- 更新 `docs/real_route_planning_plan.md`，记录用户确认的策略：默认打车、超限可选 POI 自动移除并进入替换池、远距离必去景点单独成日、生产只使用预计算高德边、优化方案面向多数城市。
- 在计划书中补充当前真实高德边算法说明：现有脚本使用近邻稀疏图加连通桥接边，不需要对每两个景点建立全量高德边。
- 新增多城市稀疏边构建、替换池、远距离必去景点单独成日等后续任务与真实效果测试方法。

### 原因
- 用户确认了关键产品策略，并询问是否需要全量两两建立高德边。
- 需要把已确认决策写入项目文档，避免后续实现时重新假设。

### 影响范围
- 仅影响真实路线规划文档，不改变当前运行逻辑、数据文件或部署行为。

## 2026-06-21 18:21 - 新增小红书帖子可视化模块

### 变更内容
- 新建 	ools/xhs_parser.py — SSR 抓取小红书公开帖子内容（URL 解析 + __INITIAL_STATE__ 提取 + meta 降级）
- 修改 pi_multi_agent.py — 新增 3 个 FastAPI 端点：POST /api/xhs/parse、POST /api/xhs/analyze、GET /api/xhs/proxy
- 修改 web/index.html — 替换 xhsPanel 占位符为完整的小红书解析界面（输入视图 + 结果视图 + Lightbox + 景点 CRUD Modal）
- 修改 web/styles.css — 新增 ~480 行 XHS 模块样式（输入卡片、Hero、画廊、类型统计、时间线、响应式布局、动画）
- 修改 web/app.js — 新增 ~260 行 XHS 前端逻辑（解析流水线、结果渲染、Day 切换、景点 CRUD、图片 Lightbox、保存/导出）

### 原因
参考 4evour/Tour-AI 和 4evour/TripStar 两个项目的实现，为 Tour Pass 新增小红书帖子解析+可视化功能。采用零依赖方案（无需 Cookie/Puppeteer/签名引擎），公开帖子通过 SSR 抓取获取内容，LLM 提纯结构化行程数据。

### 影响范围
- 	ools/xhs_parser.py — 新模块，无副作用
- pi_multi_agent.py — 新增 3 个端点，不影响现有 API
- web/index.html — 仅替换 xhsPanel 区域，不影响其他面板
- web/styles.css — 仅追加样式，不影响现有样式
- web/app.js — 仅追加 XHS 函数，不影响现有路由/逻辑

## 2026-06-24 14:23 - 修复移动端侧栏当前路由点击不关闭

### 变更内容
- 修改 `web/app.js`：为侧栏链接增加点击兜底，当用户点击当前已激活的 hash 路由时也主动执行 `applyRoute()`，确保移动端侧栏关闭。
- 修改 `tests/test_sidebar_hash_routing.js`：新增移动端当前路由重复点击回归测试，覆盖 hash 不变化时不会触发 `hashchange` 的场景。

### 原因
- 移动端在 `#/plan` 页面打开侧栏后再次点击“AI 助手”，由于 hash 没变化不会触发 `hashchange`，侧栏保持打开并遮挡内容，用户看到类似空白页面。

### 影响范围
- 影响移动端/窄屏侧栏导航点击行为。
- 不改变路由结构、面板内容、桌面侧栏布局或小红书笔记解析模块。

## 2026-06-23 20:40 - 修复重庆山城探险行程过少

### 变更内容
- 修改 `agents/hotel_agent.py`：修复酒店选择提示词中的 JSON 示例转义，避免 LangChain 将 `hotel_id` 误当成模板变量；酒店 fallback 排序改为优先参考必去景点和候选景点中心，并将命中必去区域文案的酒店前置。
- 修改 `tools/matching.py`：新增“解放碑”到“人民解放纪念碑”这类碑类地标简称匹配，确保必去景点能被 POI、调度和审核链路统一识别。
- 修改 `tests/test_multi_agent.py`：新增酒店提示词、酒店 fallback 位置选择、重庆解放碑必去匹配的回归测试。

### 原因
- “重庆山城探险”3 天游生成时，酒店 fallback 选到了远离主城的秀山酒店，调度器随后按酒店通勤过远移除了多数主城景点，导致三天只剩极少景点。
- “解放碑”在数据中的正式 POI 名称是“人民解放纪念碑”，原必去匹配无法识别这个简称。

### 影响范围
- 影响多 Agent 行程规划中的酒店选择、必去景点匹配和重庆等含碑类地标简称的行程生成。
- 不改变前端展示结构、路线 API 或 POI 数据文件。

## 2026-06-23 12:13 - 修复 Tour-AI 风格布局加载

### 变更内容
- 修改 `src/api.cpp`：将 `/css/` 静态资源路径加入公开白名单，确保 `web/css/sidebar.css` 和 `web/css/plan-form.css` 在认证前可加载。
- 修改 `web/index.html`：为登录页添加 Tour-AI 风格顶部栏和左侧导航骨架；为主应用添加固定顶部品牌栏，并调整侧栏导航文案为纯文字布局。
- 修改 `web/styles.css`：将登录页从全屏绿色遮罩改为灰色工作区 + 居中白色登录卡；统一主色为橙色按钮和焦点态；调整 AI 规划卡片为白色工具面板。
- 修改 `web/css/sidebar.css`：重做主应用左侧导航、顶部栏、内容区灰底布局，并修复平板/移动端侧栏表现。
- 修改 `web/css/plan-form.css`：将结构化表单的选中、hover、focus 和提交按钮改为当前橙色主题。
- 修改 `web/app.js`：让固定顶部栏菜单按钮复用现有移动端侧栏开关。
- 新增 `tests/test_public_static_paths.js`、`tests/test_tour_ai_layout_markup.js`、`tests/test_shell_menu_binding.js`：覆盖 CSS 白名单、布局骨架和顶部菜单绑定。

### 原因
- 线上页面出现裸链接式侧栏，是因为子目录 CSS 没有通过认证前置白名单，导致关键布局样式没有加载。
- 用户明确要求按 `tour-ai-azure.vercel.app/login` 截图里的 Tour-AI 版式调整当前布局。

### 影响范围
- 影响主站登录页、主应用外壳、左侧导航、AI 规划入口表单的视觉和移动端侧栏开关。
- 不改变行程规划 API、AI Agent 请求流程、行程渲染数据结构或编辑器内部实现。
