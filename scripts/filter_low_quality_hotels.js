/**
 * filter_low_quality_hotels.js
 * 
 * 清洗低质量酒店数据：
 * 1. 移除评分 < 3.0 的酒店
 * 2. 移除名称含低质量关键词且评分 < 3.8 的酒店
 * 3. 移除名称含明显非酒店业态的住宿（日租房、钟点房等）
 * 4. 保留：品牌酒店、高评分民宿/客栈、度假酒店
 */

const fs = require("fs");
const path = require("path");

// 品牌关键词 - 这些酒店永远不会被过滤
const BRAND_KEYWORDS = [
  "如家", "汉庭", "7天", "七天", "全季", "亚朵", "维也纳", "锦江之星",
  "格林豪泰", "桔子", "希尔顿", "万豪", "洲际", "喜来登", "凯悦",
  "丽思卡尔顿", "香格里拉", "华美达", "假日", "豪生", "速8", "速八",
  "宜必思", "美居", "和颐", "星程", "开元", "首旅", "建国", "铂涛",
  "东呈", "尚美", "华住", "携程", "漫心", "CitiGO", "欢朋",
  "铂尔曼", "索菲特", "诺富特", "美爵", "瑞吉", "W酒店",
  "威斯汀", "艾美", "JW万豪", "华尔道夫", "安缦", "悦榕庄",
  "半岛", "文华东方", "四季", "柏悦", "安仕达", "傲途格",
  "臻品之选", "源宿", "万枫", "万丽", "福朋", "雅乐轩",
  "丽笙", "丽柏", "丽怡", "康铂", "郁锦香", "凯里亚德",
  "IU", "你好", "ZMAX", "潮漫", "非繁城品", "窝趣",
  "花筑", "途窝", "途家", "斯维登", "泊客行", "易佰",
  "布丁", "贝壳", "城市便捷", "都市118", "尚客优", "骏怡",
  "银座佳驿", "驿家365", "百时快捷", "莫泰", "南苑e家",
  "锐思特", "金广快捷", "云上四季", "佳驿", "海友",
];

// 低质量关键词 - 评分低于阈值时移除
const LOW_QUALITY_KEYWORDS = [
  "招待所", "出租屋", "日租房", "钟点房", "短租",
  "家庭旅馆", "小旅馆", "个人公寓", "床位",
];

// 中等质量关键词 - 评分低于 3.5 时移除
const MID_QUALITY_KEYWORDS = [
  "旅馆", "宾馆", "旅店", "旅社",
];

// 青旅/民宿/客栈 - 评分低于 3.2 时移除
const HOSTEL_KEYWORDS = [
  "青年旅舍", "青旅", "青年旅社", "国际青旅",
];

// 名称含这些关键词但评分 >= 阈值时保留
const ACCEPTABLE_KEYWORDS = [
  "度假", "精品", "精选", "轻奢", "设计师",
  "网红", "景观", "江景", "海景", "湖景", "山景",
];

function isBrandHotel(name) {
  return BRAND_KEYWORDS.some(b => name.includes(b));
}

function isAcceptable(name, rating) {
  if (isBrandHotel(name)) return true;
  if (ACCEPTABLE_KEYWORDS.some(k => name.includes(k)) && rating >= 3.8) return true;
  return false;
}

function shouldRemove(name, rating) {
  // 品牌酒店永远保留
  if (isBrandHotel(name)) return false;

  // 极低评分直接移除
  if (rating < 3.0) return true;

  // 明确的低质量业态
  if (LOW_QUALITY_KEYWORDS.some(k => name.includes(k))) return true;

  // 青旅类：评分低于 3.5 移除
  if (HOSTEL_KEYWORDS.some(k => name.includes(k)) && rating < 3.5) return true;

  // 旅馆/宾馆/旅店类：评分低于 3.5 移除
  if (MID_QUALITY_KEYWORDS.some(k => name.includes(k)) && rating < 3.5) return true;

  // 民宿/客栈类：评分低于 3.2 移除
  if ((name.includes("民宿") || name.includes("客栈")) && rating < 3.2) return true;

  // 公寓类（非品牌）：评分低于 3.5 移除
  if (name.includes("公寓") && !isAcceptable(name, rating) && rating < 3.5) return true;

  return false;
}

