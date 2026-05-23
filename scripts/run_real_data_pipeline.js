const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const os = require("os");

function parseArgs(argv) {
  const args = {
    config: "config/amap.changsha.json",
    outDir: "output/amap-changsha",
    cacheDir: "output/amap-cache",
    searchMockDir: "",
    routeMockDir: "",
    minPois: 500,
    neighbors: 6,
    fallback: "geo_estimated",
    strictEdges: false,
    minAmapRatio: null,
    mode: "driving",
    batchSize: 100,
    sizes: "100,200,500",
    iterations: 5,
    app: "bin/tourpass.exe",
    port: 8100,
    cacheMode: "auto",
    scaleReport: "docs/scale_experiment_report.md",
    scaleJsonReport: "output/scale_experiment_report.json",
    report: "docs/real_data_pipeline_report.md",
    jsonReport: "output/real_data_pipeline_manifest.json",
    skipScale: false,
    skipFetch: false,
    skipEdges: false,
  };

  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--config") args.config = value;
    if (key === "--out-dir") args.outDir = value;
    if (key === "--cache-dir") args.cacheDir = value;
    if (key === "--search-mock-dir") args.searchMockDir = value;
    if (key === "--route-mock-dir") args.routeMockDir = value;
    if (key === "--min-pois") args.minPois = Number(value);
    if (key === "--neighbors") args.neighbors = Number(value);
    if (key === "--fallback") args.fallback = value;
    if (key === "--strict-edges") args.strictEdges = true;
    if (key === "--min-amap-ratio") args.minAmapRatio = Number(value);
    if (key === "--mode") args.mode = value;
    if (key === "--batch-size") args.batchSize = Number(value);
    if (key === "--sizes") args.sizes = value;
    if (key === "--iterations") args.iterations = Number(value);
    if (key === "--app") args.app = value;
    if (key === "--port") args.port = Number(value);
    if (key === "--cache-mode") args.cacheMode = value;
    if (key === "--scale-report") args.scaleReport = value;
    if (key === "--scale-json-report") args.scaleJsonReport = value;
    if (key === "--report") args.report = value;
    if (key === "--json-report") args.jsonReport = value;
    if (key === "--skip-scale") args.skipScale = true;
    if (key === "--skip-fetch") args.skipFetch = true;
    if (key === "--skip-edges") args.skipEdges = true;
    if (key.startsWith("--") && !["--strict-edges", "--skip-scale", "--skip-fetch", "--skip-edges"].includes(key)) i += 1;
  }

  args.minPois = Math.max(1, Math.floor(Number.isFinite(args.minPois) ? args.minPois : 500));
  args.neighbors = Math.max(1, Math.floor(Number.isFinite(args.neighbors) ? args.neighbors : 6));
  args.iterations = Math.max(1, Math.floor(Number.isFinite(args.iterations) ? args.iterations : 5));
  args.batchSize = Math.max(1, Math.floor(Number.isFinite(args.batchSize) ? args.batchSize : 100));
  args.port = Math.max(1, Math.floor(Number.isFinite(args.port) ? args.port : 8100));
  if (args.strictEdges) {
    args.fallback = "fail";
    if (args.minAmapRatio === null) args.minAmapRatio = 0.8;
  }
  if (args.minAmapRatio === null) args.minAmapRatio = 0.7;
  if (!["geo_estimated", "fail"].includes(args.fallback)) throw new Error("--fallback must be geo_estimated or fail");
  if (!["driving", "walking", "mixed"].includes(args.mode)) throw new Error("--mode must be driving, walking, or mixed");
  if (!["auto", "all_pairs", "on_demand", "disabled"].includes(args.cacheMode)) {
    throw new Error("--cache-mode must be auto, all_pairs, on_demand, or disabled");
  }
  args.minAmapRatio = Math.max(0, Math.min(1, args.minAmapRatio));
  return args;
}

