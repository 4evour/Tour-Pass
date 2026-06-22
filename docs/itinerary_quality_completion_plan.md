# Itinerary Quality Completion Plan

## Status

Active implementation plan.

## Date

2026-06-21

## Scope

This plan covers all user-reported issues that affect itinerary quality and trust. Route time is only one part of the goal.

## Problems From Prior Conversation

1. Attraction image carousel could not reliably switch left/right when images failed or placeholders appeared.
2. Commute time and distance between stops were missing, then later shown but based on weak estimates.
3. Structured form submission was unresponsive or returned 404.
4. Night markets and evening districts could be scheduled in the morning.
5. Restaurant scheduling could dominate a day, leaving too few attractions.
6. Low-quality POIs could enter attraction slots, such as gift shops, hotels, apartments, or vague businesses.
7. Route planning could cross large districts or produce unrealistic commute values.
8. The planner did not reliably use real AMap travel time when judging feasibility.
9. Optional far POIs needed to be removed from the active itinerary while remaining available as replacement candidates.
10. The system needed a scalable real-data route crawl strategy across most cities, not only one city.

## Product Decisions

- Default travel mode is taxi/driving.
- Production planning should use precomputed AMap route edges, not live per-request AMap calls.
- Route edges should use a sparse graph: nearest neighbors plus targeted hotel, cluster, must-visit, popular, and reported-problem pairs.
- Optional POIs that exceed commute caps should be removed from active stops and placed in `replacement_pool`.
- Must-visit POIs should remain even when far; the planner should build a lighter standalone day around them when possible.
- Generic sightseeing trips should stay attraction-first; only explicit food-focused trips may include more restaurants.
- Night markets, night views, and nightlife POIs must be scheduled in evening slots.
- Frontend should expose replacement candidates through the existing switch-attraction behavior.
- Multi-city route refresh should run first, then coverage should be judged from manifests instead of guessed in advance.

## Current Implementation State

### Already Implemented Locally

- Structured form 404 proxy fix.
- Attraction image carousel bad-image fallback.
- Route segment display with time, distance, and source.
- Explicit route-pair AMap fetch tool.
- `build_commute_edges.js` mock route fixture fix.
- Default route metric helper in `tools.route`.
- Route segment calculation defaults to taxi/driving time.
- Scheduler optional-stop feasibility filter with `replacement_pool`.
- API response preserves `replacement_pool`.
- Night-market restaurant no longer enters lunch-only trips.
- Generic non-food trips default to one restaurant per day.
- Restaurant candidate selection includes area representatives.
- Far restaurants/nightlife are not forced into unrelated day clusters.
- Low-quality commercial/gift-shop POIs are filtered from generic attraction candidates.
- Real driving route refresh pilots:
  - qingdao: 473 POIs, 2467 edges, AMap 100%.
  - chongqing: 483 POIs, 2535 edges, AMap 100%.
  - chengdu: 444 POIs, 2298 edges, AMap 100%.
  - beijing: 428 POIs, 2179 edges, AMap 100%.
  - shanghai: 536 POIs, 2730 edges, AMap 100%.
  - guangzhou: 492 POIs, 2512 edges, AMap 100%.
  - hangzhou: 478 POIs, 2425 edges, AMap 100%.
  - xian: 494 POIs, 2567 edges, AMap 100%.
  - shenzhen: 513 POIs, 2553 edges, AMap 100%.
  - suzhou: 522 POIs, 2647 edges, AMap 100%.
  - nanjing: 2257 edges, AMap 100%.
  - wuhan: 2315 edges, AMap 100%.
  - guilin: 2857 edges, AMap 100%.
  - xiamen: 2711 edges, AMap 100%.
  - harbin: 2484 edges, AMap 100%.
  - changsha: 1680 edges, AMap 100%.
  - dali: 2331 edges, AMap 100%.
  - kunming: 2449 edges, AMap 100%.
  - lijiang: 1930 edges, AMap 100%.
  - sanya: 1756 edges, AMap 100%.
  - zhangjiajie: 1734 edges, AMap 100%.
  - Total refreshed routes-v2 output: 21 cities, 49,417 driving edges, AMap 100%.
