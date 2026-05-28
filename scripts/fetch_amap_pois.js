const fs = require("fs");
const path = require("path");

const AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text";
const VALID_TYPES = new Set(["attraction", "restaurant", "hotel", "transit", "nightlife"]);

const DRINK_KEYWORDS = ["茶饮", "冷饮", "甜品", "奶茶", "咖啡", "果汁", "饮品", "茶室", "茶馆", "冰淇淋", "冷饮店", "甜品店"];
const SNACK_KEYWORDS = ["夜市", "烧烤", "甜点", "点心", "面包店", "蛋糕", "串串", "炸鸡", "卤味", "鸭脖", "小吃街", "小吃店", "卤味店"];

function deriveMealType(poiType, tags, categoryName) {
  if (poiType !== "restaurant") return "main";
  // Check category name first (most reliable signal)
  const catLower = (categoryName || "").toLowerCase();
  if (catLower.includes("茶饮") || catLower.includes("茶颜")) return "drink";
  if (catLower.includes("夜市") || catLower.includes("夜游")) return "snack";
  // Check tags
  const lowerTags = tags.map(t => t.toLowerCase());
  for (const kw of DRINK_KEYWORDS) {
    if (lowerTags.some(t => t.includes(kw))) return "drink";
  }
  for (const kw of SNACK_KEYWORDS) {
    if (lowerTags.some(t => t.includes(kw))) return "snack";
  }
  return "main";
}

