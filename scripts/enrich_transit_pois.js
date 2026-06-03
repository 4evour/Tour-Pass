#!/usr/bin/env node
// Enrich transit POIs (train stations, airports) from Amap API
// Usage: node scripts/enrich_transit_pois.js
// Requires: AMAP_KEY environment variable

const fs = require('fs');
const path = require('path');
const https = require('https');

const KEY = process.env.AMAP_API_KEY || process.env.AMAP_KEY;
if (!KEY) { console.error('Error: AMAP_API_KEY not set'); process.exit(1); }

const CITIES = [
  { dir: 'changsha', name: '长沙', adcode: '430100' },
  { dir: 'wuhan', name: '武汉', adcode: '420100' },
  { dir: 'dali', name: '大理', adcode: '290100' },
  { dir: 'lijiang', name: '丽江', adcode: '070100' },
  { dir: 'nanjing', name: '南京', adcode: '320100' },
  { dir: 'suzhou', name: '苏州', adcode: '320500' },
  { dir: 'beijing', name: '北京', adcode: '110100' },
  { dir: 'chengdu', name: '成都', adcode: '510100' },
  { dir: 'chongqing', name: '重庆', adcode: '500100' },
  { dir: 'hangzhou', name: '杭州', adcode: '330100' },
  { dir: 'xian', name: '西安', adcode: '610100' },
  { dir: 'shanghai', name: '上海', adcode: '310100' },
  { dir: 'guangzhou', name: '广州', adcode: '440100' },
  { dir: 'shenzhen', name: '深圳', adcode: '440300' },
  { dir: 'xiamen', name: '厦门', adcode: '350200' },
  { dir: 'qingdao', name: '青岛', adcode: '370200' },
  { dir: 'guilin', name: '桂林', adcode: '450300' },
  { dir: 'sanya', name: '三亚', adcode: '460200' },
  { dir: 'harbin', name: '哈尔滨', adcode: '230100' },
  { dir: 'kunming', name: '昆明', adcode: '530100' },
  { dir: 'zhangjiajie', name: '张家界', adcode: '430800' },
];

const TRANSIT_TYPES = [
  { code: '150100', label: '火车站' },
  { code: '150200', label: '飞机场' },
  { code: '150500', label: '地铁站' },
  { code: '150700', label: '长途汽车站' },
];

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function fetchTransitPois(adcode, cityName) {
  const results = [];
  for (const tt of TRANSIT_TYPES) {
    try {
      const url = `https://restapi.amap.com/v5/place/text?key=${KEY}&city=${encodeURIComponent(cityName)}&types=${tt.code}&page_size=20&page_num=1`;
      const data = await fetchJSON(url);
      if (data.pois) {
        for (const p of data.pois) {
          const [lng, lat] = (p.location || '0,0').split(',').map(Number);
          if (lat === 0 && lng === 0) continue;
          results.push({
            id: 'transit_' + p.id,
            name: p.name,
            type: 'transit',
            area: p.adname || cityName,
            lat, lng,
            popularity: 4.0,
            price_level: 0,
            description: `${p.name}，${cityName}主要${tt.label}。`,
            meal_type: '',
            recommendation: `${p.name}是${cityName}的${tt.label}，适合作为行程起点或终点。`,
            tags: [tt.label, '交通', cityName],
            visit_duration: 15,
          });
        }
      }
      await sleep(200);
    } catch (e) {
      console.warn(`  WARN: ${tt.label} fetch failed: ${e.message}`);
    }
  }
  return results;
}

async function main() {
  let totalAdded = 0;

  for (const city of CITIES) {
    const f = city.dir === 'changsha' ? 'data/pois.json' : path.join('data', city.dir, 'pois.json');
    if (!fs.existsSync(f)) { console.log(`${city.name}: file not found, skip`); continue; }

    const existingPois = JSON.parse(fs.readFileSync(f, 'utf-8'));
    const existingNames = new Set(existingPois.map(p => p.name));

    const transitPois = await fetchTransitPois(city.adcode, city.name);
    const newPois = transitPois.filter(p => !existingNames.has(p.name));

    if (newPois.length > 0) {
      existingPois.push(...newPois);
      fs.writeFileSync(f, JSON.stringify(existingPois, null, 2), 'utf-8');
    }

    totalAdded += newPois.length;
    console.log(`${city.name.padEnd(6)} | ${transitPois.length} found, ${newPois.length} added (${existingPois.length} total)`);
  }

  console.log(`\nDone: ${totalAdded} transit POIs added across all cities`);
}

main().catch(e => { console.error(e); process.exit(1); });
