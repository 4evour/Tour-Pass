#!/usr/bin/env node
// Generate recommendation text for POIs that lack it
// Usage: node scripts/generate_recommendations.js

const fs = require("fs");
const path = require("path");

const CITY_DIRS = [
  { dir: "data", label: "changsha" },
  { dir: "data/wuhan", label: "wuhan" },
  { dir: "data/dali", label: "dali" },
  { dir: "data/lijiang", label: "lijiang" },
  { dir: "data/nanjing", label: "nanjing" },
  { dir: "data/suzhou", label: "suzhou" },
];

// Templates by type
const TEMPLATES = {
  attraction: [
    (p) => `${p.name}是当地热门景点，建议游览${p.visit_duration_minutes || 60}分钟左右`,
    (p) => `推荐${p.area ? "在" + p.area : ""}参观${p.name}，人气评分${(p.popularity || 0).toFixed(1)}`,
    (p) => `${p.name}适合${(p.tags || []).slice(0, 2).join("、")}爱好者`,
  ],
  restaurant: [
    (p) => `${p.name}是当地人气餐厅，推荐尝试特色菜品`,
    (p) => `在${p.area || "当地"}觅食推荐${p.name}，性价比不错`,
    (p) => `${p.name}口碑很好，建议避开高峰期就餐`,
  ],
  hotel: [
    (p) => `${p.name}位置便利，适合作为旅行住宿据点`,
    (p) => `${p.name}位于${p.area || "市中心"}，出行方便`,
    (p) => `推荐入住${p.name}，交通便利`,
  ],
  nightlife: [
    (p) => `${p.name}是夜间休闲好去处`,
    (p) => `晚上去${p.name}感受当地夜生活氛围`,
    (p) => `${p.name}适合饭后散步或消遣`,
  ],
};

function generateRecommendation(poi) {
  if (poi.recommendation && poi.recommendation.length > 5) return poi.recommendation;
  const type = poi.type || "attraction";
  const templates = TEMPLATES[type] || TEMPLATES.attraction;
  // Pick based on hash of POI id for determinism
  const hash = (poi.id || "").split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  const fn = templates[hash % templates.length];
  return fn(poi);
}

let totalUpdated = 0;
let totalSkipped = 0;

for (const city of CITY_DIRS) {
  const poisPath = path.join(city.dir, city.dir === "data" ? "pois.json" : "pois.json");
  if (!fs.existsSync(poisPath)) {
    console.log(`[SKIP] ${poisPath} not found`);
    continue;
  }
  const pois = JSON.parse(fs.readFileSync(poisPath, "utf-8"));
  let updated = 0;
  for (const poi of pois) {
    if (!poi.recommendation || poi.recommendation.length < 5) {
      poi.recommendation = generateRecommendation(poi);
      updated++;
    }
  }
  if (updated > 0) {
    fs.writeFileSync(poisPath, JSON.stringify(pois, null, 2), "utf-8");
    console.log(`[${city.label}] Updated ${updated}/${pois.length} POIs`);
    totalUpdated += updated;
  } else {
    console.log(`[${city.label}] All ${pois.length} POIs already have recommendations`);
    totalSkipped += pois.length;
  }
}

console.log(`\nDone: ${totalUpdated} updated, ${totalSkipped} skipped`);
