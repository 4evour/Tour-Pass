const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const CITY_CONFIGS = {
  dali: { config: "config/amap.dali.json", target: 300 },
  chengdu: { config: "config/amap.chengdu.json", target: 500 },
  chongqing: { config: "config/amap.chongqing.json", target: 500 },
  xian: { config: "config/amap.xian.json", target: 500 },
  hangzhou: { config: "config/amap.hangzhou.json", target: 500 },
  beijing: { config: "config/amap.beijing.json", target: 500 },
};

function parseArgs(argv) {
  const args = {
    cities: Object.keys(CITY_CONFIGS),
    skipPois: false,
    skipEdges: false,
    dryRun: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--cities") args.cities = value.split(",").map((s) => s.trim());
    if (key === "--skip-pois") args.skipPois = true;
    if (key === "--skip-edges") args.skipEdges = true;
    if (key === "--dry-run") args.dryRun = true;
    if (key === "--help") {
      console.log("Usage: node scripts/batch_crawl.js [--cities dali,chengdu,...] [--skip-pois] [--skip-edges] [--dry-run]");
      process.exit(0);
    }
  }
  return args;
}

function run(cmd, opts = {}) {
  console.log(`  $ ${cmd}`);
  if (opts.dryRun) return "";
  try {
    return execSync(cmd, { encoding: "utf8", stdio: ["pipe", "pipe", "pipe"], timeout: 600000, ...opts });
  } catch (err) {
    console.error(`  ERROR: ${err.stderr || err.message}`);
    return null;
  }
}

function cityDir(city) {
  return `data/${city}`;
}

function hasCompleteData(city) {
  const poisPath = path.join(cityDir(city), "pois.json");
  const edgesPath = path.join(cityDir(city), "edges.json");
  if (!fs.existsSync(poisPath) || !fs.existsSync(edgesPath)) return false;
  try {
    const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
    const edges = JSON.parse(fs.readFileSync(edgesPath, "utf8"));
    const amapEdges = edges.filter((e) => e.source === "amap").length;
    return pois.length >= 100 && amapEdges > 0;
  } catch {
    return false;
  }
}

async function crawlCity(city, opts) {
  const cfg = CITY_CONFIGS[city];
  if (!cfg) {
    console.log(`\n=== ${city}: unknown city, skipping ===`);
    return false;
  }

  console.log(`\n${"=".repeat(60)}`);
  console.log(`Crawling: ${city} (target=${cfg.target})`);
  console.log(`${"=".repeat(60)}`);

  const outDir = `output/amap-${city}`;
  const dir = cityDir(city);

  // Step 1: Fetch POIs
  if (!opts.skipPois) {
    console.log(`\n--- Step 1: Fetch POIs ---`);
    fs.mkdirSync(dir, { recursive: true });

    // Check if POIs already exist
    const poisPath = path.join(dir, "pois.json");
    if (fs.existsSync(poisPath)) {
      const existing = JSON.parse(fs.readFileSync(poisPath, "utf8"));
      if (existing.length >= cfg.target * 0.8) {
        console.log(`  POIs already exist (${existing.length}), skipping fetch`);
      } else {
        const result = run(`node scripts/fetch_amap_pois.js --config ${cfg.config} --out-dir ${outDir} --min-pois ${Math.floor(cfg.target * 0.5)}`);
        if (result === null) {
          console.log(`  POI fetch failed for ${city}, continuing...`);
        } else {
          // Copy to data dir
          if (fs.existsSync(path.join(outDir, "pois.json"))) {
            fs.copyFileSync(path.join(outDir, "pois.json"), poisPath);
          }
        }
      }
    } else {
      const result = run(`node scripts/fetch_amap_pois.js --config ${cfg.config} --out-dir ${outDir} --min-pois ${Math.floor(cfg.target * 0.5)}`);
      if (result === null) {
        console.log(`  POI fetch failed for ${city}, continuing...`);
      } else if (fs.existsSync(path.join(outDir, "pois.json"))) {
        fs.copyFileSync(path.join(outDir, "pois.json"), poisPath);
      }
    }
  }

  // Verify POIs exist
  const poisPath = path.join(dir, "pois.json");
  if (!fs.existsSync(poisPath)) {
    console.log(`  No POIs for ${city}, skipping edges`);
    return false;
  }
  const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
  console.log(`  POIs: ${pois.length}`);

  // Step 2: Build edges with real Amap data
  if (!opts.skipEdges) {
    console.log(`\n--- Step 2: Build edges (driving + walking batch) ---`);
    const edgesPath = path.join(dir, "edges.json");
    const result = run(`node scripts/build_commute_edges.js --pois ${poisPath} --out-dir ${outDir} --neighbors 6 --mode mixed --fallback geo_estimated`);
    if (result === null) {
      console.log(`  Edge building had errors for ${city}`);
    }
    if (fs.existsSync(path.join(outDir, "edges.json"))) {
      fs.copyFileSync(path.join(outDir, "edges.json"), edgesPath);
    }
  }

  // Step 3: Validate
  console.log(`\n--- Step 3: Validate ---`);
  const edgesPath = path.join(dir, "edges.json");
  if (fs.existsSync(edgesPath)) {
    const valResult = run(`node scripts/validate_data.js --pois ${poisPath} --edges ${edgesPath}`);
    if (valResult !== null) {
      console.log(valResult.trim().split("\n").pop());
    }
  }

  return true;
}

async function main() {
  const args = parseArgs(process.argv);

  console.log("=== Batch Crawl ===");
  console.log(`Cities: ${args.cities.join(", ")}`);
  console.log(`Skip POIs: ${args.skipPois}`);
  console.log(`Skip Edges: ${args.skipEdges}`);
  console.log(`Dry Run: ${args.dryRun}`);

  const results = { success: [], failed: [], skipped: [] };

  for (const city of args.cities) {
    if (hasCompleteData(city) && !args.skipEdges) {
      console.log(`\n=== ${city}: already has complete data, skipping ===`);
      results.skipped.push(city);
      continue;
    }

    const ok = await crawlCity(city, args);
    if (ok) {
      results.success.push(city);
    } else {
      results.failed.push(city);
    }
  }

  console.log(`\n${"=".repeat(60)}`);
  console.log("=== Summary ===");
  console.log(`Success: ${results.success.join(", ") || "none"}`);
  console.log(`Failed: ${results.failed.join(", ") || "none"}`);
  console.log(`Skipped: ${results.skipped.join(", ") || "none"}`);
  console.log(`${"=".repeat(60)}`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