function parseArgs(argv) {
  const args = {
    config: "config/amap.changsha.json",
    outDir: "output/amap-changsha",
    cacheDir: "output/amap-cache",
    mockDir: "",
    minPois: 0,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--config") args.config = value;
    if (key === "--out-dir") args.outDir = value;
    if (key === "--cache-dir") args.cacheDir = value;
    if (key === "--mock-dir") args.mockDir = value;
    if (key === "--min-pois") args.minPois = Number(value);
    if (key.startsWith("--")) i += 1;
  }
  args.minPois = Math.max(0, Number.isFinite(args.minPois) ? Math.floor(args.minPois) : 0);
  return args;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function sanitizeAmapResponse(json) {
  if (!json || typeof json !== "object") return json;
  const copy = Array.isArray(json) ? [...json] : { ...json };
  delete copy.key;
  delete copy.sec_code;
  delete copy.sec_code_debug;
  return copy;
}

function explainAmapFailure(json, category, page) {
  const info = json?.info || "unknown";
  const infocode = json?.infocode ? `/${json.infocode}` : "";
  let hint = "";
  if (info === "USERKEY_PLAT_NOMATCH" || json?.infocode === "10009") {
    hint = "；请确认 AMAP_API_KEY 是高德开放平台的 Web服务 Key，不是 Web端(JS API)、Android、iOS 或小程序 Key";
  } else if (info === "INVALID_USER_KEY" || json?.infocode === "10001") {
    hint = "；请确认 AMAP_API_KEY 是否复制完整且未被禁用";
  } else if (info === "INSUFFICIENT_PRIVILEGES" || json?.infocode === "10012") {
    hint = "；请确认该 Key 已开通当前 Web 服务接口权限";
  }
  return `AMap search failed for ${category.name} page ${page}: ${info}${infocode}${hint}`;
}

function hashText(value) {
  let hash = 2166136261;
  for (const char of String(value)) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function sanitizeFilePart(value) {
  return String(value || "empty").replace(/[^\p{L}\p{N}_-]+/gu, "_").slice(0, 60);
}

function splitTags(value) {
  if (!value) return [];
  return String(value)
    .split(/[|;,，、\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function typeDefaults(type) {
  if (type === "hotel") return { open: "00:00", close: "23:59", duration: 30, price: 3, tags: ["酒店"] };
  if (type === "restaurant") return { open: "10:00", close: "22:00", duration: 60, price: 2, tags: ["美食"] };
  if (type === "nightlife") return { open: "18:00", close: "23:00", duration: 90, price: 3, tags: ["夜景"] };
  return { open: "09:00", close: "21:30", duration: 90, price: 2, tags: ["城市游览"] };
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

function normalizePoi(amapPoi, category, index) {
  const location = parseLocation(amapPoi.location);
  if (!location) return null;
  const poiType = VALID_TYPES.has(category.poi_type) ? category.poi_type : "attraction";
  const defaults = typeDefaults(poiType);
  const amapId = String(amapPoi.id || "");
  const name = String(amapPoi.name || "").trim();
  if (!name) return null;
  const tags = Array.from(new Set([
    ...defaults.tags,
    ...(Array.isArray(category.tags) ? category.tags : []),
    ...splitTags(amapPoi.type),
    ...splitTags(amapPoi.business_area),
  ])).slice(0, 10);
  const rating = amapPoi.biz_ext && amapPoi.biz_ext.rating && amapPoi.biz_ext.rating !== "[]"
    ? clamp(amapPoi.biz_ext.rating, 0, 10, 7)
    : 7;
  const cost = amapPoi.biz_ext && amapPoi.biz_ext.cost && amapPoi.biz_ext.cost !== "[]"
    ? clamp(Math.round(Number(amapPoi.biz_ext.cost) / 80) + 1, 1, 5, defaults.price)
    : defaults.price;

  return {
    id: `amap_${hashText(amapId || `${name}_${amapPoi.location}_${index}`)}`,
    name,
    type: poiType,
    lat: location.lat,
    lng: location.lng,
    area: String(amapPoi.adname || amapPoi.business_area || category.name || "长沙").trim(),
    open_time: category.open_time || defaults.open,
    close_time: category.close_time || defaults.close,
    visit_duration_minutes: Number(category.visit_duration_minutes || defaults.duration),
    tags,
    popularity: Number(rating.toFixed(1)),
    price_level: cost,
    meal_type: deriveMealType(poiType, tags, category.name),
    description: `${name}，来自高德 Web 服务 POI 搜索；分类：${category.name || poiType}。`,
    source: "amap",
    source_id: amapId,
  };
}

function mockFileFor(mockDir, category, page) {
  const fileName = `search-${sanitizeFilePart(category.name || category.keywords || category.types)}-${page}.json`;
  return path.join(mockDir, fileName);
}

async function fetchSearchPage({ apiKey, city, category, page, pageSize, mockDir, cacheDir }) {
  if (mockDir) {
    return readJson(mockFileFor(mockDir, category, page));
  }

  const params = new URLSearchParams({
    key: apiKey,
    city,
    keywords: category.keywords || "",
    types: category.types || "",
    offset: String(pageSize),
    page: String(page),
    extensions: "all",
    citylimit: "true",
  });
  const url = `${AMAP_PLACE_TEXT_URL}?${params.toString()}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`AMap POI search HTTP ${response.status}`);
  }
  const json = await response.json();
  assertAmapSearchResponse(json, category, page);
  fs.mkdirSync(cacheDir, { recursive: true });
  fs.writeFileSync(
    path.join(cacheDir, `search-${sanitizeFilePart(category.name || category.keywords)}-${page}.json`),
    `${JSON.stringify(sanitizeAmapResponse(json), null, 2)}\n`,
    "utf8",
  );
  return json;
}

function assertAmapSearchResponse(json, category, page) {
  if (!json || typeof json !== "object") {
    throw new Error(`invalid AMap search response for ${category.name} page ${page}`);
  }
  if (String(json.status) !== "1") {
    throw new Error(explainAmapFailure(json, category, page));
  }
  if (!Array.isArray(json.pois)) {
    throw new Error(`AMap search response missing pois array for ${category.name} page ${page}`);
  }
}

async function collectPois(config, options) {
  const apiKey = process.env.AMAP_API_KEY;
  if (!options.mockDir && !apiKey) {
    throw new Error("missing AMAP_API_KEY; use --mock-dir for offline tests");
  }
  const categories = Array.isArray(config.categories) ? config.categories : [];
  const pageSize = Number(config.page_size || 25);
  const maxPages = Number(config.max_pages_per_category || 20);
  const targetCount = Number(config.target_count || 500);
  const byKey = new Map();
  const stats = [];
  let duplicateCount = 0;
  let failedPages = 0;

  for (const category of categories) {
    let categoryAccepted = 0;
    let categoryDuplicates = 0;
    let categoryFailedPages = 0;
    const categoryTarget = Math.max(1, Number(category.target_count || targetCount));
    for (let page = 1; page <= maxPages && categoryAccepted < categoryTarget; page += 1) {
      let json;
      try {
        json = await fetchSearchPage({
          apiKey,
          city: config.city || "长沙",
          category,
          page,
          pageSize,
          mockDir: options.mockDir,
          cacheDir: options.cacheDir,
        });
        assertAmapSearchResponse(json, category, page);
      } catch (error) {
        failedPages += 1;
        categoryFailedPages += 1;
        throw error;
      }
      if (json.pois.length === 0) break;
      json.pois.forEach((item, index) => {
        const poi = normalizePoi(item, category, byKey.size + index);
        if (!poi) return;
        const dedupeKey = poi.source_id || `${poi.name}_${poi.lat}_${poi.lng}`;
        if (!byKey.has(dedupeKey) && categoryAccepted < categoryTarget) {
          byKey.set(dedupeKey, poi);
          categoryAccepted += 1;
        } else {
          duplicateCount += 1;
          categoryDuplicates += 1;
        }
      });
      if (json.pois.length < pageSize) break;
    }
    stats.push({
      name: category.name || category.keywords || category.types || "unknown",
      accepted: categoryAccepted,
      duplicates: categoryDuplicates,
      failed_pages: categoryFailedPages,
    });
  }

  return { pois: [...byKey.values()].slice(0, targetCount), stats, duplicateCount, failedPages };
}

function typeCounts(pois) {
  return pois.reduce((acc, poi) => {
    acc[poi.type] = (acc[poi.type] || 0) + 1;
    return acc;
  }, {});
}

function areaCounts(pois) {
  return pois.reduce((acc, poi) => {
    const area = poi.area || "unknown";
    acc[area] = (acc[area] || 0) + 1;
    return acc;
  }, {});
}

function writeOutputs(config, options, result) {
  if (options.minPois > 0 && result.pois.length < options.minPois) {
    throw new Error(`min-pois gate failed: got ${result.pois.length}, expected at least ${options.minPois}`);
  }
  fs.mkdirSync(options.outDir, { recursive: true });
  const manifest = {
    generated_at: new Date().toISOString(),
    city: config.city || "长沙",
    target_count: Number(config.target_count || 500),
    min_pois: options.minPois,
    poi_count: result.pois.length,
    type_counts: typeCounts(result.pois),
    area_counts: areaCounts(result.pois),
    categories: result.stats,
    duplicate_count: result.duplicateCount || 0,
    failed_pages: result.failedPages || 0,
    source: options.mockDir ? "mock" : "amap_web_service",
    raw_cache_dir: options.cacheDir,
  };
  fs.writeFileSync(path.join(options.outDir, "pois.json"), `${JSON.stringify(result.pois, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(options.outDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  fs.writeFileSync(
    path.join(options.outDir, "real_data_report.md"),
    [
      "# AMap POI Import Report",
      "",
      `- City: ${manifest.city}`,
      `- Source: ${manifest.source}`,
      `- POIs: ${manifest.poi_count}`,
      `- Minimum POI gate: ${manifest.min_pois || "not enforced"}`,
      `- Type counts: ${Object.entries(manifest.type_counts).map(([type, count]) => `${type}=${count}`).join(", ")}`,
      `- Area coverage: ${Object.keys(manifest.area_counts).length} areas`,
      `- Duplicates skipped: ${manifest.duplicate_count}`,
      `- Failed pages: ${manifest.failed_pages}`,
      `- Raw cache: ${manifest.raw_cache_dir}`,
      "",
      "| Category | Accepted POIs | Duplicates | Failed pages |",
      "| --- | ---: | ---: | ---: |",
      ...manifest.categories.map((item) => `| ${item.name} | ${item.accepted} | ${item.duplicates || 0} | ${item.failed_pages || 0} |`),
      "",
    ].join("\n"),
    "utf8",
  );
  return manifest;
}

async function main() {
  const args = parseArgs(process.argv);
  const config = readJson(args.config);
  const result = await collectPois(config, args);
  const manifest = writeOutputs(config, args, result);
  console.log(`AMap POI import written: ${manifest.poi_count} POIs -> ${args.outDir}`);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}

module.exports = {
  collectPois,
  normalizePoi,
  parseArgs,
  writeOutputs,
};
