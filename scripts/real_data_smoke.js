const fs = require("fs");

function parseArgs(argv) {
  const args = {
    baseUrl: process.env.TOURPASS_BASE_URL || "http://127.0.0.1:8080",
    expectedPois: 500,
    minAmapRatio: 0.7,
    edgesManifest: "output/amap-changsha/edges_manifest.json",
    request: "docs/sample_candidate_request.json",
    requireAllPairs: false,
  };
  const positional = [];
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (!key.startsWith("--")) {
      positional.push(key);
      continue;
    }
    if (key === "--expected-pois") args.expectedPois = Number(value);
    if (key === "--min-amap-ratio") args.minAmapRatio = Number(value);
    if (key === "--edges-manifest") args.edgesManifest = value;
    if (key === "--request") args.request = value;
    if (key === "--require-all-pairs") args.requireAllPairs = true;
    if (key.startsWith("--") && key !== "--require-all-pairs") i += 1;
  }
  if (positional.length > 0) args.baseUrl = positional[0];
  args.expectedPois = Math.max(1, Math.floor(Number.isFinite(args.expectedPois) ? args.expectedPois : 500));
  args.minAmapRatio = Math.max(0, Math.min(1, Number.isFinite(args.minAmapRatio) ? args.minAmapRatio : 0.7));
  return args;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForHealth(baseUrl) {
  let lastError = "";
  for (let i = 0; i < 60; i += 1) {
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) return await response.json();
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error.message;
    }
    await sleep(500);
  }
  throw new Error(`service did not become healthy: ${lastError}`);
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} failed with ${response.status}: ${(await response.text()).slice(0, 240)}`);
  }
  return response.json();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${url} failed with ${response.status}: ${(await response.text()).slice(0, 240)}`);
  }
  return response.json();
}

function readManifest(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return null;
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function amapRatioFromManifest(manifest) {
  if (!manifest) return null;
  if (Number.isFinite(manifest.amap_ratio)) return manifest.amap_ratio;
  const counts = manifest.source_counts || {};
  const total = Number(manifest.edge_count || 0);
  return total > 0 ? Number(counts.amap || 0) / total : 0;
}

async function runSmoke(args) {
  const health = await waitForHealth(args.baseUrl);
  if (health.status !== "ok" || !health.data_loaded) {
    throw new Error(`unexpected health response: ${JSON.stringify(health)}`);
  }
  if (Number(health.poi_count || 0) < args.expectedPois) {
    throw new Error(`expected at least ${args.expectedPois} POIs, got ${health.poi_count}`);
  }
  if (Number(health.edge_count || 0) <= 0) {
    throw new Error("expected positive edge_count");
  }
  const distanceCache = health.distance_cache || {};
  const requiredFields = ["mode", "startup_ms", "entries", "max_entries", "hits", "misses"];
  for (const field of requiredFields) {
    if (!(field in distanceCache)) throw new Error(`health.distance_cache missing ${field}`);
  }
  if (args.requireAllPairs && distanceCache.mode !== "all_pairs") {
    throw new Error(`expected all_pairs distance cache, got ${distanceCache.mode}`);
  }

  const manifest = readManifest(args.edgesManifest);
  const amapRatio = amapRatioFromManifest(manifest);
  if (amapRatio !== null && amapRatio < args.minAmapRatio) {
    throw new Error(`expected amap edge ratio >= ${args.minAmapRatio}, got ${amapRatio.toFixed(3)}`);
  }

  const tripRequest = JSON.parse(fs.readFileSync(args.request, "utf8"));
  const plan = await postJson(`${args.baseUrl}/trip/plan`, tripRequest);
  if (!Array.isArray(plan.candidates) || plan.candidates.length === 0) {
    throw new Error("trip plan did not return candidates");
  }

  const search = await getJson(`${args.baseUrl}/poi/search?q=${encodeURIComponent("历史文化")}&limit=3`);
  if (!Array.isArray(search.data) || search.data.length === 0) {
    throw new Error("poi search did not return data");
  }

  return {
    poi_count: health.poi_count,
    edge_count: health.edge_count,
    distance_cache_mode: distanceCache.mode,
    distance_cache_entries: distanceCache.entries,
    amap_ratio: amapRatio,
    candidates: plan.candidates.length,
    search_results: search.data.length,
  };
}

async function main() {
  const args = parseArgs(process.argv);
  const summary = await runSmoke(args);
  console.log(
    `Real data smoke passed: ${summary.poi_count} POIs, ${summary.edge_count} edges, cache=${summary.distance_cache_mode}, amap_ratio=${summary.amap_ratio === null ? "not checked" : `${(summary.amap_ratio * 100).toFixed(1)}%`}, candidates=${summary.candidates}.`,
  );
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}

module.exports = { parseArgs, runSmoke, amapRatioFromManifest };
