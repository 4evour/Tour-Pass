const fs = require("fs");
const path = require("path");

const AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text";

const BRAND_SEARCHES = [
  { brand: "如家", keywords: "如家酒店", tier: 1 },
  { brand: "汉庭", keywords: "汉庭酒店", tier: 1 },
  { brand: "7天", keywords: "7天酒店", tier: 1 },
  { brand: "全季", keywords: "全季酒店", tier: 2 },
  { brand: "亚朵", keywords: "亚朵酒店", tier: 2 },
  { brand: "维也纳", keywords: "维也纳酒店", tier: 2 },
  { brand: "锦江之星", keywords: "锦江之星", tier: 1 },
  { brand: "格林豪泰", keywords: "格林豪泰", tier: 1 },
  { brand: "桔子", keywords: "桔子酒店", tier: 2 },
  { brand: "希尔顿", keywords: "希尔顿酒店", tier: 3 },
  { brand: "万豪", keywords: "万豪酒店", tier: 3 },
  { brand: "洲际", keywords: "洲际酒店", tier: 3 },
  { brand: "喜来登", keywords: "喜来登酒店", tier: 3 },
  { brand: "凯悦", keywords: "凯悦酒店", tier: 3 },
  { brand: "华住", keywords: "华住会酒店", tier: 2 },
  { brand: "首旅如家", keywords: "首旅如家", tier: 1 },
  { brand: "速8", keywords: "速8酒店", tier: 1 },
  { brand: "宜必思", keywords: "宜必思酒店", tier: 2 },
  { brand: "开元", keywords: "开元大酒店", tier: 3 },
  { brand: "香格里拉", keywords: "香格里拉大酒店", tier: 3 },
  { brand: "丽思卡尔顿", keywords: "丽思卡尔顿", tier: 3 },
  { brand: "美居", keywords: "美居酒店", tier: 2 },
  { brand: "假日", keywords: "假日酒店", tier: 2 },
  { brand: "铂涛", keywords: "铂涛酒店", tier: 2 },
  { brand: "东呈", keywords: "东呈酒店", tier: 2 },
];

const CITIES = {
  beijing: "北京", changsha: "长沙", chengdu: "成都", chongqing: "重庆",
  dali: "大理", guangzhou: "广州", guilin: "桂林", hangzhou: "杭州",
  harbin: "哈尔滨", kunming: "昆明", lijiang: "丽江", nanjing: "南京",
  qingdao: "青岛", sanya: "三亚", shanghai: "上海", shenzhen: "深圳",
  suzhou: "苏州", wuhan: "武汉", xiamen: "厦门", xian: "西安",
  zhangjiajie: "张家界",
};

const TIER_PRICE = { 1: 1, 2: 2, 3: 3 };
const TIER_RATING = { 1: [3.3, 4.2], 2: [3.8, 4.6], 3: [4.2, 4.9] };

function hashText(value) {
  let hash = 2166136261;
  for (const char of String(value)) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
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
  if (cityDir === "changsha") {
    const rootPath = path.join("data", "pois.json");
    if (fs.existsSync(rootPath)) return rootPath;
  }
  return null;
}

function parseArgs(argv) {
  const args = { cities: Object.keys(CITIES), maxPerBrand: 15, dryRun: false, verbose: false };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--cities") args.cities = value.split(",").map(s => s.trim());
    if (key === "--max-per-brand") args.maxPerBrand = Number(value);
    if (key === "--dry-run") args.dryRun = true;
    if (key === "--verbose") args.verbose = true;
    if (key === "--help") {
      console.log("Usage: node scripts/crawl_brand_hotels.js [--cities beijing,shanghai] [--max-per-brand 15] [--dry-run] [--verbose]");
      process.exit(0);
    }
  }
  return args;
}

function normalizeAmapHotel(amapPoi, brandInfo, cityDir, index) {
  const location = parseLocation(amapPoi.location);
  if (!location) return null;
  const amapId = String(amapPoi.id || "");
  const name = String(amapPoi.name || "").trim();
  if (!name) return null;

  const tier = brandInfo.tier;
  const ratingRange = TIER_RATING[tier];
  const rating = amapPoi.biz_ext && amapPoi.biz_ext.rating && amapPoi.biz_ext.rating !== "[]"
    ? clamp(Number(amapPoi.biz_ext.rating), 0, 10, (ratingRange[0] + ratingRange[1]) / 2)
    : +(ratingRange[0] + Math.random() * (ratingRange[1] - ratingRange[0])).toFixed(1);

  const cost = amapPoi.biz_ext && amapPoi.biz_ext.cost && amapPoi.biz_ext.cost !== "[]"
    ? clamp(Math.round(Number(amapPoi.biz_ext.cost) / 80) + 1, 1, 5, TIER_PRICE[tier])
    : TIER_PRICE[tier];

  const tags = Array.from(new Set([
    "住宿", "酒店", brandInfo.brand,
    ...splitTags(amapPoi.type),
    ...splitTags(amapPoi.business_area),
  ])).slice(0, 10);

  const area = String(amapPoi.adname || amapPoi.business_area || "").trim() || "市中心";

  return {
    id: cityDir + "_brand_" + hashText(amapId || name + "_" + index),
    name,
    type: "hotel",
    lat: location.lat,
    lng: location.lng,
    area,
    open_time: "00:00",
    close_time: "23:59",
    visit_duration_minutes: 30,
    tags,
    popularity: Number(rating.toFixed(1)),
    price_level: cost,
    meal_type: "",
    description: name + "，" + brandInfo.brand + "连锁品牌酒店，位于" + area + "，品质有保障。",
    source: "amap",
    source_id: amapId,
    recommendation: brandInfo.brand + "是知名连锁品牌，品质有保障。",
    visit_duration: 30,
  };
}

