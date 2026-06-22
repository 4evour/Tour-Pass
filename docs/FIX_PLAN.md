# Tour Pass 修复方案（详细执行手册）

> 本文档供接手修复的 AI / 工程师使用。每项包含：**问题定位、根因、修复方案（含代码骨架）、验收标准、风险点**。
> 建议按 `P0 → P1 → P2` 顺序执行，每完成一组跑一次端到端回归（`tests/test_multi_agent.py` + 手动 `/agent/plan`）。

## 术语与约定
- **C\*** = 多Agent工作流类缺陷
- **P\*** = 景点数据库(POI)类缺陷
- **S\*** = 行程保存/持久化类缺陷
- **G\*** = 通用/配置类缺陷
- 文件路径相对仓库根 `D:\Tour Pass`
- Python 服务：`api_multi_agent.py` (端口 8090)
- C++ 主服务：`src/api.cpp` (端口 8080，含认证/行程持久化/路由优化，反代 `/agent/*` 到 Python)

---

# P0 — 必须立即修复（影响核心功能正确性）

## 【C1】审核错误数兜底逻辑失效
**文件**：`graph.py:42,197-210` + `agents/state.py:98-100,141`

**根因**：`errors` 字段用 `replace_list` reducer，每个节点返回时**整体替换** errors，所以 `route_review` 里 `len(errors) >= _MAX_TOLERABLE_ERRORS(3)` 这个"防死循环"判断永远不成立（单节点一次最多产生 1~2 个 error）。

**修复方案**：新增一个**累加型计数器**字段，专门追踪"本请求累积的非关键错误数"，独立于会被重置的 `errors` 列表。

1. `agents/state.py` 新增字段：
```python
# 在 TourState 中新增（与 errors 解耦的累计计数器）
cumulative_error_count: Annotated[int, "累计非关键错误数，只增不减"]
# reducer: 累加
def accumulate_int(left: int, right: int) -> int:
    return left + (right or 0)
```
把字段定义改为：
```python
cumulative_error_count: Annotated[int, accumulate_int]
```

2. `agents/base.py` 非关键 agent 降级返回时，同时返回计数：
```python
# agents/base.py 第 99 行附近
return {
    "errors": [error_msg],
    "cumulative_error_count": 1,   # 新增
    "sse_events": [...],
}
```
`graph.py` 的 `node_data_gather` 在合并 errors 时也要同步累加（`merged["cumulative_error_count"] = len(errors)` 或逐个加）。

3. `graph.py:route_review` 改用新字段：
```python
def route_review(state: TourState) -> str:
    review = state.get("review_result")
    cycle = state.get("review_cycle", 0)
    cum_errors = state.get("cumulative_error_count", 0)  # 改这里
    if cum_errors >= _MAX_TOLERABLE_ERRORS:
        ...
```

4. `create_initial_state` / `create_initial_state_from_intent` 初始化 `"cumulative_error_count": 0`。

**验收**：构造一个 WeatherAgent 必失败的用例（QWEATHER_KEY 故意置空 + 断网），连续触发 3 次以上非关键错误，确认 route_review 能 force-pass 而非无限重排。

**风险**：低。新字段不影响现有逻辑。

---

## 【P1】open_minutes/close_minutes 字段不匹配（营业时间感知完全失效）
**文件**：`agents/scheduler_agent.py:229-238`（`_check_opening_time`）

**根因**：实测 `data/changsha/pois.json`（321 条）**0 个** POI 有 `open_minutes`/`close_minutes`，全部用字符串 `open_time:"09:00"`。`_check_opening_time` 直接读 `attr.get("open_minutes", 480)` 永远拿到默认值，营业时间保护形同虚设。

**修复方案**：在 PoiAgent 加载 POI 时，**一次性把 `open_time`/`close_time` 字符串预解析成分钟数**写入 POI，下游全部读数值字段。

