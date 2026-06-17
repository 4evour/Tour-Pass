#!/usr/bin/env node
/**
 * XHS Route Crawler (Browser-based)
 * Uses Playwright to search XHS for complete travel route posts
 * Extracts full note content, then uses LLM to parse structured itineraries
 *
 * Output: data/{city}/xhs_routes.json
 *
 * Usage:
 *   node scripts/crawl_xhs_routes_browser.js --city beijing
 *   node scripts/crawl_xhs_routes_browser.js --city beijing --max-notes 20
 *   node scripts/crawl_xhs_routes_browser.js --all --max-notes 10
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');

// ============ Config ============
const CFG = {
  searchWait: 5000,
  noteWait: 4000,
  maxNotesPerKeyword: 5,
  pageTimeout: 25000,
};

const ALL_CITIES = [
  'beijing','changsha','chengdu','chongqing','dali','guangzhou','guilin',
  'hangzhou','harbin','kunming','lijiang','nanjing','qingdao','sanya',
  'shanghai','shenzhen','suzhou','wuhan','xiamen','xian','zhangjiajie'
];

const CITY_NAMES = {
  beijing:'北京',changsha:'长沙',chengdu:'成都',chongqing:'重庆',dali:'大理',
  guangzhou:'广州',guilin:'桂林',hangzhou:'杭州',harbin:'哈尔滨',kunming:'昆明',
  lijiang:'丽江',nanjing:'南京',qingdao:'青岛',sanya:'三亚',shanghai:'上海',
  shenzhen:'深圳',suzhou:'苏州',wuhan:'武汉',xiamen:'厦门',xian:'西安',zhangjiajie:'张家界'
};

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ============ LLM Config ============
function loadLLMConfig() {
  const cfgPath = path.join(__dirname, '..', 'config', 'llm.local.json');
  let cfg = {};
  if (fs.existsSync(cfgPath)) {
    try { cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf-8').replace(/^\uFEFF/, '')); } catch(e) {}
  }
  return {
    apiKey: cfg.api_key || cfg.apiKey || process.env.DEEPSEEK_API_KEY || '',
    baseUrl: (cfg.base_url || cfg.baseUrl || 'https://api.deepseek.com').replace(/\/+$/, ''),
    model: cfg.model || 'deepseek-chat',
  };
}

function callLLM(llmCfg, sysPrompt, userPrompt) {
  return new Promise((resolve) => {
    const body = JSON.stringify({
      model: llmCfg.model,
      messages: [
        { role: 'system', content: sysPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: 0.1,
      max_tokens: 3000,
    });
    const url = new URL(llmCfg.baseUrl + '/v1/chat/completions');
    const req = https.request({
      hostname: url.hostname, port: 443, path: url.pathname, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + llmCfg.apiKey },
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        if (res.statusCode !== 200) { resolve({ error: 'HTTP ' + res.statusCode + ': ' + data.slice(0, 200) }); return; }
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

// ============ Route Extraction ============
const ROUTE_EXTRACT_PROMPT = `你是旅游路线分析专家。从小红书笔记中提取完整的旅游行程路线。

返回 JSON 对象，格式如下：
{
  "days": 2,
  "travel_style": "休闲/穷游/亲子/情侣/闺蜜/独自旅行",
  "season": "春秋/夏/冬/全年/未提及",
  "budget_hint": "经济/中等/高端/未提及",
  "itinerary": [
    {
      "day": 1,
      "label": "第一天",
      "stops": [
        {
          "time_hint": "上午/中午/下午/傍晚/晚上",
          "name": "景点或地点名称",
          "duration_hint": "2小时/半天/1小时/未提及",
          "activity": "简短活动描述",
          "transport_to_next": "步行/地铁/打车/公交/未提及"
        }
      ]
    }
  ],
  "route_summary": "一句话概括这条路线的核心逻辑",
  "tags": ["关键词标签"]
}

规则：
- 只提取文中明确提到的地点，不编造
- 地点名称保持原文用法
- 如果文中没有明确分天，按时间顺序排列为一天
- stops 的顺序就是游览顺序
- 如果内容不包含完整路线信息（只是单个景点介绍），返回 null
- 只返回 JSON，不要其他文字`;

// ============ Search Keywords ============
function buildKeywords(cityName) {
  return [
    `${cityName}三日游路线`,
    `${cityName}四天三夜攻略`,
    `${cityName}五日游行程`,
    `${cityName}两天一夜路线`,
    `${cityName}旅游路线推荐`,
    `${cityName}经典路线`,
    `${cityName}自由行攻略`,
    `${cityName}一日游路线`,
    `${cityName}周末游攻略`,
    `${cityName}深度游`,
  ];
}

// ============ Progress ============
function getProgFile(city) {
  return path.join(__dirname, 'route_browser_' + city + '_progress.json');
}

function loadProgress(city) {
  const f = getProgFile(city);
  if (fs.existsSync(f)) return JSON.parse(fs.readFileSync(f, 'utf-8'));
  return { done: [], date: new Date().toISOString().split('T')[0] };
}

function saveProgress(city, p) {
  fs.writeFileSync(getProgFile(city), JSON.stringify(p, null, 2), 'utf-8');
}

// ============ Main ============
async function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');
  const runAll = args.includes('--all');
  const cityArg = args.includes('--city') ? args[args.indexOf('--city') + 1] : null;
  const maxNotes = args.includes('--max-notes') ? parseInt(args[args.indexOf('--max-notes') + 1]) : 30;
  const skipLLM = args.includes('--skip-llm');

  const cities = runAll ? ALL_CITIES : (cityArg ? [cityArg] : ['beijing']);

  console.log('\n=== XHS Route Crawler (Browser) ===');
  console.log('Cities:', cities.join(', '));
  console.log('Max notes per city:', maxNotes);
  console.log('Mode:', dryRun ? 'DRY RUN' : 'LIVE');

  const llmCfg = skipLLM ? null : loadLLMConfig();
  console.log('LLM:', llmCfg?.apiKey ? llmCfg.model + ' @ ' + llmCfg.baseUrl : 'DISABLED');

  if (dryRun) {
    for (const city of cities) {
      const name = CITY_NAMES[city] || city;
      console.log(`\n${name} (${city}):`);
      buildKeywords(name).forEach(k => console.log('  -', k));
    }
    return;
  }

  // Load cookies from .env
  const envPath = path.join(__dirname, '..', '.env');
  let rawCookie = '';
  if (fs.existsSync(envPath)) {
    const env = fs.readFileSync(envPath, 'utf-8');
    const m = env.match(/^XHS_COOKIE=(.+)$/m);
    if (m) rawCookie = m[1].trim();
  }
  if (!rawCookie) { console.error('No XHS_COOKIE in .env'); process.exit(1); }

  const cookiePairs = rawCookie.split(/;\s*/).map(p => {
    const i = p.indexOf('=');
    return { name: p.substring(0, i).trim(), value: p.substring(i + 1).trim(), domain: '.xiaohongshu.com', path: '/' };
  }).filter(c => c.name && c.value);

  // Launch browser
  console.log('\nLaunching browser...');
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
    viewport: { width: 1920, height: 1080 },
  });
  await ctx.addCookies(cookiePairs);
  const page = await ctx.newPage();

  for (const city of cities) {
    const cityName = CITY_NAMES[city] || city;
    const outDir = path.join(__dirname, '..', 'data', city);
    const outFile = path.join(outDir, 'xhs_routes.json');
    const prog = loadProgress(city);

    console.log(`\n${'='.repeat(50)}`);
    console.log(`City: ${cityName} (${city})`);
    console.log(`Previously done: ${prog.done.length} notes`);

    // Load existing routes
    let existingRoutes = [];
    if (fs.existsSync(outFile)) {
      try { existingRoutes = JSON.parse(fs.readFileSync(outFile, 'utf-8')); } catch(e) {}
    }

    const keywords = buildKeywords(cityName);
    const collectedNotes = [];
    let noteCount = 0;

    // Search phase
    console.log('\n[1/3] Searching for route notes...');
    for (const kw of keywords) {
      if (noteCount >= maxNotes) break;
      console.log('\n  Search:', kw);

      let searchItems = [];
      const interceptHandler = async (response) => {
        if (response.url().includes('/api/sns/web/v1/search/notes')) {
          try {
            const json = await response.json();
            searchItems = json.data?.items || [];
          } catch(e) {}
        }
      };
      page.on('response', interceptHandler);

      try {
        await page.goto(
          'https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent(kw) + '&source=web_search_result_notes&type=51',
          { waitUntil: 'domcontentloaded', timeout: CFG.pageTimeout }
        );
        await sleep(CFG.searchWait);
      } catch(e) {
        console.log('    Nav error:', e.message);
        page.off('response', interceptHandler);
        continue;
      }
      page.off('response', interceptHandler);

      const validNotes = searchItems
        .filter(i => i.model_type === 'note')
        .filter(i => !prog.done.includes(i.id))
        .slice(0, CFG.maxNotesPerKeyword);

      console.log('    Found', searchItems.length, 'results,', validNotes.length, 'new');

      for (const item of validNotes) {
        const nc = item.note_card || {};
        collectedNotes.push({
          id: item.id,
          xsecToken: item.xsec_token || '',
          title: nc.display_title || '',
          likes: nc.interact_info?.liked_count || '0',
        });
        noteCount++;
        if (noteCount >= maxNotes) break;
      }
    }

    // Deduplicate
    const uniqueNotes = [];
    const seenIds = new Set();
    for (const n of collectedNotes) {
      if (!seenIds.has(n.id)) { seenIds.add(n.id); uniqueNotes.push(n); }
    }
    console.log('\n  Total unique notes to process:', uniqueNotes.length);

    // Detail + extract phase
    console.log('\n[2/3] Fetching details and extracting routes...');
    const routes = [];

    for (const note of uniqueNotes) {
      console.log('\n  Note:', note.title.slice(0, 50), '(' + note.id + ')');

      const noteUrl = 'https://www.xiaohongshu.com/explore/' + note.id
        + '?xsec_token=' + encodeURIComponent(note.xsecToken)
        + '&xsec_source=pc_search';

      // Intercept feed API
      let feedData = null;
      const feedHandler = async (response) => {
        if (response.url().includes('/api/sns/web/v1/feed')) {
          try { feedData = await response.json(); } catch(e) {}
        }
      };
      page.on('response', feedHandler);

      try {
        await page.goto(noteUrl, { waitUntil: 'domcontentloaded', timeout: CFG.pageTimeout });
        await sleep(CFG.noteWait);
      } catch(e) {
        console.log('    Nav error:', e.message);
        page.off('response', feedHandler);
        prog.done.push(note.id);
        saveProgress(city, prog);
        continue;
      }
      page.off('response', feedHandler);

      // Extract content from page
      const content = await page.evaluate(() => {
        const title = (document.querySelector('#detail-title, [class*="title"]') || {}).textContent || '';
        const desc = (document.querySelector('#detail-desc, [class*="desc"]') || {}).textContent || '';
        return { title: title.trim(), desc: desc.trim() };
      });

      // Also try feed API for fuller content
      let fullDesc = content.desc;
      if (feedData?.data?.items?.length > 0) {
        const nc = feedData.data.items[0].note_card || {};
        if ((nc.desc || '').length > fullDesc.length) fullDesc = nc.desc;
      }

      const noteTitle = content.title || note.title;
      console.log('    Title:', noteTitle.slice(0, 40));
      console.log('    Content length:', fullDesc.length, 'chars');

      if (fullDesc.length < 50) {
        console.log('    Too short, skipping');
        prog.done.push(note.id);
        saveProgress(city, prog);
        continue;
      }

      // LLM extraction
      if (llmCfg?.apiKey) {
        const result = await callLLM(
          llmCfg,
          ROUTE_EXTRACT_PROMPT,
          `城市：${cityName}\n标题：${noteTitle}\n内容：\n${fullDesc.slice(0, 5000)}`
        );

        if (result.error) {
          console.log('    LLM error:', result.error);
        } else {
          try {
            const m = result.text.match(/\{[\s\S]*\}/);
            if (m) {
              const route = JSON.parse(m[0]);
              if (route && route.itinerary && route.itinerary.length > 0) {
                const totalStops = route.itinerary.reduce((s, d) => s + (d.stops?.length || 0), 0);
                console.log('    Route: ' + route.days + ' days, ' + totalStops + ' stops');
                routes.push({
                  source_note_id: note.id,
                  source_url: noteUrl,
                  source_title: noteTitle,
                  source_likes: note.likes,
                  crawled_at: new Date().toISOString(),
                  city: city,
                  city_name: cityName,
                  ...route,
                });
              } else {
                console.log('    No route in content (single POI or non-itinerary post)');
              }
            }
          } catch(e) {
            console.log('    JSON parse error:', e.message);
          }
        }
      } else {
        // No LLM: save raw content for later extraction
        routes.push({
          source_note_id: note.id,
          source_url: noteUrl,
          source_title: noteTitle,
          source_likes: note.likes,
          crawled_at: new Date().toISOString(),
          city: city,
          city_name: cityName,
          raw_content: fullDesc.slice(0, 6000),
          route_extracted: false,
        });
      }

      prog.done.push(note.id);
      saveProgress(city, prog);
    }

    // Save
    console.log('\n[3/3] Saving routes...');
    const merged = [...existingRoutes];
    const existingIds = new Set(merged.map(r => r.source_note_id));
    let newCount = 0;
    for (const r of routes) {
      if (!existingIds.has(r.source_note_id)) {
        merged.push(r);
        existingIds.add(r.source_note_id);
        newCount++;
      }
    }
    merged.sort((a, b) => (a.days || 99) - (b.days || 99));

    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(outFile, JSON.stringify(merged, null, 2), 'utf-8');
    console.log(`  Saved: ${merged.length} total routes (${newCount} new) -> ${outFile}`);
  }

  await browser.close();
  console.log('\n=== Done ===');
}

main().catch(e => { console.error('Fatal:', e.message); console.error(e.stack); process.exit(1); });
