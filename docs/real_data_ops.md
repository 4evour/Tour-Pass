# Tour Pass Real Data Ops

This page records the current one-command real-data workflow, the geo-estimated edge retry workflow, and the real-data smoke check. It intentionally avoids API keys, raw AMap responses, and full generated datasets.

## One-Command Pipeline

Default command, matching the verified local 500 POI profile:

```powershell
node scripts/run_real_data_pipeline.js --config config/amap.changsha.json --out-dir output/amap-changsha --min-pois 500 --neighbors 6 --fallback geo_estimated --min-amap-ratio 0.7 --mode driving --sizes 100,200,500 --iterations 5
```

Strict gate, useful before writing a formal report:

```powershell
node scripts/run_real_data_pipeline.js --strict-edges --min-pois 200 --sizes 100,200
```

The pipeline runs POI fetch, commute edge generation, data validation, and the real scale experiment. It writes `docs/real_data_pipeline_report.md` and `output/real_data_pipeline_manifest.json`.

## Retry geo_estimated Edges

Use this after a successful edge build if `edges_manifest.json` still shows `geo_estimated` edges:

```powershell
node scripts/retry_geo_edges.js --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --out-dir output/amap-changsha-retry --mode driving --min-amap-ratio 0.8
```

Outputs:

- `output/amap-changsha-retry/edges.json`
- `output/amap-changsha-retry/edges_manifest.json`
- `output/amap-changsha-retry/geo_estimated_edges_report.md`
- `output/amap-changsha-retry/geo_estimated_edges_report.json`

If the retry result is still below `--min-amap-ratio`, the script exits non-zero. That keeps estimated commute edges from being silently presented as real route data.

## Real Data Smoke

Start the service with real generated data:

```powershell
$env:TOURPASS_POIS_PATH="output/amap-changsha/pois.json"
$env:TOURPASS_EDGES_PATH="output/amap-changsha/edges.json"
$env:LLM_DISABLED="1"
mingw32-make run
```

Then run:

```powershell
node scripts/real_data_smoke.js http://127.0.0.1:8080 --expected-pois 500 --min-amap-ratio 0.7 --edges-manifest output/amap-changsha/edges_manifest.json --require-all-pairs
```

The smoke checks `/health`, `health.distance_cache` fields, POI/edge counts, AMap edge ratio, `/trip/plan`, and `/poi/search`.

## Boundary

- The generated `output/` dataset is local evidence and remains ignored by git.
- `geo_estimated` edges must be disclosed in reports and interviews.
- These commands prove local reproducibility and regression performance, not a production SLA or an online demo.
