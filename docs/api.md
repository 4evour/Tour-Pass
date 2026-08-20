# Tour Pass API 文档

默认服务地址：

```text
http://127.0.0.1:8080
```

OpenAPI/Swagger 规范见 [`docs/openapi.yaml`](openapi.yaml)。可以将该文件导入 Swagger Editor 或 Swagger UI 预览；当前服务不内置 Swagger UI，避免把文档展示功能耦合进 C++ 演示服务。

## GET /health

返回服务、数据和 LLM 配置状态。

```json
{
  "status": "ok",
  "data_loaded": true,
  "poi_count": 25,
  "edge_count": 46,
  "distance_cache": {
    "enabled": true,
    "mode": "all_pairs",
    "poi_count": 25,
    "entries": 625,
    "max_entries": 625,
    "hits": 0,
    "misses": 0,
    "evictions": 0,
    "startup_ms": 0
  },
  "llm_configured": false,
  "workers": 8,
  "job_workers": 2,
  "max_queue": 64,
  "max_in_flight": 32,
  "in_flight_requests": 1,
  "cache_enabled": true,
  "db_enabled": true,
  "db_path": "storage/tourpass.sqlite"
}
```

所有响应都会附带 `X-Request-Id` 和 `X-Response-Time-Ms`。支持缓存的接口还会返回 `X-Cache: HIT` 或 `X-Cache: MISS`。

## POST /trip/plan

根据用户偏好生成结构化行程。规划器使用 Beam Search 在每个时间槽保留 Top-K 局部状态，综合站点评分、通勤成本、开放时间和必去覆盖选择路线。`candidate_count` 大于 1 时返回 `candidates` 数组，候选方案会体现轻松少走路、紧凑多覆盖、文化优先、美食优先、雨天室内等真实评分策略差异。

请求示例：

```json
{
  "city": "长沙",
  "days": 2,
  "start_time": "09:30",
  "end_time": "21:30",
  "hotel_location": "五一广场酒店",
  "interests": ["历史文化", "美食", "夜景"],
  "pace": "轻松",
  "must_visit": ["橘子洲", "湖南博物院"],
  "avoid": ["排队太久"],
  "candidate_count": 3
}
```

关键响应字段：

- `variant_name`：候选方案名称。
- `strategy`：候选策略标识，例如 `low_travel`、`compact`、`culture`、`food`、`rainy`。
- `comparison`：候选方案对比指标，包含总站点数、总通勤、游玩时长、必去覆盖、开放时间风险、未安排数量、总评分、Pareto 层级和取舍说明。
- `comparison.pareto_debug`：Pareto 分层调试说明，展示指标向量和是否被其他候选支配的原因。
- `comparison.poi_overlap_with_baseline` / `comparison.area_overlap_with_baseline`：相对第一个候选基线的 POI 与区域重合率，取值 `0..1`。
- `comparison.unique_poi_count` / `comparison.unique_pois`：相对基线方案的独有 POI 数量和名称。
- `comparison.diversity_tags` / `comparison.diversity_summary`：候选多样性标签和自然语言说明。
- `summary`：每日安排摘要，包含 Beam Search 选择过程、节奏、兴趣优先级和演示重点。
- `beam_trace`：每日 Beam Search 调试轨迹，按时间槽记录输入状态数、展开状态数、保留状态数、Top 状态摘要和保留决策。
- `stops[].reason`：站点级决策依据，说明兴趣匹配、通勤、评分、开放时间等因素。
- `stops[].time_window_status` / `stops[].time_window_reason`：站点级时间窗复核状态和精确原因，例如等待、闭馆、餐饮窗口或顺序风险。
- `stops[].score_breakdown`：站点评分拆解，包含热度、兴趣匹配、必去加权、通勤惩罚、价格惩罚和时间窗惩罚等组件。
- `optimization_summary`：日内局部交换优化结果，说明优化前后通勤变化。
- `original_travel_minutes` / `optimized_travel_minutes`：优化前后通勤时间。
- `time_window_feasible` / `time_window_diagnostics`：当日最终顺序统一复核结果，覆盖站点顺序、开放时间、餐饮窗口和当日结束时间。
- `constraint_explanations`：开放时间约束、餐饮窗口、必去点、通勤成本等解释。
- `unscheduled_reasons`：未安排原因、必去点覆盖说明或约束取舍说明。

