const fs = require("fs");
const path = require("path");

const AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text";

const CITIES = {
  beijing: { name: "北京", center: "116.4074,39.9042" },
  changsha: { name: "长沙", center: "112.9388,28.2282" },
  chengdu: { name: "成都", center: "104.0668,30.5728" },
  chongqing: { name: "重庆", center: "106.5516,29.563" },
  dali: { name: "大理", center: "100.225,25.589" },
  guangzhou: { name: "广州", center: "113.2644,23.1291" },
  guilin: { name: "桂林", center: "110.29,25.274" },
  hangzhou: { name: "杭州", center: "120.1551,30.2741" },
  harbin: { name: "哈尔滨", center: "126.6424,45.757" },
  kunming: { name: "昆明", center: "102.7183,25.0389" },
  lijiang: { name: "丽江", center: "100.225,26.872" },
  nanjing: { name: "南京", center: "118.7969,32.0603" },
  qingdao: { name: "青岛", center: "120.3826,36.0671" },
  sanya: { name: "三亚", center: "109.512,18.2528" },
  shanghai: { name: "上海", center: "121.4737,31.2304" },
  shenzhen: { name: "深圳", center: "114.0579,22.5431" },
  suzhou: { name: "苏州", center: "120.5853,31.299" },
  wuhan: { name: "武汉", center: "114.3055,30.5928" },
  xiamen: { name: "厦门", center: "118.0894,24.4798" },
  xian: { name: "西安", center: "108.9398,34.3416" },
  zhangjiajie: { name: "张家界", center: "110.4793,29.117" },
};

// 搜索关键词 - 覆盖各类景点
const ATTRACTION_SEARCHES = [
  { keywords: "景点", types: "110000", tags: ["景点", "城市游览"], target: 60 },
  { keywords: "博物馆", types: "140000", tags: ["博物馆", "室内"], target: 30 },
  { keywords: "公园", types: "110100", tags: ["公园", "户外"], target: 30 },
  { keywords: "景区", types: "110000", tags: ["景区", "风景名胜"], target: 40 },
  { keywords: "寺庙", types: "110000", tags: ["宗教", "历史文化"], target: 15 },
  { keywords: "古镇", types: "110000", tags: ["古镇", "历史文化"], target: 20 },
  { keywords: "步行街 商圈", types: "060000", tags: ["商圈", "购物"], target: 25 },
  { keywords: "夜市 夜景", types: "050000|060000", tags: ["夜景", "夜市"], target: 15 },
  { keywords: "海滩 温泉", types: "110000|080000", tags: ["休闲", "度假"], target: 15 },
];

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

// 根据景点类型和名称推断合理评分
function inferPopularity(amapPoi, name) {
  // 如果高德有评分就用
  if (amapPoi.biz_ext && amapPoi.biz_ext.rating && amapPoi.biz_ext.rating !== "[]") {
    return clamp(Number(amapPoi.biz_ext.rating), 0, 5, 4.0);
  }
  // 根据类型和名称推断
  const type = (amapPoi.type || "").toLowerCase();
  const tname = name.toLowerCase();
  
  // 知名景点高分
  if (tname.includes("故宫") || tname.includes("长城") || tname.includes("天安门")) return 4.9;
  if (tname.includes("西湖") || tname.includes("外滩") || tname.includes("东方明珠")) return 4.8;
  if (tname.includes("兵马俑") || tname.includes("大雁塔")) return 4.8;
  if (tname.includes("鼓浪屿") || tname.includes("曾厝垵")) return 4.7;
  if (tname.includes("迪士") || tname.includes("环球影城") || tname.includes("欢乐谷")) return 4.7;
  if (tname.includes("国家森林") || tname.includes("国家公园") || tname.includes("5A")) return 4.6;
  
  // 按类型给基础分
  if (type.includes("博物馆")) return 4.3;
  if (type.includes("公园") || type.includes("广场")) return 4.0;
  if (type.includes("寺庙") || type.includes("教堂")) return 4.1;
  if (type.includes("古") || tname.includes("古城")) return 4.2;
  if (type.includes("风景名胜")) return 4.4;
  if (type.includes("世界遗产")) return 4.8;
  
  // 默认
  return 3.8;
}

// 判断是否是优质景点（值得推荐）
function isQualityAttraction(name, popularity) {
  const blacklisted = [
    "停车场", "厕所", "洗手间", "ATM", "取款机",
    "小卖部", "便利店", "超市", "商店", "售楼处",
    "加油站", "充电站", "维修", "回收", "废品",
    "工地", "工厂", "仓库", "物流", "快递",
    "诊所", "医院", "药店", "卫生院",
    "学校", "幼儿园", "培训", "辅导",
    "银行", "电信", "移动", "联通",
    "公墓", "殡仪", "陵园",
  ];
  if (blacklisted.some(b => name.includes(b))) return false;
  if (popularity < 3.0) return false;
  return true;
}

