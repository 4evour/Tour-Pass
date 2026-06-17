const fs = require("fs");
const path = require("path");

const AMAP_DETAIL_URL = "https://restapi.amap.com/v3/place/detail";

function parseArgs(argv) {
  const args = {
    pois: "data/changsha/pois.json",
    outDir: "output/amap-details",
    cacheDir: "output/amap-cache",
    limit: 0, // 0 = all POIs with source_id
    dryRun: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--pois") args.pois = value;
    if (key === "--out-dir") args.outDir = value;
    if (key === "--cache-dir") args.cacheDir = value;
    if (key === "--limit") args.limit = Number(value);
    if (key === "--dry-run") args.dryRun = true;
    if (key.startsWith("--")) i += 1;
  }
  return args;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function cacheKey(sourceId) {
  return `detail-${sourceId}.json`;
}

async function fetchDetail(apiKey, sourceId, cacheDir) {
  const cacheFile = path.join(cacheDir, cacheKey(sourceId));
  if (fs.existsSync(cacheFile)) {
    return JSON.parse(fs.readFileSync(cacheFile, "utf8"));
  }

  const params = new URLSearchParams({ key: apiKey, id: sourceId });
  const url = `${AMAP_DETAIL_URL}?${params.toString()}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`AMap detail HTTP ${response.status} for ${sourceId}`);
  }
  const json = await response.json();

  fs.mkdirSync(cacheDir, { recursive: true });
  fs.writeFileSync(cacheFile, JSON.stringify(json, null, 2) + "\n", "utf8");
  return json;
}

function extractDetail(amapPoi) {
  if (!amapPoi) return {};
  const detail = {};

  // Rating
  const rating = amapPoi.biz_ext?.rating;
  if (rating && rating !== "[]") {
    detail.rating = Number(rating);
  }

  // Cost (人均消费)
  const cost = amapPoi.biz_ext?.cost;
  if (cost && cost !== "[]") {
    detail.avg_cost = cost;
  }

  // Photos
  if (Array.isArray(amapPoi.photos) && amapPoi.photos.length > 0) {
    detail.photos = amapPoi.photos.slice(0, 3).map(p => ({
      url: p.url || "",
      title: p.title || "",
    }));
  }

  // Business hours (more precise than config defaults)
  if (amapPoi.business_hours && amapPoi.business_hours !== "[]") {
    detail.business_hours = amapPoi.business_hours;
  }

  // Telephone
  if (amapPoi.tel && amapPoi.tel !== "[]") {
    detail.telephone = amapPoi.tel;
  }

  // Address
  if (amapPoi.address && amapPoi.address !== "[]") {
    detail.address = amapPoi.address;
  }

  // Entrance location
  if (amapPoi.entr_location && amapPoi.entr_location !== "[]") {
    detail.entrance = amapPoi.entr_location;
  }

  // Indoor map
  if (amapPoi.indoor_map === "1") {
    detail.has_indoor_map = true;
  }

  // Recommendation tag
  if (amapPoi.recommend && amapPoi.recommend !== "[]") {
    detail.recommend = amapPoi.recommend;
  }

  // Cuisine type (for restaurants)
  if (amapPoi.cuisine && amapPoi.cuisine !== "[]") {
    detail.cuisine = amapPoi.cuisine;
  }

  // Rating description
  if (amapPoi.rating && amapPoi.rating !== "[]") {
    detail.dianping_rating = amapPoi.rating;
  }

  return detail;
}

async function enrichPois(pois, options) {
  const apiKey = process.env.AMAP_API_KEY;
  if (!options.dryRun && !apiKey) {
    throw new Error("missing AMAP_API_KEY");
  }

  const toEnrich = pois
    .filter(p => p.source_id)
    .filter(p => p.type === "attraction" || p.type === "restaurant" || p.type === "nightlife");

  const limit = options.limit > 0 ? options.limit : toEnrich.length;
  const targets = toEnrich.slice(0, limit);

  console.log(`Enriching ${targets.length} POIs (out of ${pois.length} total)...`);

  let success = 0;
  let cached = 0;
  let failed = 0;
  let enriched = 0;

  for (let i = 0; i < targets.length; i++) {
    const poi = targets[i];
    const cacheFile = path.join(options.cacheDir, cacheKey(poi.source_id));
    const isCached = fs.existsSync(cacheFile);

    if (options.dryRun) {
      console.log(`  [DRY] ${poi.name} (${poi.source_id})`);
      continue;
    }

    try {
      const json = await fetchDetail(apiKey, poi.source_id, options.cacheDir);
      if (String(json.status) !== "1" || !Array.isArray(json.pois) || json.pois.length === 0) {
        failed++;
        continue;
      }
      if (isCached) cached++;

      const detail = extractDetail(json.pois[0]);
      if (Object.keys(detail).length > 0) {
        // Merge detail into POI
        if (detail.rating && detail.rating > 0) {
          poi.popularity = Number((detail.rating / 2).toFixed(1)); // Amap 0-10 -> 0-5
        }
        if (detail.avg_cost) {
          const costNum = Number(detail.avg_cost);
          if (Number.isFinite(costNum) && costNum > 0) {
            poi.price_level = Math.min(5, Math.max(1, Math.round(costNum / 80) + 1));
          }
        }
        if (detail.business_hours) {
          // Parse business hours to open/close time if available
          const hoursMatch = String(detail.business_hours).match(/(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})/);
          if (hoursMatch) {
            poi.open_time = hoursMatch[1].padStart(5, "0");
            poi.close_time = hoursMatch[2].padStart(5, "0");
          }
        }
        if (detail.cuisine) {
          poi.description = poi.description.replace(/。$/, "") + `；菜系：${detail.cuisine}。`;
        }
        if (detail.avg_cost && detail.avg_cost !== "[]") {
          poi.description = poi.description.replace(/。$/, "") + `；人均：${detail.avg_cost}元。`;
        }
        poi.amap_detail = detail;
        enriched++;
      }
      success++;

      // Rate limit: small delay between requests
      if (!isCached && i < targets.length - 1) {
        await new Promise(r => setTimeout(r, 200));
      }
    } catch (error) {
      console.error(`  Error enriching ${poi.name}: ${error.message}`);
      failed++;
      if (error.message.includes("CUQPS_HAS_EXCEEDED_THE_LIMIT")) {
        console.log("  Rate limit hit, stopping. Re-run later to continue from cache.");
        break;
      }
    }

    if ((i + 1) % 50 === 0) {
      console.log(`  Progress: ${i + 1}/${targets.length} (success=${success}, cached=${cached}, failed=${failed}, enriched=${enriched})`);
    }
  }

  return { success, cached, failed, enriched, total: targets.length };
}

async function main() {
  const args = parseArgs(process.argv);
  const pois = readJson(args.pois);

  fs.mkdirSync(args.outDir, { recursive: true });

  const result = await enrichPois(pois, args);

  if (!args.dryRun) {
    // Write enriched POIs back
    const outPath = path.join(args.outDir, "pois_enriched.json");
    fs.writeFileSync(outPath, JSON.stringify(pois, null, 2) + "\n", "utf8");
    console.log(`\nEnriched POIs written: ${outPath}`);
    console.log(`Stats: ${result.success} fetched, ${result.cached} cached, ${result.failed} failed, ${result.enriched} enriched out of ${result.total} targets`);
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}

module.exports = { extractDetail, enrichPois };