多候选响应示意：

```json
{
  "city": "长沙",
  "candidates": [
    {
      "variant_name": "平衡推荐方案",
      "strategy": "balanced",
      "total_score": 712.4,
      "comparison": {
        "total_stops": 10,
        "total_travel_minutes": 188,
        "must_visit_covered": 2,
        "open_time_risks": 0,
        "pareto_rank": 1,
        "dominated": false,
        "tradeoff_summary": "Pareto 第 1 层：在评分、通勤、风险和必去覆盖之间没有被其他候选完全支配。",
        "pareto_debug": [
          "未发现其他候选在总分、必去覆盖、通勤、开放时间风险和未安排数量上同时不差且至少一项更优。",
          "指标向量：score=712.4, must=2, travel=188, risk=0, unscheduled=0"
        ],
        "poi_overlap_with_baseline": 1.0,
        "area_overlap_with_baseline": 1.0,
        "unique_poi_count": 0,
        "unique_pois": [],
        "diversity_tags": ["基线方案"],
        "diversity_summary": "作为候选对比基线，其他方案会计算相对它的 POI 和区域差异。"
      },
      "days": [
        {
          "day": 1,
          "time_window_feasible": true,
          "time_window_diagnostics": [
            "最终顺序已通过统一时间窗复核：站点顺序、开放时间、餐饮窗口和当日结束时间均可行。"
          ],
          "beam_trace": [
            {
              "slot": "上午",
              "input_states": 1,
              "expanded_states": 6,
              "kept_states": 5,
              "kept_state_summaries": ["score=194.8 travel=22 stops=1 path=湖南博物院"],
              "decision": "按 Beam 状态评分保留 Top-5，评分综合兴趣、通勤惩罚和站点覆盖。"
            }
          ]
        }
      ]
    }
  ]
}
```

## GET /route/shortest

查询两个 POI 间最短通勤路径。

参数：

- `from`：起点 POI id 或名称。
- `to`：终点 POI id 或名称。
- `algorithm`：`dijkstra` 或 `astar`，默认 `dijkstra`。

示例：

```powershell
curl.exe "http://127.0.0.1:8080/route/shortest?from=hotel_wuyi&to=yuelu_academy&algorithm=astar"
```

## GET /poi/search

检索 POI、餐厅或注意事项。服务端使用轻量 BM25 饱和项、字段权重和热度加权排序，字段权重覆盖名称、标签、区域和描述。

参数：

- `q`：关键词。
- `type`：可选，`attraction`、`restaurant`、`hotel`、`nightlife`。
- `limit`：返回数量，默认 10。

响应字段除基础 POI 信息外，还包含：

- `matched_terms`：命中的查询词。
- `score_explanation`：排序解释，说明 BM25 和字段权重如何影响结果。
- `score_contributions`：排序贡献拆解，按名称、标签、区域、描述和热度说明 BM25 分数来源。

## POST /trip/alternatives

按场景返回替换方案。

支持场景：

- `下雨`
- `闭馆`
- `太累`
- `预算降低`

## POST /itinerary/explain

输入结构化行程或行程偏好，返回 LLM 或模板生成的中文解释。

远程 LLM 使用内置 HTTP client 调用 OpenAI 兼容 `chat/completions` 接口。未配置 `OPENAI_API_KEY`、设置 `LLM_DISABLED=1` 或远程调用失败时自动回退到本地模板。

## POST /trip/chat

