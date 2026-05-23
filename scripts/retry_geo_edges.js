const fs = require("fs");
const path = require("path");
const {
  fetchAmapDrivingDistanceBatch,
  fetchAmapRouteMetrics,
  pairKey,
} = require("./build_commute_edges");

function parseArgs(argv) {
  const args = {
    pois: "output/amap-changsha/pois.json",
    edges: "output/amap-changsha/edges.json",
    outDir: "output/amap-changsha-retry",
    cacheDir: "output/amap-cache-retry",
    mockDir: "",
    mode: "driving",
    batchSize: 100,
    minAmapRatio: 0,
    overwrite: false,
    report: "",
    jsonReport: "",
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--pois") args.pois = value;
    if (key === "--edges") args.edges = value;
    if (key === "--out-dir") args.outDir = value;
    if (key === "--cache-dir") args.cacheDir = value;
    if (key === "--mock-dir") args.mockDir = value;
    if (key === "--mode") args.mode = value;
    if (key === "--batch-size") args.batchSize = Number(value);
    if (key === "--min-amap-ratio") args.minAmapRatio = Number(value);
    if (key === "--overwrite") args.overwrite = true;
    if (key === "--report") args.report = value;
    if (key === "--json-report") args.jsonReport = value;
    if (key.startsWith("--") && key !== "--overwrite") i += 1;
  }
  if (!["driving", "walking", "mixed"].includes(args.mode)) throw new Error("--mode must be driving, walking, or mixed");
  args.batchSize = Math.max(1, Math.min(100, Math.floor(Number.isFinite(args.batchSize) ? args.batchSize : 100)));
  args.minAmapRatio = Math.max(0, Math.min(1, Number.isFinite(args.minAmapRatio) ? args.minAmapRatio : 0));
  if (!args.report) args.report = path.join(args.outDir, "geo_estimated_edges_report.md");
  if (!args.jsonReport) args.jsonReport = path.join(args.outDir, "geo_estimated_edges_report.json");
  return args;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function sourceCounts(edges) {
  return edges.reduce((acc, edge) => {
    const source = edge.source || "unknown";
    acc[source] = (acc[source] || 0) + 1;
    return acc;
  }, {});
}

function ratioFromCounts(counts, total) {
  return total > 0 ? (counts.amap || 0) / total : 0;
}

function toPair(edge, poiById) {
  const from = poiById.get(edge.from);
  const to = poiById.get(edge.to);
  if (!from || !to) return null;
  return { from, to, edge };
}

function applyMetrics(edge, metrics, mode, status = "retry_ok") {
  const minutes = Math.max(1, Math.round(metrics.durationSeconds / 60));
  const next = { ...edge };
  next.source = "amap";
  next.provider = "amap";
  next.mode = mode;
  next.duration_seconds = metrics.durationSeconds;
  next.distance_meters = metrics.distanceMeters || edge.distance_meters;
  next.amap_status = status;
  if (mode === "walking") {
    next.walk_minutes = minutes;
    next.transit_minutes = Math.max(5, Math.round((minutes + (edge.taxi_minutes || minutes)) / 2));
  } else {
    next.taxi_minutes = minutes;
    next.transit_minutes = Math.max(5, Math.round(((edge.walk_minutes || minutes) + minutes) / 2));
  }
  return next;
}

async function retryEdges(pois, edges, options) {
  const apiKey = process.env.AMAP_API_KEY;
  const canUseAmap = Boolean(options.mockDir || apiKey);
  if (!canUseAmap) {
    throw new Error("missing AMAP_API_KEY; use --mock-dir for offline tests");
  }

  const poiById = new Map(pois.map((poi) => [poi.id, poi]));
  const retryPairs = edges
    .filter((edge) => edge.source === "geo_estimated")
    .map((edge) => toPair(edge, poiById))
    .filter(Boolean);

  const updatedByKey = new Map();
  const failures = [];

  if (!options.mockDir && (options.mode === "driving" || options.mode === "mixed")) {
    const drivingMetrics = await fetchAmapDrivingDistanceBatch({
      pairs: retryPairs,
      apiKey,
      cacheDir: options.cacheDir,
      batchSize: options.batchSize,
    });
    for (const pair of retryPairs) {
      const metrics = drivingMetrics.get(pairKey(pair.from, pair.to));
      if (metrics) {
        updatedByKey.set(pairKey(pair.from, pair.to), applyMetrics(pair.edge, metrics, "driving", "retry_distance_ok"));
      }
    }
  }

  for (const pair of retryPairs) {
    const key = pairKey(pair.from, pair.to);
    if (updatedByKey.has(key)) continue;
    let metrics = null;
    if (options.mode === "walking" || options.mode === "mixed") {
      metrics = await fetchAmapRouteMetrics({
        from: pair.from,
        to: pair.to,
        mode: "walk",
        apiKey,
        mockDir: options.mockDir,
        cacheDir: options.cacheDir,
      });
      if (metrics) {
        updatedByKey.set(key, applyMetrics(pair.edge, metrics, "walking", "retry_route_ok"));
        continue;
      }
    }
    if (options.mode === "driving" || options.mode === "mixed") {
      metrics = await fetchAmapRouteMetrics({
        from: pair.from,
        to: pair.to,
        mode: "drive",
        apiKey,
        mockDir: options.mockDir,
        cacheDir: options.cacheDir,
      });
      if (metrics) {
        updatedByKey.set(key, applyMetrics(pair.edge, metrics, "driving", "retry_route_ok"));
        continue;
      }
    }
    failures.push({
      from: pair.edge.from,
      to: pair.edge.to,
      from_name: pair.from.name,
      to_name: pair.to.name,
      reason: "amap_retry_no_route",
    });
  }

  const updatedEdges = edges.map((edge) => {
    if (edge.source !== "geo_estimated") return edge;
    const from = poiById.get(edge.from);
    const to = poiById.get(edge.to);
    if (!from || !to) return edge;
    return updatedByKey.get(pairKey(from, to)) || edge;
  });

  const beforeCounts = sourceCounts(edges);
  const afterCounts = sourceCounts(updatedEdges);
  const manifest = {
    generated_at: new Date().toISOString(),
    input_edges: options.edges,
    edge_count: edges.length,
    retry_candidates: retryPairs.length,
    retried_success: updatedByKey.size,
    still_geo_estimated: afterCounts.geo_estimated || 0,
    before_source_counts: beforeCounts,
    after_source_counts: afterCounts,
    before_amap_ratio: ratioFromCounts(beforeCounts, edges.length),
    after_amap_ratio: ratioFromCounts(afterCounts, updatedEdges.length),
    mode: options.mode,
    min_amap_ratio: options.minAmapRatio,
    failures: failures.slice(0, 25),
  };
  return { updatedEdges, manifest };
}

function writeReport(filePath, manifest) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const lines = [
    "# geo_estimated Edge Retry Report",
    "",
    "该报告只记录聚合指标和少量失败样例，用于说明估算边是否已被高德通勤结果替换。",
    "",
    `- Generated at: ${manifest.generated_at}`,
    `- Input edges: \`${manifest.input_edges}\``,
    `- Edge count: ${manifest.edge_count}`,
    `- Retry candidates: ${manifest.retry_candidates}`,
    `- Retry success: ${manifest.retried_success}`,
    `- Still geo_estimated: ${manifest.still_geo_estimated}`,
    `- AMap ratio before: ${(manifest.before_amap_ratio * 100).toFixed(1)}%`,
    `- AMap ratio after: ${(manifest.after_amap_ratio * 100).toFixed(1)}%`,
    `- Mode: \`${manifest.mode}\``,
    "",
    "## Source Counts",
    "",
    "| Stage | amap | geo_estimated | unknown |",
    "| --- | ---: | ---: | ---: |",
    `| Before | ${manifest.before_source_counts.amap || 0} | ${manifest.before_source_counts.geo_estimated || 0} | ${manifest.before_source_counts.unknown || 0} |`,
    `| After | ${manifest.after_source_counts.amap || 0} | ${manifest.after_source_counts.geo_estimated || 0} | ${manifest.after_source_counts.unknown || 0} |`,
    "",
  ];
  if (manifest.failures.length > 0) {
    lines.push("## Failure Samples", "");
    lines.push("| From | To | Reason |");
    lines.push("| --- | --- | --- |");
    for (const failure of manifest.failures) {
      lines.push(`| ${failure.from_name || failure.from} | ${failure.to_name || failure.to} | ${failure.reason} |`);
    }
    lines.push("");
  }
  fs.writeFileSync(filePath, lines.join("\n"), "utf8");
}

