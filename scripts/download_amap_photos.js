/**
 * Download Amap POI photos — multi-key, multi-city, concurrent version.
 *
 * Usage:
 *   node scripts/download_amap_photos.js                      # all cities
 *   node scripts/download_amap_photos.js --city guangzhou     # single city
 *   node scripts/download_amap_photos.js --limit 50
 *   node scripts/download_amap_photos.js --concurrency 10     # 10 parallel requests
 */
const fs = require("fs");
const path = require("path");
const https = require("https");
const http = require("http");

// ============ Config ============
const AMAP_DETAIL_URL = "https://restapi.amap.com/v3/place/detail";
const API_KEYS = [
  "2bcf1910bfdffcff162453d02153d64c",
  "64ca7624c4f373ec3b123b2298b81019",
];

const DATA_DIR = path.join(__dirname, "..", "data");
const CACHE_DIR = path.join(__dirname, "..", "output", "amap-detail-cache");
const MAX_PHOTOS = 3;

// ============ Key rotation ============
let keyIdx = 0;
function nextKey() {
  const key = API_KEYS[keyIdx % API_KEYS.length];
  keyIdx++;
  return key;
}

// ============ HTTP helpers ============
function downloadImage(url, dest) {
  return new Promise((resolve, reject) => {
    if (fs.existsSync(dest) && fs.statSync(dest).size > 1000) {
      return resolve(fs.statSync(dest).size);
    }
    const proto = url.startsWith("https") ? https : http;
    const opts = { headers: { Referer: "https://www.amap.com/" }, timeout: 10000 };
    const req = proto.get(url, opts, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return downloadImage(res.headers.location, dest).then(resolve).catch(reject);
      }
      if (res.statusCode !== 200) { reject(new Error("HTTP " + res.statusCode)); return; }
      const chunks = [];
      res.on("data", c => chunks.push(c));
      res.on("end", () => {
        const buf = Buffer.concat(chunks);
        if (buf.length < 1000) { reject(new Error("Too small")); return; }
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        fs.writeFileSync(dest, buf);
        resolve(buf.length);
      });
      res.on("error", reject);
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("timeout")); });
  });
}

async function fetchDetail(sourceId) {
  const cacheFile = path.join(CACHE_DIR, sourceId + ".json");
  if (fs.existsSync(cacheFile)) {
    try {
      const cached = JSON.parse(fs.readFileSync(cacheFile, "utf8"));
      if (cached.status === "1") return cached;
      return null;
    } catch {}
  }
  const key = nextKey();
  const url = AMAP_DETAIL_URL + "?id=" + sourceId + "&key=" + key;
  try {
    const resp = await fetch(url);
    if (!resp.ok) return null;
    const json = await resp.json();
    fs.mkdirSync(CACHE_DIR, { recursive: true });
    fs.writeFileSync(cacheFile, JSON.stringify(json, null, 2));
    if (json.status !== "1") return null;
    return json;
  } catch {
    return null;
  }
}