自然语言行程规划接口。用户用中文描述旅行需求，系统自动解析意图、匹配 POI、规划行程并生成自然语言回复。

这是 LLM + 传统算法 Hybrid 架构的核心端点：LLM 负责理解意图和生成文案，Beam Search 负责约束求解。

请求示例：

```json
{
  "message": "帮我规划3天长沙之旅，带老人同行，想去橘子洲头和岳麓山，不要太累",
  "context": [
    {"role": "user", "content": "之前聊过，我对历史文化比较感兴趣"}
  ]
}
```

- `message`：用户自然语言输入，必填。
- `context`：可选，多轮对话历史数组，每项含 `role` 和 `content`。

响应示例：

```json
{
  "reply": "为您规划了一条轻松的3天长沙文化之旅！第一天...",
  "parsed_request": {
    "city": "长沙",
    "days": 3,
    "interests": ["历史文化", "休闲"],
    "must_visit": ["poi_juzizhou"],
    "pace": "轻松"
  },
  "poi_matching": [
    {
      "query": "橘子洲头",
      "matched_id": "poi_juzizhou",
      "matched_name": "橘子洲头景区",
      "score": 8.5,
      "confidence": "high"
    }
  ],
  "candidates": [ ... ],
  "suggestions": []
}
```

关键流程：

1. LLM 从自然语言中提取结构化参数（天数、兴趣、必去景点、节奏等）。
2. 通过 BM25 搜索引擎模糊匹配 POI 名称，解决"岳麓山"→"岳麓山风景名胜区"的名称不一致问题。
3. 调用 Beam Search 引擎生成 5 个策略候选方案。
4. LLM 根据最佳候选生成自然语言行程摘要。

错误码：

- `400 VALIDATION_ERROR`：message 为空。
- `422 PARSE_FAILED`：LLM 无法理解用户意图。
- `503 LLM_NOT_CONFIGURED`：未配置 LLM API Key。

需要配置 LLM 环境变量才能使用此端点：

```bash
export LLM_BASE_URL=https://api.deepseek.com
export OPENAI_API_KEY=your-key
export LLM_MODEL=deepseek-chat
```

## POST /trip/jobs

异步提交行程规划任务。请求体与 `/trip/plan` 相同，适合候选方案较多或希望演示削峰链路的场景。

响应：

```json
{
  "job_id": "req-18b0f1-1",
  "status": "QUEUED",
  "status_url": "/trip/jobs/req-18b0f1-1"
}
```

## GET /trip/jobs/{id}

查询异步任务状态。`status` 可能为 `QUEUED`、`RUNNING`、`SUCCEEDED`、`FAILED`、`CANCELLED`。成功后返回 `result`，其结构与 `/trip/plan` 同步响应一致。响应同时包含 `queue_wait_ms` 和 `execution_ms`，用于观察排队等待与实际规划耗时。

## DELETE /trip/jobs/{id}

取消尚未运行或已完成的任务，并返回：

```json
{
  "job_id": "req-18b0f1-1",
  "status": "CANCELLED"
}
```

## GET /metrics

返回 JSON 指标快照，用于本地演示、压测和面试说明：

```json
{
  "total_requests": 12,
  "in_flight_requests": 1,
  "rejected_requests": 0,
  "max_in_flight": 32,
  "status_codes": { "200": 10, "202": 1 },
  "cache": { "hits": 4, "misses": 3, "hit_rate": 0.57, "entries": 3, "evictions": 0 },
  "db": { "enabled": true, "path": "storage/tourpass.sqlite", "write_count": 5, "write_failures": 0 },
  "jobs": { "QUEUED": 0, "RUNNING": 0, "SUCCEEDED": 1, "FAILED": 0, "CANCELLED": 0, "total": 1, "queue_depth": 0, "worker_count": 2, "completed_jobs": 1, "failed_jobs": 0, "avg_queue_wait_ms": 12.5, "avg_execution_ms": 430.0 },
  "runtime": { "workers": 8, "job_workers": 2, "max_queue": 64, "max_in_flight": 32, "max_body_bytes": 65536 }
}
```

