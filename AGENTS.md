# Tour Pass 项目协作规则

本文件适用于整个仓库。修改前先阅读本文件、相关模块文档和调用上下文；如果子目录新增更具体的 `AGENTS.md`，以更近目录的规则为准。不要把空的 `.agents/` 目录当作规则入口。

## 1. 项目边界与目录地图

- `src/`、`include/tourpass/`：C++17 主服务、HTTP API、规划算法、POI 图、路线计算、认证和存储层。
- `tests/`：C++、Node.js、数据和回归测试。
- `agent/`：旧版 Python Agent 及其 RAG、调度和评分实现。
- `agents/`：当前多 Agent 工作流组件，包括检索、POI、酒店、餐厅、调度、审核和总结 Agent。
- `api_multi_agent.py`、`main_multi_agent.py`：Python 多 Agent 服务入口及 FastAPI 接口。
- `web/`：主站静态前端；`web/editor/` 是 React + TypeScript + Vite 行程编辑器源码。
- `web/editor-dist/`：编辑器发布静态产物。源码修改影响发布包时，必须按现有项目流程重新构建并检查生成差异。
- `data/`：城市 POI、路线边和相关数据；数据修改不是纯文案修改，必须执行数据校验。
- `scripts/`：数据采集、清洗、路线构建、质量检查、容器和 UI 验证脚本。
- `config/`：本地和外部服务配置模板；密钥放环境变量或未跟踪的本地配置，不得提交。

主要运行链路是：Web/编辑器 → C++ API → Python Agent（规划、RAG、审核）→ 数据/存储/外部服务。涉及接口、鉴权、数据格式或跨服务调用的修改，必须同时检查调用方和被调用方。

## 2. 知识图谱工作流

项目使用 `codebase-memory-mcp` 维护代码知识图谱，项目名为 `Tour-Pass`。

### 修改前

1. 使用 `search_graph` 查找目标函数、类、路由或变量定义。
2. 使用 `trace_path` 查看调用方、被调用方和影响范围。
3. 使用 `get_code_snippet` 读取准确实现；需要整体结构时使用 `get_architecture`。
4. 再阅读目标文件、测试文件和配置文件，确认图谱与工作区没有明显过期。

### 修改后

- 代码结构、调用关系、路由、接口或依赖发生变化：使用 `index_repository` 重新索引并设置 `persistence: true`，更新 `.codebase-memory/graph.db.zst`。
- 仅文档、注释或不影响代码图的修改：无需为了形式重新做 full 索引，但如果本次工作已修改代码，仍需刷新索引。
- 小范围普通代码修改可使用 `fast`；需要语义关系、相似关系或架构分析时使用 `moderate` 或 `full`。
- 不得把未重新索引的图谱当作当前代码的完整事实；索引失败时必须在结果中明确说明。

## 3. 开发与验证命令

只运行与改动相关的最小充分验证；如果命令不可用或依赖缺失，记录实际错误，不得把未执行的测试写成通过。

### C++ 主服务

```text
make build
make test
cmake -S . -B build -DTOURPASS_BUILD_TESTS=ON
cmake --build build
ctest --test-dir build --output-on-failure
```

算法、API、存储、认证或数据加载改动至少运行对应 C++ 测试；构建配置或跨平台改动优先使用 CMake 流程。

### Python Agent 与数据

```text
npm run test:multi-agent
npm run validate:data
npm run validate:data:all
npm run test:validate-data-all
```

修改 `agents/`、`agent/`、`api_multi_agent.py` 或规划数据结构时，优先运行 Python 多 Agent 测试；修改 `data/`、清洗脚本或路线边时，必须运行全城市数据校验。

### 编辑器与前端

```text
npm run editor:test
npm run editor:build
npm run verify:ui
```

修改 `web/editor/` 时至少运行编辑器测试和构建；修改主站 HTML、CSS、JavaScript、路由或交互时运行相关 UI/回归测试，必要时使用 `verify:ui`。

### 集成与部署

```text
npm run container:smoke
npm run quality:algorithm
npm run quality:itinerary-smoke
```

修改 Docker、Render 配置、服务启动、C++ 到 Agent 代理或生产路由时，优先运行容器 smoke；修改规划质量约束时运行算法和行程质量检查。

## 4. 修改原则

- 先读代码和测试，再写代码；使用现有模块边界、命名、错误处理和序列化方式。
- 保持最小变更，不顺手重构无关代码，不删除或覆盖其他未提交改动。
- 新增行为必须补测试；修 bug 优先添加能复现原问题的回归测试。
- API、数据库字段、POI JSON 字段和前后端 payload 属于接口契约，修改前先查所有调用方和测试。
- 修改 C++ API 或 Python FastAPI 路由时，保留鉴权、CORS、路径 allowlist、输入校验和错误码语义；不要扩大公开路径或静态文件访问范围。
- 外部输入不能直接拼接 HTML、SQL、文件路径、命令或代理 URL；沿用项目已有的转义、参数化查询和 allowlist 模式。
- 数据采集、清洗和生成脚本可能覆盖大量文件。执行前确认输入、输出目录和参数，禁止把本地密钥、Cookie、日志、缓存或大体积中间文件纳入提交。
- 前端展示外部或用户输入时使用已有的安全渲染方式；不要为了方便恢复 `innerHTML` 等不安全输出路径。

## 5. 文件与产物规则

- `.env`、本地密钥、Cookie、调试日志、数据库、缓存和图片中间产物不得提交。
- 修改真实数据前先备份或确认 Git 工作区状态；数据变更必须说明来源、范围和校验结果。
- 修改编辑器源码后，确认是否需要同步 `web/editor-dist/`；不要手工编辑构建产物来修复源码问题。
- `.codebase-memory/graph.db.zst` 是知识图谱持久化产物。若项目需要团队共享索引，应按仓库 Git 忽略/提交约定处理，不得隐式改变该约定。
- 每次项目文件修改都要在根目录 `CHANGELOG.md` 追加时间、变更内容、原因和影响范围。

## 6. Git 与交付

- 开始工作前查看 `git status`，只处理本次请求相关文件；不得重置、清理或覆盖用户已有改动。
- 完成后检查 `git diff --check`，并报告实际运行过的验证命令及结果。
- 未经明确要求不自动提交、推送或创建 Pull Request。
- 如果验证失败，修复根因；不要通过放宽断言、跳过测试或修改测试预期来掩盖失败。
- 最终说明应列出修改文件、验证结果、知识图谱是否刷新，以及仍存在的限制。

## 7. 文档与沟通

- 解释、计划、变更记录使用中文；代码标识符保持英文并遵循附近代码风格。
- 新增或改变公共 API、部署方式、数据格式、架构边界时，同步更新相关 README 或 `docs/` 文档。
- 不确定的路径、函数、测试结果和运行状态必须先检查；不得编造。
