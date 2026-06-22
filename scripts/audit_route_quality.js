const fs = require("fs");
const path = require("path");

function usage() {
  console.log(`Usage: node scripts/audit_route_quality.js --data-dir <path> [options]

Audit route edge quality for city data directories.

Options:
  --data-dir <path>             Data directory containing city/edges.json files (required)
  --cities <list>               Comma-separated city dirs; default: all dirs with edges.json
  --min-amap-ratio <n>          Fail if a city's AMap ratio is below n (default: 0)
  --max-long-edge-minutes <n>   Fail if any edge duration is above n minutes (default: disabled)
  --top <n>                     Number of worst edges to include per city (default: 10)
  --report <path>               JSON report path (default: output/route_quality_audit.json)
  --help, -h                    Show this help message`);
}

function parseArgs(argv) {
  const args = {
    dataDir: "",
    cities: [],
    minAmapRatio: 0,
    maxLongEdgeMinutes: 0,
    top: 10,
    report: path.join("output", "route_quality_audit.json"),
    help: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--help" || key === "-h") args.help = true;
    if (key === "--data-dir") args.dataDir = value;
    if (key === "--cities") args.cities = String(value || "").split(",").map((city) => city.trim()).filter(Boolean);
    if (key === "--min-amap-ratio") args.minAmapRatio = Number(value);
    if (key === "--max-long-edge-minutes") args.maxLongEdgeMinutes = Number(value);
    if (key === "--top") args.top = Number(value);
    if (key === "--report") args.report = value;
    if (key.startsWith("--") && !["--help", "-h"].includes(key)) i += 1;
  }
  if (args.help) return args;
  if (!args.dataDir) throw new Error("missing --data-dir");
  args.minAmapRatio = Number.isFinite(args.minAmapRatio) ? Math.max(0, Math.min(1, args.minAmapRatio)) : 0;
  args.maxLongEdgeMinutes = Number.isFinite(args.maxLongEdgeMinutes) ? Math.max(0, args.maxLongEdgeMinutes) : 0;
  args.top = Number.isFinite(args.top) ? Math.max(1, Math.floor(args.top)) : 10;
  return args;
}

function listCities(dataDir) {
  return fs.readdirSync(dataDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .filter((entry) => fs.existsSync(path.join(dataDir, entry.name, "edges.json")))
    .map((entry) => entry.name)
    .sort();
}

function readEdges(dataDir, city) {
  const filePath = path.join(dataDir, city, "edges.json");
  const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (!Array.isArray(value)) throw new Error(`${filePath} must be a JSON array`);
  return value;
}

function isAmap(edge) {
  return String(edge.provider || edge.source || "").toLowerCase() === "amap";
}

function edgeMinutes(edge) {
  for (const field of ["taxi_minutes", "duration_minutes", "transit_minutes", "walk_minutes"]) {
    const value = edge[field];
    if (typeof value === "number" && value > 0) return value;
  }
  const seconds = edge.duration_seconds;
  if (typeof seconds === "number" && seconds > 0) return Math.max(1, Math.round(seconds / 60));
  return 0;
}

function edgeSummary(edge) {
  return {
    from: edge.from || edge.source || "",
    to: edge.to || edge.target || "",
    minutes: edgeMinutes(edge),
    distance_meters: edge.distance_meters || edge.distance_m || 0,
    source: edge.source || "",
    provider: edge.provider || "",
  };
}

function auditCity(dataDir, city, options) {
  const edges = readEdges(dataDir, city);
  const amapEdges = edges.filter(isAmap).length;
  const estimatedEdges = edges.length - amapEdges;
  const sortedByMinutes = edges
    .map(edgeSummary)
    .sort((left, right) => right.minutes - left.minutes);
  const longEdges = options.maxLongEdgeMinutes > 0
    ? sortedByMinutes.filter((edge) => edge.minutes > options.maxLongEdgeMinutes).slice(0, options.top)
    : [];

  return {
    city,
    edge_count: edges.length,
    amap_edges: amapEdges,
    estimated_edges: estimatedEdges,
    amap_ratio: edges.length > 0 ? amapEdges / edges.length : 0,
    worst_edges: sortedByMinutes.slice(0, options.top),
    long_edges: longEdges,
  };
}

function auditRoutes(args) {
  const cities = args.cities.length > 0 ? args.cities : listCities(args.dataDir);
  const cityReports = cities.map((city) => auditCity(args.dataDir, city, args));
  const failures = [];

  for (const report of cityReports) {
    if (report.amap_ratio < args.minAmapRatio) {
      failures.push({
        city: report.city,
        reason: "amap_ratio_below_threshold",
        actual: report.amap_ratio,
        expected: args.minAmapRatio,
      });
    }
    if (args.maxLongEdgeMinutes > 0 && report.long_edges.length > 0) {
      failures.push({
        city: report.city,
        reason: "long_edge_above_threshold",
        actual: report.long_edges[0].minutes,
        expected: args.maxLongEdgeMinutes,
      });
    }
  }

  return {
    generated_at: new Date().toISOString(),
    data_dir: args.dataDir,
    city_count: cityReports.length,
    total_edges: cityReports.reduce((sum, city) => sum + city.edge_count, 0),
    total_amap_edges: cityReports.reduce((sum, city) => sum + city.amap_edges, 0),
    total_estimated_edges: cityReports.reduce((sum, city) => sum + city.estimated_edges, 0),
    min_amap_ratio: cityReports.length > 0 ? Math.min(...cityReports.map((city) => city.amap_ratio)) : 0,
    max_amap_ratio: cityReports.length > 0 ? Math.max(...cityReports.map((city) => city.amap_ratio)) : 0,
    failed: failures.length > 0,
    failures,
    cities: cityReports,
  };
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    usage();
    return;
  }
  const report = auditRoutes(args);
  writeJson(args.report, report);
  console.log(`Route quality audit: ${report.city_count} cities, ${report.total_edges} edges, min_amap_ratio=${report.min_amap_ratio.toFixed(4)}`);
  if (report.failed) process.exit(1);
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}

module.exports = {
  auditCity,
  auditRoutes,
  edgeMinutes,
  listCities,
  parseArgs,
};