## GET /history/jobs

返回最近异步任务摘要，供本地演示持久化能力使用；不返回完整行程结果。

参数：

- `limit`：默认 `20`，最大 `100`。

```json
{
  "data": [
    {
      "id": "req-18b0f1-1",
      "status": "SUCCEEDED",
      "queue_wait_ms": 4,
      "execution_ms": 430,
      "created_at": "2026-05-22T00:00:00.000Z",
      "updated_at": "2026-05-22T00:00:01.000Z"
    }
  ]
}
```

## POST /benchmark/runs

记录一次本地 benchmark 摘要到 SQLite。该接口面向本地压测脚本，不承诺 Prometheus 或商业 APM 格式。

请求字段：

- `started_at`
- `duration_seconds`
- `concurrency_steps_json`
- `summary_json`
- `report_path`

## 运行时环境变量

- `TOURPASS_WORKERS`：HTTP 线程池 worker 数，默认按 CPU 核心数保守设置。
- `TOURPASS_MAX_QUEUE`：HTTP 请求队列上限。
- `TOURPASS_MAX_BODY_BYTES`：JSON 请求体大小限制。
- `TOURPASS_MAX_IN_FLIGHT`：进行中请求上限，超过时返回 `TOO_MANY_REQUESTS`。
- `TOURPASS_CACHE_ENTRIES`：进程内响应缓存容量。
- `TOURPASS_CACHE_TTL_SECONDS`：缓存 TTL。
- `TOURPASS_MAX_TRIP_JOBS`：异步任务仓库保留数量。
- `TOURPASS_JOB_WORKERS`：异步规划任务 worker 数。
- `TOURPASS_DB_PATH`：SQLite 数据库路径，默认 `storage/tourpass.sqlite`。
- `TOURPASS_DB_DISABLED=1`：禁用 SQLite，服务退回纯内存演示模式。
- `TOURPASS_POIS_PATH` / `TOURPASS_EDGES_PATH`：覆盖默认样例数据路径，主要用于 synthetic 规模实验。
- `TOURPASS_DISTANCE_CACHE_MODE`：POI 最短路缓存模式，支持 `auto`、`all_pairs`、`on_demand`、`disabled`。
- `TOURPASS_DISTANCE_CACHE_MAX_POIS`：`auto` 模式下允许全量两两缓存的最大 POI 数，默认 `300`。
- `TOURPASS_DISTANCE_CACHE_ENTRIES`：`on_demand` 模式 LRU 缓存容量，默认 `10000`。
- `TOURPASS_BEAM_WIDTH` / `TOURPASS_BRANCH_FACTOR`：Beam Search 保留状态数和每槽分支数，默认 `5` / `6`。
- `TOURPASS_TRAVEL_TIME_PROVIDER`：通勤时间数据源，`local`（默认，使用本地 edges.json）或 `amap`（实时高德路线 API）。
- `TOURPASS_AMAP_API_KEY` / `AMAP_API_KEY`：高德 API Key，`amap` provider 需要。
- `TOURPASS_DEFAULT_CITY`：设置默认规划城市（如 `changsha`、`wuhan`）；如果未设置，则使用城市列表中的第一个可用城市。单次请求仍可通过请求体中的 `city` 选择目的地。

## 错误格式

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数不合法",
    "details": {
      "reason": "days must be between 1 and 7"
    }
  }
}
```

新增错误码包括 `PAYLOAD_TOO_LARGE`、`TOO_MANY_REQUESTS`、`QUEUE_FULL`、`DB_UNAVAILABLE`、`JOB_NOT_FOUND`、`JOB_FAILED` 和 `INTERNAL_ERROR`，仍保持统一错误结构。