function normalizeAttraction(amapPoi, category, existingIds, index) {
  const location = parseLocation(amapPoi.location);
  if (!location) return null;
  const amapId = String(amapPoi.id || "");
  const name = String(amapPoi.name || "").trim();
  if (!name) return null;
  if (existingIds.has(amapId)) return null;

  const popularity = inferPopularity(amapPoi, name);
  if (!isQualityAttraction(name, popularity)) return null;

  const tags = Array.from(new Set([
    ...(Array.isArray(category.tags) ? category.tags : []),
    ...splitTags(amapPoi.type),
    ...splitTags(amapPoi.business_area),
    "景点",
  ])).slice(0, 10);

  const area = String(amapPoi.adname || amapPoi.business_area || "").trim() || "市中心";

  return {
    id: "amap_" + hashText(amapId || name + "_" + index),
    name,
    type: "attraction",
    lat: location.lat,
    lng: location.lng,
    area,
    open_time: "09:00",
    close_time: "21:30",
    visit_duration_minutes: 90,
    tags,
    popularity: Number(popularity.toFixed(1)),
    price_level: 0,
    meal_type: "main",
    description: name + "，当地热门景点，建议游览90分钟左右。",
    source: "amap",
    source_id: amapId,
    recommendation: name + "是当地热门景点。",
    open_minutes: 540,
    close_minutes: 1290,
    visit_duration: 90,
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

async function crawlCityAttractions(cityDir, cityInfo, apiKey, opts) {
  const poisPath = resolvePoisPath(cityDir);
  if (!poisPath) { console.log("  " + cityDir + ": no data"); return { added: 0 }; }

  const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
  const existingIds = new Set(pois.filter(p => p.source_id).map(p => p.source_id));
  const existingNames = new Set(pois.filter(p => p.type === "attraction").map(p => p.name));
  const existingCount = pois.filter(p => p.type === "attraction").length;

  const newPois = [];
  for (const search of ATTRACTION_SEARCHES) {
    let page = 1, added = 0;
    while (added < search.target && page <= 3) {
      try {
        const amapPois = await fetchPage(apiKey, cityInfo.name, search.keywords, search.types, page, 25);
        if (amapPois.length === 0) break;
        for (const ap of amapPois) {
          const poi = normalizeAttraction(ap, search, existingIds, newPois.length);
          if (!poi) continue;
          if (existingNames.has(poi.name)) continue;
          existingIds.add(poi.source_id);
          existingNames.add(poi.name);
          newPois.push(poi);
          added++;
        }
        page++;
        await new Promise(r => setTimeout(r, 200));
      } catch (err) {
        console.warn("  WARN " + search.keywords + " p" + page + ": " + err.message);
        break;
      }
    }
  }

  if (newPois.length > 0 && !opts.dryRun) {
    pois.push(...newPois);
    fs.writeFileSync(poisPath, JSON.stringify(pois, null, 2));
  }

  return { added: newPois.length, total: existingCount + newPois.length };
}

async function main() {
  const apiKey = process.env.AMAP_API_KEY;
  if (!apiKey) { console.error("ERROR: AMAP_API_KEY required"); process.exit(1); }

  const opts = { dryRun: false };
  const cities = process.argv.includes("--dry-run") ? [] : Object.keys(CITIES);
  if (process.argv.includes("--dry-run")) opts.dryRun = true;

  const targetCities = [];
  for (let i = 2; i < process.argv.length; i++) {
    if (process.argv[i] === "--cities" && process.argv[i+1]) {
      targetCities.push(...process.argv[i+1].split(",").map(s=>s.trim()));
    }
  }
  const cityList = targetCities.length > 0 ? targetCities : Object.keys(CITIES);

  console.log("=== 景点补抓 ===");
  console.log("Dry Run: " + opts.dryRun);
  console.log("");

  let totalAdded = 0;
  for (const cityDir of cityList) {
    const cityInfo = CITIES[cityDir];
    if (!cityInfo) continue;
    console.log(cityInfo.name + " (" + cityDir + "):");
    const result = await crawlCityAttractions(cityDir, cityInfo, apiKey, opts);
    console.log("  +" + result.added + " attractions -> " + result.total + " total");
    totalAdded += result.added;
  }
  console.log("\n=== Total added: " + totalAdded + " attractions ===");
}

main().catch(err => { console.error(err.message); process.exit(1); });
