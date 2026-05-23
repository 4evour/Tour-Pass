# Tour Pass 真实数据运行手册

这份手册用于把项目从默认 `25 POI / 46 edges` 样例切到本地生成的 `200+` 长沙真实 POI 数据集。仓库不提交高德 API key、原始响应或完整真实数据产物。

## 1. 准备密钥

```powershell
$env:AMAP_API_KEY="your-amap-web-service-key"
```

如果没有 `AMAP_API_KEY`，真实采集命令会失败；CI 和本地离线测试只使用 `tests/fixtures/`。

## 2. 采集 200+ POI

```powershell
node scripts/fetch_amap_pois.js --config config/amap.changsha.json --out-dir output/amap-changsha --min-pois 200
```

检查 `output/amap-changsha/manifest.json`：

- `poi_count >= 200`
- `type_counts` 覆盖景点、餐饮、酒店、夜游等类型
- `area_counts` 显示不是集中在单一商圈
- `duplicate_count` 和 `failed_pages` 可解释

## 3. 生成真实通勤边

```powershell
node scripts/build_commute_edges.js --pois output/amap-changsha/pois.json --out-dir output/amap-changsha --neighbors 6 --fallback fail --min-amap-ratio 0.8 --mode mixed --batch-size 100
```

正式报告使用 `--fallback fail` 和 `--min-amap-ratio 0.8`，避免高德通勤不足时静默生成估算图。开发调试才使用 `--fallback geo_estimated`。

## 4. 数据校验

```powershell
node scripts/validate_data.js --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --min-pois 200 --require-edge-source
```

校验通过后，把 `edge_sources`、孤立点、连通性和类型分布写入报告。

## 5. 真实规模实验

```powershell
node scripts/scale_experiment.js --dataset real --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --sizes 100,200 --iterations 5 --cache-mode auto --report docs/scale_experiment_report.md --json-report output/scale_experiment_report.json
node scripts/algorithm_quality_check.js --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --subset 9 --report docs/algorithm_quality_report.md
```

报告必须包含 avg/p95/p99、失败数、缓存模式、`source=amap` 比例和机器环境。没有这些数字时，不要在简历里写“真实规模压测完成”。

## 6. Docker 演示

```powershell
docker build -t tour-pass:local .
docker run --rm -d --name tour-pass-smoke -p 8150:8080 -e LLM_DISABLED=1 tour-pass:local
node scripts/container_smoke.js http://127.0.0.1:8150
docker stop tour-pass-smoke
```

如果要让容器使用真实数据，需要把 `output/amap-changsha` 挂载进容器，并设置 `TOURPASS_POIS_PATH` / `TOURPASS_EDGES_PATH`。
