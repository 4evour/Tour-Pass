const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const root = path.resolve(__dirname, "..");
const outDir = path.join(root, "output", "test-amap-pipeline");
const configPath = path.join(outDir, "amap.test.json");
const searchFixture = path.join(root, "tests", "fixtures", "amap_search");
const routeFixture = path.join(root, "tests", "fixtures", "amap_route");

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(configPath, JSON.stringify({
  city: "长沙",
  target_count: 6,
  page_size: 25,
  max_pages_per_category: 1,
  categories: [
    { name: "核心景点", keywords: "长沙 景点", poi_type: "attraction", tags: ["景点"] },
    { name: "博物馆与文化", keywords: "长沙 博物馆", poi_type: "attraction", tags: ["历史文化", "室内"] },
    { name: "本地餐饮", keywords: "长沙 湘菜", poi_type: "restaurant", tags: ["美食"] },
    { name: "夜游夜市", keywords: "长沙 夜游", poi_type: "nightlife", tags: ["夜景"] },
    { name: "演示酒店", keywords: "长沙 酒店", poi_type: "hotel", tags: ["酒店"] },
    { name: "公园与户外", keywords: "长沙 公园", poi_type: "attraction", tags: ["户外"] },
    { name: "商圈街区", keywords: "长沙 商圈", poi_type: "attraction", tags: ["街区"] }
  ]
}, null, 2));

const missingKeyResult = spawnSync(process.execPath, [
  "scripts/fetch_amap_pois.js",
  "--config", configPath,
  "--out-dir", path.join(outDir, "missing-key"),
], {
  cwd: root,
  encoding: "utf8",
  env: { ...process.env, AMAP_API_KEY: "" },
});
assert.notStrictEqual(missingKeyResult.status, 0, "real AMap mode fails clearly without AMAP_API_KEY");
assert.ok((missingKeyResult.stderr + missingKeyResult.stdout).includes("AMAP_API_KEY"), "missing key error names AMAP_API_KEY");
assert.ok(!fs.existsSync(path.join(outDir, "missing-key", "pois.json")), "missing key failure does not write partial pois");

const importResult = spawnSync(process.execPath, [
  "scripts/fetch_amap_pois.js",
  "--config", configPath,
  "--out-dir", outDir,
  "--min-pois", "6",
  "--mock-dir", searchFixture,
], { cwd: root, encoding: "utf8" });
assert.strictEqual(importResult.status, 0, importResult.stderr || importResult.stdout);

const pois = JSON.parse(fs.readFileSync(path.join(outDir, "pois.json"), "utf8"));
const manifest = JSON.parse(fs.readFileSync(path.join(outDir, "manifest.json"), "utf8"));
assert.strictEqual(pois.length, 6, "imports unique mock AMap POIs and removes duplicates");
assert.strictEqual(new Set(pois.map((poi) => poi.source_id)).size, 6, "deduplicates by source id");
assert.ok(pois.some((poi) => poi.type === "hotel"), "keeps hotel category");
assert.ok(pois.some((poi) => poi.type === "restaurant"), "keeps restaurant category");
assert.ok(pois.every((poi) => poi.id.startsWith("amap_")), "normalizes stable AMap ids");
assert.strictEqual(manifest.source, "mock", "manifest records mock source for offline tests");
assert.strictEqual(manifest.min_pois, 6, "manifest records minimum POI gate");
assert.strictEqual(manifest.duplicate_count, 1, "manifest records duplicate POIs skipped");
assert.ok(manifest.area_counts && Object.keys(manifest.area_counts).length > 0, "manifest records area distribution");

const tooFewResult = spawnSync(process.execPath, [
  "scripts/fetch_amap_pois.js",
  "--config", configPath,
  "--out-dir", path.join(outDir, "too-few"),
  "--min-pois", "7",
  "--mock-dir", searchFixture,
], { cwd: root, encoding: "utf8" });
assert.notStrictEqual(tooFewResult.status, 0, "min-pois gate fails when fixture has too few unique POIs");
assert.ok((tooFewResult.stderr + tooFewResult.stdout).includes("min-pois"), "min-pois failure names the gate");

const edgeResult = spawnSync(process.execPath, [
  "scripts/build_commute_edges.js",
  "--pois", path.join(outDir, "pois.json"),
  "--out-dir", outDir,
  "--neighbors", "2",
  "--mock-dir", routeFixture,
], { cwd: root, encoding: "utf8" });
assert.strictEqual(edgeResult.status, 0, edgeResult.stderr || edgeResult.stdout);