- Route edge merge/promote script exists locally with fixture coverage.
- Staging route promotion has been generated under `output/data-routes-staging`: 21 cities, 49,450 merged edges, 17,287 replaced, 32,130 inserted, 49,450 AMap-sourced edges after the Dali route-pair patch. The verified staging `edges.json` files have now been copied into production `data/{city}/edges.json`.
- Route quality audit command exists locally. `output/data-routes-staging` passes `--min-amap-ratio 1` with 21 cities, 49,450 edges, 49,450 AMap edges, and 0 remaining estimated edges after the Dali route-pair patch.
- Deterministic itinerary smoke command exists locally. Qingdao and Chongqing pass against `output/data-routes-staging`: Qingdao 9 stops / 6 AMap route segments / 0 estimated segments / 4 replacement candidates; Chongqing 8 stops / 5 AMap route segments / 0 estimated segments / 6 replacement candidates.
- API graph initialization now accepts a custom data root, and `api_multi_agent.py` can use `TOUR_PASS_DATA_DIR=output/data-routes-staging` or `DATA_DIR=output/data-routes-staging` for local API/browser smoke without replacing production `data/`.
- Local API health smoke passes when the API is started with `TOUR_PASS_DATA_DIR=output/data-routes-staging`.
- Local Chongqing live API staging smoke passes for the reported structured-form scenario with `hotel_area=解放碑`: selected hotel is `重庆解放碑国贸中心亚朵酒店` in 渝中区, itinerary has 8 stops, 5 AMap route segments, 0 estimated active segments, no morning night POIs, no low-quality Hongyadong shops, and no far-county active POIs.
- Local Qingdao live API staging smoke passes for a generic sightseeing scenario with `hotel_area=市南区`: selected hotel is `青岛栈桥火车站美居酒店` in 市南区, itinerary has 9 stops, 6 AMap route segments, 0 estimated active segments, no morning night POIs, no low-quality keyword matches, and no restaurant-dominated days.
- Frontend browser regression `scripts/verify_agent_image_carousel.js` passes with mocked API responses, covering structured form submission, image carousel switching/fallback, route metric display, and replacement-list server refresh behavior.
- Scheduler now treats missing precomputed real route edges as infeasible when a planning state explicitly carries `data_dir`; optional POIs are moved into `replacement_pool`, and connected alternatives from `available_pois` can fill the day.
- Scheduler now checks hotel-to-first-stop and last-stop-to-hotel commute feasibility. Real hotel route edges are preferred; missing hotel edges use a stricter estimated fallback so nearby hotel legs are not over-pruned while far cross-county single-stop days are removed.
- Scheduler can seed an empty day from hotel-nearby candidates after far optional stops are removed, then use real connected edges to fill additional stops.
- Hotel selection now matches requested business areas against hotel name, tags, description, recommendation, and address, not only administrative `area`.
- Reviewer flags evening-oriented POIs scheduled before 18:00 as high severity.
- Reviewer flags days whose total commute exceeds 150 minutes as high severity.
- Agent result cards expose day-level replacement pool candidates through a per-stop replacement list.
- Agent replacement actions call `/agent/modify` when a session exists, then re-render server-returned route metrics.

### Not Yet Complete

- Production `data/{city}/edges.json` has been replaced with the verified staging route edges; deployment still needs to be pushed and verified on the public URL.
- Scheduler route ordering still needs deeper real-time use, especially when Python fallback chooses stop order.
- Reviewer day-level commute budget exists; the next step is using it in automatic repair/replan decisions.
- Replacement candidates exist as a pool and render in the frontend; the next step is automatic repair when a replacement still violates route feasibility.
- Far must-visit standalone-day behavior is documented but not fully implemented.
- Deployed URL verification is not complete; local deterministic smoke covers Qingdao and Chongqing with default production `data/` after promotion, and local Qingdao/Chongqing live API itinerary-generation smoke passes with the promoted production route data.
- Dali's remaining estimated staging edge (`amap_391850b7` -> `amap_58eb5224`) has been targeted-patched with an AMap driving edge in staging.

## Phased Completion Plan

### Phase 1: Stabilize Current Local Changes

Acceptance:

- All modified behavior has tests.
- `CHANGELOG.md` records every project file change.
- Existing Python and AMap pipeline tests pass.
- No generated `output/` data is accidentally committed unless explicitly promoted.

