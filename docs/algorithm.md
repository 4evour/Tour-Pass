# Tour Pass 算法说明

本文记录 Tour Pass 当前已经落地的核心算法与工程取舍，面向简历、面试讲解和后续迭代维护。项目目标不是求一个带实时地图数据的全局最优旅行商解，而是在本地样例数据上稳定生成可解释、可对比、可离线演示的多日自由行方案。

## 1. 数据建模

### POI 节点

`data/pois.json` 中每个 POI 表示一个图节点，包含：

- 基础属性：`id`、`name`、`type`、`lat`、`lng`、`area`
- 时间约束：`open_time`、`close_time`、`visit_duration_minutes`
- 排序特征：`tags`、`popularity`、`price_level`、`description`

POI 类型覆盖 `hotel`、`attraction`、`restaurant`、`nightlife` 和 `transit`。规划器会把酒店作为每日起点，把餐厅放入午餐/晚餐时间槽，把夜生活点优先放入晚上时间槽。

### 通勤边

`data/edges.json` 中每条边连接两个 POI，包含 `distance_meters` 和步行、公交、打车耗时。当前图按无向图处理，核心通勤权重优先使用：

```text
transit_minutes -> taxi_minutes -> walk_minutes
```

这个选择让默认演示更贴近城市自由行中的公共交通场景，同时保留距离和其他出行方式字段，方便后续扩展多交通方式规划。

## 2. 路径查询：Dijkstra 与 A*

`PoiGraph` 提供两类路径查询：

- `shortestRoute(from, to)`：Dijkstra，保证在非负边权图上得到最短通勤时间。
- `aStarRoute(from, to)`：A*，在 Dijkstra 的累计代价上叠加地理启发函数。

A* 启发函数基于经纬度粗略估算直线距离，并假设城市通勤速度约为 28 km/h：

```text
h(n) = rough_distance_km / 28 * 60
```

在当前小规模数据上，两者性能都足够快；保留 A* 的意义主要是展示算法岗位常见的“启发式图搜索”能力，并为未来更大 POI 图扩展做准备。

复杂度：

- Dijkstra：`O((V + E) log V)`
- A*：最坏仍为 `O((V + E) log V)`，启发函数有效时会减少实际扩展节点数

## 3. 行程规划：时间槽 Beam Search

`TripPlanner` 将一天拆成固定时间槽：

```text
上午 -> 午餐 -> 下午 -> 晚餐 -> 晚上
```

每个时间槽先按类型过滤候选 POI，再用评分函数排序并保留最多 6 个分支。规划器维护一组 Beam 状态：

- 已选站点序列
- 已使用 POI 集合
- 当前所在 POI
- 当前时间
- 累计通勤时间
- 累计游玩时间
- 累计兴趣得分

每处理一个时间槽，算法展开当前 Beam 中的状态，生成下一批状态，再按 Beam 状态评分排序，保留最多 5 个状态。

Beam 状态评分：

```text
state_score = interest_score - total_travel_minutes * travel_penalty + stop_count * 8
```

其中 `travel_penalty` 会随候选策略变化：

- `low_travel`：提高通勤惩罚，偏好少走路和同区域活动
- `compact`：降低通勤惩罚，鼓励覆盖更多高分 POI
- 其他策略：使用平衡通勤惩罚

为什么不用纯贪心：纯贪心每个时间槽只选当前最高分 POI，容易过早锁定局部最优，导致后续餐饮窗口、闭馆时间或通勤顺序变差。Beam Search 保留 Top-K 局部状态，在可解释性、运行速度和候选多样性之间更适合面试演示。

复杂度近似：

```text
O(days * slots * beam_width * branch_factor * score_cost)
```

当前参数为 `slots=5`、`beam_width=5`、`branch_factor<=6`，所以在本地样例数据上可以稳定毫秒级返回。

接口会在 `days[].beam_trace` 输出调试轨迹，记录每个时间槽的输入状态数、展开状态数、保留状态数、Top 状态摘要和保留决策。这个字段用于面试演示和算法排查，不改变行程业务语义。

