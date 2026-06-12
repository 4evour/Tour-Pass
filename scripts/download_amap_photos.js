/**
 * Download Amap POI photos via Detail API.
 * Usage: node scripts/download_amap_photos.js [--limit N]
 */
const fs = require("fs");
const path = require("path");
const https = require("https");
const http = require("http");

const AMAP_DETAIL_URL = "https://restapi.amap.com/v3/place/detail";
const API_KEY = "2bcf1910bfdffcff162453d02153d64c";
const DATA_DIR = path.join(__dirname, "..", "data", "guangzhou");
const POIS_PATH = path.join(DATA_DIR, "pois.json");
const IMG_DIR = path.join(DATA_DIR, "images");
const CACHE_DIR = path.join(__dirname, "..", "output", "amap-detail-cache");
const TARGETS_PATH = path.join(__dirname, "..", "output", "guangzhou_photo_targets.json");
const MAX_PHOTOS = 3;
const DELAY_MS = 300;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function downloadImage(url, dest) {
  return new Promise((resolve, reject) => {
    const proto = url.startsWith("https") ? https : http;
    const opts = { headers: { Referer: "https://www.amap.com/" }, timeout: 15000 };
    const req = proto.get(url, opts, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return downloadImage(res.headers.location, dest).then(resolve).catch(reject);
      }
      if (res.statusCode !== 200) { reject(new Error("HTTP " + res.statusCode)); return; }
      const chunks = [];
      res.on("data", c => chunks.push(c));
      res.on("end", () => {
        const buf = Buffer.concat(chunks);
        if (buf.length < 1000) { reject(new Error("Too small: " + buf.length)); return; }
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
    const cached = JSON.parse(fs.readFileSync(cacheFile, "utf8"));
    if (cached.status === "1") return cached;
    return null;
  }
  const url = AMAP_DETAIL_URL + "?id=" + sourceId + "&key=" + API_KEY;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error("HTTP " + resp.status);
  const json = await resp.json();
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  fs.writeFileSync(cacheFile, JSON.stringify(json, null, 2));
  if (json.status !== "1") return null;
  return json;
}

async function main() {
  const limitArg = process.argv.indexOf("--limit");
  const limit = limitArg > 0 ? parseInt(process.argv[limitArg + 1]) : 100;

  const targets = JSON.parse(fs.readFileSync(TARGETS_PATH, "utf8"));
  const pois = JSON.parse(fs.readFileSync(POIS_PATH, "utf8"));
  const poiByName = {};
  for (const p of pois) poiByName[p.name] = p;

  // Filter: skip POIs that already have images
  const needPhotos = targets.filter(t => {
    const poi = poiByName[t.name];
    if (!poi) return false;
    if (poi.image_url && poi.images && poi.images.length >= 2) return false;
    return true;
  });

  console.log("Total targets: " + targets.length);
  console.log("Already have images: " + (targets.length - needPhotos.length));
  console.log("Need photos: " + needPhotos.length);
  console.log("Will process: " + Math.min(needPhotos.length, limit));

  let success = 0, failed = 0, noPhoto = 0, totalPhotos = 0;
  const batch = needPhotos.slice(0, limit);

  for (let i = 0; i < batch.length; i++) {
    const target = batch[i];
    const sid = target.source_id;
    const name = target.name;
    const poi = poiByName[name];
    if (!poi) continue;

    try {
      const detail = await fetchDetail(sid);
      if (!detail) { noPhoto++; continue; }

      const amapPoi = detail.pois[0];
      const photos = amapPoi.photos || [];
      if (!photos.length) { noPhoto++; continue; }

      const imgSubDir = path.join(IMG_DIR, poi.id);
      fs.mkdirSync(imgSubDir, { recursive: true });

      const imageUrls = [];
      for (let j = 0; j < Math.min(photos.length, MAX_PHOTOS); j++) {
        const photoUrl = photos[j].url || "";
        if (!photoUrl) continue;
        const ext = ".jpg";
        const fileName = (j + 1) + ext;
        const dest = path.join(imgSubDir, fileName);
        const relPath = "images/guangzhou/images/" + poi.id + "/" + fileName;

        if (fs.existsSync(dest) && fs.statSync(dest).size > 1000) {
          imageUrls.push({ url: relPath, source: "amap" });
          continue;
        }
        try {
          await downloadImage(photoUrl, dest);
          imageUrls.push({ url: relPath, source: "amap" });
          totalPhotos++;
        } catch (e) { /* skip */ }
      }

      if (imageUrls.length > 0) {
        poi.image_url = imageUrls[0].url;
        poi.images = imageUrls;
        success++;
      }

      if ((i + 1) % 10 === 0) {
        console.log("[" + (i + 1) + "/" + batch.length + "] ok=" + success + " noPhoto=" + noPhoto + " fail=" + failed + " photos=" + totalPhotos);
      }

      await sleep(DELAY_MS);
    } catch (e) {
      failed++;
      if (e.message.includes("10044") || e.message.includes("OVER_LIMIT")) {
        console.error("API limit hit at step " + (i + 1));
        break;
      }
    }
  }

  fs.writeFileSync(POIS_PATH, JSON.stringify(pois, null, 2));

  console.log("\n=== DONE ===");
  console.log("  Updated: " + success + " POIs");
  console.log("  No photos: " + noPhoto);
  console.log("  Failed: " + failed);
  console.log("  Photos downloaded: " + totalPhotos);
  console.log("  Remaining: " + Math.max(0, needPhotos.length - batch.length));
}

main().catch(e => { console.error("Fatal:", e.message); process.exit(1); });