const edges = JSON.parse(fs.readFileSync(path.join(outDir, "edges.json"), "utf8"));
const edgeManifest = JSON.parse(fs.readFileSync(path.join(outDir, "edges_manifest.json"), "utf8"));
assert.ok(edges.length >= 6, "builds nearest-neighbor commute graph");
assert.ok(edges.some((edge) => edge.source === "amap"), "uses mocked AMap route when fixture exists");
assert.ok(edges.some((edge) => edge.source === "geo_estimated"), "falls back to geo_estimated when route fixture is missing");
assert.ok(edgeManifest.source_counts.amap >= 1, "edge manifest counts AMap edges");
assert.ok(edgeManifest.source_counts.geo_estimated >= 1, "edge manifest counts fallback edges");
assert.ok(edgeManifest.amap_ratio > 0 && edgeManifest.amap_ratio < 1, "edge manifest records AMap source ratio");
assert.ok(edges.some((edge) => edge.provider === "amap" && edge.mode === "mixed"), "AMap edge records provider and mode");
assert.ok(edges.some((edge) => Number.isFinite(edge.duration_seconds)), "edges include duration_seconds for compatibility with AMap timing");

const drivingCacheResult = spawnSync(process.execPath, [
  "-e",
  `
  const assert = require("assert");
  const fs = require("fs");
  const path = require("path");
  const { fetchAmapDrivingDistanceBatch } = require("./scripts/build_commute_edges.js");
  const cacheDir = path.join("${outDir.replace(/\\/g, "\\\\")}", "driving-cache");
  fs.mkdirSync(cacheDir, { recursive: true });
  fs.writeFileSync(path.join(cacheDir, "distance-dst-0.json"), JSON.stringify({
    status: "1",
    results: [{ origin_id: "1", duration: "540", distance: "5200" }]
  }));
  global.fetch = async () => { throw new Error("network should not be called for cached driving distance"); };
  (async () => {
    const metrics = await fetchAmapDrivingDistanceBatch({
      pairs: [{ from: { id: "src", lat: 30, lng: 120 }, to: { id: "dst", lat: 30.1, lng: 120.1 } }],
      apiKey: "test",
      cacheDir,
      batchSize: 10,
    });
    const metric = metrics.get("dst<->src");
    assert.strictEqual(metric.durationSeconds, 540);
    assert.strictEqual(metric.distanceMeters, 5200);
  })().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
  `,
], { cwd: root, encoding: "utf8" });
assert.strictEqual(drivingCacheResult.status, 0, drivingCacheResult.stderr || drivingCacheResult.stdout);

const fallbackFailDir = path.join(outDir, "fallback-fail");
const fallbackFailResult = spawnSync(process.execPath, [
  "scripts/build_commute_edges.js",
  "--pois", path.join(outDir, "pois.json"),
  "--out-dir", fallbackFailDir,
  "--neighbors", "2",
  "--mock-dir", routeFixture,
  "--fallback", "fail",
], { cwd: root, encoding: "utf8" });
assert.notStrictEqual(fallbackFailResult.status, 0, "fallback=fail rejects missing AMap route coverage");
assert.ok((fallbackFailResult.stderr + fallbackFailResult.stdout).includes("geo_estimated"), "fallback failure explains estimated edge rejection");
assert.ok(!fs.existsSync(path.join(fallbackFailDir, "edges.json")), "fallback=fail does not write partial edges");

const minRatioDir = path.join(outDir, "min-ratio");
const minRatioResult = spawnSync(process.execPath, [
  "scripts/build_commute_edges.js",
  "--pois", path.join(outDir, "pois.json"),
  "--out-dir", minRatioDir,
  "--neighbors", "2",
  "--mock-dir", routeFixture,
  "--min-amap-ratio", "0.8",
], { cwd: root, encoding: "utf8" });
assert.notStrictEqual(minRatioResult.status, 0, "min-amap-ratio rejects low AMap coverage");
assert.ok((minRatioResult.stderr + minRatioResult.stdout).includes("min-amap-ratio"), "ratio failure names min-amap-ratio");

