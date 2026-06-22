# Real Route Planning Plan

## Status

Draft for review.

## Date

2026-06-20

## Problem Record

User-reported issues:

- Attraction image carousel and structured form bugs were separate UI/API issues and are not part of this route plan.
- Itinerary generation produced long cross-area moves, for example:
  - 青岛世界园艺博览园 -> 广开·尚宴·海鲜·青岛菜(万象汇店): page showed 116 minutes / 9.7 km estimated.
  - 广开·尚宴·海鲜·青岛菜(万象汇店) -> 崂山太清宫: page showed 249 minutes / 21 km estimated.
  - 吕家庄夜市 -> 李家河夜市: page showed 386 minutes / 32 km estimated.
- Night markets and evening POIs could still be placed too early.
- Some days were restaurant-heavy instead of attraction-focused.
- Some selected POIs looked low quality or too far from the hotel/day cluster.

Current confirmed route data issue:

- `tools.route.calculate_route_segments` can display route segment data from `edges.json`, but scheduling still mostly decides clusters and order before checking real route feasibility.
- Existing `edges.json` coverage can contain many `geo_estimated` edges. Estimated time is not reliable enough for planning feasibility.
- Live AMap checks for three reported Qingdao pairs show the old multi-hour values were not real driving time:
  - 青岛世界园艺博览园 -> 广开·尚宴: driving 25 min, 13.0 km.
  - 广开·尚宴 -> 崂山太清宫: driving 46 min, 27.0 km.
  - 吕家庄夜市 -> 李家河夜市: driving 46 min, 47.0 km.
- The last pair is still unsuitable for a same-day local cluster because distance is 47 km even though driving time is 46 minutes.

## Goal

Make itinerary feasibility depend on real route data wherever possible, and prevent the planner from silently accepting long cross-area moves when real route data is missing.

The system should:

- Prefer real AMap route edges when selecting, clustering, ordering, and reviewing stops.
- Treat estimated route data as low confidence.
- Reject or penalize excessive commute before the itinerary reaches the frontend.
- Keep the trip attraction-focused unless the user explicitly chooses food-first planning.
- Produce test evidence for each optimization using real or recorded AMap route data.

## Data Sources

- AMap Web Service route planning API.
- Existing local POI data in `data/{city}/pois.json`.
- Existing and generated route edges in `data/{city}/edges.json` or output patches.
- XHS route evidence remains secondary: it can support popularity/co-occurrence, but not replace route-time feasibility.

References:

- https://lbs.amap.com/api/webservice/guide/api/direction
- https://lbs.amap.com/api/webservice/guide/api/newroute

## Architecture Decision

Use a two-layer route strategy.

Layer 1: offline/refresh data

- Use scripts to fetch AMap route metrics for important POI pairs.
- Store results as edge patches with `provider: "amap"`, `route_confidence: "real"`, `taxi_minutes`, `walk_minutes`, `distance_meters`, and `duration_seconds`.
- Keep generated output ignored unless explicitly promoted into `data/{city}/edges.json`.
- Use taxi/driving as the default planning mode.
- Do not build all-pairs route data. Build a sparse route graph from nearest POI neighbors, then add targeted edges for hotels, must-visit POIs, popular clusters, and reported/problematic pairs.

Layer 2: planner/runtime constraints

- Scheduler and Reviewer should use a single route metric helper instead of raw Haversine estimates.
- Real AMap data wins.
- Estimated edges are allowed only under stricter caps and must be marked as estimated.
- If a segment exceeds caps, the planner should replace, move, or drop the optional stop instead of presenting a bad itinerary.
- Optional POIs above the route cap should be removed from the active itinerary and retained in a replacement list.
- Every planned stop should expose alternative POIs that can replace it.
- If a must-visit POI is far away, build a lighter standalone day around that POI instead of forcing it into an unrelated cluster.
- Production planning should use precomputed route edges only. Live AMap calls are for offline data preparation and tests, not per-request runtime planning.

Rejected alternatives:

- Calling AMap live during every user plan request: more accurate, but risks latency, quota exhaustion, API-key exposure, and unstable tests.
- Keeping current display-only route check: insufficient, because bad routes are only discovered after the plan is already built.
- Using Haversine-only distance caps: useful as a fallback, but it does not reflect real road networks or bridges/tunnels.
- Building every pair of POIs with AMap: complete but unnecessary and expensive. For N POIs it creates roughly N*(N-1)/2 edges; a city with 500 POIs would need about 124,750 unique pairs before walk/drive mode expansion.

