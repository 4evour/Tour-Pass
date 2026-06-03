#!/usr/bin/env node
// Enrich POI open_hours from Amap detail API
// Usage: node scripts/enrich_open_hours.js [--city wuhan] [--limit 50]
// Requires: AMAP_KEY environment variable

const fs = require('fs');
const path = require('path');
const https = require('https');

const KEY = process.env.AMAP_API_KEY || process.env.AMAP_KEY;
if (!KEY) { console.error('Error: AMAP_API_KEY not set'); process.exit(1); }

const CITIES = [
  'changsha','wuhan','dali','lijiang','nanjing','suzhou','beijing','chengdu',
  'chongqing','hangzhou','xian','shanghai','guangzhou','shenzhen','xiamen',
  'qingdao','guilin','sanya','harbin','kunming','zhangjiajie'
];

// Parse args
const args = process.argv.slice(2);
const cityFilter = args.includes('--city') ? args[args.indexOf('--city') + 1] : null;
const limitPerCity = args.includes('--limit') ? parseInt(args[args.indexOf('--limit') + 1]) : 999;

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.setTimeout(5000, () => { req.destroy(); reject(new Error('timeout')); });
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// Parse business_time string like "08:00-18:00" or "08:00-17:30 (周一至周日)"
function parseTimeRange(str) {
  if (!str) return null;
  const match = str.match(/(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})/);
  if (!match) return null;
  return {
    open: parseInt(match[1]) * 60 + parseInt(match[2]),
    close: parseInt(match[3]) * 60 + parseInt(match[4]),
  };
}

async function enrichCity(cityName) {
  const f = cityName === 'changsha' ? 'data/pois.json' : path.join('data', cityName, 'pois.json');
  if (!fs.existsSync(f)) return { processed: 0, enriched: 0 };

  const pois = JSON.parse(fs.readFileSync(f, 'utf-8'));
  let enriched = 0;
  let processed = 0;
  let skipped = 0;

  // Only enrich attractions and restaurants (skip hotels, transit)
  const toEnrich = pois.filter(p =>
    (p.type === 'attraction' || p.type === 'restaurant' || p.type === 'nightlife') &&
    p.open_minutes == null
  ).slice(0, limitPerCity);

  for (const poi of toEnrich) {
    processed++;
    try {
      // Use Amap v5 text search API with show_fields=business for open hours
      const url = `https://restapi.amap.com/v5/place/text?key=${KEY}&keywords=${encodeURIComponent(poi.name)}&city=${encodeURIComponent(cityName)}&page_size=1&show_fields=business`;
      const data = await fetchJSON(url);

      if (data.pois && data.pois.length > 0) {
        const detail = data.pois[0];
        // Open hours are in business.opentime_today or business.opentime_week
        const biz = detail.business || {};
        const bt = biz.opentime_today || biz.opentime_week || '';

        let timeRange = parseTimeRange(bt);

        if (timeRange) {
          poi.open_minutes = timeRange.open;
          poi.close_minutes = timeRange.close;
          enriched++;
        }
      }

      if (processed % 50 === 0) {
        process.stdout.write(`  ${cityName}: ${processed}/${toEnrich.length} processed, ${enriched} enriched\r`);
      }
      await sleep(100); // Rate limit: ~10 QPS
    } catch (e) {
      skipped++;
      if (skipped <= 3) console.warn(`  WARN: ${poi.name}: ${e.message}`);
    }
  }

  if (enriched > 0) {
    fs.writeFileSync(f, JSON.stringify(pois, null, 2), 'utf-8');
  }

  return { processed, enriched, skipped, total: pois.length };
}

async function main() {
  const cities = cityFilter ? [cityFilter] : CITIES;
  let totalProcessed = 0, totalEnriched = 0;

  for (const city of cities) {
    const result = await enrichCity(city);
    totalProcessed += result.processed;
    totalEnriched += result.enriched;
    console.log(`${city.padEnd(12)} | ${result.processed} processed | ${result.enriched} enriched | ${result.skipped} errors | ${result.total} total POIs`);
  }

  console.log(`\nDone: ${totalProcessed} processed, ${totalEnriched} enriched with open hours`);
}

main().catch(e => { console.error(e); process.exit(1); });
