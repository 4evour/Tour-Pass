#!/usr/bin/env node
// Generate structured city travel guides using LLM
// Usage: node scripts/generate_city_guides.js [--city beijing] [--concurrency 3]

const fs = require('fs');
const path = require('path');
const https = require('https');

const ALL_CITIES = [
  'beijing','changsha','chengdu','chongqing','dali','guangzhou','guilin',
  'hangzhou','harbin','kunming','lijiang','nanjing','qingdao','sanya',
  'shanghai','shenzhen','suzhou','wuhan','xiamen','xian','zhangjiajie'
];

// Load LLM config
let API_KEY = '', BASE_URL = '', MODEL = '';
try {
  const raw = fs.readFileSync(path.join(__dirname, '..', 'config', 'llm.local.json'), 'utf-8').replace(/^\uFEFF/, '');
  const cfg = JSON.parse(raw);
  if (cfg.api_key) API_KEY = cfg.api_key;
  if (cfg.base_url) BASE_URL = cfg.base_url;
  if (cfg.model) MODEL = cfg.model;
} catch (e) { console.warn('Config error:', e.message); }
if (!API_KEY) API_KEY = process.env.OPENAI_API_KEY || '';
if (!BASE_URL) BASE_URL = 'https://api.deepseek.com';
if (!MODEL) MODEL = 'deepseek-v4-flash';
if (!BASE_URL.endsWith('/v1')) BASE_URL = BASE_URL.replace(/\/+$/, '') + '/v1';

if (!API_KEY) { console.error('Error: No API key'); process.exit(1); }

const args = process.argv.slice(2);
const cityFilter = args.includes('--city') ? args[args.indexOf('--city') + 1] : null;
const CONCURRENCY = args.includes('--concurrency') ? parseInt(args[args.indexOf('--concurrency') + 1]) : 3;

const CITY_NAMES = {
  beijing:'北京',changsha:'长沙',chengdu:'成都',chongqing:'重庆',dali:'大理',
  guangzhou:'广州',guilin:'桂林',hangzhou:'杭州',harbin:'哈尔滨',kunming:'昆明',
  lijiang:'丽江',nanjing:'南京',qingdao:'青岛',sanya:'三亚',shanghai:'上海',
  shenzhen:'深圳',suzhou:'苏州',wuhan:'武汉',xiamen:'厦门',xian:'西安',zhangjiajie:'张家界'
};

function callLLM(prompt) {
  return new Promise((resolve) => {
    const body = JSON.stringify({
      model: MODEL,
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.5,
      max_tokens: 2000,
    });
    const url = new URL(BASE_URL + '/chat/completions');
    const req = https.request({
      hostname: url.hostname, port: 443, path: url.pathname, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body), 'Authorization': 'Bearer ' + API_KEY },
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        if (res.statusCode !== 200) { resolve({ error: `HTTP ${res.statusCode}: ${data.slice(0,200)}` }); return; }
        try {
          const json = JSON.parse(data);
          resolve({ text: json.choices?.[0]?.message?.content?.trim() || '' });
        } catch { resolve({ error: 'parse error' }); }
      });
    });
    req.on('error', e => resolve({ error: e.message }));
    req.setTimeout(60000, () => { req.destroy(); resolve({ error: 'timeout' }); });
    req.write(body);
    req.end();
  });
}

function loadCityData(cityDir) {
  const poisPath = path.join('data', cityDir, 'pois.json');
  const guidePath = path.join('data', cityDir, 'guidebook.json');
  
  let pois = [];
  let guidebook = {};
  
  if (fs.existsSync(poisPath)) {
    pois = JSON.parse(fs.readFileSync(poisPath, 'utf-8'));
  }
  if (fs.existsSync(guidePath)) {
    try { guidebook = JSON.parse(fs.readFileSync(guidePath, 'utf-8')); } catch(e) { /* skip */ }
  }
  
  return { pois, guidebook };
}

