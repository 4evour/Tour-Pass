const fs = require("fs");
const path = require("path");

const AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text";

const CITIES = {
  beijing: "北京", changsha: "长沙", chengdu: "成都", chongqing: "重庆",
  dali: "大理", guangzhou: "广州", guilin: "桂林", hangzhou: "杭州",
  harbin: "哈尔滨", kunming: "昆明", lijiang: "丽江", nanjing: "南京",
  qingdao: "青岛", sanya: "三亚", shanghai: "上海", shenzhen: "深圳",
  suzhou: "苏州", wuhan: "武汉", xiamen: "厦门", xian: "西安",
  zhangjiajie: "张家界",
};

const TRANSIT_SEARCHES = [
  { keywords: "火车站", types: "150000", tags: ["交通", "枢纽", "火车站"], target: 5 },
  { keywords: "机场", types: "150000", tags: ["交通", "枢纽", "机场"], target: 3 },
  { keywords: "地铁站", types: "150000", tags: ["交通", "地铁"], target: 30 },
  { keywords: "高铁站", types: "150000", tags: ["交通", "枢纽", "高铁"], target: 5 },
  { keywords: "汽车站 客运站", types: "150000", tags: ["交通", "客运"], target: 5 },
];

function hashText(value) {
  let hash = 2166136261;
  for (const char of String(value)) { hash ^= char.charCodeAt(0); hash = Math.imul(hash, 16777619); }
  return (hash >>> 0).toString(16);
}

function parseLocation(location) {
  const [lng, lat] = String(location || "").split(",").map(Number);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return { lat: Number(lat.toFixed(6)), lng: Number(lng.toFixed(6)) };
}

function resolvePoisPath(cityDir) {
  const cityPath = path.join("data", cityDir, "pois.json");
  if (fs.existsSync(cityPath)) return cityPath;
  return null;
}

function normalizeTransit(amapPoi, category, existingIds, index) {
  const location = parseLocation(amapPoi.location);
  if (!location) return null;
  const amapId = String(amapPoi.id || "");
  const name = String(amapPoi.name || "").trim();
  if (!name) return null;
  if (existingIds.has(amapId)) return null;

  const tags = Array.from(new Set([
    ...(Array.isArray(category.tags) ? category.tags : []),
    "交通设施服务",
  ])).slice(0, 10);

  const area = String(amapPoi.adname || "").trim() || "市区";

  return {
    id: "amap_" + hashText(amapId || name + "_" + index),
    name, type: "transit", lat: location.lat, lng: location.lng, area,
    open_time: "00:00", close_time: "23:59", visit_duration_minutes: 15,
    tags, popularity: 4.0, price_level: 0,
    meal_type: "", description: name + "，交通枢纽。",
    source: "amap", source_id: amapId,
    recommendation: name + "是重要交通枢纽。",
    visit_duration: 15,
  };
}

async function fetchPage(apiKey, cityName, keywords, types, page, pageSize) {
  const params = new URLSearchParams({
    key: apiKey, city: cityName, keywords, types,
    offset: String(pageSize), page: String(page),
    extensions: "all", citylimit: "true",
  });
  const url = AMAP_PLACE_TEXT_URL + "?" + params.toString();
  const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error("HTTP " + response.status);
  const json = await response.json();
  if (String(json.status) !== "1") throw new Error("AMap error: " + (json.info || "unknown"));
  return json.pois || [];
}

async function crawlCity(cityDir, cityName, apiKey) {
  const poisPath = resolvePoisPath(cityDir);
  if (!poisPath) return { added: 0 };

  const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
  const existingIds = new Set(pois.filter(p => p.source_id).map(p => p.source_id));
  const existingNames = new Set(pois.filter(p => p.type === "transit").map(p => p.name));
  const existingCount = pois.filter(p => p.type === "transit").length;

  const newPois = [];
  for (const search of TRANSIT_SEARCHES) {
    let added = 0;
    for (let page = 1; added < search.target && page <= 5; page++) {
      try {
        const amapPois = await fetchPage(apiKey, cityName, search.keywords, search.types, page, 25);
        if (amapPois.length === 0) break;
        for (const ap of amapPois) {
          if (added >= search.target) break;
          const poi = normalizeTransit(ap, search, existingIds, newPois.length);
          if (!poi) continue;
          if (existingNames.has(poi.name)) continue;
          existingIds.add(poi.source_id);
          existingNames.add(poi.name);
          newPois.push(poi);
          added++;
        }
        await new Promise(r => setTimeout(r, 200));
      } catch (err) {
        console.warn("  WARN " + search.keywords + ": " + err.message);
        break;
      }
    }
  }

  if (newPois.length > 0) {
    pois.push(...newPois);
    fs.writeFileSync(poisPath, JSON.stringify(pois, null, 2));
  }

  return { added: newPois.length, total: existingCount + newPois.length };
}

async function main() {
  const apiKey = process.env.AMAP_API_KEY;
  if (!apiKey) { console.error("ERROR: AMAP_API_KEY required"); process.exit(1); }

  const targetCities = [];
  for (let i = 2; i < process.argv.length; i++) {
    if (process.argv[i] === "--cities" && process.argv[i+1]) {
      targetCities.push(...process.argv[i+1].split(",").map(s=>s.trim()));
    }
  }
  const cityList = targetCities.length > 0 ? targetCities : Object.keys(CITIES);

  console.log("=== 交通枢纽补抓 ===\n");
  let totalAdded = 0;
  for (const cityDir of cityList) {
    const cityName = CITIES[cityDir];
    if (!cityName) continue;
    console.log(cityName + ":");
    const result = await crawlCity(cityDir, cityName, apiKey);
    console.log("  +" + result.added + " transit -> " + result.total + " total");
    totalAdded += result.added;
  }
  console.log("\n=== Total: " + totalAdded + " transit POIs ===");
}

main().catch(err => { console.error(err.message); process.exit(1); });
