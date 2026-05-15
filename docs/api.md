# Tour Pass API 文档

默认服务地址：

```text
http://127.0.0.1:8080
```

## GET /health

返回服务、数据和 LLM 配置状态。

```json
{
  "status": "ok",
  "data_loaded": true,
  "poi_count": 25,
  "llm_configured": false
}
```

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
- `summary`：每日安排摘要，包含 Beam Search 选择过程、节奏、兴趣优先级和演示重点。
- `stops[].reason`：站点级决策依据，说明兴趣匹配、通勤、评分、开放时间等因素。
- `stops[].score_breakdown`：站点评分拆解，包含热度、兴趣匹配、必去加权、通勤惩罚、价格惩罚和时间窗惩罚等组件。
- `optimization_summary`：日内局部交换优化结果，说明优化前后通勤变化。
- `original_travel_minutes` / `optimized_travel_minutes`：优化前后通勤时间。
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
        "tradeoff_summary": "Pareto 第 1 层：在评分、通勤、风险和必去覆盖之间没有被其他候选完全支配。"
      },
      "days": []
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