function buildPrompt(cityDir, pois, guidebook) {
  const cityName = CITY_NAMES[cityDir] || cityDir;
  
  // Get top attractions
  const attractions = pois
    .filter(p => p.type === 'attraction')
    .sort((a, b) => (b.popularity || 0) - (a.popularity || 0))
    .slice(0, 30)
    .map(p => `- ${p.name}(${p.area}): ${p.description || ''}`.slice(0, 150))
    .join('\n');
  
  // Get top restaurants
  const restaurants = pois
    .filter(p => p.type === 'restaurant')
    .sort((a, b) => (b.popularity || 0) - (a.popularity || 0))
    .slice(0, 15)
    .map(p => `- ${p.name}(${p.area})`)
    .join('\n');
  
  // Guidebook context
  const guideCtx = guidebook?.sections ? [
    guidebook.sections.overview ? `城市概况: ${guidebook.sections.overview.slice(0, 300)}` : '',
    guidebook.sections.climate ? `气候: ${guidebook.sections.climate.slice(0, 200)}` : '',
    guidebook.sections.safety ? `安全: ${guidebook.sections.safety.slice(0, 200)}` : '',
  ].filter(Boolean).join('\n') : '';

  return `你是资深旅行攻略达人。请为${cityName}生成一份结构化旅行攻略。

参考信息：
${guideCtx}

热门景点（按热度排序）：
${attractions}

热门餐厅：
${restaurants}

请严格按以下 JSON 格式输出，不要输出其他内容：
{
  "city": "${cityName}",
  "best_routes": [
    "路线1: 景点A→景点B→景点C（描述为什么这样安排）",
    "路线2: ..."
  ],
  "timing_tips": [
    "景点名: 具体时间建议（如故宫建议早上9点开门就去，至少留半天）",
    "..."
  ],
  "crowd_tips": [
    "避坑建议1（如周末别去南锣鼓巷，人挤人）",
    "..."
  ],
  "food_tips": [
    "美食建议1（如长沙必吃茶颜悦色、文和友小龙虾）",
    "..."
  ],
  "transport_tips": [
    "交通建议1（如北京地铁比打车快，早晚高峰别开车）",
    "..."
  ],
  "seasonal_tips": [
    "季节建议1（如春天去玉渊潭看樱花）",
    "..."
  ],
  "hidden_gems": [
    "隐藏玩法1（如故宫角楼看日落）",
    "..."
  ]
}

要求：
1. 每个类别至少3条，最多8条
2. 基于上面提供的真实景点和餐厅数据
3. 包含具体的实用信息（时间、交通、避坑）
4. 语气轻松自然，像朋友推荐一样`;
}

async function generateCityGuide(cityDir) {
  const { pois, guidebook } = loadCityData(cityDir);
  if (pois.length === 0) return { error: 'no POI data' };

  const prompt = buildPrompt(cityDir, pois, guidebook);
  const result = await callLLM(prompt);
  
  if (result.error) return { error: result.error };
  
  // Parse JSON from response
  try {
    const start = result.text.indexOf('{');
    const end = result.text.lastIndexOf('}');
    if (start === -1 || end === -1) return { error: 'no JSON in response' };
    const jsonStr = result.text.substring(start, end + 1);
    const guide = JSON.parse(jsonStr);
    
    // Write to city_guide.json
    const outPath = path.join('data', cityDir, 'city_guide.json');
    fs.writeFileSync(outPath, JSON.stringify(guide, null, 2), 'utf-8');
    
    return { 
      guide,
      stats: {
        best_routes: (guide.best_routes || []).length,
        timing_tips: (guide.timing_tips || []).length,
        crowd_tips: (guide.crowd_tips || []).length,
        food_tips: (guide.food_tips || []).length,
        transport_tips: (guide.transport_tips || []).length,
      }
    };
  } catch (e) {
    return { error: `JSON parse failed: ${e.message}`, raw: result.text.slice(0, 500) };
  }
}

async function main() {
  const cities = cityFilter ? [cityFilter] : ALL_CITIES;
  console.log(`Generating city guides for ${cities.length} cities...`);
  console.log(`LLM: ${MODEL} | Concurrency: ${CONCURRENCY}\n`);

  let success = 0, failed = 0;
  const globalStart = Date.now();

  // Process cities in batches
  for (let i = 0; i < cities.length; i += CONCURRENCY) {
    const batch = cities.slice(i, i + CONCURRENCY);
    const results = await Promise.all(batch.map(c => generateCityGuide(c)));
    
    for (let j = 0; j < batch.length; j++) {
      const city = batch[j];
      const r = results[j];
      if (r.error) {
        console.log(`${city.padEnd(14)} | ERROR: ${r.error}`);
        failed++;
      } else {
        const s = r.stats;
        console.log(`${city.padEnd(14)} | OK | routes:${s.best_routes} tips:${s.timing_tips} crowd:${s.crowd_tips} food:${s.food_tips} transport:${s.transport_tips}`);
        success++;
      }
    }
  }

  const elapsed = ((Date.now() - globalStart) / 1000).toFixed(0);
  console.log(`\nDone: ${success} success, ${failed} failed in ${elapsed}s`);
}

main().catch(e => { console.error(e); process.exit(1); });
