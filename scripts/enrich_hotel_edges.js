/**
 * enrich_hotel_edges.js
 * 用 AMap 路线 API 精确计算酒店→最近景点/餐饮的通勤时间
 * 只处理酒店相关的边，大幅减少 API 调用量
 */
const fs = require("fs");
const path = require("path");

const AMAP_DRIVING_URL = "https://restapi.amap.com/v3/direction/driving";
const AMAP_WALKING_URL = "https://restapi.amap.com/v3/direction/walking";
const AMAP_DISTANCE_URL = "https://restapi.amap.com/v3/distances";

const CITIES = {
  beijing: "北京", changsha: "长沙", chengdu: "成都", chongqing: "重庆",
  dali: "大理", guangzhou: "广州", guilin: "桂林", hangzhou: "杭州",
  harbin: "哈尔滨", kunming: "昆明", lijiang: "丽江", nanjing: "南京",
  qingdao: "青岛", sanya: "三亚", shanghai: "上海", shenzhen: "深圳",
  suzhou: "苏州", wuhan: "武汉", xiamen: "厦门", xian: "西安",
  zhangjiajie: "张家界",
};

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function resolvePoisPath(cityDir) {
  const cityPath = path.join("data", cityDir, "pois.json");
  if (fs.existsSync(cityPath)) return cityPath;
  return null;
}

function resolveEdgesPath(cityDir) {
  const cityPath = path.join("data", cityDir, "edges.json");
  if (fs.existsSync(cityPath)) return cityPath;
  return null;
}

function distanceMeters(a, b) {
  const R = 6371000;
  const dLat = (b.lat - a.lat) * Math.PI / 180;
  const dLng = (b.lng - a.lng) * Math.PI / 180;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * Math.PI / 180) * Math.cos(b.lat * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

function findNearestPois(hotel, pois, count) {
  return pois
    .filter(p => p.id !== hotel.id && (p.type === "attraction" || p.type === "restaurant"))
    .map(p => ({ poi: p, dist: distanceMeters(hotel, p) }))
    .sort((a, b) => a.dist - b.dist)
    .slice(0, count)
    .map(x => x.poi);
}

async function fetchDrivingRoute(apiKey, from, to) {
  const origin = from.lng + "," + from.lat;
  const dest = to.lng + "," + to.lat;
  const url = AMAP_DRIVING_URL + "?key=" + apiKey + "&origin=" + origin + "&destination=" + dest + "&extensions=base";
  try {
    const resp = await fetch(url, { signal: AbortSignal.timeout(8000) });
    const json = await resp.json();
    if (String(json.status) === "1" && json.route && json.route.paths && json.route.paths[0]) {
      const path = json.route.paths[0];
      return { distance: Number(path.distance), duration: Math.round(Number(path.duration) / 60) };
    }
  } catch (e) {}
  return null;
}

async function enrichCity(cityDir, apiKey, opts) {
  const poisPath = resolvePoisPath(cityDir);
  const edgesPath = resolveEdgesPath(cityDir);
  if (!poisPath || !edgesPath) return { enriched: 0 };

  const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
  const edges = JSON.parse(fs.readFileSync(edgesPath, "utf8"));
  const hotels = pois.filter(p => p.type === "hotel");
  const nonHotels = pois.filter(p => p.type === "hotel" || p.type === "attraction" || p.type === "restaurant");

  // Build edge lookup
  const edgeMap = new Map();
  edges.forEach(e => { edgeMap.set(e.from + "|" + e.to, e); });

  let enriched = 0;
  let apiCalls = 0;
  const maxCalls = opts.maxCalls || 500;

  for (const hotel of hotels) {
    if (apiCalls >= maxCalls) break;
    const targets = findNearestPois(hotel, nonHotels, 5);
    for (const target of targets) {
      if (apiCalls >= maxCalls) break;
      const edgeKey = hotel.id + "|" + target.id;
      const existing = edgeMap.get(edgeKey);
      // Only enrich if currently geo_estimated
      if (existing && existing.source === "amap") continue;

      const route = await fetchDrivingRoute(apiKey, hotel, target);
      apiCalls++;
      if (route) {
        const walkMin = Math.max(1, Math.round(route.distance / 1000 * 12 * 1.35));
        const newEdge = {
          from: hotel.id, to: target.id,
          distance_meters: route.distance,
          walk_minutes: walkMin,
          transit_minutes: Math.max(8, Math.round(route.duration * 1.8)),
          taxi_minutes: route.duration,
          source: "amap", provider: "amap", mode: "mixed",
          duration_seconds: route.duration * 60,
          amap_status: "ok",
        };
        // Update or add edge
        if (existing) {
          Object.assign(existing, newEdge);
        } else {
          edges.push(newEdge);
        }
        // Also add reverse edge
        const reverseKey = target.id + "|" + hotel.id;
        const reverseExisting = edgeMap.get(reverseKey);
        const reverseEdge = {
          from: target.id, to: hotel.id,
          distance_meters: route.distance,
          walk_minutes: walkMin,
          transit_minutes: Math.max(8, Math.round(route.duration * 1.8)),
          taxi_minutes: route.duration,
          source: "amap", provider: "amap", mode: "mixed",
          duration_seconds: route.duration * 60,
          amap_status: "ok",
        };
        if (reverseExisting) {
          Object.assign(reverseExisting, reverseEdge);
        } else {
          edges.push(reverseEdge);
        }
        enriched++;
      }
      await sleep(250); // Rate limit
    }
  }

  if (enriched > 0 && !opts.dryRun) {
    fs.writeFileSync(edgesPath, JSON.stringify(edges, null, 2));
  }

  return { enriched, apiCalls, totalEdges: edges.length };
}

async function main() {
  const apiKey = process.env.AMAP_API_KEY;
  if (!apiKey) { console.error("ERROR: AMAP_API_KEY required"); process.exit(1); }

  const maxCallsPerCity = 200;
  const targetCities = [];
  for (let i = 2; i < process.argv.length; i++) {
    if (process.argv[i] === "--cities" && process.argv[i+1]) {
      targetCities.push(...process.argv[i+1].split(",").map(s=>s.trim()));
    }
  }
  const cityList = targetCities.length > 0 ? targetCities : Object.keys(CITIES);

  console.log("=== Hotel edge enrichment (AMap routing) ===");
  console.log("Max API calls per city: " + maxCallsPerCity);
  console.log("");

  let totalEnriched = 0, totalCalls = 0;
  for (const cityDir of cityList) {
    const cityName = CITIES[cityDir];
    if (!cityName) continue;
    console.log(cityName + ":");
    const result = await enrichCity(cityDir, apiKey, { maxCalls: maxCallsPerCity });
    console.log("  " + result.enriched + " edges enriched (" + result.apiCalls + " API calls) -> " + result.totalEdges + " total");
    totalEnriched += result.enriched;
    totalCalls += result.apiCalls;
  }
  console.log("\n=== Total: " + totalEnriched + " edges enriched, " + totalCalls + " API calls ===");
}

main().catch(err => { console.error(err.message); process.exit(1); });
