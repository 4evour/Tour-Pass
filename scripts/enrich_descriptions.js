#!/usr/bin/env node
// Enrich POI descriptions using LLM (DeepSeek)
// Usage: node scripts/enrich_descriptions.js [--city wuhan] [--limit 10]
// Requires: OPENAI_API_KEY or LLM env vars, or reads from config/llm.local.json

const fs = require('fs');
const path = require('path');
const https = require('https');

const CITIES = [
  'changsha','wuhan','dali','lijiang','nanjing','suzhou','beijing','chengdu',
  'chongqing','hangzhou','xian','shanghai','guangzhou','shenzhen','xiamen',
  'qingdao','guilin','sanya','harbin','kunming','zhangjiajie'
];

// Load LLM config
let API_KEY = process.env.OPENAI_API_KEY || '';
let BASE_URL = process.env.LLM_BASE_URL || 'https://api.deepseek.com/v1';
let MODEL = process.env.LLM_MODEL || 'deepseek-chat';

// Try loading from config file
try {
  const configPath = path.join(__dirname, '..', 'config', 'llm.local.json');
  if (fs.existsSync(configPath)) {
    const cfg = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
    if (cfg.api_key && !API_KEY) API_KEY = cfg.api_key;
    if (cfg.base_url) BASE_URL = cfg.base_url;
    if (cfg.model) MODEL = cfg.model;
  }
} catch {}

if (!API_KEY) {
  console.error('Error: No LLM API key found. Set OPENAI_API_KEY or create config/llm.local.json');
  process.exit(1);
}

// Parse args
const args = process.argv.slice(2);
const cityFilter = args.includes('--city') ? args[args.indexOf('--city') + 1] : null;
const limitPerCity = args.includes('--limit') ? parseInt(args[args.indexOf('--limit') + 1]) : 999;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function postJSON(urlStr, body, headers) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlStr);
    const postData = JSON.stringify(body);
    const options = {
      hostname: url.hostname,
      port: url.port || 443,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
        ...headers,
      },
    };
    const req = (url.protocol === 'https:' ? https : require('http')).request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (e) { reject(new Error(`Parse error: ${data.substring(0, 100)}`)); }
      });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => { req.destroy(); reject(new Error('timeout')); });
    req.write(postData);
    req.end();
  });
}

async function generateDescription(poi) {
  const prompt = `你是一位旅游攻略达人。请为以下景点写一段简洁的中文介绍（80-120字）。
包含：特色看点、游玩建议、适合人群。
不要写"来自高德"或"POI搜索"等系统文字。用轻松自然的语气。

景点名称：${poi.name}
类型：${poi.type}
区域：${poi.area}
标签：${(poi.tags || []).join('、')}

直接输出介绍文字，不要加标题或前缀。`;

  const resp = await postJSON(`${BASE_URL}/chat/completions`, {
    model: MODEL,
    messages: [{ role: 'user', content: prompt }],
    temperature: 0.7,
    max_tokens: 200,
  }, {
    'Authorization': `Bearer ${API_KEY}`,
  });

  return resp.choices?.[0]?.message?.content?.trim() || '';
}

async function enrichCity(cityName) {
  const f = cityName === 'changsha' ? 'data/pois.json' : path.join('data', cityName, 'pois.json');
  if (!fs.existsSync(f)) return { processed: 0, enriched: 0 };

  const pois = JSON.parse(fs.readFileSync(f, 'utf-8'));
  let enriched = 0;
  let processed = 0;
  let errors = 0;

  // Only enrich POIs with short/template descriptions
  const toEnrich = pois.filter(p => {
    const desc = p.description || '';
    return desc.length < 50 || desc.includes('来自高德') || desc.includes('POI 搜索');
  }).slice(0, limitPerCity);

  for (const poi of toEnrich) {
    processed++;
    try {
      const desc = await generateDescription(poi);
      if (desc && desc.length > 20) {
        poi.description = desc;
        enriched++;
      }
      if (processed % 10 === 0) {
        process.stdout.write(`  ${cityName}: ${processed}/${toEnrich.length} processed, ${enriched} enriched\r`);
      }
      await sleep(200); // Rate limit: ~5 QPS
    } catch (e) {
      errors++;
      if (errors <= 3) console.warn(`  WARN: ${poi.name}: ${e.message}`);
    }
  }

  if (enriched > 0) {
    fs.writeFileSync(f, JSON.stringify(pois, null, 2), 'utf-8');
  }

  return { processed, enriched, errors, total: pois.length };
}

async function main() {
  const cities = cityFilter ? [cityFilter] : CITIES;
  let totalProcessed = 0, totalEnriched = 0;

  console.log(`Using LLM: ${MODEL} at ${BASE_URL}`);
  console.log('');

  for (const city of cities) {
    const result = await enrichCity(city);
    totalProcessed += result.processed;
    totalEnriched += result.enriched;
    console.log(`${city.padEnd(12)} | ${result.processed} processed | ${result.enriched} enriched | ${result.errors} errors | ${result.total} total POIs`);
  }

  console.log(`\nDone: ${totalProcessed} processed, ${totalEnriched} descriptions enriched`);
}

main().catch(e => { console.error(e); process.exit(1); });