## Current Real Edge Algorithm

Existing `scripts/build_commute_edges.js` already uses a sparse graph algorithm:

1. For every POI, compute approximate geographic distance to all other POIs.
2. Keep the nearest `neighbors` POIs for each point. The current default is 6 and the accepted range is 1-12.
3. Deduplicate undirected pairs.
4. Add bridge pairs between disconnected components so the route graph remains connected.
5. Fetch AMap route metrics for the selected sparse pairs.
6. Write `edges.json` with `taxi_minutes`, `walk_minutes`, `transit_minutes`, `distance_meters`, `source`, `provider`, `mode`, and `duration_seconds`.
7. If AMap is unavailable, the script can fall back to `geo_estimated`, but strict production data builds should fail or warn when AMap coverage is too low.

This is the right foundation. The next optimization is not all-pairs; it is smarter sparse-pair selection:

- `nearest_k`: connect each POI to nearby POIs, default 8 for most cities and 6 for smaller or API-budget-constrained runs.
- `hotel_anchor`: connect each hotel to the nearest attractions, restaurants, transport hubs, and night POIs.
- `cluster_anchor`: connect top attractions inside each district/theme cluster.
- `popular_cross_check`: add a small number of edges between high-popularity POIs that users often combine, even if they are not geographically nearest.
- `must_visit_patch`: when users or audits reveal important pairs, fetch explicit route-pair patches.
- `problem_pair_patch`: add reported bad route pairs to a regression pair list so their real time is always known.

This gives enough real edges for practical planning without creating a full city all-pairs graph.

## Confirmed Product Decisions

- Default travel mode: taxi/driving.
- Optional POIs that violate commute caps: automatically remove from active itinerary.
- Removed optional POIs: preserve in a replacement pool, not discarded.
- Stop alternatives: every stop should have replacement candidates when the data allows it, and the frontend should expose them through the attraction switching list.
- Far must-visit POIs: create a lighter standalone day centered on that POI.
- Production route source: precomputed AMap edges only.
- Missing route edges: expected to be rare after offline data completion; use stricter estimated fallback and reviewer warnings, but do not set a final coverage gate before the crawl evidence exists.
- City scope: design the fix so it can run across most cities, not only Qingdao/Chongqing.
- Sparse graph default: use nearest-neighbor count 8 for most cities; use 6 for smaller or API-budget-constrained datasets.

## Implementation Plan

### Phase 1: Route Data Foundation

Task 1: Keep explicit route-pair fetcher

- Status: done locally.
- Files: `scripts/fetch_real_route_pairs.js`, `package.json`, `tests/test_amap_pipeline.js`.
- Acceptance:
  - Fetch named POI pairs by id or name.
  - Output edge patches compatible with `edges.json`.
  - Support mock fixtures for CI.
- Verification:
  - `node tests/test_amap_pipeline.js`.
  - Live pilot fetch for reported Qingdao pairs.

Task 2: Add route edge merge workflow

- Status: done locally for explicit edge merge script, batch staging promotion script, fixture tests, 21-city staging output, and production `data/{city}/edges.json` promotion.
- Files likely touched: `scripts/merge_route_edges.js`, `scripts/promote_route_edges.js`, `tests/test_amap_pipeline.js`, `docs/real_data_ops.md`.
- Acceptance:
  - Merge explicit AMap edge patches into an existing city `edges.json`.
  - Prefer `provider=amap` over `geo_estimated` for the same pair.
  - Write a manifest with counts of replaced, inserted, unchanged, and estimated edges.
- Real-effect test:
  - Dry-run merge all 21 refreshed route outputs into `output/route_promotion_dry_run_manifest.json`.
  - Generate staging data under `output/data-routes-staging`.
  - Verify a staging Qingdao pair resolves as `amap_cached` in route segment calculation.

Task 2A: Add multi-city sparse route edge builder profile

