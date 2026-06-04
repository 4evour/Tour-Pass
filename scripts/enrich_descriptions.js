#!/usr/bin/env node
// Enrich POI descriptions using LLM (DeepSeek) — batch concurrent mode
// Usage: node scripts/enrich_descriptions.js [--city wuhan] [--limit 10] [--concurrency 10]

const fs = require('fs');
const path = require('path');
const https = require('https');

const CITIES = [
  'lijiang','nanjing','suzhou','beijing','chengdu',
  'chongqing','hangzhou','xian','shanghai','guangzhou','shenzhen','xiamen',
  'qingdao','guilin','sanya','harbin','kunming','zhangjiajie'
  // changsha, wuhan, dali already done
];

// Load LLM config
let API_KEY = '', BASE_URL = '', MODEL = '';
try {
  const raw = fs.readFileSync(path.join(__dirname, '..', 'config', 'llm.local.json'), 'utf-8').replace(/^﻿/, '');
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
const limitPerCity = args.includes('--limit') ? parseInt(args[args.indexOf('--limit') + 1]) : 9999;
const CONCURRENCY = args.includes('--concurrency') ? parseInt(args[args.indexOf('--concurrency') + 1]) : 10;

function callLLM(poi) {
  return new Promise((resolve) => {
    const prompt = `你是一位旅游攻略达人。请为以下景点写一段简洁的中文介绍（80-120字）。
包含：特色看点、游玩建议、适合人群。
不要写"来自高德"或"POI搜索"等系统文字。用轻松自然的语气。

景点名称：${poi.name}
类型：${poi.type}
区域：${poi.area}
标签：${(poi.tags || []).join('、')}

直接输出介绍文字，不要加标题或前缀。`;

    const body = JSON.stringify({
      model: MODEL,
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.7,
      max_tokens: 200,
    });

    const url = new URL(BASE_URL + '/chat/completions');
    const req = https.request({
      hostname: url.hostname, port: 443, path: url.pathname, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body), 'Authorization': 'Bearer ' + API_KEY },
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        if (res.statusCode !== 200) { resolve({ poi, error: `HTTP ${res.statusCode}` }); return; }
        try {
          const json = JSON.parse(data);
          const text = json.choices?.[0]?.message?.content?.trim() || '';
          resolve({ poi, text });
        } catch { resolve({ poi, error: 'parse' }); }
      });
    });
    req.on('error', e => resolve({ poi, error: e.message }));
    req.setTimeout(15000, () => { req.destroy(); resolve({ poi, error: 'timeout' }); });
    req.write(body);
    req.end();
  });
}

async function enrichCity(cityName) {
  const f = cityName === 'changsha' ? 'data/pois.json' : path.join('data', cityName, 'pois.json');
  if (!fs.existsSync(f)) return { processed: 0, enriched: 0 };

  const pois = JSON.parse(fs.readFileSync(f, 'utf-8'));

  // Find indices of POIs that need enrichment
  const indices = [];
  for (let i = 0; i < pois.length; i++) {
    const p = pois[i];
    if (p.type === 'transit' || p.type === 'hotel') continue;
    const desc = p.description || '';
    if (desc.length < 50 || desc.includes('来自高德') || desc.includes('POI 搜索')) {
      indices.push(i);
    }
  }
  const toProcess = indices.slice(0, limitPerCity);
  if (toProcess.length === 0) return { processed: 0, enriched: 0, errors: 0, total: pois.length };

  let enriched = 0, errors = 0;
  const startTime = Date.now();

  // Process in concurrent batches
  for (let i = 0; i < toProcess.length; i += CONCURRENCY) {
    const batch = toProcess.slice(i, i + CONCURRENCY).map(idx => callLLM(pois[idx]));
    const results = await Promise.all(batch);

    for (const r of results) {
      if (r.text && r.text.length > 20) {
        r.poi.description = r.text;
        enriched++;
      } else if (r.error) {
        errors++;
        if (errors <= 5) console.warn(`  WARN: ${r.poi.name}: ${r.error}`);
      }
    }

    const done = Math.min(i + CONCURRENCY, toProcess.length);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
    const eta = Math.ceil(((toProcess.length - done) / (done / (Date.now() - startTime))) / 1000 / 60);
    process.stdout.write(`  ${cityName}: ${done}/${toProcess.length} | ${enriched} enriched | ${elapsed}s | ~${eta}min left   \r`);
  }

  console.log('');
  if (enriched > 0) {
    fs.writeFileSync(f, JSON.stringify(pois, null, 2), 'utf-8');
  }

  return { processed: toProcess.length, enriched, errors, total: pois.length };
}

async function main() {
  const cities = cityFilter ? [cityFilter] : CITIES;
  let totalProcessed = 0, totalEnriched = 0, totalErrors = 0;
  const globalStart = Date.now();

  console.log(`LLM: ${MODEL} | Concurrency: ${CONCURRENCY}`);
  console.log('');

  for (const city of cities) {
    const result = await enrichCity(city);
    totalProcessed += result.processed;
    totalEnriched += result.enriched;
    totalErrors += result.errors;
    const elapsed = ((Date.now() - globalStart) / 1000 / 60).toFixed(1);
    console.log(`${city.padEnd(12)} | ${result.processed} done | ${result.enriched} enriched | ${result.errors} err | ${elapsed}min total`);
  }

  const totalTime = ((Date.now() - globalStart) / 1000 / 60).toFixed(1);
  console.log(`\nDone: ${totalProcessed} processed, ${totalEnriched} enriched, ${totalErrors} errors in ${totalTime} min`);
}

main().catch(e => { console.error(e); process.exit(1); });