1. `agents/poi_agent.py` 新增解析函数并在 `_load_pois` 返回前调用：
```python
@staticmethod
def _normalize_time_fields(poi: dict) -> None:
    """把 open_time/close_time ('HH:MM') 预解析成 open_minutes/close_minutes。"""
    def _parse(t):
        if not t or not isinstance(t, str):
            return None
        try:
            h, m = t.split(":")[:2]
            v = int(h) * 60 + int(m)
            return v if 0 <= v < 1440 else None
        except (ValueError, IndexError):
            return None
    # 仅当数值字段缺失时才补，避免覆盖已有数据
    if poi.get("open_minutes") is None:
        poi["open_minutes"] = _parse(poi.get("open_time"))
    if poi.get("close_minutes") is None:
        close = _parse(poi.get("close_time"))
        poi["close_minutes"] = close
```
在 `_load_pois` 的 `return deduped` 前加：
```python
for p in deduped:
    self._normalize_time_fields(p)
```

2. `agents/scheduler_agent.py:_check_opening_time` 改为容忍 None：
```python
@staticmethod
def _check_opening_time(attr: dict, arrival: int) -> tuple[int, int]:
    duration = attr.get("visit_duration_minutes", 60)
    open_t = attr.get("open_minutes") or 480      # None → 默认
    close_t = attr.get("close_minutes") or 1080
    if arrival < open_t:
        arrival = open_t
    end = min(arrival + duration, close_t)
    duration = max(end - arrival, 30)
    return arrival, duration
```
注意 `open_t = attr.get("open_minutes") or 480` —— 用 `or` 同时处理 None 和 0。

3. 同步修正 `_preferred_evening_start`（已有 fallback 解析 open_time，但应优先读 open_minutes，保持一致）。

**验收**：选一个 open_time=09:00 的景点，构造 arrival=480（8:00），确认被调整到 540（9:00）。再选 close_time=17:00 的，确认 end 不超过 1020。

**风险**：低。`_normalize_time_fields` 只补不覆盖。

---

## 【S1】修改后的行程永远不会回写到已保存行程（PG）
**文件**：`src/pg_store.cpp:515` + `src/pg_store.h` + `src/api.cpp`（新增路由）+ `web/app.js`

**根因**：`saveTrip` 只 `INSERT`，无 `updateTrip`；C++ 无 `/trips/:id` 的 PUT/PATCH。用户 `/agent/modify` 后改动只在 Python 进程内，刷新即丢，PG 永远是旧版。

**修复方案**：

1. **后端 C++ — 新增 updateTrip**：
`src/pg_store.h` 加声明：
```cpp
bool updateTrip(int64_t tripId, int64_t userId, const std::string& title,
                const std::string& requestJson, const std::string& responseJson);
```
`src/pg_store.cpp` 实现：
```cpp
bool PostgresStore::updateTrip(int64_t tripId, int64_t userId, const std::string& title,
                               const std::string& requestJson, const std::string& responseJson) {
    std::lock_guard<std::mutex> lock(mutex_);
    // title 为空则不更新标题
    std::string sql = "UPDATE saved_trips SET response_json=$1, request_json=COALESCE(NULLIF($2,''), request_json), "
                      "title=COALESCE(NULLIF($3,''), title), updated_at=NOW() WHERE id=$4 AND user_id=$5;";
    auto params = std::vector<std::string>{responseJson, requestJson, title,
                                            std::to_string(tripId), std::to_string(userId)};
    PGresult* res = queryP(sql, params);
    bool ok = PQresultStatus(res) == PGRES_COMMAND_OK;
    PQclear(res);
    return ok;
}
```
（若 `saved_trips` 表无 `updated_at` 列，先加 migration：`ALTER TABLE saved_trips ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();`）

2. **C++ 路由** `src/api.cpp` 在 `/trips/save` 之后新增：
```cpp
server.Put(R"(/trips/(\d+))", [&](const httplib::Request& req, httplib::Response& res) {
    auto [userId, role] = getAuthUser(req);
    if (userId <= 0) { setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401); return; }
    int64_t tripId = 0;
    try { tripId = std::stoll(req.matches[1]); } catch (...) {}
    try {
        auto body = nlohmann::json::parse(req.body);
        std::string title = body.value("title", "");
        std::string reqJson = body.contains("request") ? body["request"].dump() : "";
        std::string respJson = body.contains("response") ? body["response"].dump() : "";
        if (!context.store->updateTrip(tripId, userId, title, reqJson, respJson)) {
            setJson(res, errorJson("NOT_FOUND", "行程不存在或无权修改"), 404); return;
        }
        setJson(res, {{"status", "updated"}, {"id", tripId}});
    } catch (const std::exception& ex) {
        setJson(res, errorJson("INTERNAL_ERROR", "更新失败", {{"reason", ex.what()}}), 500);
    }
});
```