async function fetchBrandHotelPage(apiKey, cityName, keywords, page, pageSize) {
  const params = new URLSearchParams({
    key: apiKey, city: cityName, keywords, types: "100000",
    offset: String(pageSize), page: String(page), extensions: "all", citylimit: "true",
  });
  const url = AMAP_PLACE_TEXT_URL + "?" + params.toString();
  const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error("HTTP " + response.status);
  const json = await response.json();
  if (String(json.status) !== "1") {
    throw new Error("AMap error: " + (json.info || "unknown"));
  }
  return json.pois || [];
}

async function crawlCityBrands(cityDir, cityName, apiKey, opts) {
  const poisPath = resolvePoisPath(cityDir);
  if (!poisPath) {
    console.log("  " + cityDir + ": no pois.json, skipping");
    return { added: 0, total: 0 };
  }

  const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
  const existingSourceIds = new Set(pois.filter(p => p.source_id).map(p => p.source_id));
  const existingNames = new Set(pois.filter(p => p.type === "hotel").map(p => p.name));
  const existingCount = pois.filter(p => p.type === "hotel").length;

  const newHotels = [];
  let searched = 0;
  let skipped = 0;

  for (const brandInfo of BRAND_SEARCHES) {
    const brandCount = pois.filter(p => p.type === "hotel" && p.name.includes(brandInfo.brand)).length;
    if (brandCount >= 3) {
      if (opts.verbose) console.log("    " + brandInfo.brand + ": already " + brandCount + ", skipping");
      skipped++;
      continue;
    }

    try {
      const amapPois = await fetchBrandHotelPage(apiKey, cityName, brandInfo.keywords, 1, opts.maxPerBrand);
      searched++;

      let added = 0;
      for (const amapPoi of amapPois) {
        const hotel = normalizeAmapHotel(amapPoi, brandInfo, cityDir, newHotels.length);
        if (!hotel) continue;
        if (existingSourceIds.has(hotel.source_id)) continue;
        if (existingNames.has(hotel.name)) continue;
        existingSourceIds.add(hotel.source_id);
        existingNames.add(hotel.name);
        newHotels.push(hotel);
        added++;
      }

      if (opts.verbose) console.log("    " + brandInfo.brand + ": +" + added);
      await new Promise(r => setTimeout(r, 200));
    } catch (err) {
      console.warn("  WARN " + cityDir + "/" + brandInfo.brand + ": " + err.message);
    }
  }

  if (newHotels.length > 0 && !opts.dryRun) {
    pois.push(...newHotels);
    fs.writeFileSync(poisPath, JSON.stringify(pois, null, 2));
  }

  return { added: newHotels.length, total: existingCount + newHotels.length, searched, skipped };
}

async function main() {
  const opts = parseArgs(process.argv);
  const apiKey = process.env.AMAP_API_KEY;
  if (!apiKey) {
    console.error("ERROR: AMAP_API_KEY environment variable is required");
    process.exit(1);
  }

  console.log("=== 品牌酒店抓取 ===");
  console.log("城市: " + opts.cities.join(", "));
  console.log("每品牌最多: " + opts.maxPerBrand);
  console.log("Dry Run: " + opts.dryRun);
  console.log("");

  let totalAdded = 0;

  for (const cityDir of opts.cities) {
    const cityName = CITIES[cityDir];
    if (!cityName) { console.log("SKIP: " + cityDir); continue; }

    console.log(cityName + " (" + cityDir + "):");
    const result = await crawlCityBrands(cityDir, cityName, apiKey, opts);
    console.log("  + " + result.added + " brand hotels -> " + result.total + " total");
    totalAdded += result.added;
  }

  console.log("\n=== Total added: " + totalAdded + " brand hotels ===");
}

main().catch(err => { console.error(err.message); process.exit(1); });