function readJson(filePath, fallback = null) {
  if (!fs.existsSync(filePath)) return fallback;
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function ensureParent(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function runStep(name, command, args, options = {}) {
  const started = Date.now();
  console.log(`\n== ${name}`);
  console.log([command, ...args].join(" "));
  const result = spawnSync(command, args, {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: options.capture ? "pipe" : "inherit",
    env: { ...process.env, ...(options.env || {}) },
  });
  const elapsedMs = Date.now() - started;
  const step = {
    name,
    command: [command, ...args],
    status: result.status,
    elapsed_ms: elapsedMs,
  };
  if (options.capture) {
    step.stdout = result.stdout || "";
    step.stderr = result.stderr || "";
  }
  if (result.status !== 0) {
    const output = `${result.stderr || ""}${result.stdout || ""}`.trim();
    throw Object.assign(new Error(`${name} failed${output ? `: ${output.slice(0, 600)}` : ""}`), { step });
  }
  return step;
}

function sourceSummary(edgesManifest) {
  const counts = edgesManifest?.source_counts || {};
  const total = Number(edgesManifest?.edge_count || 0);
  const amap = Number(counts.amap || 0);
  const geo = Number(counts.geo_estimated || 0);
  return { total, amap, geo, amapRatio: total > 0 ? amap / total : 0 };
}

function environmentSnapshot() {
  return {
    platform: `${process.platform}-${process.arch}`,
    node: process.version,
    cpu: os.cpus()[0]?.model || "unknown",
  };
}

function writeReport(filePath, manifest) {
  ensureParent(filePath);
  const poi = manifest.poi_manifest || {};
  const edge = manifest.edge_manifest || {};
  const source = sourceSummary(edge);
  const lines = [
    "# Tour Pass Real Data Pipeline Report",
    "",
    "这份报告记录本地真实数据流水线的聚合结果。仓库不提交 API key、原始高德响应或完整真实 POI/edge 产物。",
    "",
    "## Summary",
    "",
    `- Generated at: ${manifest.generated_at}`,
    `- Output dir: \`${manifest.out_dir}\``,
    `- POIs: ${poi.poi_count ?? "unknown"} (min gate: ${manifest.args.minPois})`,
    `- Edges: ${source.total}`,
    `- AMap edges: ${source.amap} (${(source.amapRatio * 100).toFixed(1)}%)`,
    `- geo_estimated edges: ${source.geo}`,
    `- Edge fallback: \`${manifest.args.fallback}\``,
    `- Edge mode: \`${manifest.args.mode}\``,
    `- Scale experiment: ${manifest.args.skipScale ? "skipped" : `\`${manifest.args.sizes}\`, iterations=${manifest.args.iterations}`}`,
    "",
    "## POI Coverage",
    "",
    `- Type counts: ${Object.entries(poi.type_counts || {}).map(([key, value]) => `${key}=${value}`).join(", ") || "unknown"}`,
    `- Area coverage: ${Object.keys(poi.area_counts || {}).length || "unknown"}`,
    `- Duplicates skipped: ${poi.duplicate_count ?? "unknown"}`,
    `- Failed pages: ${poi.failed_pages ?? "unknown"}`,
    "",
    "## Steps",
    "",
    "| Step | Status | Time |",
    "| --- | ---: | ---: |",
    ...manifest.steps.map((step) => `| ${step.name} | ${step.status} | ${step.elapsed_ms} ms |`),
    "",
    "## Boundary",
    "",
    "- 这是一条本地可复现的数据与性能证据链，不等同于线上生产压测。",
    "- 若存在 `geo_estimated` 边，必须在简历和答辩中披露比例，不能声称通勤时间 100% 来自真实路网。",
    "- `output/` 下的真实数据产物默认不进入仓库；报告只记录聚合指标。",
    "",
  ];
  fs.writeFileSync(filePath, lines.join("\n"), "utf8");
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.searchMockDir && !args.skipFetch && !process.env.AMAP_API_KEY) {
    throw new Error("missing AMAP_API_KEY; use --search-mock-dir for offline tests");
  }

  const steps = [];
  const poisPath = path.join(args.outDir, "pois.json");
  const edgesPath = path.join(args.outDir, "edges.json");
  const poiManifestPath = path.join(args.outDir, "manifest.json");
  const edgeManifestPath = path.join(args.outDir, "edges_manifest.json");

  if (!args.skipFetch) {
    const cmd = [
      "scripts/fetch_amap_pois.js",
      "--config", args.config,
      "--out-dir", args.outDir,
      "--cache-dir", args.cacheDir,
      "--min-pois", String(args.minPois),
    ];
    if (args.searchMockDir) cmd.push("--mock-dir", args.searchMockDir);
    steps.push(runStep("fetch pois", process.execPath, cmd));
  }

  if (!args.skipEdges) {
    const cmd = [
      "scripts/build_commute_edges.js",
      "--pois", poisPath,
      "--out-dir", args.outDir,
      "--cache-dir", args.cacheDir,
      "--neighbors", String(args.neighbors),
      "--fallback", args.fallback,
      "--min-amap-ratio", String(args.minAmapRatio),
      "--mode", args.mode,
      "--batch-size", String(args.batchSize),
    ];
    if (args.routeMockDir) cmd.push("--mock-dir", args.routeMockDir);
    steps.push(runStep("build commute edges", process.execPath, cmd));
  }

  steps.push(runStep("validate data", process.execPath, [
    "scripts/validate_data.js",
    "--pois", poisPath,
    "--edges", edgesPath,
    "--min-pois", String(args.minPois),
    "--require-edge-source",
  ]));

  if (!args.skipScale) {
    steps.push(runStep("scale experiment", process.execPath, [
      "scripts/scale_experiment.js",
      "--app", args.app,
      "--port", String(args.port),
      "--dataset", "real",
      "--pois", poisPath,
      "--edges", edgesPath,
      "--sizes", args.sizes,
      "--iterations", String(args.iterations),
      "--cache-mode", args.cacheMode,
      "--report", args.scaleReport,
      "--json-report", args.scaleJsonReport,
    ]));
  }

  const manifest = {
    generated_at: new Date().toISOString(),
    out_dir: args.outDir,
    args,
    environment: environmentSnapshot(),
    steps,
    poi_manifest: readJson(poiManifestPath, {}),
    edge_manifest: readJson(edgeManifestPath, {}),
    scale_report: args.skipScale ? null : readJson(args.scaleJsonReport, null),
  };
  ensureParent(args.jsonReport);
  fs.writeFileSync(args.jsonReport, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  writeReport(args.report, manifest);
  console.log(`\nReal data pipeline report written to ${args.report}`);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    if (error.step) console.error(`failed step: ${error.step.name}`);
    process.exit(1);
  });
}

module.exports = { parseArgs, runStep, sourceSummary, writeReport };