- Status: done locally for all supported cities. `output/amap-{city}-routes-v2/edges_manifest.json` exists for 21 cities, with 49,417 total driving edges and 100% AMap coverage in the refresh outputs.
- Files likely touched: `scripts/build_commute_edges.js`, `scripts/run_real_data_pipeline.js`, `docs/real_data_ops.md`, `tests/test_amap_pipeline.js`.
- Acceptance:
  - Use taxi/driving as default production mode.
  - Build sparse route graphs for every supported city using nearest neighbors plus anchors.
  - Use `neighbors=8` as the default multi-city profile, with `neighbors=6` available for smaller or quota-constrained runs.
  - Avoid all-pairs generation.
  - Produce per-city manifests with AMap coverage, edge counts, and fallback counts.
- Real-effect test:
  - Run on at least Qingdao and Chongqing first, then expand to all cities with available POIs.
  - Confirm edge count grows roughly `N * K`, not `N * N`.
  - Confirm reported long-commute pairs are either covered by real edges or rejected by feasibility gates.

Task 3: Add route quality audit command

- Status: done locally for JSON audit output, CLI threshold gates, fixture tests, and staging audit.
- Files likely touched: `scripts/audit_route_quality.js`, `tests/test_amap_pipeline.js`, `package.json`, `docs/real_data_ops.md`.
- Acceptance:
  - Report AMap coverage ratio per city.
  - List worst estimated or long-distance route pairs.
  - Fail when `amap` coverage is below a configured threshold.
- Real-effect test:
  - Run against `output/data-routes-staging` with `--min-amap-ratio 1`.
  - Confirm staging report writes 21 city summaries, lists worst edges, and reports 49,450/49,450 AMap edges after the Dali route-pair patch.

### Phase 2: Route Metric Contract

Task 4: Add one route metric helper

- Status: done locally.
- Files likely touched: `tools/route.py`, `tests/test_multi_agent.py`.
- Acceptance:
  - Return `{minutes, distance_meters, source, confidence}` for a POI pair.
  - Prefer real AMap edge durations.
  - Fall back to Haversine estimate with `confidence=estimated`.
- Real-effect test:
  - Fixture with real edge returns actual taxi/transit minutes.
  - Missing edge returns estimated source and lower confidence.

Task 5: Use route metric helper in Scheduler route ordering

- Status: not started.
- Files likely touched: `tools/route.py`, `agents/scheduler_agent.py`, `tests/test_multi_agent.py`.
- Acceptance:
  - Python fallback ordering uses route metric time when edge data exists.
  - Haversine is only the fallback.
  - Stop annotations still populate frontend route fields.
- Real-effect test:
  - Construct a fixture where geographically closer order is slower by real edge time.
  - Verify the scheduler chooses the lower real travel-time order.

### Phase 3: Feasibility Gates

Task 6: Add per-segment commute caps

- Status: partially done locally in Scheduler; Reviewer now flags evening POIs before 18:00 and days above 150 total commute minutes, but automatic repair from those issues still needs update.
- Files likely touched: `agents/scheduler_agent.py`, `agents/reviewer_agent.py`, `tests/test_multi_agent.py`.
- Proposed defaults:
  - Real AMap segment: warn above 45 min, reject optional stop above 60 min.
  - Estimated segment: warn above 30 min, reject optional stop above 45 min or 20 km.
  - Must-visit stop: keep only if explicitly requested, but label as long commute and avoid adding extra far stops around it.
- Real-effect test:
  - Qingdao pilot pair with 47 km should be rejected as optional same-day filler.
  - Must-visit far POI should remain but produce a warning and a lighter day.

Task 6A: Add replacement pool for removed optional stops

- Status: partially done locally for day-level replacement_pool, API output, frontend replacement list rendering, and server-side route recalculation after replacement.
- Files likely touched: `agents/scheduler_agent.py`, `api_multi_agent.py`, frontend itinerary rendering if alternatives are exposed.
- Acceptance:
  - When an optional POI is removed by commute feasibility, preserve it with a reason such as `commute_too_far`.
  - Each planned stop can expose nearby alternatives from the same type and area where possible.
  - The frontend exposes this list through the existing attraction switching interaction, so users can replace an unsatisfying stop without re-planning from scratch.
- Real-effect test:
  - A far optional restaurant/night market is absent from active stops but appears in replacement candidates.
  - Nearby same-area alternatives are present for a planned attraction.
  - Frontend smoke test confirms the switch list renders for a stop with alternatives.

Task 7: Add day-level commute budget