const validateResult = spawnSync(process.execPath, [
  "scripts/validate_data.js",
  "--pois", path.join(outDir, "pois.json"),
  "--edges", path.join(outDir, "edges.json"),
  "--min-pois", "6",
  "--require-edge-source",
], { cwd: root, encoding: "utf8" });
assert.strictEqual(validateResult.status, 0, validateResult.stderr || validateResult.stdout);
assert.ok(validateResult.stdout.includes("edge_sources"), "validation summary includes edge source counts");

const routePairsPath = path.join(outDir, "route-pairs.json");
const routePairsOut = path.join(outDir, "route-pair-edges.json");
fs.writeFileSync(routePairsPath, JSON.stringify([
  { from: "amap_7af8f074", to: "amap_7df8f52d" },
], null, 2));
const routePairsHelp = spawnSync(process.execPath, [
  "scripts/fetch_real_route_pairs.js",
  "--help",
], { cwd: root, encoding: "utf8" });
assert.strictEqual(routePairsHelp.status, 0, routePairsHelp.stderr || routePairsHelp.stdout);
assert.ok(routePairsHelp.stdout.includes("fetch_real_route_pairs.js"), "explicit route pair help uses its own CLI usage");
const routePairsResult = spawnSync(process.execPath, [
  "scripts/fetch_real_route_pairs.js",
  "--pois", path.join(outDir, "pois.json"),
  "--pairs", routePairsPath,
  "--out", routePairsOut,
  "--mock-dir", routeFixture,
  "--require-all",
], { cwd: root, encoding: "utf8" });
assert.strictEqual(routePairsResult.status, 0, routePairsResult.stderr || routePairsResult.stdout);
const routePairEdges = JSON.parse(fs.readFileSync(routePairsOut, "utf8"));
const routePairManifest = JSON.parse(fs.readFileSync(path.join(outDir, "route-pair-edges.manifest.json"), "utf8"));
assert.strictEqual(routePairEdges.length, 1, "explicit route pair fetch writes one edge patch");
assert.strictEqual(routePairEdges[0].source, "amap", "explicit route pair uses AMap source");
assert.strictEqual(routePairEdges[0].taxi_minutes, 4, "explicit route pair records driving minutes");
assert.strictEqual(routePairEdges[0].walk_minutes, 10, "explicit route pair records walking minutes");
assert.strictEqual(routePairEdges[0].route_confidence, "real", "explicit route pair marks real confidence");
assert.strictEqual(routePairManifest.success_count, 1, "explicit route pair manifest counts success");

const pipelineConfigPath = path.join(outDir, "pipeline.amap.test.json");
const pipelineOutDir = path.join(outDir, "pipeline");
fs.writeFileSync(pipelineConfigPath, JSON.stringify({
  city: "长沙",
  target_count: 6,
  page_size: 25,
  max_pages_per_category: 1,
  categories: [
    { name: "核心景点", keywords: "长沙 景点", poi_type: "attraction", tags: ["景点"] },
    { name: "博物馆与文化", keywords: "长沙 博物馆", poi_type: "attraction", tags: ["历史文化", "室内"] },
    { name: "本地餐饮", keywords: "长沙 湘菜", poi_type: "restaurant", tags: ["美食"] },
    { name: "夜游夜市", keywords: "长沙 夜游", poi_type: "nightlife", tags: ["夜景"] },
    { name: "演示酒店", keywords: "长沙 酒店", poi_type: "hotel", tags: ["酒店"] },
    { name: "公园与户外", keywords: "长沙 公园", poi_type: "attraction", tags: ["户外"] },
    { name: "商圈街区", keywords: "长沙 商圈", poi_type: "attraction", tags: ["街区"] },
  ],
}, null, 2));
const pipelineResult = spawnSync(process.execPath, [
  "scripts/run_real_data_pipeline.js",
  "--config", pipelineConfigPath,
  "--out-dir", pipelineOutDir,
  "--search-mock-dir", searchFixture,
  "--route-mock-dir", routeFixture,
  "--min-pois", "6",
  "--neighbors", "2",
  "--min-amap-ratio", "0",
  "--skip-scale",
  "--report", path.join(pipelineOutDir, "pipeline.md"),
  "--json-report", path.join(pipelineOutDir, "pipeline.json"),
], { cwd: root, encoding: "utf8" });
assert.strictEqual(pipelineResult.status, 0, pipelineResult.stderr || pipelineResult.stdout);
const pipelineManifest = JSON.parse(fs.readFileSync(path.join(pipelineOutDir, "pipeline.json"), "utf8"));
assert.strictEqual(pipelineManifest.poi_manifest.poi_count, 6, "one-command real data pipeline records POI count");
assert.ok(pipelineManifest.edge_manifest.edge_count >= 6, "one-command pipeline records edge count");
assert.ok(fs.existsSync(path.join(pipelineOutDir, "pipeline.md")), "one-command pipeline writes markdown report");