// ============ Process single POI ============
async function processPoi(poi, cityImgDir, cityName) {
  try {
    const detail = await fetchDetail(poi.source_id);
    if (!detail || !detail.pois || !detail.pois[0]) return false;
    const photos = detail.pois[0].photos || [];
    if (!photos.length) return false;

    const imgSubDir = path.join(cityImgDir, poi.id);
    fs.mkdirSync(imgSubDir, { recursive: true });

    // Download all photos in parallel
    const tasks = [];
    for (let j = 0; j < Math.min(photos.length, MAX_PHOTOS); j++) {
      const photoUrl = photos[j].url || "";
      if (!photoUrl) continue;
      const fileName = (j + 1) + ".jpg";
      const dest = path.join(imgSubDir, fileName);
      const relPath = "images/" + cityName + "/images/" + poi.id + "/" + fileName;
      tasks.push(
        downloadImage(photoUrl, dest)
          .then(() => ({ url: relPath, source: "amap" }))
          .catch(() => null)
      );
    }

    const results = await Promise.all(tasks);
    const imageUrls = results.filter(Boolean);
    if (imageUrls.length > 0) {
      poi.image_url = imageUrls[0].url;
      poi.images = imageUrls;
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

// ============ Concurrent batch processor ============
async function processBatch(items, concurrency, fn) {
  let idx = 0;
  let completed = 0;
  const total = items.length;

  async function worker() {
    while (idx < items.length) {
      const i = idx++;
      await fn(items[i], i);
      completed++;
      if (completed % 100 === 0) {
        console.log("    progress: " + completed + "/" + total);
      }
    }
  }

  const workers = [];
  for (let w = 0; w < concurrency; w++) {
    workers.push(worker());
  }
  await Promise.all(workers);
  return completed;
}

// ============ City processing ============
async function processCity(cityName, limit, concurrency, dryRun) {
  const cityDir = path.join(DATA_DIR, cityName);
  const poisPath = path.join(cityDir, "pois.json");
  if (!fs.existsSync(poisPath)) {
    console.log("[" + cityName + "] skipped (no pois.json)");
    return { city: cityName, skipped: true };
  }

  const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
  const imgDir = path.join(cityDir, "images");

  const needPhotos = pois
    .filter(p => p.source_id)
    .filter(p => !(p.image_url && p.images && p.images.length >= 2))
    .sort((a, b) => {
      const ord = { attraction: 0, nightlife: 1, restaurant: 2, hotel: 3, transit: 4 };
      return (ord[a.type] ?? 5) - (ord[b.type] ?? 5);
    });

  const batch = needPhotos.slice(0, limit);
  console.log("[" + cityName + "] " + pois.length + " total, " + batch.length + " to process (concurrency=" + concurrency + ")");

  if (dryRun) return { city: cityName, total: pois.length, batch: batch.length, dryRun: true };

  const t0 = Date.now();
  let success = 0;

  await processBatch(batch, concurrency, async (poi) => {
    const ok = await processPoi(poi, imgDir, cityName);
    if (ok) success++;
  });

  // Write back
  fs.writeFileSync(poisPath, JSON.stringify(pois, null, 2));
  const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
  const rate = (batch.length / (Date.now() - t0) * 1000).toFixed(1);
  console.log("[" + cityName + "] done: " + success + "/" + batch.length + " in " + elapsed + "s (" + rate + "/s)");
  return { city: cityName, success, total: batch.length, elapsed: parseFloat(elapsed) };
}

// ============ Main ============
async function main() {
  const args = process.argv.slice(2);
  const cityArg = args.indexOf("--city");
  const limitArg = args.indexOf("--limit");
  const concArg = args.indexOf("--concurrency");
  const dryRun = args.includes("--dry-run");

  const limit = limitArg > 0 ? parseInt(args[limitArg + 1]) : 9999;
  const concurrency = concArg > 0 ? parseInt(args[concArg + 1]) : 5;

  let cities;
  if (cityArg > 0 && args[cityArg + 1]) {
    cities = [args[cityArg + 1]];
  } else {
    cities = fs.readdirSync(DATA_DIR)
      .filter(d => fs.existsSync(path.join(DATA_DIR, d, "pois.json")))
      .sort();
  }

  console.log("=== Amap Photo Downloader (concurrent) ===");
  console.log("Keys: " + API_KEYS.length + ", Cities: " + cities.length + ", Concurrency: " + concurrency);
  console.log("");

  const results = [];
  for (const city of cities) {
    const r = await processCity(city, limit, concurrency, dryRun);
    results.push(r);
  }

  console.log("\n=== SUMMARY ===");
  let totalOk = 0, totalAll = 0;
  for (const r of results) {
    if (r.skipped || r.dryRun) continue;
    totalOk += r.success || 0;
    totalAll += r.total || 0;
    console.log("  " + r.city + ": " + (r.success || 0) + "/" + (r.total || 0) + " (" + (r.elapsed || 0) + "s)");
  }
  console.log("Total: " + totalOk + "/" + totalAll + " POIs updated");
}

main().catch(e => { console.error("Fatal:", e.message); process.exit(1); });
