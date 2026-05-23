# 真实 POI 数据采集流水线

Tour Pass 默认仍保留 `data/pois.json` 的小样例，便于离线演示和测试。真实规模数据通过高德 Web 服务脚本按需生成，不提交 API key，也不默认提交原始响应。

本轮真实数据验收目标是 `200+` 个长沙真实 POI。`500+` 可作为后续增强目标，但不再把未跑通的 500 规模包装成当前能力。

## 采集 POI

```powershell
$env:AMAP_API_KEY="your-amap-web-service-key"
node scripts/fetch_amap_pois.js --config config/amap.changsha.json --out-dir output/amap-changsha --min-pois 200
```

输出：

- `output/amap-changsha/pois.json`：标准化后的项目 POI 数据。
- `output/amap-changsha/manifest.json`：采集时间、类别覆盖、类型分布、区域分布、重复点数量和失败页数。
- `output/amap-changsha/real_data_report.md`：可复制进文档的采集摘要。
- `output/amap-cache/`：高德原始响应缓存，默认被 `.gitignore` 排除。

没有 `AMAP_API_KEY` 时脚本会直接失败；CI 使用 `--mock-dir tests/fixtures/amap_search` 走离线 fixture。

## 生成通勤边

```powershell
node scripts/build_commute_edges.js --pois output/amap-changsha/pois.json --out-dir output/amap-changsha --neighbors 6 --fallback fail --min-amap-ratio 0.8 --mode mixed --batch-size 100
```

脚本会先按地理距离为每个 POI 连接近邻点，再优先调用高德距离测量/路径规划接口补真实 `distance_meters`、`duration_seconds`、`walk_minutes` / `taxi_minutes`。如果没有 key、额度不足或路径响应不可用，开发模式可以退回地理距离估算；正式真实数据报告建议使用 `--fallback fail --min-amap-ratio 0.8`，让真实通勤比例不足时直接失败。

每条边会保留旧字段，并补充：

```json
{
  "source": "amap",
  "provider": "amap",
  "mode": "mixed",
  "duration_seconds": 612,
  "amap_status": "ok"
}
```

或：

```json
{ "source": "geo_estimated" }
```

因此真实 POI 和真实通勤是两个层次：POI 可以来自高德真实地点，通勤边仍需要看 `source` 比例，不能把估算边包装成真实路网。

## 数据校验

```powershell
node scripts/validate_data.js --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --min-pois 200 --require-edge-source
```

校验覆盖必填字段、类型分布、坐标范围、时间窗、图连通性、孤立点、边来源统计和最小 POI 数量。

## 本地运行真实数据集

```powershell
$env:TOURPASS_POIS_PATH="output/amap-changsha/pois.json"
$env:TOURPASS_EDGES_PATH="output/amap-changsha/edges.json"
$env:TOURPASS_DISTANCE_CACHE_MODE="auto"
mingw32-make run
```

`auto` 缓存模式默认在 `500` POI 以内使用全量最短路缓存；这对 200 级课程/作品集数据更简单也更容易解释。超过阈值才切到按需 LRU，LRU 是保护策略，不作为几百点规模的主要亮点。

## 真实规模实验

```powershell
node scripts/scale_experiment.js --dataset real --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --sizes 100,200 --iterations 5 --cache-mode auto --report docs/scale_experiment_report.md --json-report output/scale_experiment_report.json
node scripts/algorithm_quality_check.js --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --subset 9 --report docs/algorithm_quality_report.md
```

报告必须记录真实 POI 数、边数、`source=amap` 比例、缓存模式、启动耗时、avg/p95/p99、失败数和机器环境。没有跑出真实数据前，不要把报告写成“已完成真实 200 POI 压测”。