3. **前端** `web/app.js`：`/agent/modify` 成功后，若 `state.tripSaved`，自动回写：
```js
// 在 modify 成功的 then/await 之后（约 2527 行 fetch("/agent/modify") 的成功分支）
if (state.tripSaved && state.savedTripId) {
  try {
    await api(`/trips/${state.savedTripId}`, {
      method: "PUT",
      body: JSON.stringify({
        response: updatedItinerary,   // modify 返回的最新行程
        request: state.lastPayload,
      }),
    });
    toast("已同步保存的行程", "info");
  } catch (e) { console.warn("回写保存行程失败:", e); }
}
```

4. **分享链接同步**：`generateShareId` 后行程若被修改，share 链接指向的仍是旧数据。建议修改后若该 trip 已有 share_id，刷新 share 缓存（或在 `/s/:id` 渲染时实时读 DB，已是这样，无需额外处理，但需确认 `getTripByShareId` 读的是最新 response_json）。

**验收**：完整流程——规划→保存→modify 改一个景点→刷新页面→打开 profile→重新打开该行程，确认看到的是**修改后**的版本。

**风险**：中。涉及 C++ 重新编译（`build/`）、PG schema migration、前端联调。建议分两步先上后端再上前端。

---

# P1 — 高优先级（质量与数据正确性）

## 【S4】缓存 key 漏掉关键维度，返回错误方案
**文件**：`tools/cache.py:22-26`

**根因**：`_cache_key` 只含 `city:days:pace:strategy:must_visit`，**不含** budget/travelers/interests/hotel_area/hotel_budget/avoid/special_requests。`/agent/plan-sync` 的缓存快路径会直接返回错误方案。

**修复方案**：
```python
def _cache_key(city: str, days: int, pace: str, strategy: str,
               must_visit: list[str], **extra) -> str:
    must_sorted = sorted([m for m in (must_visit or []) if m])
    # 把所有影响行程的维度都纳入
    budget = (extra.get("budget") or "").strip()
    travelers = (extra.get("travelers") or "").strip()
    interests = "|".join(sorted(extra.get("interests") or []))
    avoid = "|".join(sorted(extra.get("avoid") or []))
    hotel_area = (extra.get("hotel_area") or "").strip()
    hotel_budget = f"{extra.get('hotel_budget_min',0)}-{extra.get('hotel_budget_max',0)}"
    special = (extra.get("special_requests") or "").strip().lower()
    raw = f"{city}:{days}:{pace}:{strategy}:{budget}:{travelers}:{interests}:{avoid}:{hotel_area}:{hotel_budget}:{special}:{'|'.join(must_sorted)}"
    return hashlib.md5(raw.encode()).hexdigest()
```
同步更新 `get_cached_itinerary` / `set_cached_itinerary` 的签名，传入完整 intent 维度。调用点（`api_multi_agent.py:559, 619, 725`）改为传 `intent=...` 或展开传参。

**注意**：key 变更后旧缓存自然失效（hash 不同），无需手动清理，但部署当天缓存命中率会降。

**验收**：两个请求 city/days/must_visit 相同但 budget 不同 → 缓存不命中。

**风险**：低。

---

## 【P2】酒店四层过滤中三层失效（brand_category/price 全缺失）
**文件**：`agents/hotel_agent.py:41-110, 197-208` + 数据层

**根因**：实测 65 家酒店 **0 个**有 `brand_category`/`price_per_night`/`price_range`。Layer3 品牌过滤永远空集跳过；`score_hotel_location` 的 `price_per_night` 恒 0。

**修复方案**（按工作量从小到大三选一，推荐 A+B 组合）：

