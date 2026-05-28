const fs = require("fs");
const path = require("path");

const WIKIVOYAGE_API = "https://zh.wikivoyage.org/w/api.php";

function parseArgs(argv) {
  const args = {
    cities: "南京,苏州,丽江,大理,长沙,武汉",
    outDir: "data",
    cacheDir: "output/wikivoyage-cache",
    dryRun: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--cities") args.cities = value;
    if (key === "--out-dir") args.outDir = value;
    if (key === "--cache-dir") args.cacheDir = value;
    if (key === "--dry-run") args.dryRun = true;
    if (key.startsWith("--")) i += 1;
  }
  return args;
}

function cityNameToDir(name) {
  const map = {
    "南京": "nanjing", "苏州": "suzhou", "丽江": "lijiang", "大理": "dali",
    "长沙": "changsha", "武汉": "wuhan", "成都": "chengdu", "重庆": "chongqing",
    "西安": "xian", "杭州": "hangzhou", "北京": "beijing", "上海": "shanghai",
    "广州": "guangzhou", "深圳": "shenzhen", "厦门": "xiamen",
  };
  return map[name] || name;
}

async function fetchWikiArticle(title, cacheDir) {
  const safeName = title.replace(/[\/\\:*?"<>|]/g, "_");
  const cacheFile = path.join(cacheDir, `${safeName}.json`);

  if (fs.existsSync(cacheFile)) {
    return JSON.parse(fs.readFileSync(cacheFile, "utf8"));
  }

  const params = new URLSearchParams({
    action: "parse",
    page: title,
    prop: "wikitext|sections",
    format: "json",
    origin: "*",
  });
  const url = `${WIKIVOYAGE_API}?${params.toString()}`;

  const response = await fetch(url, {
    headers: { "User-Agent": "TourPass/1.0 (travel planner project)" },
  });
  if (!response.ok) {
    throw new Error(`Wikivoyage HTTP ${response.status} for ${title}`);
  }
  const json = await response.json();

  fs.mkdirSync(cacheDir, { recursive: true });
  fs.writeFileSync(cacheFile, JSON.stringify(json, null, 2) + "\n", "utf8");
  return json;
}

function extractSections(wikitext) {
  if (!wikitext) return {};

  const sections = {};
  const lines = wikitext.split("\n");
  let currentSection = "intro";
  let currentContent = [];

  for (const line of lines) {
    const sectionMatch = line.match(/^(={2,3})\s*(.+?)\s*\1\s*$/);
    if (sectionMatch) {
      if (currentContent.length > 0) {
        sections[currentSection] = currentContent.join("\n").trim();
      }
      currentSection = sectionMatch[2].replace(/\s*\[编辑\]|\[edit\]/g, "").trim();
      currentContent = [];
    } else {
      currentContent.push(line);
    }
  }
  if (currentContent.length > 0) {
    sections[currentSection] = currentContent.join("\n").trim();
  }
  return sections;
}

function cleanWikitext(text) {
  if (!text) return "";
  return text
    // Remove templates
    .replace(/\{\{[^}]*\}\}/g, "")
    // Remove wiki links but keep text
    .replace(/\[\[([^\]|]*\|)?([^\]]*)\]\]/g, "$2")
    // Remove external links
    .replace(/\[https?:\/\/[^\s]+ ([^\]]*)\]/g, "$1")
    // Remove references
    .replace(/<ref[^>]*>.*?<\/ref>/gs, "")
    .replace(/<ref[^>]*\/>/g, "")
    // Remove HTML tags
    .replace(/<[^>]+>/g, "")
    // Remove bold/italic markers
    .replace(/'{2,3}/g, "")
    // Clean up extra whitespace
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function extractGuidebook(wikitext) {
  const sections = extractSections(wikitext);
  const guide = {};

  // Key sections to extract
  const sectionMap = {
    "了解": "overview",
    "了解当地": "overview",
    "景点": "attractions",
    "参看": "attractions",
    "活动": "activities",
    "做": "activities",
    "买": "shopping",
    "吃": "food",
    "餐饮": "food",
    "喝": "drinks",
    "夜生活": "nightlife",
    "住宿": "accommodation",
    "到达": "transport",
    "交通": "transport",
    "出行": "get_around",
    "安全": "safety",
    "注意": "safety",
    "气候": "climate",
    "旅行时间": "best_time",
  };

  for (const [sectionName, content] of Object.entries(sections)) {
    for (const [cn, key] of Object.entries(sectionMap)) {
      if (sectionName.includes(cn) && !guide[key]) {
        guide[key] = cleanWikitext(content).slice(0, 2000);
        break;
      }
    }
  }

  return guide;
}

async function fetchCityGuide(cityName, cacheDir) {
  // Try multiple possible article titles
  const candidates = [cityName, `${cityName}市`];
  for (const title of candidates) {
    try {
      const json = await fetchWikiArticle(title, cacheDir);
      if (json.error) {
        console.log(`  ${title}: ${json.error.info || "not found"}`);
        continue;
      }
      if (json.parse?.wikitext?.["*"]) {
        return {
          title: json.parse.title,
          guide: extractGuidebook(json.parse.wikitext["*"]),
          raw_sections: Object.keys(extractSections(json.parse.wikitext["*"])),
        };
      }
    } catch (error) {
      console.log(`  ${title}: ${error.message}`);
    }
  }
  return null;
}

async function main() {
  const args = parseArgs(process.argv);
  const cities = args.cities.split(",").map(s => s.trim()).filter(Boolean);

  console.log(`Fetching Wikivoyage guides for: ${cities.join(", ")}`);

  for (const city of cities) {
    console.log(`\n--- ${city} ---`);
    const result = await fetchCityGuide(city, args.cacheDir);

    if (!result) {
      console.log(`  No Wikivoyage article found for ${city}`);
      continue;
    }

    console.log(`  Found: ${result.title}`);
    console.log(`  Sections: ${result.raw_sections.join(", ")}`);

    const cityDir = cityNameToDir(city);
    const outPath = path.join(args.outDir, cityDir, "guidebook.json");
    const outDirPath = path.join(args.outDir, cityDir);

    if (!args.dryRun) {
      fs.mkdirSync(outDirPath, { recursive: true });
      fs.writeFileSync(outPath, JSON.stringify({
        source: "wikivoyage",
        license: "CC-BY-SA 3.0",
        url: `https://zh.wikivoyage.org/wiki/${encodeURIComponent(result.title)}`,
        city,
        fetched_at: new Date().toISOString(),
        sections: result.guide,
      }, null, 2) + "\n", "utf8");
      console.log(`  Written: ${outPath}`);
      console.log(`  Sections saved: ${Object.keys(result.guide).join(", ")}`);
    }

    // Small delay between requests
    await new Promise(r => setTimeout(r, 500));
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}

module.exports = { extractGuidebook, fetchCityGuide };
