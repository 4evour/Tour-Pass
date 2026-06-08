/**
 * keep_brand_hotels_only.js
 * 只保留品牌酒店，移除非品牌酒店，每城市上限100家（按评分排序保留最优）
 */

const fs = require("fs");
const path = require("path");

const BRAND_KEYWORDS = [
  "如家", "汉庭", "7天", "七天", "全季", "亚朵", "维也纳", "锦江之星",
  "格林豪泰", "桔子", "希尔顿", "万豪", "洲际", "喜来登", "凯悦",
  "丽思卡尔顿", "香格里拉", "华美达", "假日", "豪生", "速8", "速八",
  "宜必思", "美居", "和颐", "星程", "开元", "首旅", "建国", "铂涛",
  "东呈", "尚美", "华住", "漫心", "CitiGO", "欢朋",
  "铂尔曼", "索菲特", "诺富特", "美爵", "瑞吉", "W酒店",
  "威斯汀", "艾美", "JW万豪", "华尔道夫", "安缦", "悦榕庄",
  "半岛", "文华东方", "四季", "柏悦", "安仕达", "傲途格",
  "臻品之选", "源宿", "万枫", "万丽", "福朋", "雅乐轩",
  "丽笙", "丽柏", "丽怡", "康铂", "郁锦香", "凯里亚德",
  "IU", "ZMAX", "潮漫", "非繁城品", "窝趣",
  "花筑", "途窝", "途家", "斯维登", "泊客行", "易佰",
  "布丁", "贝壳", "城市便捷", "都市118", "尚客优", "骏怡",
  "银座佳驿", "驿家365", "百时快捷", "莫泰", "南苑e家",
  "锐思特", "金广快捷", "云上四季", "佳驿", "海友",
  "携程", "你好", "瑞幸", "皇冠", "福朋喜来登",
];

const MAX_PER_CITY = 100;

function isBrandHotel(name) {
  return BRAND_KEYWORDS.some(b => name.includes(b));
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
  const args = { cities: [], dryRun: false };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--cities") args.cities = value.split(",").map(s => s.trim());
    if (key === "--dry-run") args.dryRun = true;
    if (key === "--max") { /* handled below */ }
    if (key === "--help") {
      console.log("Usage: node scripts/keep_brand_hotels_only.js [--cities beijing,shanghai] [--dry-run]");
      process.exit(0);
    }
  }
  return args;
}

function main() {
  const opts = parseArgs(process.argv);
  let cityDirs = opts.cities.length > 0 ? opts.cities :
    fs.readdirSync("data", { withFileTypes: true }).filter(d => d.isDirectory()).map(d => d.name);

  console.log("=== 只保留品牌酒店 ===");
  console.log("城市: " + cityDirs.join(", "));
  console.log("每城市上限: " + MAX_PER_CITY);
  console.log("Dry Run: " + opts.dryRun);
  console.log("");

  let totalBefore = 0, totalAfter = 0;

  for (const cityDir of cityDirs) {
    const poisPath = resolvePoisPath(cityDir);
    if (!poisPath) { console.log(cityDir + ": 无数据"); continue; }

    const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
    const nonHotels = pois.filter(p => p.type !== "hotel");
    const allHotels = pois.filter(p => p.type === "hotel");
    const brandHotels = allHotels.filter(h => isBrandHotel(h.name));
    const nonBrandHotels = allHotels.filter(h => !isBrandHotel(h.name));

    // Sort brand hotels by popularity descending, keep top MAX_PER_CITY
    brandHotels.sort((a, b) => (b.popularity || 0) - (a.popularity || 0));
    const kept = brandHotels.slice(0, MAX_PER_CITY);

    totalBefore += allHotels.length;
    totalAfter += kept.length;

    console.log(cityDir + ": " + allHotels.length + " -> " + kept.length + " hotels (移除 " + nonBrandHotels.length + " 非品牌, 截断 " + Math.max(0, brandHotels.length - MAX_PER_CITY) + ")");

    if (!opts.dryRun) {
      const newPois = [...nonHotels, ...kept];
      fs.writeFileSync(poisPath, JSON.stringify(newPois, null, 2));
    }
  }

  console.log("\n=== 汇总 ===");
  console.log("清洗前: " + totalBefore + " 家酒店");
  console.log("清洗后: " + totalAfter + " 家品牌酒店");
  console.log("移除: " + (totalBefore - totalAfter) + " 家");
}

main();
