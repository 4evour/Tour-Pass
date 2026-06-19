# Multi-Agent Itinerary Quality Design

## 背景

本轮目标是修复多 Agent 生成逻辑导致的行程质量问题：小众非景点进入主行程、餐厅和景点分配不均、最后一天内容塌陷、通勤和天气信息没有被充分消费、前端无法解释行程为什么这样排。

用户确认的方向：

- 真实路线优先，参考小红书和后续旅游攻略数据。
- 借鉴经典可靠策略，严格拦截无证据小众点。
- 复用现有结构化表单里的 `pace` 表达行程饱满度。
- 每天景点尽量在同一区域，通勤合理是硬约束。
- 预留后续上传其他城市旅游攻略 PDF 的数据接口。
- 前端展示、导出路线图、高德导航能力要和后端质量数据打通。

## 非目标

- 本轮不实现 PDF 解析器。
- 本轮不全量补齐所有城市高德路径边。
- 本轮不删除交通枢纽数据；只要求它们不进入主行程候选。
- 本轮不生成伪造景点图片。

## 当前数据审计结论

- 所有 `data/*/pois.json` 中 `lat/lng` 缺失或为 0 的 POI 数量为 0。
- 非高德来源或缺少 `source_id` 的 POI 共 152 个：
  - `transit`: 116 个，主要是交通枢纽，存在标签/描述错乱，例如火车站被描述为机场。
  - `hotel`: 36 个，来源为 `generated`，应作为酒店 fallback，而不是强真实推荐。
- 当前高德真实路径边覆盖不足。示例：
  - 广州：851 条边，136 条 `amap`，真实高德占 16.0%。
  - 成都：872 条边，291 条 `amap`，真实高德占 33.4%。
  - 多数城市真实高德边占比只有 3% 到 9%。
  - 长沙当前边数为 0。

结论：景点坐标数据目前完整，但路径可信度不足；通勤门禁必须区分真实高德路径和估算路径。

## 核心设计

多 Agent 不再只串行产出一个行程，而是围绕共享质量契约工作：

```text
Data Sources
-> PoiAgent 分层候选
-> SchedulerAgent 按区域、节奏、通勤排程
-> ReviewerAgent 输出结构化失败码
-> Graph 根据失败码回 Scheduler 定向返修
-> Frontend 展示质量证据和降级原因
```

## POI 分层

`rank_pois` 继续负责排序，新分层负责判断 POI 是否有资格进入主行程。

### core_hotspots

经典热门景点。准入规则：

- `type == "attraction"`。
- 不命中低价值 POI 过滤。
- 有有效 `lat/lng` 和 `area`。
- 满足任一强证据：
  - `popularity >= 4.7`。
  - 标签命中地标、国家级景点、博物馆、风景名胜、历史文化、世界遗产等经典信号。
  - `xhs_frequency >= 3`。

缺图不影响进入 `core_hotspots`，只标记 `image_missing`。

### route_supported

真实路线支持景点。准入规则：

- 可以不是最高热度。
- 必须有真实路线证据：
  - 小红书路线出现。
  - 与核心景点存在同日共现。
  - 后续 PDF/攻略证据命中。

### fallback_only

默认不进入主行程，只作为替换或备选：

- 没有热门证据。
- 没有路线证据。
- 展示内容弱，例如无图、无有效描述、无攻略文案。
- 坐标或来源可信度不足。

### transit 和 generated hotel

- `transit` 不参与景点推荐，只能作为起点、终点、交通枢纽。
- `generated` hotel 只能作为酒店 fallback，前端和后端都应标记低可信。

## Pace 即饱满度

结构化表单中的 `pace` 直接定义每日最低质量。

```text
relaxed:
  每天至少 2 个主景点
  至少 1 餐
  允许半天自由活动，但必须明确说明

balanced:
  每天至少 3 个主景点
  午餐 + 晚餐
  最后一天至少 2 个主景点，不能只剩餐厅

intense:
  每天至少 4 个主景点
  午餐 + 晚餐
  同一区域热门点可以密集安排
```

餐厅是嵌入行程，不是填充行程。除非用户选择美食优先，否则餐厅数量不能大于或等于主景点数量。

## 区域和通勤约束

