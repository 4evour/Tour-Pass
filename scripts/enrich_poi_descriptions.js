const fs = require("fs");
const path = require("path");

const LLM_CONFIG_PATH = "config/llm.local.json";

function parseArgs(argv) {
  const args = {
    city: "changsha",
    dataDir: "data",
    dryRun: false,
    limit: 0, // 0 = all POIs
    llmBatchSize: 10,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--city") args.city = value;
    if (key === "--data-dir") args.dataDir = value;
    if (key === "--limit") args.limit = Number(value);
    if (key === "--dry-run") args.dryRun = true;
    if (key.startsWith("--")) i += 1;
  }
  return args;
}

function readJson(filePath) {
  if (!fs.existsSync(filePath)) return null;
  let content = fs.readFileSync(filePath, "utf8");
  // Strip BOM if present
  if (content.charCodeAt(0) === 0xFEFF) content = content.slice(1);
  return JSON.parse(content);
}

function loadLlmConfig() {
  const config = readJson(LLM_CONFIG_PATH);
  if (!config) return null;
  return {
    baseUrl: config.base_url || process.env.LLM_BASE_URL || "https://api.deepseek.com",
    apiKey: config.api_key || process.env.OPENAI_API_KEY || "",
    model: config.model || process.env.LLM_MODEL || "deepseek-chat",
  };
}

async function callLlm(config, systemPrompt, userContent) {
  const url = `${config.baseUrl}/chat/completions`;
  const body = {
    model: config.model,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userContent },
    ],
    temperature: 0.5,
    max_tokens: 500,
  };

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${config.apiKey}`,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`LLM HTTP ${response.status}`);
  }
  const json = await response.json();
  return json.choices?.[0]?.message?.content || "";
}

function findRelevantGuideContext(guidebook, poi) {
  if (!guidebook?.sections) return "";

  const parts = [];
  const sections = guidebook.sections;

  // Match POI type to relevant guide sections
  if (poi.type === "restaurant" || poi.type === "nightlife") {
    if (sections.food) parts.push(`【美食推荐】${sections.food.slice(0, 800)}`);
    if (sections.drinks) parts.push(`【饮品】${sections.drinks.slice(0, 400)}`);
    if (sections.nightlife && poi.type === "nightlife") {
      parts.push(`【夜生活】${sections.nightlife.slice(0, 600)}`);
    }
  } else {
    if (sections.attractions) parts.push(`【景点】${sections.attractions.slice(0, 800)}`);
    if (sections.activities) parts.push(`【活动】${sections.activities.slice(0, 600)}`);
  }

  // Add overview for context
  if (sections.overview) {
    parts.push(`【城市概况】${sections.overview.slice(0, 400)}`);
  }

  return parts.join("\n\n");
}

async function enrichBatch(config, pois, guidebook, batchSize) {
  const systemPrompt = `你是一位旅行攻略编辑。根据提供的城市攻略背景和 POI 信息，为每个 POI 写一句话推荐理由（20-40字），要求：
1. 说出这个地方的特色或亮点
2. 给一个小贴士（最佳时间/必点菜/拍照建议等）
3. 语气亲切自然，像朋友推荐
4. 不要重复 POI 原有的 description 内容

输出格式：每行一个 POI，格式为 "POI_ID|推荐理由"，不要输出其他内容。`;

  let enriched = 0;
  for (let i = 0; i < pois.length; i += batchSize) {
    const batch = pois.slice(i, i + batchSize);
    const guideContext = findRelevantGuideContext(guidebook, batch[0]);

    const poiInfo = batch.map(p => {
      const detail = p.amap_detail || {};
      return [
        `ID: ${p.id}`,
        `名称: ${p.name}`,
        `类型: ${p.type}`,
        `分类: ${p.tags?.join(", ") || ""}`,
        detail.cuisine ? `菜系: ${detail.cuisine}` : "",
        detail.avg_cost ? `人均: ${detail.avg_cost}元` : "",
        `原描述: ${p.description}`,
      ].filter(Boolean).join("\n");
    }).join("\n---\n");

    const userContent = `${guideContext}\n\n---\n\n以下是需要写推荐理由的 POI：\n\n${poiInfo}`;

    try {
      const response = await callLlm(config, systemPrompt, userContent);
      const lines = response.split("\n").filter(l => l.includes("|"));

      for (const line of lines) {
        const [id, ...reasonParts] = line.split("|");
        const reason = reasonParts.join("|").trim();
        const poi = batch.find(p => p.id === id.trim());
        if (poi && reason) {
          poi.recommendation = reason;
          enriched++;
        }
      }

      // Rate limit
      if (i + batchSize < pois.length) {
        await new Promise(r => setTimeout(r, 500));
      }
    } catch (error) {
      console.error(`  LLM batch error at offset ${i}: ${error.message}`);
    }

    if ((i + batchSize) % 50 === 0 || i + batchSize >= pois.length) {
      console.log(`  Progress: ${Math.min(i + batchSize, pois.length)}/${pois.length} (enriched=${enriched})`);
    }
  }

  return enriched;
}

async function main() {
  const args = parseArgs(process.argv);
  const cityDir = args.city;

  // Changsha is special: data/pois.json (not data/changsha/pois.json)
  const poisPath = cityDir === "changsha"
    ? path.join(args.dataDir, "pois.json")
    : path.join(args.dataDir, cityDir, "pois.json");
  const guidebookPath = cityDir === "changsha"
    ? path.join(args.dataDir, "changsha", "guidebook.json") // but guidebook IS in changsha subdir
    : path.join(args.dataDir, cityDir, "guidebook.json");

  const pois = readJson(poisPath);
  if (!pois) {
    console.error(`POIs not found: ${poisPath}`);
    process.exit(1);
  }

  const guidebook = readJson(guidebookPath);

  console.log(`City: ${cityDir}`);
  console.log(`POIs: ${pois.length}`);
  console.log(`Guidebook: ${guidebook ? "loaded (" + Object.keys(guidebook.sections || {}).join(", ") + ")" : "not found"}`);

  // Sort POIs by popularity (enrich top ones first)
  const sorted = [...pois].sort((a, b) => (b.popularity || 0) - (a.popularity || 0));
  const targets = args.limit > 0 ? sorted.slice(0, args.limit) : sorted;

  if (args.dryRun) {
    console.log(`\n[DRY RUN] Would enrich ${targets.length} POIs`);
    targets.slice(0, 5).forEach(p => {
      console.log(`  ${p.name} (${p.type}) - ${p.description.slice(0, 60)}...`);
    });
    return;
  }

  const config = loadLlmConfig();
  if (!config || !config.apiKey) {
    console.error("LLM not configured. Set LLM config in config/llm.local.json or OPENAI_API_KEY env.");
    process.exit(1);
  }

  console.log(`\nEnriching ${targets.length} POIs with LLM (${config.model})...`);
  const enriched = await enrichBatch(config, targets, guidebook, args.llmBatchSize);

  // Write enriched POIs back to the same path
  const outPath = poisPath;
  fs.writeFileSync(outPath, JSON.stringify(pois, null, 2) + "\n", "utf8");
  console.log(`\nWritten: ${outPath}`);
  console.log(`Enriched: ${enriched} POIs with recommendations`);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
