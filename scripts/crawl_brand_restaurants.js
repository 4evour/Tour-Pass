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

// 品牌餐饮搜索关键词
const RESTAURANT_SEARCHES = [
  { keywords: "海底捞火锅", tags: ["火锅", "连锁"], target: 8 },
  { keywords: "西贝莜面村", tags: ["西北菜", "连锁"], target: 5 },
  { keywords: "外婆家", tags: ["浙菜", "连锁"], target: 5 },
  { keywords: "绿茶餐厅", tags: ["融合菜", "连锁"], target: 5 },
  { keywords: "全聚德烤鸭", tags: ["烤鸭", "老字号"], target: 5 },
  { keywords: "太二酸菜鱼", tags: ["川菜", "连锁"], target: 5 },
  { keywords: "凑凑火锅", tags: ["火锅", "连锁"], target: 5 },
  { keywords: "巴奴毛肚火锅", tags: ["火锅", "连锁"], target: 5 },
  { keywords: "喜茶", tags: ["茶饮", "连锁"], target: 8 },
  { keywords: "奈雪的茶", tags: ["茶饮", "连锁"], target: 8 },
  { keywords: "星巴克", tags: ["咖啡", "连锁"], target: 10 },
  { keywords: "必胜客", tags: ["西餐", "连锁"], target: 8 },
  { keywords: "肯德基", tags: ["快餐", "连锁"], target: 8 },
  { keywords: "麦当劳", tags: ["快餐", "连锁"], target: 8 },
  { keywords: "本地特色菜", tags: ["美食", "特色"], target: 15 },
  { keywords: "老字号餐厅", tags: ["美食", "老字号"], target: 10 },
  { keywords: "美食街", tags: ["美食街", "小吃"], target: 8 },
  { keywords: "夜市美食", tags: ["夜市", "小吃"], target: 8 },
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

function clamp(value, min, max, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

function splitTags(value) {
  if (!value) return [];
  return String(value).split(/[|;,\s]+/).map(s => s.trim()).filter(Boolean);
}

function resolvePoisPath(cityDir) {
  const cityPath = path.join("data", cityDir, "pois.json");
  if (fs.existsSync(cityPath)) return cityPath;
  if (cityDir === "changsha") { const rp = path.join("data", "pois.json"); if (fs.existsSync(rp)) return rp; }
  return null;
}

// 低质量餐厅关键词
const LOW_QUALITY = [
  "路边摊", "流动", "推车", "小摊", "摆摊", "无名", "临时",
  "地沟", "苍蝇馆", "黑暗料理", "路边烧烤", "路边炸串",
];

function isLowQuality(name) {
  return LOW_QUALITY.some(k => name.includes(k));
}

function normalizeRestaurant(amapPoi, category, existingIds, index) {
  const location = parseLocation(amapPoi.location);
  if (!location) return null;
  const amapId = String(amapPoi.id || "");
  const name = String(amapPoi.name || "").trim();
  if (!name) return null;
  if (existingIds.has(amapId)) return null;
  if (isLowQuality(name)) return null;

  const rating = amapPoi.biz_ext && amapPoi.biz_ext.rating && amapPoi.biz_ext.rating !== "[]"
    ? clamp(Number(amapPoi.biz_ext.rating), 0, 5, 4.0)
    : 4.0;
  if (rating < 3.5) return null;

  const cost = amapPoi.biz_ext && amapPoi.biz_ext.cost && amapPoi.biz_ext.cost !== "[]"
    ? clamp(Math.round(Number(amapPoi.biz_ext.cost) / 80) + 1, 1, 5, 2)
    : 2;

  const tags = Array.from(new Set([
    "美食", ...(Array.isArray(category.tags) ? category.tags : []),
    ...splitTags(amapPoi.type), ...splitTags(amapPoi.business_area),
  ])).slice(0, 10);

  const area = String(amapPoi.adname || amapPoi.business_area || "").trim() || "市中心";

  // 判断 meal_type
  let mealType = "main";
  const catStr = (category.keywords || "").toLowerCase();
  if (catStr.includes("茶") || catStr.includes("咖啡")) mealType = "drink";
  if (catStr.includes("夜市") || catStr.includes("小吃")) mealType = "snack";

  return {
    id: "amap_" + hashText(amapId || name + "_" + index),
    name, type: "restaurant", lat: location.lat, lng: location.lng, area,
    open_time: "10:00", close_time: "22:00", visit_duration_minutes: 60,
    tags, popularity: Number(rating.toFixed(1)), price_level: cost,
    meal_type: mealType,
    description: name + "，" + (category.tags[0] || "美食") + "，位于" + area + "。",
    source: "amap", source_id: amapId,
    recommendation: name + "口碑不错，值得一试。",
    visit_duration: 60,
  };
}

async function fetchPage(apiKey, cityName, keywords, page, pageSize) {
  const params = new URLSearchParams({
    key: apiKey, city: cityName, keywords, types: "050000",
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
  const existingNames = new Set(pois.filter(p => p.type === "restaurant").map(p => p.name));
  const existingCount = pois.filter(p => p.type === "restaurant").length;

  // 提取已有品牌分店数，避免过多重复
  const brandCount = {};
  pois.filter(p => p.type === "restaurant").forEach(r => {
    const brand = r.name.replace(/\(.*?\)/g, "").replace(/（.*?）/g, "").trim().slice(0, 6);
    brandCount[brand] = (brandCount[brand] || 0) + 1;
  });

  const newPois = [];
  for (const search of RESTAURANT_SEARCHES) {
    let added = 0;
    for (let page = 1; added < search.target && page <= 3; page++) {
      try {
        const amapPois = await fetchPage(apiKey, cityName, search.keywords, page, 25);
        if (amapPois.length === 0) break;
        for (const ap of amapPois) {
          if (added >= search.target) break;
          const poi = normalizeRestaurant(ap, search, existingIds, newPois.length);
          if (!poi) continue;
          if (existingNames.has(poi.name)) continue;
          // 限制同一品牌分店数量（最多5家）
          const brand = poi.name.replace(/\(.*?\)/g, "").replace(/（.*?）/g, "").trim().slice(0, 6);
          if ((brandCount[brand] || 0) >= 5) continue;
          existingIds.add(poi.source_id);
          existingNames.add(poi.name);
          brandCount[brand] = (brandCount[brand] || 0) + 1;
          newPois.push(poi);
          added++;
        }
        await new Promise(r => setTimeout(r, 200));
      } catch (err) {
        console.warn("  WARN " + search.keywords + " p" + page + ": " + err.message);
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

  console.log("=== 品牌餐饮补抓 ===\n");

  let totalAdded = 0;
  for (const cityDir of cityList) {
    const cityName = CITIES[cityDir];
    if (!cityName) continue;
    console.log(cityName + " (" + cityDir + "):");
    const result = await crawlCity(cityDir, cityName, apiKey);
    console.log("  +" + result.added + " restaurants -> " + result.total + " total");
    totalAdded += result.added;
  }
  console.log("\n=== Total added: " + totalAdded + " restaurants ===");
}

main().catch(err => { console.error(err.message); process.exit(1); });
