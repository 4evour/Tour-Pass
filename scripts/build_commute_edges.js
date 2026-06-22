const fs = require("fs");
const path = require("path");

function usage() {
  console.log(`Usage: node scripts/build_commute_edges.js --pois <path> [options]

Build commute edges between POIs using AMap routing APIs.

Options:
  --pois <path>           Path to POI JSON array (required)
  --out-dir <path>        Output directory (default: output/amap-changsha)
  --neighbors <n>         Nearest neighbors per POI (1-12, default: 6)
  --cache-dir <path>      API cache directory (default: output/amap-cache)
  --mock-dir <path>       Use mock data instead of live API
  --no-amap               Disable AMap routing, use geo estimates only
  --fallback <mode>       Fallback strategy: geo_estimated or fail (default: geo_estimated)
  --min-amap-ratio <n>    Minimum ratio of AMap-sourced edges (0-1, default: 0)
  --mode <mode>           Routing mode: driving, walking, or mixed (default: mixed)
  --batch-size <n>        Batch size for distance API (1-100, default: 100)
  --help, -h              Show this help message`);
}

function sanitizeAmapResponse(json) {
  if (!json || typeof json !== "object") return json;
  const copy = Array.isArray(json) ? [...json] : { ...json };
  delete copy.key;
  delete copy.sec_code;
  delete copy.sec_code_debug;
  return copy;
}

const AMAP_WALKING_URL = "https://restapi.amap.com/v3/direction/walking";
const AMAP_DRIVING_URL = "https://restapi.amap.com/v3/direction/driving";
const AMAP_DISTANCE_URL = "https://restapi.amap.com/v3/distance";

// Rate limiting and retry
const API_DELAY_MS = 250;
const MAX_RETRIES = 3;

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function fetchWithRetry(url, retries = MAX_RETRIES) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
      if (!response.ok) {
        if (attempt < retries) { await sleep(1000 * (attempt + 1)); continue; }
        return null;
      }
      const json = await response.json();
      // Check for QPS limit
      if (json && json.infocode === "10021") {
        const delay = 2000 * (attempt + 1);
        console.warn(`  QPS limit hit, waiting ${delay}ms (attempt ${attempt + 1}/${retries + 1})`);
        if (attempt < retries) { await sleep(delay); continue; }
        return json;
      }
      return json;
    } catch (err) {
      if (attempt < retries) { await sleep(1000 * (attempt + 1)); continue; }
      return null;
    }
  }
  return null;
}

