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

根据用户偏好生成结构化行程。`candidate_count` 大于 1 时返回 `candidates` 数组。

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
- `optimization_summary`：日内局部交换优化结果。
- `original_travel_minutes` / `optimized_travel_minutes`：优化前后通勤时间。
- `constraint_explanations`：开放时间、餐饮窗口、必去点、通勤成本等解释。
- `unscheduled_reasons`：未安排原因或必去点覆盖说明。

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

检索 POI、餐厅或注意事项。

参数：

- `q`：关键词。
- `type`：可选，`attraction`、`restaurant`、`hotel`、`nightlife`。
- `limit`：返回数量，默认 10。

## POST /trip/alternatives

按场景返回替换方案。

支持场景：

- `下雨`
- `闭馆`
- `太累`
- `预算降低`

## POST /itinerary/explain

输入结构化行程或行程偏好，返回 LLM 或模板生成的中文解释。

未配置 `OPENAI_API_KEY` 时自动回退到本地模板。

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
