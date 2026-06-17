#!/usr/bin/env node
// Enrich POI price_level based on name/type/tags rules
// Usage: node scripts/enrich_price_level.js

const fs = require('fs');
const path = require('path');

const CITIES = [
  'changsha','wuhan','dali','lijiang','nanjing','suzhou','beijing','chengdu',
  'chongqing','hangzhou','xian','shanghai','guangzhou','shenzhen','xiamen',
  'qingdao','guilin','sanya','harbin','kunming','zhangjiajie'
];

// Level 0: Free attractions
const FREE_PATTERNS = [
  '公园', '广场', '步行街', '古街', '老街', '商业街', '小吃街',
  '教堂', '寺庙', '祠堂', '故居', '旧址', '遗址',
  '大学', '学院', '图书馆', '美术馆', '画廊',
  '江滩', '海滩', '沙滩', '湖', '河', '江', '溪', '瀑布',
  '山', '峰', '岭', '崖', '洞', '峡谷', '森林', '湿地',
  '桥', '塔', '亭', '阁', '楼', '门', '城墙', '牌坊',
  '纪念馆', '纪念碑', '陵', '墓',
  '夜市', '集市', '市场', '花市',
  '观景台', '观景', '步道', '栈道', '绿道',
];

// Level 3: Expensive attractions
const EXPENSIVE_PATTERNS = [
  '乐园', '世界', '主题', '水上', '滑雪', '温泉',
  '海底', '海洋馆', '水族馆', '动物园',
];

// High-price whitelist (known expensive attractions)
const HIGH_PRICE_WHITELIST = {
  '张家界国家森林公园': 3, '天门山国家森林公园': 3,
  '上海迪士尼乐园': 3, '北京环球影城': 3, '长隆欢乐世界': 3,
  '三亚亚特兰蒂斯': 3, '黄山风景区': 3, '九寨沟': 3,
  '故宫博物院': 2, '兵马俑': 2, '布达拉宫': 2,
  '东方明珠': 2, '广州塔': 2, '黄鹤楼': 2,
  '拙政园': 2, '留园': 2, '颐和园': 2, '圆明园': 2,
  '西湖游船': 2, '漓江游船': 2,
};

function inferPriceLevel(poi) {
  // Check whitelist first
  if (HIGH_PRICE_WHITELIST[poi.name]) return HIGH_PRICE_WHITELIST[poi.name];

  // By type
  if (poi.type === 'restaurant') return 1;
  if (poi.type === 'nightlife') return 2;
  if (poi.type === 'hotel') return 1;
  if (poi.type === 'transit') return 0;

  // Attraction: check name patterns
  const name = poi.name || '';
  const tags = (poi.tags || []).join(' ');

  // Free patterns
  for (const p of FREE_PATTERNS) {
    if (name.includes(p) || tags.includes(p)) return 0;
  }

  // Expensive patterns
  for (const p of EXPENSIVE_PATTERNS) {
    if (name.includes(p)) return 3;
  }

  // Default for attractions
  return 1;
}

let totalProcessed = 0;
let totalChanged = 0;
const stats = { 0: 0, 1: 0, 2: 0, 3: 0 };

for (const city of CITIES) {
  const f = path.join('data', city, 'pois.json');
  if (!fs.existsSync(f)) continue;

  const pois = JSON.parse(fs.readFileSync(f, 'utf-8'));
  let changed = 0;

  for (const poi of pois) {
    const oldLevel = poi.price_level || 0;
    const newLevel = inferPriceLevel(poi);
    if (newLevel !== oldLevel) {
      poi.price_level = newLevel;
      changed++;
    }
    stats[newLevel] = (stats[newLevel] || 0) + 1;
    totalProcessed++;
  }

  if (changed > 0) {
    fs.writeFileSync(f, JSON.stringify(pois, null, 2), 'utf-8');
  }
  totalChanged += changed;
  console.log(`${city.padEnd(12)} | ${pois.length} POIs | ${changed} changed`);
}

console.log('-'.repeat(50));
console.log(`Total: ${totalProcessed} processed, ${totalChanged} changed`);
console.log(`Price distribution: Level 0=${stats[0]}, Level 1=${stats[1]}, Level 2=${stats[2]}, Level 3=${stats[3]}`);