async function main() {
  const args = parseArgs(process.argv);
  const pois = readJson(args.pois);
  const edges = readJson(args.edges);
  if (!Array.isArray(pois)) throw new Error("--pois must point to a JSON array");
  if (!Array.isArray(edges)) throw new Error("--edges must point to a JSON array");
  const { updatedEdges, manifest } = await retryEdges(pois, edges, args);
  if (args.minAmapRatio > 0 && manifest.after_amap_ratio < args.minAmapRatio) {
    throw new Error(`min-amap-ratio gate failed after retry: got ${manifest.after_amap_ratio.toFixed(3)}, expected at least ${args.minAmapRatio}`);
  }
  const targetEdgesPath = args.overwrite ? args.edges : path.join(args.outDir, "edges.json");
  writeJson(targetEdgesPath, updatedEdges);
  writeJson(path.join(args.outDir, "edges_manifest.json"), {
    generated_at: manifest.generated_at,
    edge_count: updatedEdges.length,
    source_counts: manifest.after_source_counts,
    amap_ratio: manifest.after_amap_ratio,
    retry_source: args.edges,
  });
  writeJson(args.jsonReport, manifest);
  writeReport(args.report, manifest);
  console.log(`Geo edge retry report written: ${manifest.retried_success}/${manifest.retry_candidates} converted -> ${args.report}`);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}

module.exports = { parseArgs, retryEdges, sourceCounts, writeReport };