- Status: partially done locally. Reviewer flags excessive day commute, and Scheduler now removes optional stops whose adjacent route is missing a precomputed real edge when `data_dir` is explicit.
- Files likely touched: `agents/scheduler_agent.py`, `agents/reviewer_agent.py`, `tests/test_multi_agent.py`.
- Proposed defaults:
  - Relaxed: max 75 route minutes/day.
  - Balanced: max 105 route minutes/day.
  - Intense: max 140 route minutes/day.
- Real-effect test:
  - A day with multiple individually acceptable segments but excessive total travel should be rebalanced or fail review.

Task 8: Enforce hotel/day-cluster proximity

- Status: partially done locally. Scheduler now checks selected-hotel to first stop and last stop back to hotel, removes optional far hotel legs, and seeds empty days from hotel-nearby candidates after far optional stops are removed. Hotel selection and the deterministic smoke script both honor `hotel_area` business-district matches such as `解放碑`.
- Files likely touched: `tools/clustering.py`, `agents/scheduler_agent.py`, `tests/test_multi_agent.py`.
- Acceptance:
  - Optional attractions and restaurants must be near the selected hotel or dominant day cluster.
  - Cross-area POIs require must-visit status or strong route/popularity evidence.
- Real-effect test:
  - A hotel near one Qingdao district should not produce a day that jumps to a far night market unless the user requested it.

Task 8A: Build standalone day around far must-visit POIs

- Status: not started.
- Files likely touched: `tools/clustering.py`, `agents/scheduler_agent.py`, `tests/test_multi_agent.py`.
- Acceptance:
  - Detect must-visit POIs that are too far from all existing day clusters.
  - Assign the far must-visit to its own day when trip length allows.
  - Fill that day only with nearby compatible POIs and meals.
- Real-effect test:
  - A far must-visit remains in the itinerary.
  - The day around it has low local commute and does not mix unrelated distant districts.

### Phase 4: Attraction-First Scheduling

Task 9: Preserve attraction priority

- Status: partially done locally for restaurant over-selection.
- Files likely touched: `agents/scheduler_agent.py`, `tools/clustering.py`, `tests/test_multi_agent.py`.
- Acceptance:
  - Non-food trips default to one restaurant stop per day.
  - Food-focused trips may include lunch and dinner.
  - Restaurants cannot displace core attractions.
- Real-effect test:
  - Generic sightseeing request should produce more attractions than restaurants each day.
  - Food-focused request can include dinner/night market without failing balance checks.

Task 10: Lock evening-only POIs to evening

- Status: partially done locally.
- Files likely touched: `agents/scheduler_agent.py`, `agents/reviewer_agent.py`, `tests/test_multi_agent.py`.
- Acceptance:
  - Night markets, night views, bars, and explicit evening POIs cannot be scheduled before 18:00 unless their metadata contradicts the keyword.
  - Reviewer flags any remaining violation as high severity.
- Real-effect test:
  - `吕家庄夜市` and `洪崖洞夜市街区` fixtures schedule at or after 18:00.

### Phase 5: Data Completeness and POI Quality

Task 11: Audit missing popular POIs

- Status: not started.
- Files likely touched: `scripts/audit_city_poi_coverage.js`, `docs/real_data_report.md`.
- Acceptance:
  - Compare city POIs against AMap search and XHS route references.
  - Flag missing high-priority attractions and suspicious low-quality attractions.
- Real-effect test:
  - Qing岛 and 重庆 produce reports listing missing/weak POIs with source evidence.

Task 12: Add low-quality POI filters

- Status: not started.
- Files likely touched: `tools/scoring.py`, `agents/poi_agent.py`, `tests/test_multi_agent.py`.
- Acceptance:
  - Hotels, generic shops, apartments, vague businesses, and weak POIs do not enter attraction slots.
  - Must-visit user input can still force inclusion.
- Real-effect test:
  - `哈哈Home(重庆解放碑步行街洪崖洞店)` style entries are rejected as attractions unless explicitly requested.

### Phase 6: Production Verification

Task 13: Add end-to-end route regression fixtures

- Status: not started.
- Files likely touched: `tests/test_multi_agent.py`, possibly `tests/fixtures/`.
- Acceptance:
  - Fixtures cover Qingdao long commute, Chongqing night market timing, restaurant-heavy day, low-quality POI filtering.
  - Tests fail on current bad behavior and pass after fixes.
- Real-effect test:
  - Run all route-related regression tests locally.

Task 14: Run local demo smoke before deploy