const retryMockDir = path.join(outDir, "retry-route");
fs.mkdirSync(retryMockDir, { recursive: true });
const retrySourceEdges = JSON.parse(fs.readFileSync(path.join(pipelineOutDir, "edges.json"), "utf8"));
const retrySourceEdge = retrySourceEdges.find((edge) => edge.source === "geo_estimated");
assert.ok(retrySourceEdge, "fixture pipeline has a geo_estimated edge to retry");
fs.writeFileSync(
  path.join(retryMockDir, `drive-${[retrySourceEdge.from, retrySourceEdge.to].sort().join("_")}.json`),
  JSON.stringify({ status: "1", route: { paths: [{ duration: "360", distance: "2100" }] } }, null, 2),
);
const retryOutDir = path.join(outDir, "retry");
const retryResult = spawnSync(process.execPath, [
  "scripts/retry_geo_edges.js",
  "--pois", path.join(pipelineOutDir, "pois.json"),
  "--edges", path.join(pipelineOutDir, "edges.json"),
  "--out-dir", retryOutDir,
  "--mock-dir", retryMockDir,
  "--mode", "driving",
  "--min-amap-ratio", "0",
], { cwd: root, encoding: "utf8" });
assert.strictEqual(retryResult.status, 0, retryResult.stderr || retryResult.stdout);
const retryReport = JSON.parse(fs.readFileSync(path.join(retryOutDir, "geo_estimated_edges_report.json"), "utf8"));
assert.strictEqual(retryReport.retried_success, 1, "geo_estimated retry converts a mocked route");
assert.ok(retryReport.after_amap_ratio > retryReport.before_amap_ratio, "geo_estimated retry improves AMap edge ratio");

const mergeBaseEdgesPath = path.join(outDir, "merge-base-edges.json");
const mergePatchEdgesPath = path.join(outDir, "merge-patch-edges.json");
const mergeOutPath = path.join(outDir, "merge-out-edges.json");
const mergeManifestPath = path.join(outDir, "merge-manifest.json");
fs.writeFileSync(mergeBaseEdgesPath, JSON.stringify([
  {
    from: "amap_7af8f074",
    to: "amap_7df8f52d",
    distance_meters: 999,
    walk_minutes: 20,
    transit_minutes: 15,
    taxi_minutes: 12,
    source: "geo_estimated",
    provider: "geo_estimated",
  },
  {
    from: "amap_keep",
    to: "amap_other",
    distance_meters: 300,
    walk_minutes: 4,
    transit_minutes: 3,
    taxi_minutes: 2,
    source: "amap",
    provider: "amap",
  },
], null, 2));
fs.writeFileSync(mergePatchEdgesPath, JSON.stringify([
  {
    from: "amap_7af8f074",
    to: "amap_7df8f52d",
    distance_meters: 2100,
    walk_minutes: 10,
    transit_minutes: 8,
    taxi_minutes: 4,
    source: "amap",
    provider: "amap",
    route_confidence: "real",
  },
], null, 2));
const mergeResult = spawnSync(process.execPath, [
  "scripts/merge_route_edges.js",
  "--base-edges", mergeBaseEdgesPath,
  "--patch-edges", mergePatchEdgesPath,
  "--out", mergeOutPath,
  "--manifest", mergeManifestPath,
], { cwd: root, encoding: "utf8" });
assert.strictEqual(mergeResult.status, 0, mergeResult.stderr || mergeResult.stdout);
const mergedEdges = JSON.parse(fs.readFileSync(mergeOutPath, "utf8"));
const mergeManifest = JSON.parse(fs.readFileSync(mergeManifestPath, "utf8"));
const replacedEdge = mergedEdges.find((edge) => edge.from === "amap_7af8f074" && edge.to === "amap_7df8f52d");
assert.strictEqual(replacedEdge.source, "amap", "merge replaces estimated edge with AMap edge");
assert.strictEqual(replacedEdge.taxi_minutes, 4, "merge keeps patched taxi minutes");
assert.strictEqual(mergeManifest.replaced_count, 1, "merge manifest counts replaced edge");
assert.strictEqual(mergeManifest.inserted_count, 0, "merge manifest counts inserted edge");
assert.strictEqual(mergeManifest.edge_count, 2, "merge preserves total edge count");

