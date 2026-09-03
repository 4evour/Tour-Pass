# CHANGELOG

## 2026-09-03 - 切换 Responses 中转模型

### 变更内容
- `trip_agent/llm.py` - 增加 OpenAI Responses 流式协议、`/responses` SSE 增量解析和输出文本聚合，同时保留 Chat Completions 兼容能力；流开始后发生中断时禁止重复提交同一生成请求。
- `trip_agent/runtime.py`、`trip_agent/.env.example` - 将默认中转地址和模型更新为 `https://ztoken.zlux.top`、`gpt-5.6-luna`，推理强度设为 `high`，整单运行上限提高到 600 秒。
- `tests/trip_agent_test.py` - 增加 Responses 请求结构、响应解析及读取超时不重试的回归测试。

### 原因
- 原 DeepSeek 配置使用失效密钥，请求返回 HTTP 401；切换后仍使用同步 Responses 请求，无法产生首字时间，高推理生成又超过原 90 秒读取上限，自动重试造成多个仍在上游执行的重复请求并最终触发整单超时。

### 影响范围
- 本地 Trip Agent 改用 Responses SSE 流式协议，允许中转站持续返回增量事件；单次高推理生成读取上限 480 秒，整单最多 600 秒。真实密钥只保存在被 Git 忽略的 `.env` 中。


## 2026-09-03 - 独立 Trip Agent 成为主线

### 变更内容
- 主线只保留独立 `trip_agent/` 应用、对应测试和持久化代码知识图谱。
- 移除旧 C++ 服务、多 Agent、旧 RAG、旧 Web/编辑器、历史数据及其构建部署配置。
- 旧版本由 `legacy/tour-pass-before-trip-agent` 分支和 `grounded-planner-before-migration-20260830` 标签保留。

### 原因
- 当前产品方向已经切换为单一、对话式 Trip Agent；继续保留旧系统会污染代码检索、运行入口和后续开发判断。

### 影响范围
- 默认开发与运行对象改为 `python -m trip_agent.app`。
- 旧接口、旧前端和旧部署配置不再存在于主线；需要查看或恢复时切换到归档分支或标签。

## 2026-09-03 - 完整行程输出与证据边界

### 变更内容
- `trip_agent/loop.py`、`trip_agent/prompts.py`、`trip_agent/plan_output.py` - 将模型输出升级为逐日时间轴、住宿闭环、区域比较、风险和叙事完整契约；增加分阶段批量工具调用、重复查询拦截、模型 JSON 重试及事实归一化。
- `trip_agent/llm.py`、`trip_agent/runtime.py`、`trip_agent/.env.example` - 扩大长行程输出与运行预算，并为临时模型传输错误增加有限重试。
- `trip_agent/static/` - 重做行程工作台，展示每日时段、地点证据、交通段、地图坐标、风险来源、候选区域和完整度检查。
- `tests/trip_agent_test.py` - 覆盖批量查询、重复调用、长 JSON 重试、地点证据清洗、路线端点绑定、天气来源绑定、住宿闭环及重复 POI 合并。

### 原因
- 原预览仅能返回简化景点列表，无法承载可直接执行的多日行程；同时必须防止模型生成的坐标、开放时间或路线数字被误标为外部已核验事实。

### 影响范围
- 模型负责路线取舍和表达，高德与天气 Provider 负责外部事实。
- 未与请求端点和响应哈希匹配的路线不展示精确时间或距离，而是明确标为待核验；模型建议与已核验事实分开展示。

## 2026-09-02 - 新增独立对话式 Trip Agent

### 变更内容
- `trip_agent/` - 新增独立 FastAPI 对话入口、OpenAI-compatible 模型适配器、有限工具循环、高德地点/路线/天气查询、和风天气优先策略、SQLite 原始响应缓存与单页界面。
- `tests/trip_agent_test.py` - 覆盖模型 JSON 提取、未核验地点拒绝、地点简称规范化、工具预算和冷/热缓存行为。
- `trip_agent/.env.example`、`.gitignore` - 补充环境变量示例及本地缓存忽略规则。

### 原因
- 在不复制旧多 Agent 编排和旧规划数据链路的前提下，验证由单一对话 Agent 按需获取实时证据并生成结构化行程的完整闭环。

### 影响范围
- 独立入口默认监听 `127.0.0.1:8123`。
- 最终行程地点必须匹配本轮高德查询证据；工具调用有界，外部响应按 TTL 缓存在本地 SQLite。