- Status: partially done locally for deterministic backend smoke, local API smoke, and mocked browser regression against promoted production route data.
- Files likely touched: none unless bugs are found.
- Acceptance:
  - Generate Qingdao and Chongqing itineraries using fixed logic.
  - Confirm frontend route labels show real/estimated source correctly.
  - Confirm no reported long commute/night-market-morning case appears.
- Real-effect test:
  - `py -3 scripts/smoke_itinerary_quality.py --data-dir data --city qingdao --city chongqing --out output\itinerary_quality_smoke_data.json` passes with the same promoted route data now used by production.
  - Local Chongqing live API smoke passes for the reported structured-form scenario: selected hotel is in 解放碑/渝中, active itinerary has 8 stops, 5 AMap segments, 0 estimated segments, no morning night POIs, no low-quality Hongyadong shops, and no far-county active POIs.
  - Local Qingdao live API smoke passes for a generic sightseeing scenario: selected hotel is in 市南区, active itinerary has 9 stops, 6 AMap segments, 0 estimated segments, no morning night POIs, no low-quality keyword matches, and no restaurant-dominated days.
  - Mocked browser regression passes for structured form submission, image carousel controls/fallback, route metric display, and replacement-list server refresh.

Task 15: Deploy only after tests and smoke pass

- Status: not started.
- Files likely touched: none.
- Acceptance:
  - Commit intentional changes only.
  - Push deployment branch or target branch as requested.
  - Verify deployed URL behavior.
- Real-effect test:
  - Re-run the same Qingdao and Chongqing scenarios on production URL.

## Suggested Thresholds For Review

These are proposed defaults, not final decisions:

| Rule | Relaxed | Balanced | Intense |
| --- | ---: | ---: | ---: |
| Real segment warn | 35 min | 45 min | 55 min |
| Real segment reject optional | 50 min | 60 min | 75 min |
| Estimated segment warn | 25 min | 30 min | 40 min |
| Estimated segment reject optional | 35 min | 45 min | 55 min |
| Day total commute max | 75 min | 105 min | 140 min |
| Optional same-day distance cap | 15 km | 20 km | 30 km |

## Resolved Questions

1. User-facing travel mode: default to taxi/driving.
2. Threshold strictness: automatically remove optional POIs above the cap, but keep them in the replacement pool.
3. Must-visit behavior: if a must-visit POI is far away, arrange a separate day around it.
4. API usage policy: production should rely on precomputed route edges first.
5. City priority: optimize the plan for most cities, not only one city.

## Crawl Baseline And Refresh Result

Production `data/{city}/edges.json` still has low AMap edge coverage in most cities. Examples from the pre-refresh audit:

- qingdao: 473 POIs, 849 edges, 38 AMap edges, 4.5% AMap coverage.
- chongqing: 483 POIs, 980 edges, 296 AMap edges, 30.2% AMap coverage.
- chengdu: 444 POIs, 872 edges, 291 AMap edges, 33.4% AMap coverage.
- beijing: 428 POIs, 816 edges, 218 AMap edges, 26.7% AMap coverage.
- many other production city files are currently around 3%-8% AMap coverage.

The sparse graph refresh has now completed under `output/` for all supported cities. The refreshed route outputs have been merged into `output/data-routes-staging`, the one remaining Dali estimated edge has been targeted-patched with an AMap driving edge, and the verified staging `edges.json` files have been copied into production `data/{city}/edges.json`. Staging and production route data now have 100% AMap route coverage. Deterministic Qingdao and Chongqing itinerary smoke tests pass against default production `data/`. Local API health smoke and Qingdao/Chongqing live API itinerary-generation smoke pass with the promoted production route data, and mocked frontend browser regression passes for the previously reported UI surfaces.

## Remaining Questions

1. Should replacement lists include only same-type POIs, or allow same-slot substitutes such as attraction -> scenic street/night market when time and distance fit?
2. Should deployment proceed directly from the current branch after final production-data smoke, or should the changes be split into smaller commits first?

## Immediate Next Step

Recommended next implementation step after review:

1. Decide whether same-slot substitutes can cross POI type when time and distance fit.
2. Commit, push, and deploy the promoted production route data and algorithm/UI fixes.
3. After deployment, re-run the same Qingdao and Chongqing scenarios on the deployed URL.

This keeps deployment gated on production-data verification rather than on the temporary staging directory.
