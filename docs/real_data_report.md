# Tour Pass 真实数据报告

当前仓库不提交高德真实采集产物，避免 API key、原始响应和数据再分发边界混在代码仓库中。真实数据应在本地通过 `docs/real_data_pipeline.md` 的命令生成。

本轮目标从“默认样例 25 POI”升级为“本地可复现生成 `200+` 长沙真实 POI，并用高德来源通勤边比例作为门禁”。2026-05-22 本机已用高德 Web 服务 Key 跑通一次 `500` POI 真实采集；仓库仍不提交 `output/amap-changsha/` 和 `output/amap-cache/` 的完整数据产物。

## 当前仓库内可验证状态

- 默认样例：`25 POI / 46 edges`，用于离线演示和回归测试。
- 真实 POI 入口：`scripts/fetch_amap_pois.js --min-pois 200`，支持高德 Web 服务分页、去重、字段标准化、类型分布、区域分布、重复数和失败页统计。
- 通勤边入口：`scripts/build_commute_edges.js --fallback fail --min-amap-ratio 0.8`，支持高德距离/路径优先、地理估算开发降级，并为每条边标记 `source`、`provider`、`mode`、`duration_seconds` 和 `amap_status`。
- 离线测试：`tests/test_amap_pipeline.js` 使用 fixture 验证采集、去重、`--min-pois` 门禁、边来源比例、`--fallback fail` 和 `--min-amap-ratio`。

## 2026-05-22 本机真实采集摘要

- POI：`500`
- 类型分布：`attraction=240`，`restaurant=160`，`nightlife=35`，`hotel=65`
- 区域覆盖：`9` 个区县/区域
- 重复 POI：`120`
- 失败页数：`0`
- 通勤边：`1937`
- 边来源：`amap=1706`，`geo_estimated=231`
- 高德来源比例：`88.1%`
- 边生成口径：`neighbors=6`，`mode=driving`，`fallback=geo_estimated`，`min_amap_ratio=0.7`
- 数据校验：`node scripts/validate_data.js --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --min-pois 500 --require-edge-source` 通过，图连通。

说明：正式强门禁 `--fallback fail --min-amap-ratio 0.8` 曾拦截 `119` 条估算边，证明脚本不会把低覆盖真实通勤伪装成完整真实路网。为获得可运行的 500 POI 图，本次报告采用 `fallback=geo_estimated`，并显式披露估算边比例。

## 生成后应记录的指标

运行真实采集后，把 `output/amap-changsha/real_data_report.md` 的摘要同步到本文件或课程报告中，至少记录：

- POI 总数，当前验收目标不少于 `200`。
- `attraction` / `restaurant` / `hotel` / `nightlife` 类型分布。
- 行政区/商圈覆盖数量，重复 POI 数，失败页数。
- 边总数。
- `source=amap` 与 `source=geo_estimated` 的边数量和比例。
- 数据校验命令与结果。
- 规模实验中的 avg / p95 / p99 / failure count。

## 本地真实数据命令链

```powershell
$env:AMAP_API_KEY="your-amap-web-service-key"
node scripts/fetch_amap_pois.js --config config/amap.changsha.json --out-dir output/amap-changsha --min-pois 200
node scripts/build_commute_edges.js --pois output/amap-changsha/pois.json --out-dir output/amap-changsha --neighbors 6 --fallback fail --min-amap-ratio 0.8 --mode mixed --batch-size 100
node scripts/validate_data.js --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --min-pois 200 --require-edge-source
node scripts/scale_experiment.js --dataset real --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --sizes 100,200 --iterations 5 --cache-mode auto --report docs/scale_experiment_report.md --json-report output/scale_experiment_report.json
```

运行完成后，只把 `manifest.json`、`edges_manifest.json` 和 scale experiment 的聚合摘要同步到课程报告或本文件，不提交 `output/amap-cache/` 原始响应。

## 真实规模实验摘要

来自 `docs/scale_experiment_report.md`：

| POI | Edges | AMap edge ratio | cache mode | startup | iterations | failures | avg | p95 | p99 |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 106 | 85.8% | all_pairs | 0 ms | 5 | 0 | 4.9 ms | 6.5 ms | 6.5 ms |
| 200 | 391 | 87.0% | all_pairs | 18 ms | 5 | 0 | 5.2 ms | 6.3 ms | 6.3 ms |
| 500 | 1937 | 88.1% | all_pairs | 339 ms | 5 | 0 | 128.0 ms | 128.9 ms | 128.9 ms |

## 表达边界

真实 POI 数据能回应“只有 25 个点”的问题；但如果边中仍有大量 `geo_estimated`，就只能说明项目接入了真实地点和估算通勤图，不能声称拥有真实地图路网或实时交通能力。