**方案 A（代码层兜底，快）**：用 `price_level`（数据有 1~5）推断 brand_category 与价格区间，让过滤真正生效：
```python
# agents/hotel_agent.py 新增
def _ensure_hotel_meta(hotel: dict) -> dict:
    """数据补全：从 price_level 推断缺失的 brand_category / price_range。"""
    h = dict(hotel)
    level = int(h.get("price_level") or 1)
    if not h.get("brand_category"):
        cat_map = {1:"经济型", 2:"经济型", 3:"中端", 4:"高端", 5:"豪华"}
        h["brand_category"] = cat_map.get(level, "中端")
    if not h.get("price_range"):
        rng_map = {1:"100-300", 2:"200-400", 3:"300-600", 4:"500-1000", 5:"800-2000"}
        h["price_range"] = rng_map.get(level, "200-400")
    return h
```
在 `execute` 里 `hotels = load_pois_by_type(...)` 后立刻：
```python
hotels = [_ensure_hotel_meta(h) for h in hotels]
```
这样 Layer2 budget filter（`_matches_budget` 已能解析 price_range）和 Layer3 brand filter 都能生效。

**方案 B（数据层修复，彻底）**：写脚本 `scripts/enrich_hotels.py` 批量给 `data/*/pois.json` 的 hotel 类型补 `brand_category`/`price_range`（基于 price_level 规则），跑一次回写。已有 `scripts/enrich_hotels.py` 可扩展。

**方案 C（接真实价格 API）**：配置 `HOTEL_PRICE_PROVIDER`（`tools/hotel_price_api.py` 已预留接口），`merge_price_quotes` 会注入 `price_per_night`。需要供应商授权。

**验收**：构造 hotel_budget_max=300 的请求，确认预算外的酒店被过滤掉；budget=luxury 时 brand_category 落在"高端/豪华"。

**风险**：方案 A 低；方案 B 中（要回写数据，注意备份）。

---

## 【C2】thread_id 派生方式无效 + graph 无 checkpointer（误导性隔离）
**文件**：`api_multi_agent.py:458-464` + `main_multi_agent.py:56` + `graph.py:237`

**根因**：`builder.compile()` 没传 checkpointer，LangGraph 不按 thread_id 持久化；`thread_id = sha256(message)` 让发相同消息的用户共享同一 id。当前真正的隔离靠每次新建 state，thread_id 是误导。

**修复方案（二选一）**：

**方案 A（推荐，最小改动）**：删除 thread_id 的"隔离"承诺，改用每请求唯一 id，避免误导：
```python
# api_multi_agent.py
def _make_thread_id() -> str:
    """每请求唯一，避免相同消息共享状态。"""
    return uuid.uuid4().hex
```
调用处 `thread_id = _make_thread_id()`。同步更新注释说明"graph 无 checkpointer，thread_id 仅用于日志"。

**方案 B（真正持久化）**：若未来要支持断点续算，加 MemorySaver/SqliteSaver：
```python
from langgraph.checkpoint.memory import MemorySaver
graph = builder.compile(checkpointer=MemorySaver())
```
并让 thread_id 与 session_id 绑定（而非消息 hash）。成本较高，当前不必要。

**验收**：两个并发相同消息的请求，结果互不影响（本就该如此，加测试固化）。

**风险**：低（方案 A）。

---

## 【H5】IntentAgent must_visit 解析漏召回
**文件**：`agents/intent_agent.py:187-192, 282-339`

**根因**：must_visit 正则要求"必去/要去"等关键词；"我想去长沙，橘子洲和岳麓山"这种无关键词的句子 city 识别成功就不走 LLM 回退，must_visit 丢失。

**修复方案**：在 city 已识别的情况下，**若 must_visit 为空且消息包含明显的地名并列结构**，仍触发 LLM 补充 must_visit（仅这一字段，不全量重解析）：
```python
# agents/intent_agent.py execute() 中，city 识别后、构造 TripIntent 前
if not must_visit and city:
    # 启发式：消息里有"、"或"和"连接的地名，且不是已知 city 本身
    has_compound = any(sep in user_message for sep in ("、", "和", "还有", "以及"))
    if has_compound:
        try:
            data = await self._llm_parse_must_visit(user_message, city, state=state)
            if data:
                must_visit = data
        except Exception as e:
            logger.warning("LLM must_visit 补充失败: %s", e)
```
新增专用小 prompt（只提取 must_visit，省 token）：
```python
def _llm_parse_must_visit(self, message, city, state=None):
    # 用一个独立的精简 prompt，只问 must_visit
    ...
```