每天先确定 `day_anchor_area`：

1. 必去景点所在区域。
2. 真实路线同日共现最多的区域。
3. `core_hotspots` 密度最高的区域。
4. 酒店附近或通勤最短区域。

当天景点选择优先级：

1. `day_anchor_area` 内的 `core_hotspots`。
2. `day_anchor_area` 内的 `route_supported`。
3. 邻近区域的 `core_hotspots`。
4. 仍不足时降级并给出 `quality_warnings`，不乱塞远距离小众点。

建议通勤门槛：

```text
单段景点间通勤:
  relaxed <= 35min
  balanced <= 30min
  intense <= 25min

当天总通勤:
  relaxed <= 90min
  balanced <= 110min
  intense <= 130min
```

紧凑行程允许总通勤稍高，但单段通勤必须更短。

## 路径数据可信度

新增统一路径结果结构：

```json
{
  "minutes": 12,
  "distance_meters": 1800,
  "route_source": "amap_live | amap_cached | geo_estimated | missing",
  "polyline": []
}
```

调度使用优先级：

1. `amap_cached`: `edges.json` 中已有真实高德边。
2. `amap_live`: 线上配置允许时实时查询高德并缓存。
3. `geo_estimated`: 经纬度估算，只能作为弱依据。
4. `missing`: 不能用于紧凑行程。

`SchedulerAgent` 必须为每个 stop 写入：

- `travel_minutes_from_previous`
- `route_source`
- `distance_meters`
- `transport_hint`

`ReviewerAgent` 判断通勤失败时必须区分：

- `excessive_commute_confirmed`: 高德真实路径超阈值，必须返修。
- `excessive_commute_estimated`: 估算路径超阈值，优先返修并显示可信度提示。

城市真实高德边覆盖率低于 60% 时，前端需要显示“部分通勤为估算”。

## Reviewer 失败码

`ReviewerAgent` 输出机器可执行失败码，而不是只输出自然语言建议。

```json
{
  "passed": false,
  "quality_failures": [
    {
      "code": "unsupported_poi",
      "severity": "high",
      "day": 2,
      "poi_name": "某小众点",
      "reason": "不是热门 POI，也没有真实路线证据",
      "repair": "remove_or_replace",
      "preferred_area": "越秀区"
    }
  ]
}
```

第一阶段支持：

- `unsupported_poi`
- `day_underfilled`
- `weak_last_day`
- `meal_attraction_imbalance`
- `area_scattered`
- `excessive_commute_confirmed`
- `excessive_commute_estimated`
- `isolated_poi`
- `weather_mismatch`
- `location_unverified`

返修动作：

- `unsupported_poi`: 替换为同区 `core_hotspots` 或 `route_supported`。
- `day_underfilled`: 从 `day_anchor_area` 补主景点，不用餐厅凑数。
- `weak_last_day`: 从前几天过满区域挪点，或从同区热门池补。
- `meal_attraction_imbalance`: 删除低优先餐厅或补主景点。
- `area_scattered`: 重新选择当天 `day_anchor_area`。
- `excessive_commute_*`: 替换远点或重排区域。
- `isolated_poi`: 非必去移出；必去独立成半天主题。
- `weather_mismatch`: 室内优先替换，但不能导致空日。
- `location_unverified`: 主行程移除或要求用户确认。

如果返修达到最大轮次仍不达标，不能静默通过，必须返回 `quality_warnings`。

## 天气约束

天气只影响排序和替换，不允许直接删景点导致当天过空。

- 雨天或恶劣天气：室内点优先。
- 高 UV：室内或阴凉点优先。
- 极端天气：可以降低饱满度，但前端必须显示降级原因。

前端优先使用后端 QWeather 数据，不再另行调用 Open-Meteo 生成另一套天气。

## 新旅游数据接口

后续 PDF、官方攻略、人工导入、小红书路线都统一转成 `TravelEvidence`。

```json
{
  "city": "广州",
  "source_type": "xhs_route | pdf_guide | official_guide | manual",
  "source_title": "广州三日游攻略",
  "source_url": "",
  "poi_name": "陈家祠",
  "matched_poi_id": "amap_xxx",
  "evidence_type": "mention | same_day_route | recommended_combo | area_cluster",
  "day_index": 1,
  "cooccur_poi_names": ["沙面", "永庆坊"],
  "area": "荔湾区",
  "confidence": 0.82
}
```