## 4. 站点评分函数

每个 POI 的评分会输出到 `stops[].score_breakdown`，用于解释“为什么选这个点”。主要组件包括：

- 热度分：`popularity * multiplier`
- 兴趣匹配：命中用户 `interests` 中的标签时加分
- 必去加权：命中 `must_visit` 时大幅加分
- 通勤惩罚：从上一站最短通勤时间越长，扣分越多
- 价格惩罚：`price_level` 越高扣分越多
- 时间窗惩罚：早到等待或超出关闭时间都会扣分
- 策略加权：不同候选策略加入不同主题权重

当前候选策略差异：

| 策略 | 标识 | 主要权重变化 |
| --- | --- | --- |
| 轻松少走路 | `low_travel` | 增加短通勤奖励和通勤惩罚 |
| 紧凑多覆盖 | `compact` | 提高热度/兴趣权重，降低通勤惩罚 |
| 文化优先 | `culture` | 加权历史文化、博物馆、古建筑、书院、寺庙 |
| 美食优先 | `food` | 加权餐饮、小吃、湘菜、夜市、茶饮、街区 |
| 雨天室内 | `rainy` | 加权室内 POI，惩罚户外 POI |

这种设计让候选方案不只是名称不同，而是在 POI 选择和解释文本中体现真实评分差异。

## 5. 日内通勤优化

Beam Search 先生成满足时间槽语义的路线。随后 `optimizeDayOrder` 对非餐饮站点做局部交换，评估理论上是否可以降低通勤时间。

当前展示层仍保持原时间线顺序，因为午餐、晚餐和晚上活动有明确时间语义；理论优化收益只在交换后仍满足站点顺序、开放时间和餐饮窗口时才计入。优化摘要会输出：

- 原时间线通勤时间
- 局部交换后的理论更优通勤时间
- 可节省分钟数

这个设计适合面试时说明“算法知道更短路径，但产品展示要尊重时间窗和用户理解成本”。

## 6. 严格时间窗复核

规划器会对最终每日 stop 顺序做统一复核，并输出：

- `stops[].time_window_status`：`ok`、`wait`、`closed`、`meal_window`、`sequence`、`day_end` 或 `missing_poi`
- `stops[].time_window_reason`：精确解释，例如“预计 17:40 离开，但 17:00 关闭”
- `days[].time_window_feasible`：当日最终时间窗是否整体可行
- `days[].time_window_diagnostics`：日级诊断列表

午餐必须完整落在 `11:30-13:30`，晚餐必须完整落在 `17:30-19:30`。Beam Search 生成候选时会过滤不满足完整餐饮窗口的餐厅安排；最终复核还会检查站点顺序、开放时间和当日结束时间。

## 7. 多候选方案与 Pareto 非支配排序

当 `/trip/plan` 的 `candidate_count > 1` 时，系统会生成多种策略候选。每个候选都会计算对比指标：

- `total_score`：总兴趣/行程评分
- `total_stops`：站点覆盖数量
- `total_travel_minutes`：总通勤时间
- `must_visit_covered`：必去点覆盖数
- `open_time_risks`：开放时间风险数
- `unscheduled_count`：未安排必去点数量
- `poi_overlap_with_baseline`：相对第一个候选基线的 POI 重合率
- `area_overlap_with_baseline`：相对第一个候选基线的区域重合率
- `unique_poi_count`：相对基线的独有 POI 数量

排序使用标准 Pareto 非支配分层。若方案 A 在所有目标上不差于方案 B，且至少一个目标更好，则 A 支配 B。第一层 Pareto front 表示没有被其他候选完全支配的方案；后续层级表示取舍成本逐渐增加。

这个模块对应算法岗面试中的多目标优化思想：不是把所有目标强行压成一个总分，而是保留“高评分、低通勤、低风险、必去覆盖”之间的取舍关系。