const promoteDataDir = path.join(outDir, "promote-data");
const promoteRoutesDir = path.join(outDir, "promote-routes");
const promoteStageDir = path.join(outDir, "promote-stage");
fs.mkdirSync(path.join(promoteDataDir, "chromadb"), { recursive: true });
for (const city of ["citya", "cityb"]) {
  fs.mkdirSync(path.join(promoteDataDir, city), { recursive: true });
  fs.writeFileSync(path.join(promoteDataDir, city, "pois.json"), JSON.stringify([{ id: `${city}_1` }, { id: `${city}_2` }], null, 2));
  fs.writeFileSync(path.join(promoteDataDir, city, "edges.json"), JSON.stringify([
    {
      from: `${city}_1`,
      to: `${city}_2`,
      distance_meters: 900,
      taxi_minutes: 12,
      source: "geo_estimated",
      provider: "geo_estimated",
    },
  ], null, 2));
  fs.mkdirSync(path.join(promoteRoutesDir, `amap-${city}-routes-v2`), { recursive: true });
  fs.writeFileSync(path.join(promoteRoutesDir, `amap-${city}-routes-v2`, "edges.json"), JSON.stringify([
    {
      from: `${city}_1`,
      to: `${city}_2`,
      distance_meters: 2100,
      taxi_minutes: 4,
      source: "amap",
      provider: "amap",
    },
    {
      from: `${city}_2`,
      to: `${city}_new`,
      distance_meters: 1000,
      taxi_minutes: 3,
      source: "amap",
      provider: "amap",
    },
  ], null, 2));
}
const promoteDryManifest = path.join(outDir, "promote-dry-run.json");
const promoteDryRun = spawnSync(process.execPath, [
  "scripts/promote_route_edges.js",
  "--data-dir", promoteDataDir,
  "--routes-dir", promoteRoutesDir,
  "--out-dir", promoteStageDir,
  "--cities", "citya,cityb",
  "--manifest", promoteDryManifest,
  "--dry-run",
], { cwd: root, encoding: "utf8" });
assert.strictEqual(promoteDryRun.status, 0, promoteDryRun.stderr || promoteDryRun.stdout);
assert.ok(fs.existsSync(promoteDryManifest), "route promotion dry-run writes aggregate manifest");
assert.ok(!fs.existsSync(path.join(promoteStageDir, "citya", "edges.json")), "route promotion dry-run does not write staged edges");

const promoteManifestPath = path.join(outDir, "promote-manifest.json");
const promoteRun = spawnSync(process.execPath, [
  "scripts/promote_route_edges.js",
  "--data-dir", promoteDataDir,
  "--routes-dir", promoteRoutesDir,
  "--out-dir", promoteStageDir,
  "--cities", "citya,cityb",
  "--manifest", promoteManifestPath,
], { cwd: root, encoding: "utf8" });
assert.strictEqual(promoteRun.status, 0, promoteRun.stderr || promoteRun.stdout);
const promoteManifest = JSON.parse(fs.readFileSync(promoteManifestPath, "utf8"));
const cityaPromotedEdges = JSON.parse(fs.readFileSync(path.join(promoteStageDir, "citya", "edges.json"), "utf8"));
assert.strictEqual(promoteManifest.city_count, 2, "route promotion manifest counts cities");
assert.strictEqual(promoteManifest.total_replaced, 2, "route promotion aggregates replaced edges");
assert.strictEqual(promoteManifest.total_inserted, 2, "route promotion aggregates inserted edges");
assert.strictEqual(promoteManifest.total_amap_edges, 4, "route promotion aggregates AMap edges");
assert.strictEqual(cityaPromotedEdges.length, 2, "route promotion writes merged city edges");
assert.strictEqual(cityaPromotedEdges.find((edge) => edge.to === "citya_2").taxi_minutes, 4, "route promotion applies refreshed AMap taxi minutes");
assert.ok(fs.existsSync(path.join(promoteStageDir, "citya", "pois.json")), "route promotion copies city POIs into staging data dir");

