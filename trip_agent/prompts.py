from __future__ import annotations

PLAN_OUTPUT_GUIDE = r"""
最终交付时，action 必须为 "plan"，reply 是 1~2 句可直接展示给用户的总览，plan 必须严格使用下面的 JSON 结构。不要省略字段；未知事实写 null 或 "unknown"，不能编造。

{
  "city": "城市",
  "title": "有辨识度的行程标题",
  "overview": "100~160 字，解释整体路线、节奏和核心取舍",
  "date_range": {"start": "YYYY-MM-DD|null", "end": "YYYY-MM-DD|null"},
  "trip_profile": {
    "days": 3,
    "pace": "relaxed|balanced|intensive",
    "transport_preference": "public_transit|driving|walking|mixed",
    "travelers": "同行人说明",
    "preferences": ["偏好"],
    "assumptions": ["模型采用的默认假设"]
  },
  "hotel": {
    "name": "酒店名；未指定时写推荐住宿区域",
    "area": "区域",
    "address": "地址|null",
    "location": "经度,纬度|null",
    "status": "confirmed|recommended_area|unknown",
    "reason": "为何适合作为每日锚点",
    "source": "amap|user|model_judgment"
  },
  "candidate_comparison": {
    "areas": [{"name": "候选区域", "highlights": ["优点"], "tradeoffs": ["代价"], "fit_score": 0, "selected": true}],
    "selected_areas": ["最终区域"],
    "selection_reason": "区域组合与取舍"
  },
  "days": [
    {
      "day": 1,
      "date": "YYYY-MM-DD|null",
      "weekday": "星期几|null",
      "theme": "当天主题",
      "summary": "当天玩法和节奏说明",
      "start_time": "HH:MM",
      "end_time": "HH:MM",
      "start_anchor": {"name": "酒店或起点", "type": "hotel|area|station|place", "location": "经度,纬度|null"},
      "end_anchor": {"name": "酒店或终点", "type": "hotel|area|station|place", "location": "经度,纬度|null"},
      "area_cluster": {"primary_area": "主活动区域", "secondary_areas": ["相邻区域"], "rationale": "为何适合同一天"},
      "schedule": [
        {
          "period": "morning|lunch|afternoon|dinner|evening",
          "type": "visit|meal|hotel|free_time",
          "start": "HH:MM",
          "end": "HH:MM",
          "duration_minutes": 120,
          "place_id": "高德 POI ID|null",
          "name": "地点或活动名称",
          "reason": "具体体验价值，避免空泛套话",
          "opening_hours": "工具返回的营业时间|null",
          "opening_match": "matched|unknown|risk",
          "reservation": {"required": false, "status": "not_required|recommended|required|unknown", "note": "预约说明|null"},
          "address": "地址|null",
          "location": "经度,纬度|null",
          "source": "amap|user|model_judgment",
          "practical_tips": ["现场执行建议"]
        }
      ],
      "transfers": [
        {
          "from_name": "出发地", "to_name": "目的地",
          "from_location": "route 请求的 origin；未查询则为 null", "to_location": "route 请求的 destination；未查询则为 null",
          "mode": "walking|transit|driving|taxi|mixed", "start": "HH:MM", "end": "HH:MM",
          "duration_minutes": 30, "distance_meters": 5000, "instructions": "简洁换乘或行驶说明",
          "source": "amap|unknown", "evidence_hash": "route 工具返回的 response_hash；未查询则为 null"
        }
      ],
      "risks": [{"level": "info|warning|critical", "type": "weather|opening|reservation|traffic|walking|other", "title": "风险标题", "detail": "风险事实", "mitigation": "应对方式", "source": "amap|qweather|model_judgment", "evidence_hash": "天气事实复制 weather 工具 response_hash；其他建议为 null"}]
    }
  ],
  "map": {
    "route_overview": "整趟行程的空间移动说明；points 和 center 由系统根据已核验地点生成"
  },
  "narrative": {
    "headline": "一句话体验定位", "summary": "120 字以内的可读行程叙事",
    "highlights": ["亮点"], "tradeoffs": ["明确取舍"], "weather_advice": "结合天气的调整建议|null"
  },
  "warnings": ["最多 3 条全局提醒"]
}

输出要求：
1. 每天必须有起止时间、起终点、摘要、区域聚类、统一时间轴、交通段和风险列表。
2. 时间轴按时间升序，至少覆盖上午、午餐、下午；适合夜游时加入晚餐和晚间。每项都有开始、结束和停留分钟数。
3. 相邻时间轴项目之间必须有交通段。已查询路线必须原样复制 route 请求的 origin/destination 到 from_location/to_location，并复制响应的 response_hash 到 evidence_hash；系统只有在三者与真实工具证据全部一致时才接受时间和距离。未查询写 source="unknown"、位置与 evidence_hash 为 null、duration_minutes=0、distance_meters=0，不得给伪精确数字。
4. 地点 ID、规范名称、地址、坐标从地点工具复制。不得把模型记忆中的地点标记为 amap。
5. opening_match 必须比较到访时段与开放时间；缺数据写 unknown，并加入风险列表。
6. 未指定酒店时，选择推荐住宿区域作为每日锚点，status="recommended_area"，不能虚构酒店。
7. 比较至少 2 个候选区域，说明入选理由和舍弃代价；candidate_comparison 明确属于模型判断。
8. 同一 POI 不得跨天重复。餐饮和自由活动也进入统一时间轴。
9. 风险覆盖已发现的天气、闭馆、预约、交通和步行问题；没有证据时说明未知。天气风险只有复制 weather 响应的 response_hash 到 evidence_hash 才能标记为 amap/qweather；其他未绑定证据的风险写 model_judgment。
10. narrative 像旅行顾问的成品方案，讲清体验节奏与取舍，不机械复述字段。
11. 完整但紧凑：每天安排 2~4 个主要时间轴项目，候选区域 2~3 个，每项 practical_tips 最多 1 条，每天 risks 最多 2 条，全局 warnings 最多 3 条；不得在多个字段重复同一段说明。无需输出 map.points、map.center 或 quality，系统会根据证据自动生成地图点与完整度检查。
12. 最终 JSON 总长度必须控制在 12000 个字符以内，并确保对象完整闭合。overview、当天 summary 和 narrative.summary 各不超过 120 字，其余单段文字不超过 60 字；使用单行紧凑 JSON，压缩措辞而不是删除时间轴、交通、风险等必需结构。
"""