**验收**：输入"我想去长沙，橘子洲和岳麓山玩3天"→ must_visit=["橘子洲","岳麓山"]。

**风险**：中。增加一次 LLM 调用，注意 `llm_call_count` 计数与 `MAX_LLM_CALLS` 预算。

---

## 【S7】_partial_replan 丢失 _serialize_state 丢掉的字段
**文件**：`api_multi_agent.py:764-772, 1034-1074`

**根因**：`_serialize_state` 只保留 12 个 key，丢弃 `xhs_routes/xhs_popular_pois/xhs_reference_routes/city_guides/review_feedback`。`_partial_replan`（change_pace）调 SchedulerAgent，而 scheduler 依赖这些字段做 XHS 亲和与 guide 注入。

**修复方案**：扩展 `_serialize_state` 保留 scheduler 所需的全部字段：
```python
def _serialize_state(state: dict) -> dict:
    keep_keys = {
        "trip_intent", "city", "days", "daily_plans", "selected_hotel",
        "pois", "hotels", "restaurants", "weather", "available_pois",
        "must_visit_coverage", "summary",
        # 新增：scheduler + reviewer 依赖
        "xhs_routes", "xhs_popular_pois", "xhs_reference_routes",
        "city_guides", "review_feedback", "tickets",
    }
    return {k: v for k, v in state.items() if k in keep_keys}
```
同时评估：`available_pois` 可能很大（几百 POI），若内存吃紧可只保留 `must_visit` 相关的子集。

**验收**：change_pace 重排后，XHS 亲和 swap（日志 "Applied XHS co-occurrence"）仍触发；day summary 仍含 guide snippet。

**风险**：低。注意内存占用上升。

---

## 【C3】PoiAgent 修改从 JSON 加载的 POI，跨请求污染风险
**文件**：`agents/poi_agent.py:110-132, 173`

**根因**：`_load_pois` 每次 `json.load`（无缓存，目前安全），但返回的 dict 被 `poi["xhs_frequency"]=...`、`poi["poi_tier"]=...` 原地修改，并写进 `available_pois` 供 scheduler 继续改（`scheduler_agent.py:660 poi["closed_days"]=...`）。`api_multi_agent.py:_load_city_pois` 的 `_poi_cache` 是另一份**有缓存**的 dict。

**修复方案**：PoiAgent 加载后**深拷贝**再修改，并明确"加载结果是每请求私有副本"：
```python
# agents/poi_agent.py _load_pois 返回前 / execute 开头
import copy
all_pois = copy.deepcopy(all_pois)   # 确保下游修改不影响缓存
```
同时给 `_load_city_pois`（api_multi_agent.py）的缓存 dict 加防御：`convert_to_frontend_format`/`_enrich_stop` 只读不写（当前已是，加注释 + 单测固化）。

**验收**：单测——同城市连续两次规划，第二次的 POI dict 不含第一次注入的 `xhs_frequency`（除非本次也命中）。

**风险**：低。深拷贝有性能成本（数百 POI），可接受。

---

# P2 — 中优先级（健壮性与体验）

## 【S2】进程内会话存储（不持久/多worker失效/无锁）
**文件**：`api_multi_agent.py:67-103`

**根因**：`_chat_sessions` 全局 dict，重启/多worker/并发均不安全。

**修复方案**：迁移到 Redis（基建已在 `tools/cache.py`，可直接复用 `_get_redis()`）：
```python
# 新建 tools/session_store.py
class SessionStore:
    def __init__(self, redis_client, ttl=1800):
        self.r = redis_client; self.ttl = ttl
    async def get(self, sid): ...   # JSON 反序列化
    async def set(self, sid, data): self.r.setex(f"session:{sid}", self.ttl, json.dumps(data, ensure_ascii=False))
    async def delete(self, sid): ...
```
`_get_or_create_session` / `_cleanup_expired_sessions` 改为走 SessionStore。Redis 不可用时回退到当前内存版（保留作为 fallback）。

**短期缓解**（若暂不接 Redis）：至少给 `_chat_sessions` 的读写加 `asyncio.Lock`，并在**所有**入口（含 `/agent/modify`）调 `_cleanup_expired_sessions`。

**验收**：重启 Python 服务后，同一 session_id 的 modify 仍可用（前提：行程已落 PG，modify 从 PG 取 fallback）。

