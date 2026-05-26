# Tour Pass Real Data Retry Report

Generated on 2026-05-22 from local AMap-derived Changsha data. The full POI/edge files and raw AMap cache remain under `output/` and are not committed.

## Input

- POIs: `500`
- Edges: `1937`
- Original source counts: `amap=1706`, `geo_estimated=231`
- Original AMap edge ratio: `88.1%`
- Input edges: `output/amap-changsha/edges.json`

## Retry Result

- Command: `node scripts/retry_geo_edges.js --pois output/amap-changsha/pois.json --edges output/amap-changsha/edges.json --out-dir output/amap-changsha-retry --mode driving --min-amap-ratio 0.7`
- Retry candidates: `231`
- Converted to AMap: `202`
- Still geo_estimated: `29`
- Final source counts: `amap=1908`, `geo_estimated=29`
- Final AMap edge ratio: `98.5%`

## Validation

```powershell
node scripts/validate_data.js --pois output/amap-changsha/pois.json --edges output/amap-changsha-retry/edges.json --min-pois 500 --require-edge-source
```

Result:

```text
Data validation passed: 500 POIs, 1937 edges, connected graph, attraction=240, hotel=65, nightlife=35, restaurant=160, edge_sources: amap=1908, geo_estimated=29.
```

## Smoke

```powershell
node scripts/real_data_smoke.js http://127.0.0.1:8110 --expected-pois 500 --min-amap-ratio 0.98 --edges-manifest output/amap-changsha-retry/edges_manifest.json --require-all-pairs
```

Result:

```text
Real data smoke passed: 500 POIs, 1937 edges, cache=all_pairs, amap_ratio=98.5%, candidates=5.
```

## Boundary

The remaining `29` estimated edges must still be disclosed. This result supports the claim that the current local dataset is mostly backed by AMap commute durations, not that the project has live traffic or production route-planning infrastructure.