响应中的 `comparison.pareto_debug` 会输出分层证据，例如是否未被其他候选完全支配，以及当前方案的指标向量。Web 演示台会把这部分作为算法调试面板展示。

候选多样性使用集合重合率计算。第一个候选作为基线，其他方案分别抽取 POI id 集合和区域集合，按 Jaccard overlap 计算重合率：

```text
overlap(A, B) = |A ∩ B| / |A ∪ B|
```

同时输出 `unique_pois`、`diversity_tags` 和 `diversity_summary`。这些字段用于说明“候选是否真的不同”，让演示更接近推荐系统中的多样性评估，而不是只展示多个同质路线。

## 8. POI 检索：BM25 + 字段权重

`SearchEngine` 使用轻量 BM25 思路对 POI 文本排序。检索字段包括：

- `name`：权重 3.0
- `tags`：权重 2.4
- `area`：权重 1.5
- `description`：权重 1.0

每个查询词先统计文档频率，再计算 IDF 和饱和后的词频贡献：

```text
idf = log(1 + (N - df + 0.5) / (df + 0.5))
normalized_tf = tf * (k1 + 1) / (tf + k1 * (1 - b + b * doc_len / avg_doc_len))
```

最终分数还会叠加 POI 热度。响应中的 `matched_terms` 和 `score_explanation` 用于解释为什么某个 POI 排在前面。

响应中的 `score_contributions` 会进一步拆分名称、标签、区域、描述和热度贡献，便于展示 BM25 排序不是黑盒。

复杂度：

```text
O(query_terms * POI_count + POI_count log POI_count)
```

当前数据规模很小，但这个模块已经具备信息检索的核心表达：字段权重、词频饱和、逆文档频率和排序解释。

## 9. 数据质量门禁

`scripts/validate_data.js` 是样例数据的质量门禁，当前检查：

- JSON 顶层结构是否为数组
- POI 必填字段、类型、坐标、时间格式、时间窗、热度和价格范围
- POI id 是否重复
- 标签是否为空、是否重复
- 是否至少包含酒店、景点、餐厅和夜间活动
- 边是否引用存在的 POI
- 边距离和通勤耗时是否合法
- 无向图是否连通

CI 会运行该脚本，本地也可以执行：

```powershell
mingw32-make validate-data
```

数据校验让演示项目更像真实工程：算法效果不只依赖代码，也依赖输入数据的结构质量。

## 10. 面试讲解建议

推荐按这条线讲：

1. 把城市 POI 建模成带时间窗属性的图。
2. 用 Dijkstra/A* 解决点到点通勤，给规划评分提供边权。
3. 用 Beam Search 做日内时间槽 Top-K 搜索，避免纯贪心陷入局部最优。
4. 用评分拆解解释每个站点的选择依据。
5. 用策略权重生成候选方案，展示轻松、紧凑、文化、美食、雨天之间的真实差异。
6. 用严格时间窗复核说明路线可信度，覆盖开放时间、餐饮窗口和顺序约束。
7. 用 POI/区域重合率和独有 POI 说明候选多样性。
8. 用 Pareto 非支配排序说明多目标取舍，而不是只给一个黑盒总分。
9. 用 BM25 支持 POI 搜索和排序解释。
10. 用数据质量校验、CI、API 冒烟测试说明工程稳定性。

## 11. 当前局限与后续优化

- 当前 POI 和边数据为人工样例，不代表实时拥堵、闭馆、排队或天气。
- A* 启发函数是粗略地理估计，适合演示，不等价于真实路网距离。
- Beam Search 不是全局最优保证，但在小数据和可解释演示场景下更合适。
- 当前中文检索主要依赖空格切分和子串匹配，后续可引入中文分词或拼音召回。
- 当前评分权重为手工规则，后续可用点击/收藏/停留数据学习权重。
- 当前数据质量校验是静态门禁，后续可增加地理异常检测、边权三角不等式抽样检查和 POI 聚类覆盖分析。
