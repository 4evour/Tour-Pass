const fs = require("fs");
const path = require("path");
const {
  fetchAmapRouteMetrics,
} = require("./build_commute_edges");

function usage() {
  console.log(`Usage: node scripts/fetch_real_route_pairs.js --pois <path> --pairs <path> --out <path> [options]

Fetch real AMap route metrics for explicit planning-critical POI pairs.

Options:
  --pois <path>        POI JSON array (required)
  --pairs <path>       Pair JSON array, e.g. [{"from":"poi_id","to":"poi_id"}] (required)
  --out <path>         Output edges patch JSON path (required)
  --manifest <path>    Output manifest path (default: <out>.manifest.json)
  --cache-dir <path>   API cache directory (default: output/amap-route-pairs-cache)
  --mock-dir <path>    Use mock AMap route responses for tests
  --mode <mode>        driving, walking, or mixed (default: mixed)
  --require-all        Fail if any pair cannot be fetched
  --help, -h           Show this help message`);
}

function parseArgs(argv) {
  const args = {
    pois: "",
    pairs: "",
    out: "",
    manifest: "",
    cacheDir: "output/amap-route-pairs-cache",
    mockDir: "",
    mode: "mixed",
    requireAll: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--help" || key === "-h") {
      args.help = true;
      continue;
    }
    if (key === "--pois") args.pois = value;
    if (key === "--pairs") args.pairs = value;
    if (key === "--out") args.out = value;
    if (key === "--manifest") args.manifest = value;
    if (key === "--cache-dir") args.cacheDir = value;
    if (key === "--mock-dir") args.mockDir = value;
    if (key === "--mode") args.mode = value;
    if (key === "--require-all") args.requireAll = true;
    if (key.startsWith("--") && key !== "--require-all" && key !== "--help" && key !== "-h") i += 1;
  }
  if (args.help) return args;
  if (!args.pois) throw new Error("missing --pois");
  if (!args.pairs) throw new Error("missing --pairs");
  if (!args.out) throw new Error("missing --out");
  if (!["driving", "walking", "mixed"].includes(args.mode)) {
    throw new Error("--mode must be driving, walking, or mixed");
  }
  if (!args.manifest) args.manifest = `${args.out.replace(/\.json$/i, "")}.manifest.json`;
  return args;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function haversineMeters(a, b) {
  const radius = 6371000;
  const toRad = (n) => (n * Math.PI) / 180;
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const x = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return Math.max(1, Math.round(radius * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x))));
}

function resolvePoi(ref, poiById, pois) {
  if (!ref) return null;
  if (poiById.has(ref)) return poiById.get(ref);
  const exact = pois.find((poi) => poi.name === ref);
  if (exact) return exact;
  return pois.find((poi) => (poi.name || "").includes(ref)) || null;
}

function normalizePair(pair) {
  if (Array.isArray(pair)) return { from: pair[0], to: pair[1] };
  return {
    from: pair.from || pair.from_id || pair.from_poi_id || pair.from_name,
    to: pair.to || pair.to_id || pair.to_poi_id || pair.to_name,
  };
}

function minutes(metrics) {
  return metrics ? Math.max(1, Math.round(metrics.durationSeconds / 60)) : 0;
}

async function buildRoutePairEdges(pois, pairs, options) {
  const apiKey = process.env.AMAP_API_KEY;
  const canUseAmap = Boolean(options.mockDir || apiKey);
  if (!canUseAmap) throw new Error("missing AMAP_API_KEY; use --mock-dir for offline tests");

  const poiById = new Map(pois.map((poi) => [poi.id, poi]));
  const edges = [];
  const failures = [];

  for (const rawPair of pairs) {
    const pair = normalizePair(rawPair);
    const from = resolvePoi(pair.from, poiById, pois);
    const to = resolvePoi(pair.to, poiById, pois);
    if (!from || !to) {
      failures.push({ from: pair.from, to: pair.to, reason: "poi_not_found" });
      continue;
    }

    const driveMetrics = options.mode === "driving" || options.mode === "mixed"
      ? await fetchAmapRouteMetrics({
        from,
        to,
        mode: "drive",
        apiKey,
        mockDir: options.mockDir,
        cacheDir: options.cacheDir,
      })
      : null;
    const walkMetrics = options.mode === "walking" || options.mode === "mixed"
      ? await fetchAmapRouteMetrics({
        from,
        to,
        mode: "walk",
        apiKey,
        mockDir: options.mockDir,
        cacheDir: options.cacheDir,
      })
      : null;

    if (!driveMetrics && !walkMetrics) {
      failures.push({ from: from.id, to: to.id, from_name: from.name, to_name: to.name, reason: "amap_no_route" });
      continue;
    }

    const taxiMinutes = minutes(driveMetrics);
    const walkMinutes = minutes(walkMetrics);
    const distanceMeters = driveMetrics?.distanceMeters
      || walkMetrics?.distanceMeters
      || haversineMeters(from, to);
    const primarySeconds = driveMetrics?.durationSeconds || walkMetrics?.durationSeconds;

    edges.push({
      from: from.id,
      to: to.id,
      from_name: from.name,
      to_name: to.name,
      distance_meters: distanceMeters,
      walk_minutes: walkMinutes || Math.max(5, Math.round((distanceMeters / 1000) * 12)),
      transit_minutes: taxiMinutes ? Math.max(8, Math.round(taxiMinutes * 1.8)) : Math.max(8, Math.round((walkMinutes || 0) * 0.45)),
      taxi_minutes: taxiMinutes || Math.max(5, Math.round((distanceMeters / 1000) * 2.8)),
      source: "amap",
      provider: "amap",
      mode: options.mode,
      duration_seconds: primarySeconds,
      route_confidence: "real",
      amap_status: driveMetrics && walkMetrics ? "ok" : "partial",
    });
  }

  const manifest = {
    generated_at: new Date().toISOString(),
    source: options.mockDir ? "mock" : "amap",
    mode: options.mode,
    pair_count: pairs.length,
    success_count: edges.length,
    failure_count: failures.length,
    failures,
  };

  return { edges, manifest };
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    usage();
    return;
  }
  const pois = readJson(args.pois);
  const pairs = readJson(args.pairs);
  if (!Array.isArray(pois)) throw new Error("--pois must point to a JSON array");
  if (!Array.isArray(pairs)) throw new Error("--pairs must point to a JSON array");
  const { edges, manifest } = await buildRoutePairEdges(pois, pairs, args);
  if (args.requireAll && manifest.failure_count > 0) {
    throw new Error(`route pair fetch failed for ${manifest.failure_count}/${manifest.pair_count} pairs`);
  }
  writeJson(args.out, edges);
  writeJson(args.manifest, manifest);
  console.log(`Route pair edges written: ${manifest.success_count}/${manifest.pair_count} -> ${args.out}`);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}

module.exports = {
  buildRoutePairEdges,
  normalizePair,
  parseArgs,
};