PDF 后续流程：

```text
上传 PDF
-> 提取文本
-> 识别城市、天数、POI 名称、同日组合、路线顺序
-> 匹配本地 pois.json 或高德 POI
-> 写入 TravelEvidence
-> 触发该城市 POI 图片和路径补全任务
```

PDF 不能直接变成行程，只能变成证据。

## 图片策略

图片来源优先级：

1. 高德照片补全。
2. 官方或开放图库图片，例如 Wikimedia Commons，并记录 license。
3. 管理员上传或绑定图片 URL。
4. PDF 图片仅作内部参考，除非确认授权。
5. 类型占位图兜底，不生成伪装实拍的 AI 图片。

质量规则：

- `core_hotspots`: 缺图不降级，只标记 `image_missing`。
- `route_supported`: 缺图轻微降权，但有路线证据仍可进主行程。
- `fallback_only`: 缺图且无路线证据且文案弱，不进主行程。

## 前端展示

结果页要展示后端质量证据，而不是只展示列表。

每日字段：

```json
{
  "day": 1,
  "anchor_area": "荔湾区",
  "fullness_status": "ok",
  "quality_warnings": [],
  "total_travel_minutes": 72,
  "amap_route_ratio": 0.83,
  "weather": {},
  "weather_adjustments": ["小雨，室内景点提前"],
  "evidence_summary": "参考 4 条真实路线"
}
```

Stop 字段：

```json
{
  "poi_name": "陈家祠",
  "poi_tier": "core_hotspot",
  "evidence_sources": ["amap_popularity", "xhs_route"],
  "image_missing": false,
  "travel_minutes_from_previous": 12,
  "route_source": "amap_cached",
  "transport_hint": "建议打车或地铁",
  "address": "广州市荔湾区中山七路",
  "amap_navigation_url": "https://uri.amap.com/navigation?..."
}
```

UI 要求：

- 每天标题显示 `Day 1 · 荔湾区深度游`。
- 每天顶部显示主区域、天气、总通勤、真实路径占比、饱满度状态。
- 景点卡显示 `core_hotspot`、`route_supported`、`必去` 标签。
- 景点之间显示通勤条：`12 分钟 · 高德路径` 或 `8 分钟 · 估算`。
- 图片轮播统一到所有结果卡。
- 无图显示“暂无实景图”，不伪造图片。
- 质量降级时展示 `quality_warnings`。

## 导出路线图和高德导航

导出分三种：

- HTML 分享页：可点击景点地址、地图 marker，打开高德导航。
- PNG：展示二维码和可读地址，适合手机保存和分享。
- PDF：地址文字可点击，同时显示二维码。

每个 POI 需要：

```json
{
  "address": "广州市荔湾区中山七路",
  "lat": 23.129,
  "lng": 113.264,
  "source_id": "B00140xxx",
  "amap_navigation_url": "https://uri.amap.com/navigation?...",
  "amap_marker_url": "https://uri.amap.com/marker?..."
}
```

路线图规则：

- 每天一种颜色。
- 景点和餐厅按顺序编号。
- 高德真实路径用实线。
- 估算路径用虚线并标注“估算”。
- 无法确认路线时只显示点位，不画路线。

## 验证计划

- 数据审计：检查无坐标 POI、非高德来源 POI、低质量 transit 文案。
- 单元测试：POI 分层、`pace` 饱满度、Reviewer 失败码、返修动作。
- 回归测试：典型城市 3 天 balanced/intense，确认最后一天不塌、餐厅不挤占景点。
- 路径测试：确认 `travel_minutes_from_previous` 和 `route_source` 被写入前端格式。
- 前端测试：天气、通勤条、图片轮播、质量警告、导出导航链接。
- 数据覆盖报告：每个城市输出高德真实边占比，低于阈值时显示估算提示。

## 交付边界

第一阶段实现质量闭环和前端展示字段，不承诺补齐所有真实高德边。

第二阶段做高德边补全队列、PDF 攻略导入、图片补全和导出路线图增强。