Verification:

- `py -3 tests/test_multi_agent.py -v`
- `node tests/test_amap_pipeline.js`
- `git diff --check`

### Phase 2: Multi-City Real Route Data

Acceptance:

- Refresh driving route edges for all supported cities with `neighbors=8`.
- Write per-city manifests with edge count, source counts, and AMap ratio.
- Produce an aggregate report that compares old and refreshed coverage.
- Keep refresh outputs under `output/` until promotion is intentional.

Verification:

- Every supported city has `output/amap-{city}-routes-v2/edges_manifest.json`.
- Each manifest reports `mode=driving`, `neighbors=8`, and source coverage.
- Any failures are listed with city and reason.
- Cities with unstable large distance batches should be retried with `--batch-size 25`.

### Phase 3: Route Data Promotion

Acceptance:

- Use the script to safely merge/promote refreshed edges into a target data directory.
- The script must prefer `provider=amap` over `geo_estimated`.
- The script must write a manifest with inserted/replaced/unchanged counts.
- The script must support dry-run and output-dir modes before touching production data.

Verification:

- Unit test with a fixture where a `geo_estimated` edge is replaced by an AMap edge.
- Dry-run output confirms intended changes without editing `data/`.
- Promoted copy can be used by `calculate_route_segments`.
- Staging output confirms intended changes without editing `data/`.

### Phase 4: Planner Feasibility And Replacement Lists

Acceptance:

- Scheduler uses real route metrics before finalizing daily stops.
- Optional over-limit stops move to `replacement_pool`.
- Replacement entries preserve reason and route metric.
- Each planned stop exposes local alternatives where possible.
- Must-visit far POIs remain and do not drag unrelated far POIs into the same day.

Verification:

- Tests cover optional far stop removal.
- Tests cover must-visit far stop retention.
- Tests cover replacement pool API output.
- Tests cover stop-specific alternatives once implemented.

### Phase 5: Time And Content Quality

Acceptance:

- Evening-only POIs cannot be scheduled before 18:00.
- Reviewer flags any remaining evening-time violation as high severity.
- Generic trips keep more attractions than restaurants.
- Food-focused trips can include food/night-market experiences without dominating non-food itineraries.
- Low-quality POIs stay out of attraction slots unless explicitly requested.

Verification:

- Tests cover night markets in Qingdao and Chongqing.
- Tests cover restaurant-heavy day rejection.
- Tests cover low-quality POI filtering and must-visit override.

### Phase 6: Frontend Integration

Acceptance:

- Replacement pool or stop alternatives render in the existing switch-attraction UI.
- Route source/time/distance remain visible after switching.
- Image carousel can switch through valid images and skip failed images.
- Structured form submits successfully and produces an itinerary.

Verification:

- Browser smoke test for generated itinerary.
- Browser smoke test for switch-attraction interaction.
- Browser smoke test for structured form.
- Browser smoke test for image carousel controls.
- Current mocked browser regression passes for structured form, switch-attraction, route display, and image carousel controls; full live backend itinerary generation remains separate.

### Phase 7: End-To-End City Quality Checks

Acceptance:

- At least Qingdao and Chongqing pass manual/API smoke tests for the originally reported scenarios.
- No morning night markets.
- No restaurant-dominated generic sightseeing days.
- No obvious low-quality attraction like gift shops/hotels in generic trips.
- No optional multi-hour/long-distance commute segments in active itinerary.
- Replacement candidates exist when optional POIs are removed.

Verification:

- Local API or browser snapshots for Qingdao and Chongqing.
- Local API/browser itinerary-generation smoke can use default production `data/` after route promotion; `TOUR_PASS_DATA_DIR=output/data-routes-staging` remains useful only for comparing staging artifacts.
- Production URL verification after deployment.

## Completion Criteria

The plan is complete only when:

- Tests pass locally.
- Refreshed route data is available or intentionally promoted for supported cities.
- Scheduler/Reviewer enforce route, timing, restaurant balance, and POI quality gates.
- Frontend exposes route metrics and replacement candidates.
- The originally reported scenarios are re-tested and no longer reproduce.
- Deployment is pushed and verified on the live URL.

Until all of the above are true, this goal remains active.