**风险**：中。需要 Redis 可用 + 序列化全部 state（注意 `available_pois` 体积）。

---

## 【S3】前端 sessionStorage 存行程，关标签页即丢
**文件**：`web/app.js:25-30, 36-46`

**根因**：`tp_candidates/tp_lastPayload/tp_savedTripId` 用 sessionStorage。

**修复方案**：行程候选改用 localStorage（带过期清理），登录态/敏感信息保留在 localStorage（已是）：
```js
// web/app.js saveTripState / restoreTripState
// 把 sessionStorage 改为 localStorage
// 并加 7 天过期判断（存时带 timestamp，读时检查）
const TRIP_TTL = 7 * 24 * 3600 * 1000;
function saveTripState() {
  const ts = Date.now();
  localStorage.setItem("tp_candidates", JSON.stringify(state.candidates));
  localStorage.setItem("tp_trip_ts", String(ts));
  // ...其余字段
}
function restoreTripState() {
  const ts = parseInt(localStorage.getItem("tp_trip_ts") || "0", 10);
  if (Date.now() - ts > TRIP_TTL) { /* 清理 */ return; }
  // ...恢复
}
```
注意：未登录游客的候选行程存 localStorage 即可（不敏感）；已保存行程走 PG。

**验收**：规划后关闭标签页，重新打开浏览器→候选行程仍在。

**风险**：低。注意 localStorage 容量（5~10MB），大行程可能超限，必要时只存 savedTripId + 轻量摘要。

---

## 【H4】Reviewer LLM 幻觉 issue 误触发重排
**文件**：`agents/reviewer_agent.py:281-288`

**根因**：LLM 返回的任意 high severity issue 直接合并进 `all_issues`，幻觉一次就强制重排（成本翻倍）。

**修复方案**：对 LLM issue 做**交叉验证**——只保留能被硬规则或数据佐证的 LLM issue：
```python
# reviewer_agent.py
# LLM issue 必须有 poi_name 且该 poi 确实在 daily_plans 中，否则丢弃
planned_names = {s.get("poi_name","") for day in daily_plans for s in _safe_get_stops(day)}
validated_llm_issues = []
for i in llm_issues:
    pname = i.get("poi_name", "")
    if pname and pname not in planned_names:
        continue   # LLM 提到了不存在的 POI，丢弃
    # 对 excessive_commute 类，校验 travel_minutes 真的超阈值
    if i.get("type") in ("excessive_commute_confirmed", "excessive_commute_estimated"):
        # 找到对应 stop 的实际 travel_minutes，不达标则丢弃
        ...
    validated_llm_issues.append(i)
all_issues = hard_issues + validated_llm_issues
```
另外可给 LLM issue 的 severity 降权（LLM 说 high → 当 medium），只有 hard_check 的 high/critical 才阻塞。

**验收**：mock LLM 返回一个幻觉 issue，确认不触发重排。

**风险**：低。

---

## 【G1】config.py .env 路径耦合 + int 解析无保护
**文件**：`agents/config.py:11, 32, 51-53, 62`

**根因**：.env 从 legacy `agent/.env` 加载；`int(os.environ.get(...))` 非数字值崩 import。

**修复方案**：
```python
# agents/config.py
def _safe_int(val, default):
    try: return int(val)
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning("Invalid int env value: %s, using default %s", val, default)
        return default

# .env 搜索多个候选位置
_HERE = os.path.dirname(os.path.abspath(__file__))
_ENV_CANDIDATES = [
    os.path.join(_HERE, ".env"),                       # agents/.env
    os.path.join(_HERE, os.pardir, "agent", ".env"),   # legacy
    os.path.join(_HERE, os.pardir, ".env"),            # root
]
for p in _ENV_CANDIDATES:
    if os.path.exists(p):
        from dotenv import load_dotenv
        load_dotenv(p); break

CACHE_TTL_SECONDS = _safe_int(os.environ.get("CACHE_TTL_SECONDS", "86400"), 86400)
MAX_LLM_CALLS_PER_REQUEST = _safe_int(os.environ.get("MAX_LLM_CALLS", "10"), 10)
# ...其余 int 字段同理
```

**验收**：设 `MAX_LLM_CALLS=abc` 启动，服务正常起来并 warning。