function parseArgs(argv) {
  const args = {
    cities: [],
    dryRun: false,
    minKeep: 20, // 每城市至少保留的酒店数
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--cities") args.cities = value.split(",").map(s => s.trim());
    if (key === "--dry-run") args.dryRun = true;
    if (key === "--min-keep") args.minKeep = Number(value);
    if (key === "--help") {
      console.log("Usage: node scripts/filter_low_quality_hotels.js [--cities beijing,shanghai] [--dry-run] [--min-keep 20]");
      process.exit(0);
    }
  }
  return args;
}

function filterCity(cityDir, opts) {
  const cityPoisPath = path.join("data", cityDir, "pois.json");
  const rootPoisPath = path.join("data", "pois.json");
  const poisPath = fs.existsSync(cityPoisPath) ? cityPoisPath : (fs.existsSync(rootPoisPath) && cityDir === "changsha" ? rootPoisPath : cityPoisPath);
  if (!fs.existsSync(poisPath)) return null;

  const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
  const hotels = pois.filter(p => p.type === "hotel");
  const nonHotels = pois.filter(p => p.type !== "hotel");

  const removed = [];
  const kept = [];

  for (const hotel of hotels) {
    const rating = hotel.popularity || 0;
    const name = hotel.name || "";

    if (shouldRemove(name, rating)) {
      removed.push(hotel);
    } else {
      kept.push(hotel);
    }
  }

  // Ensure minimum hotel count - restore some removed ones if too few remain
  if (kept.length < opts.minKeep && removed.length > 0) {
    // Sort removed by popularity descending, restore enough to hit minKeep
    const deficit = opts.minKeep - kept.length;
    const restored = removed
      .sort((a, b) => (b.popularity || 0) - (a.popularity || 0))
      .slice(0, deficit);
    kept.push(...restored);
    // Remove restored from 'removed' list
    const restoredIds = new Set(restored.map(r => r.id));
    const actuallyRemoved = removed.filter(r => !restoredIds.has(r.id));
    return {
      before: hotels.length,
      after: kept.length,
      removed: actuallyRemoved.length,
      restored: restored.length,
      keptHotels: kept,
      poisPath,
      allPois: [...nonHotels, ...kept],
      removedItems: actuallyRemoved,
    };
  }

  return {
    before: hotels.length,
    after: kept.length,
    removed: removed.length,
    poisPath,
    restored: 0,
    keptHotels: kept,
    allPois: [...nonHotels, ...kept],
    removedItems: removed,
  };
}

function main() {
  const opts = parseArgs(process.argv);

  let cityDirs = opts.cities;
  if (cityDirs.length === 0) {
    cityDirs = fs.readdirSync("data", { withFileTypes: true })
      .filter(d => d.isDirectory())
      .map(d => d.name);
  }

  console.log("=== 酒店质量清洗 ===");
  console.log(`城市: ${cityDirs.join(", ")}`);
  console.log(`最少保留: ${opts.minKeep} 家/城市`);
  console.log(`Dry Run: ${opts.dryRun}`);
  console.log("");

  let totalBefore = 0;
  let totalAfter = 0;
  let totalRemoved = 0;
  let totalRestored = 0;

  for (const cityDir of cityDirs) {
    const result = filterCity(cityDir, opts);
    if (!result) {
      console.log(`${cityDir}: 无数据`);
      continue;
    }

    totalBefore += result.before;
    totalAfter += result.after;
    totalRemoved += result.removed;
    totalRestored += result.restored;

    const diff = result.before - result.after;
    const sign = diff > 0 ? `-${diff}` : diff < 0 ? `+${-diff}` : "±0";
    console.log(`${cityDir}: ${result.before} → ${result.after} (${sign})${result.restored > 0 ? ` [恢复${result.restored}家]` : ""}`);

    // Show some removed examples
    if (result.removedItems.length > 0) {
      const samples = result.removedItems.slice(0, 3).map(h =>
        `  ✗ ${h.name} (评分:${h.popularity})`
      );
      console.log(samples.join("\n"));
    }

    if (!opts.dryRun) {
      fs.writeFileSync(
        result.poisPath,
        JSON.stringify(result.allPois, null, 2)
      );
    }
  }

  console.log(`\n=== 汇总 ===`);
  console.log(`清洗前: ${totalBefore} 家酒店`);
  console.log(`清洗后: ${totalAfter} 家酒店`);
  console.log(`移除: ${totalRemoved} 家`);
  if (totalRestored > 0) console.log(`恢复: ${totalRestored} 家 (保证最低数量)`);
  console.log(`净减少: ${totalBefore - totalAfter} 家`);
}

main();
