# Tour Pass 算法质量报告

本报告用小规模 POI 子集做精确枚举基线，并用同一候选子集补充贪心 baseline，用于解释 Beam Search 的近似质量。它不是生产路线质量评测，也不包含真实用户反馈。

## 运行口径

- POI 数据：`output\amap-changsha\pois.json`
- Edge 数据：`output\amap-changsha\edges.json`
- 子集规模：10 POI，精确枚举 stop_count=4
- Beam 参数：TOURPASS_BEAM_WIDTH=5，TOURPASS_BRANCH_FACTOR=6
- 服务健康：poi=500，edges=1937，distance_cache=all_pairs

## 小规模对比

| 方法 | 分数/目标 | 通勤分钟 | 可行性 | 耗时 | 路线 |
| --- | ---: | ---: | --- | ---: | --- |
| 精确枚举基线 | 129 | 45 | yes | - | 茶颜悦色(蝴蝶大厦店) -> 宝南二手机批发市场 -> 中山亭 -> 五一广场 |
| 贪心 baseline | 127 | 34 | yes | 0.1 ms | 茶颜悦色(蝴蝶大厦店) -> 宴长沙(五一广场店) -> 浆小白豆浆夜市(五一广场店) -> 壹号座品 |
| Beam Search 服务输出 | 128.0 | 71 | yes | 98.1 ms | 宝南二手机批发市场 -> 茶颜悦色(蝴蝶大厦店) -> 清水塘毛泽东杨开慧故居 -> 宴长沙(五一广场店) -> 浆小白豆浆夜市(五一广场店) |

## 结论

- Beam 请求耗时：98.1 ms；表中 Beam 分数按 exact/greedy 的同一简化目标函数重算。
- 通勤差值：+26 分钟。
- Beam 相比贪心分数差：+1.0；路线重合度：60.0%。
- 精确枚举只在 8-10 个候选点子集上可接受；真实 200+ POI 场景必须先做候选召回、时间窗过滤和近似搜索。
- 面试表达应说 Beam Search 是工程近似策略，不声称全局最优。