function parseArgs(argv) {
  const args = {
    pois: "",
    outDir: "output/amap-changsha",
    neighbors: 6,
    cacheDir: "output/amap-cache",
    mockDir: "",
    useAmap: true,
    fallback: "geo_estimated",
    minAmapRatio: 0,
    mode: "mixed",
    batchSize: 100,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--pois") args.pois = value;
    if (key === "--out-dir") args.outDir = value;
    if (key === "--neighbors") args.neighbors = Number(value);
    if (key === "--cache-dir") args.cacheDir = value;
    if (key === "--mock-dir") args.mockDir = value;
    if (key === "--no-amap") args.useAmap = false;
    if (key === "--fallback") args.fallback = value;
    if (key === "--min-amap-ratio") args.minAmapRatio = Number(value);
    if (key === "--mode") args.mode = value;
    if (key === "--batch-size") args.batchSize = Number(value);
    if (key.startsWith("--") && key !== "--no-amap") i += 1;
  }
  if (!args.pois) throw new Error("missing --pois");
  args.neighbors = Math.max(1, Math.min(12, Number.isFinite(args.neighbors) ? Math.floor(args.neighbors) : 6));
  if (!["geo_estimated", "fail"].includes(args.fallback)) throw new Error("--fallback must be geo_estimated or fail");
  if (!["driving", "walking", "mixed"].includes(args.mode)) throw new Error("--mode must be driving, walking, or mixed");
  args.minAmapRatio = Math.max(0, Math.min(1, Number.isFinite(args.minAmapRatio) ? args.minAmapRatio : 0));
  args.batchSize = Math.max(1, Math.min(100, Number.isFinite(args.batchSize) ? Math.floor(args.batchSize) : 100));
  return args;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function distanceMeters(a, b) {
  const dx = (a.lat - b.lat) * 111000;
  const dy = (a.lng - b.lng) * 91000;
  return Math.round(Math.sqrt(dx * dx + dy * dy));
}

function timeForDistance(distance, multiplier) {
  return Math.max(5, Math.round((distance / 1000) * multiplier));
}

function nearestPairs(pois, neighbors) {
  const pairs = new Map();
  for (const poi of pois) {
    const nearest = pois
      .filter((other) => other.id !== poi.id)
      .map((other) => ({ other, distance: distanceMeters(poi, other) }))
      .sort((left, right) => left.distance - right.distance)
      .slice(0, neighbors);
    for (const item of nearest) {
      const key = [poi.id, item.other.id].sort().join("<->");
      if (!pairs.has(key)) pairs.set(key, { from: poi, to: item.other, distance: item.distance });
    }
  }
  return [...pairs.values()];
}

function connectedComponents(pois, pairs) {
  const adjacency = new Map(pois.map((poi) => [poi.id, []]));
  for (const pair of pairs) {
    adjacency.get(pair.from.id)?.push(pair.to.id);
    adjacency.get(pair.to.id)?.push(pair.from.id);
  }
  const byId = new Map(pois.map((poi) => [poi.id, poi]));
  const seen = new Set();
  const components = [];
  for (const poi of pois) {
    if (seen.has(poi.id)) continue;
    const ids = [];
    const stack = [poi.id];
    seen.add(poi.id);
    while (stack.length > 0) {
      const id = stack.pop();
      ids.push(id);
      for (const next of adjacency.get(id) || []) {
        if (seen.has(next)) continue;
        seen.add(next);
        stack.push(next);
      }
    }
    components.push(ids.map((id) => byId.get(id)).filter(Boolean));
  }
  return components.sort((a, b) => b.length - a.length);
}

function addBridgePairs(pois, pairs) {
  const existing = new Set(pairs.map((pair) => pairKey(pair.from, pair.to)));
  const bridged = [...pairs];
  let components = connectedComponents(pois, bridged);
  while (components.length > 1) {
    const main = components[0];
    let best = null;
    for (let c = 1; c < components.length; c += 1) {
      for (const from of main) {
        for (const to of components[c]) {
          const key = pairKey(from, to);
          if (existing.has(key)) continue;
          const distance = distanceMeters(from, to);
          if (!best || distance < best.distance) {
            best = { from, to, distance };
          }
        }
      }
    }
    if (!best) break;
    existing.add(pairKey(best.from, best.to));
    bridged.push(best);
    components = connectedComponents(pois, bridged);
  }
  return bridged;
}

function mockFileFor(mockDir, from, to, mode) {
  const key = [from.id, to.id].sort().join("_");
  return path.join(mockDir, `${mode}-${key}.json`);
}

function parseAmapDuration(json) {
  if (!json || typeof json !== "object" || String(json.status) !== "1") return null;
  const route = json.route || {};
  const paths = Array.isArray(route.paths) ? route.paths : [];
  if (paths.length === 0) return null;
  const seconds = Number(paths[0].duration);
  if (!Number.isFinite(seconds) || seconds <= 0) return null;
  return Math.max(1, Math.round(seconds / 60));
}

function parseAmapRouteMetrics(json) {
  if (!json || typeof json !== "object" || String(json.status) !== "1") return null;
  const route = json.route || {};
  const paths = Array.isArray(route.paths) ? route.paths : [];
  if (paths.length === 0) return null;
  const seconds = Number(paths[0].duration);
  const distance = Number(paths[0].distance);
  if (!Number.isFinite(seconds) || seconds <= 0) return null;
  return {
    durationSeconds: Math.max(1, Math.round(seconds)),
    distanceMeters: Number.isFinite(distance) && distance > 0 ? Math.round(distance) : null,
  };
}

function parseAmapDistanceResults(json) {
  if (!json || typeof json !== "object" || String(json.status) !== "1") return [];
  const results = Array.isArray(json.results) ? json.results : [];
  return results.map((item) => {
    const duration = Number(item.duration);
    const distance = Number(item.distance);
    if (!Number.isFinite(duration) || duration <= 0) return null;
    return {
      originId: Number(item.origin_id),
      durationSeconds: Math.max(1, Math.round(duration)),
      distanceMeters: Number.isFinite(distance) && distance > 0 ? Math.round(distance) : null,
      info: item.info || "OK",
    };
  });
}

async function fetchAmapRoute({ from, to, mode, apiKey, mockDir, cacheDir }) {
  if (mockDir) {
    const filePath = mockFileFor(mockDir, from, to, mode);
    if (!fs.existsSync(filePath)) return null;
    const metrics = parseAmapRouteMetrics(readJson(filePath));
    return metrics ? Math.max(1, Math.round(metrics.durationSeconds / 60)) : null;
  }
  const endpoint = mode === "walk" ? AMAP_WALKING_URL : AMAP_DRIVING_URL;
  const params = new URLSearchParams({
    key: apiKey,
    origin: `${from.lng},${from.lat}`,
    destination: `${to.lng},${to.lat}`,
  });
  const response = await fetch(`${endpoint}?${params.toString()}`, { signal: AbortSignal.timeout(10000) });
  if (!response.ok) return null;
  const json = await response.json();
  fs.mkdirSync(cacheDir, { recursive: true });
  fs.writeFileSync(path.join(cacheDir, `${mode}-${from.id}-${to.id}.json`), `${JSON.stringify(sanitizeAmapResponse(json), null, 2)}\n`, "utf8");
  return parseAmapDuration(json);
}

async function fetchAmapRouteMetrics({ from, to, mode, apiKey, mockDir, cacheDir }) {
  if (mockDir) {
    const filePath = mockFileFor(mockDir, from, to, mode);
    if (!fs.existsSync(filePath)) return null;
    return parseAmapRouteMetrics(readJson(filePath));
  }
  const endpoint = mode === "walk" ? AMAP_WALKING_URL : AMAP_DRIVING_URL;
  const params = new URLSearchParams({
    key: apiKey,
    origin: `${from.lng},${from.lat}`,
    destination: `${to.lng},${to.lat}`,
    output: "json",
  });
  const response = await fetch(`${endpoint}?${params.toString()}`, { signal: AbortSignal.timeout(10000) });
  if (!response.ok) return null;
  const json = await response.json();
  fs.mkdirSync(cacheDir, { recursive: true });
  fs.writeFileSync(path.join(cacheDir, `${mode}-${from.id}-${to.id}.json`), `${JSON.stringify(sanitizeAmapResponse(json), null, 2)}\n`, "utf8");
  return parseAmapRouteMetrics(json);
}

function pairKey(from, to) {
  return [from.id, to.id].sort().join("<->");
}

async function fetchAmapDrivingDistanceBatch({ pairs, apiKey, cacheDir, batchSize }) {
  const metricsByPair = new Map();
  const byDestination = new Map();
  for (const pair of pairs) {
    const items = byDestination.get(pair.to.id) || [];
    items.push(pair);
    byDestination.set(pair.to.id, items);
  }

  for (const group of byDestination.values()) {
    for (let i = 0; i < group.length; i += batchSize) {
      const batch = group.slice(i, i + batchSize);
      const destination = batch[0].to;
      const cacheFile = path.join(cacheDir, `distance-${destination.id}-${i}.json`);

      if (fs.existsSync(cacheFile)) {
        const cached = JSON.parse(fs.readFileSync(cacheFile, "utf8"));
        const results = parseAmapDistanceResults(cached);
        results.forEach((result, index) => {
          if (!result) return;
          const pair = batch[index];
          if (pair) metricsByPair.set(pairKey(pair.from, pair.to), result);
        });
        continue;
      }

      const params = new URLSearchParams({
        key: apiKey,
        origins: batch.map((pair) => `${pair.from.lng},${pair.from.lat}`).join("|"),
        destination: `${destination.lng},${destination.lat}`,
        type: "1",
        output: "json",
      });
      await sleep(API_DELAY_MS);
      const json = await fetchWithRetry(`${AMAP_DISTANCE_URL}?${params.toString()}`);
      if (!json) continue;
      fs.mkdirSync(cacheDir, { recursive: true });
      fs.writeFileSync(cacheFile, `${JSON.stringify(sanitizeAmapResponse(json), null, 2)}\n`, "utf8");
      const results = parseAmapDistanceResults(json);
      results.forEach((result, index) => {
        if (!result) return;
        const pair = batch[index];
        if (pair) metricsByPair.set(pairKey(pair.from, pair.to), result);
      });
    }
  }
  return metricsByPair;
}

async function fetchAmapWalkingDistanceBatch({ pairs, apiKey, cacheDir, batchSize }) {
  const metricsByPair = new Map();
  const byDestination = new Map();
  for (const pair of pairs) {
    const items = byDestination.get(pair.to.id) || [];
    items.push(pair);
    byDestination.set(pair.to.id, items);
  }

  let callCount = 0;
  for (const group of byDestination.values()) {
    for (let i = 0; i < group.length; i += batchSize) {
      const batch = group.slice(i, i + batchSize);
      const destination = batch[0].to;
      const cacheFile = path.join(cacheDir, `walk-distance-${destination.id}-${i}.json`);

      // Use cache if available
      if (fs.existsSync(cacheFile)) {
        const cached = JSON.parse(fs.readFileSync(cacheFile, "utf8"));
        const results = parseAmapDistanceResults(cached);
        results.forEach((result, index) => {
          if (!result) return;
          const pair = batch[index];
          if (pair) metricsByPair.set(pairKey(pair.from, pair.to), result);
        });
        continue;
      }

      const params = new URLSearchParams({
        key: apiKey,
        origins: batch.map((pair) => `${pair.from.lng},${pair.from.lat}`).join("|"),
        destination: `${destination.lng},${destination.lat}`,
        type: "2", // walking
        output: "json",
      });

      await sleep(API_DELAY_MS);
      const json = await fetchWithRetry(`${AMAP_DISTANCE_URL}?${params.toString()}`);
      if (!json) continue;

      fs.mkdirSync(cacheDir, { recursive: true });
      fs.writeFileSync(cacheFile, `${JSON.stringify(sanitizeAmapResponse(json), null, 2)}\n`, "utf8");
      const results = parseAmapDistanceResults(json);
      results.forEach((result, index) => {
        if (!result) return;
        const pair = batch[index];
        if (pair) metricsByPair.set(pairKey(pair.from, pair.to), result);
      });
      callCount++;
    }
  }
  if (callCount > 0) console.log(`  Walking batch: ${callCount} API calls, ${metricsByPair.size} results`);
  return metricsByPair;
}

async function buildEdges(pois, options) {
  const apiKey = process.env.AMAP_API_KEY;
  const canUseAmap = options.useAmap && (options.mockDir || apiKey);
  const pairs = addBridgePairs(pois, nearestPairs(pois, options.neighbors));

  console.log(`Building edges for ${pois.length} POIs, ${pairs.length} pairs (mode=${options.mode})...`);

  // Batch fetch driving times
  const drivingBatch = canUseAmap && !options.mockDir && (options.mode === "driving" || options.mode === "mixed")
    ? await fetchAmapDrivingDistanceBatch({ pairs, apiKey, cacheDir: options.cacheDir, batchSize: options.batchSize })
    : new Map();
  if (drivingBatch.size > 0) console.log(`  Driving batch: ${drivingBatch.size} results`);

  // Batch fetch walking times (NEW: uses type=2 batch API instead of individual calls)
  const walkingBatch = canUseAmap && !options.mockDir && (options.mode === "walking" || options.mode === "mixed")
    ? await fetchAmapWalkingDistanceBatch({ pairs, apiKey, cacheDir: options.cacheDir, batchSize: options.batchSize })
    : new Map();
  if (walkingBatch.size > 0) console.log(`  Walking batch: ${walkingBatch.size} results`);

  const edges = [];
  let amapCount = 0;
  let geoCount = 0;
  for (const pair of pairs) {
    let walkMetrics = null;
    let taxiMetrics = null;
    const pk = pairKey(pair.from, pair.to);
    const batchedDrivingMetrics = drivingBatch.get(pk) || null;
    const batchedWalkingMetrics = walkingBatch.get(pk) || null;

    if (canUseAmap) {
      if (options.mode === "walking" || options.mode === "mixed") {
        walkMetrics = batchedWalkingMetrics || null;
        if (!walkMetrics && options.mockDir) {
          walkMetrics = await fetchAmapRouteMetrics({
            from: pair.from,
            to: pair.to,
            mode: "walk",
            apiKey,
            mockDir: options.mockDir,
            cacheDir: options.cacheDir,
          });
        }
      }
      if (options.mode === "driving" || options.mode === "mixed") {
        taxiMetrics = batchedDrivingMetrics || null;
        if (!taxiMetrics && options.mockDir) {
          taxiMetrics = await fetchAmapRouteMetrics({
            from: pair.from,
            to: pair.to,
            mode: "drive",
            apiKey,
            mockDir: options.mockDir,
            cacheDir: options.cacheDir,
          });
        }
      }
    }
    const source = walkMetrics || taxiMetrics ? "amap" : "geo_estimated";
    const walk = walkMetrics ? Math.max(1, Math.round(walkMetrics.durationSeconds / 60)) : timeForDistance(pair.distance, 12);
    const taxi = taxiMetrics ? Math.max(1, Math.round(taxiMetrics.durationSeconds / 60)) : timeForDistance(pair.distance, 2.8);
    const provider = source === "amap" ? "amap" : "geo_estimated";
    const amapStatus = source === "amap"
      ? (walkMetrics && taxiMetrics ? "ok" : "partial")
      : "fallback_geo_estimated";
    const distanceMeters = taxiMetrics?.distanceMeters || walkMetrics?.distanceMeters || Math.max(1, pair.distance);
    const durationSeconds = source === "amap"
      ? (options.mode === "walking" ? walkMetrics?.durationSeconds : taxiMetrics?.durationSeconds || walkMetrics?.durationSeconds)
      : Math.round(((walk + taxi) / 2) * 60);
    edges.push({
      from: pair.from.id,
      to: pair.to.id,
      distance_meters: distanceMeters,
      walk_minutes: walk,
      transit_minutes: Math.max(8, Math.round(taxi * 1.8)),
      taxi_minutes: taxi,
      source,
      provider,
      mode: options.mode,
      duration_seconds: durationSeconds,
      amap_status: amapStatus,
    });
  }
  return edges;
}

function summarizeSources(edges) {
  return edges.reduce((acc, edge) => {
    acc[edge.source || "unknown"] = (acc[edge.source || "unknown"] || 0) + 1;
    return acc;
  }, {});
}

function writeOutputs(options, edges) {
  const sourceCounts = summarizeSources(edges);
  const amapRatio = edges.length === 0 ? 0 : (sourceCounts.amap || 0) / edges.length;
  if (options.fallback === "fail" && (sourceCounts.geo_estimated || 0) > 0) {
    throw new Error(`geo_estimated edges are not allowed with --fallback fail: ${sourceCounts.geo_estimated} fallback edges`);
  }
  if (options.minAmapRatio > 0 && amapRatio < options.minAmapRatio) {
    throw new Error(`min-amap-ratio gate failed: got ${amapRatio.toFixed(3)}, expected at least ${options.minAmapRatio}`);
  }
  fs.mkdirSync(options.outDir, { recursive: true });
  const manifest = {
    generated_at: new Date().toISOString(),
    edge_count: edges.length,
    neighbors: options.neighbors,
    mode: options.mode,
    fallback: options.fallback,
    min_amap_ratio: options.minAmapRatio,
    amap_ratio: amapRatio,
    source_counts: sourceCounts,
  };
  fs.writeFileSync(path.join(options.outDir, "edges.json"), `${JSON.stringify(edges, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(options.outDir, "edges_manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return manifest;
}

async function main() {
  if (process.argv.includes("--help") || process.argv.includes("-h")) {
    usage();
    return;
  }
  const args = parseArgs(process.argv);
  const pois = readJson(args.pois);
  if (!Array.isArray(pois)) throw new Error("--pois must point to a JSON array");
  if (args.useAmap && !args.mockDir && !process.env.AMAP_API_KEY) {
    console.warn("AMAP_API_KEY is missing; commute edges will use geo_estimated fallback.");
  }
  const edges = await buildEdges(pois, args);
  const manifest = writeOutputs(args, edges);
  console.log(`Commute edges written: ${manifest.edge_count} edges -> ${args.outDir}`);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}

module.exports = {
  buildEdges,
  fetchAmapDrivingDistanceBatch,
  fetchAmapWalkingDistanceBatch,
  fetchAmapRouteMetrics,
  nearestPairs,
  pairKey,
  parseAmapDuration,
  parseAmapRouteMetrics,
  parseAmapDistanceResults,
  writeOutputs,
};