**风险**：低。

---

## 【P4/P5】resolve_city_dir 兜底 + must_visit 模糊匹配过宽
**文件**：`agents/constants.py:96-104` + 多处 `mv in name`

**修复方案**：
- `resolve_city_dir` 未知城市时返回 `None` 或抛带提示的异常，让上层给用户友好提示（"暂不支持该城市，支持：..."），而非静默返回空 POI。
- must_visit 匹配改为**精确优先 + 长度阈值**：
```python
def _match_must_visit(mv, pois):
    """精确 > 包含(且被包含名长度>=len(mv)+2) > id 相等"""
    exact = [p for p in pois if p.get("name") == mv]
    if exact: return exact
    by_id = [p for p in pois if p.get("id") == mv]
    if by_id: return by_id
    # 包含匹配，但要求 mv 长度>=2 且目标名不能比 mv 长太多（避免"山"匹配一切）
    if len(mv) >= 2:
        return [p for p in pois if mv in p.get("name","") and len(p.get("name","")) <= len(mv) + 4]
    return []
```
抽到 `tools/scoring.py` 或新建 `tools/matching.py`，统一供 poi_agent/scheduler/reviewer/clustering 调用（消除 4 处重复 `mv in name`）。

**验收**：must_visit="橘子洲" 精确命中"橘子洲风景名胜区"；must_visit="山" 不再命中所有 X山。

**风险**：中。改动涉及多处，需回归 must_visit 保证链（layer1~4）。

---

## 【G2/G3】weather_api 健壮性
**文件**：`tools/weather_api.py:141-184, 156-171`

**修复方案**：
- 加 `resp.raise_for_status()` 或检查 `resp.status_code != 200` 先返回 []。
- 缺失字段用 `None` 而非假默认值（25°C/湿度50），让 WeatherAgent 的 placeholder 逻辑统一处理：
```python
"temperature_high": _safe_int(daily.get("tempMax"), None),   # None 而非 25
```
- 加 days 适配：`days<=3` 用 `/3d` 再切片；`days>3` 用 `/7d`（QWeather 有 7d 端点）。
- 加响应缓存（key=city+days，TTL=CACHE_TTL_SECONDS），复用 `tools/cache` 的内存+Redis。

**验收**：QWeather 返回 4xx 时不报错、返回 placeholder；days=5 能拿到 5 天。

**风险**：低。

---

# 执行顺序与依赖

```
Phase 1（P0，1~2 天）：
  C1 (errors 计数) ──┐
  P1 (open_minutes)  ├── 三者互相独立，可并行
  S1 (modify 回写)  ──┘ S1 需 C++ 重编译

Phase 2（P1，2~3 天）：
  S4 (缓存 key) → 依赖 S1 的 intent 传递
  P2 (酒店 meta) ── 独立
  C2 (thread_id) ── 独立
  H5 (must_visit LLM) ── 独立
  S7 (_serialize 扩展) → 依赖 S2 会话存储设计
  C3 (POI 深拷贝) ── 独立

Phase 3（P2，按需）：
  S2 (Redis 会话) → 较大改动，建议独立 PR
  S3 (前端 localStorage)
  H4 (reviewer 验证)
  G1/G2/G3 (配置/天气健壮性)
  P4/P5 (城市兜底/匹配)
```

## 每项通用验收清单
- [ ] 改动文件有对应单元测试或集成测试
- [ ] `python -m pytest tests/test_multi_agent.py` 通过
- [ ] 手动跑 `/agent/plan`（长沙3天必去橘子洲）端到端无报错
- [ ] 手动跑 `/agent/plan-structured` 端到端
- [ ] 检查日志无新增 ERROR/WARNING
- [ ] commit message 遵循现有中文约定（`fix(xxx): ...`）

## 不建议在本轮动的项
- LangGraph checkpointer 接入（C2 方案B）—— 架构级改动，单开 epic
- 真实酒店价格 API 接入（P2 方案C）—— 需商务/授权
- `agent/` legacy 目录清理 —— 待 multi-agent 完全稳定后统一删除
- 仓库根 60+ 个 `_test_/_fix_/_debug` 脚本 —— 单独做一次清理 PR（`chore: remove scratch scripts`）
