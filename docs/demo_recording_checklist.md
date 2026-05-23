# Tour Pass 3 分钟演示录屏清单

目标：让面试官不用本地编译也能看懂项目已经具备数据、算法、性能和 Docker 演示证据。没有公网 URL 前，不说“已上线”。

## 录屏前准备

```powershell
mingw32-make test
node tests/test_amap_pipeline.js
docker build -t tour-pass:local .
```

如果本机有 `AMAP_API_KEY`，先按 `docs/real_data_runbook.md` 生成 `200+` 真实 POI 报告；没有 key 时，说明本次录屏展示脚本和 fixture，不展示伪造真实跑数。

## 录屏结构

1. 0:00-0:30：展示 README 的项目边界，明确默认样例是 `25 POI / 46 edges`，真实数据通过高德脚本本地生成。
2. 0:30-1:10：打开 `docs/real_data_report.md` 和 `docs/real_data_runbook.md`，展示 `--min-pois 200`、`--fallback fail`、`--min-amap-ratio 0.8`。
3. 1:10-1:50：启动 Docker 容器并运行 smoke。
4. 1:50-2:30：调用 `/health` 和 `/trip/plan`，展示 `distance_cache.mode`、POI/edge 数、候选行程和 Beam Trace。
5. 2:30-3:00：展示 `docs/algorithm_quality_report.md` 与 `docs/scale_experiment_report.md`，强调数字口径是本地回归，不是生产 SLA。

## 可复制命令

```powershell
docker run --rm -d --name tour-pass-smoke -p 8150:8080 -e LLM_DISABLED=1 tour-pass:local
curl.exe http://127.0.0.1:8150/health
curl.exe -X POST http://127.0.0.1:8150/trip/plan -H "Content-Type: application/json; charset=utf-8" --data-binary "@docs/sample_candidate_request.json"
node scripts/container_smoke.js http://127.0.0.1:8150
docker stop tour-pass-smoke
```

## 讲述边界

- `cpp-httplib` 是本地演示 HTTP 服务，不包装成生产网关。
- SQLite 用于复盘和历史记录，不在规划热路径里支撑高并发。
- `geo_estimated` 只能作为开发兜底；正式真实数据报告必须展示高德来源边比例。
- 没有公网 URL 前，只说 Docker 演示和录屏可验证，不说线上 Demo。
