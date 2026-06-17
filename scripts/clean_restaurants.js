const fs = require("fs");
const path = require("path");

function resolvePoisPath(cityDir) {
  const cityPath = path.join("data", cityDir, "pois.json");
  if (fs.existsSync(cityPath)) return cityPath;
  return null;
}

// 提取品牌名（去掉括号里的分店信息）
function extractBrand(name) {
  return name.replace(/\(.*?\)/g, "").replace(/（.*?）/g, "").replace(/·.*/g, "").trim().slice(0, 8);
}

const LOW_KEYWORDS = [
  "路边摊", "流动", "推车", "小摊", "摆摊", "无名", "临时",
  "地沟", "出租屋", "住宅", "棋牌", "网吧", "台球",
  "便利店", "超市", "小卖部", "副食", "烟酒",
  "维修", "回收", "废品", "五金", "建材",
  "诊所", "药店", "卫生", "按摩", "足浴", "洗浴",
  "美发", "美容", "美甲", "纹身", "宠物",
];

function main() {
  const cityDirs = fs.readdirSync("data", { withFileTypes: true })
    .filter(d => d.isDirectory()).map(d => d.name);

  console.log("=== 餐饮清洗 ===\n");

  let totalBefore = 0, totalAfter = 0, totalRemoved = 0;

  for (const cityDir of cityDirs) {
    const poisPath = resolvePoisPath(cityDir);
    if (!poisPath) continue;

    const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
    const nonRest = pois.filter(p => p.type !== "restaurant");
    const restaurants = pois.filter(p => p.type === "restaurant");

    // 1. 移除低质量
    const cleaned = restaurants.filter(r => {
      if (LOW_KEYWORDS.some(k => r.name.includes(k))) return false;
      if (r.popularity && r.popularity < 3.0) return false;
      return true;
    });

    // 2. 按品牌去重（同品牌最多保留3家，按评分排序）
    const byBrand = {};
    cleaned.forEach(r => {
      const brand = extractBrand(r.name);
      if (!byBrand[brand]) byBrand[brand] = [];
      byBrand[brand].push(r);
    });

    const kept = [];
    let deduped = 0;
    for (const [brand, items] of Object.entries(byBrand)) {
      if (items.length > 3) {
        items.sort((a, b) => (b.popularity || 0) - (a.popularity || 0));
        kept.push(...items.slice(0, 3));
        deduped += items.length - 3;
      } else {
        kept.push(...items);
      }
    }

    // 3. 保证最少40家
    if (kept.length < 40 && cleaned.length >= 40) {
      cleaned.sort((a, b) => (b.popularity || 0) - (a.popularity || 0));
      kept.length = 0;
      kept.push(...cleaned.slice(0, 40));
    }

    const removed = restaurants.length - kept.length;
    totalBefore += restaurants.length;
    totalAfter += kept.length;
    totalRemoved += removed;

    if (removed > 0) {
      console.log(cityDir + ": " + restaurants.length + " -> " + kept.length + " (-" + removed + ")");
      fs.writeFileSync(poisPath, JSON.stringify([...nonRest, ...kept], null, 2));
    } else {
      console.log(cityDir + ": " + restaurants.length + " (unchanged)");
    }
  }

  console.log("\n=== 汇总 ===");
  console.log("清洗前: " + totalBefore);
  console.log("清洗后: " + totalAfter);
  console.log("移除: " + totalRemoved + " (低质量+" + "品牌过多分店)");
}

main();