const promoteDefaultManifestPath = path.join(outDir, "promote-default-manifest.json");
const promoteDefaultRun = spawnSync(process.execPath, [
  "scripts/promote_route_edges.js",
  "--data-dir", promoteDataDir,
  "--routes-dir", promoteRoutesDir,
  "--out-dir", path.join(outDir, "promote-default-stage"),
  "--manifest", promoteDefaultManifestPath,
  "--dry-run",
], { cwd: root, encoding: "utf8" });
assert.strictEqual(promoteDefaultRun.status, 0, promoteDefaultRun.stderr || promoteDefaultRun.stdout);
const promoteDefaultManifest = JSON.parse(fs.readFileSync(promoteDefaultManifestPath, "utf8"));
assert.deepStrictEqual(promoteDefaultManifest.cities.map((city) => city.city), ["citya", "cityb"], "route promotion default city discovery ignores non-city data dirs");

const auditDataDir = path.join(outDir, "audit-data");
fs.mkdirSync(path.join(auditDataDir, "cityok"), { recursive: true });
fs.writeFileSync(path.join(auditDataDir, "cityok", "edges.json"), JSON.stringify([
  { from: "a", to: "b", taxi_minutes: 4, distance_meters: 1200, source: "amap", provider: "amap" },
], null, 2));
fs.mkdirSync(path.join(auditDataDir, "citybad"), { recursive: true });
fs.writeFileSync(path.join(auditDataDir, "citybad", "edges.json"), JSON.stringify([
  { from: "a", to: "b", taxi_minutes: 90, distance_meters: 45000, source: "amap", provider: "amap" },
  { from: "b", to: "c", taxi_minutes: 12, distance_meters: 5000, source: "geo_estimated", provider: "geo_estimated" },
], null, 2));
const auditPassReport = path.join(outDir, "audit-pass.json");
const auditPass = spawnSync(process.execPath, [
  "scripts/audit_route_quality.js",
  "--data-dir", auditDataDir,
  "--cities", "cityok",
  "--min-amap-ratio", "1",
  "--max-long-edge-minutes", "60",
  "--report", auditPassReport,
], { cwd: root, encoding: "utf8" });
assert.strictEqual(auditPass.status, 0, auditPass.stderr || auditPass.stdout);
const auditPassJson = JSON.parse(fs.readFileSync(auditPassReport, "utf8"));
assert.strictEqual(auditPassJson.cities[0].amap_ratio, 1, "route audit reports AMap ratio");

const auditFailReport = path.join(outDir, "audit-fail.json");
const auditFail = spawnSync(process.execPath, [
  "scripts/audit_route_quality.js",
  "--data-dir", auditDataDir,
  "--cities", "citybad",
  "--min-amap-ratio", "0.8",
  "--max-long-edge-minutes", "60",
  "--report", auditFailReport,
], { cwd: root, encoding: "utf8" });
assert.notStrictEqual(auditFail.status, 0, "route audit fails below AMap ratio or above long-edge threshold");
const auditFailJson = JSON.parse(fs.readFileSync(auditFailReport, "utf8"));
assert.strictEqual(auditFailJson.cities[0].estimated_edges, 1, "route audit counts estimated edges");
assert.strictEqual(auditFailJson.cities[0].long_edges.length, 1, "route audit lists long edges");
assert.ok(auditFailJson.failures.some((failure) => failure.reason === "amap_ratio_below_threshold"), "route audit reports AMap ratio failure");
assert.ok(auditFailJson.failures.some((failure) => failure.reason === "long_edge_above_threshold"), "route audit reports long-edge failure");

const { parseArgs: parseSmokeArgs, amapRatioFromManifest } = require("../scripts/real_data_smoke");
const smokeArgs = parseSmokeArgs(["node", "scripts/real_data_smoke.js", "http://127.0.0.1:9999", "--expected-pois", "6", "--min-amap-ratio", "0.5", "--require-all-pairs"]);
assert.strictEqual(smokeArgs.baseUrl, "http://127.0.0.1:9999", "real data smoke accepts positional base URL");
assert.strictEqual(smokeArgs.expectedPois, 6, "real data smoke parses expected POIs");
assert.strictEqual(smokeArgs.requireAllPairs, true, "real data smoke parses all_pairs gate");
assert.strictEqual(amapRatioFromManifest({ edge_count: 10, source_counts: { amap: 8, geo_estimated: 2 } }), 0.8, "real data smoke computes AMap ratio from manifest");

fs.rmSync(outDir, { recursive: true, force: true });
console.log("AMap pipeline test passed.");
