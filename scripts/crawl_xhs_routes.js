#!/usr/bin/env node
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');

const CFG = { searchWait: 6000, noteWait: 4000, maxPerKw: 8, pageTimeout: 25000, kwPause: 3000 };
const ALL_CITIES = ['beijing','changsha','chengdu','chongqing','dali','guangzhou','guilin','hangzhou','harbin','kunming','lijiang','nanjing','qingdao','sanya','shanghai','shenzhen','suzhou','wuhan','xiamen','xian','zhangjiajie'];
const CITY_NAMES = {beijing:'北京',changsha:'长沙',chengdu:'成都',chongqing:'重庆',dali:'大理',guangzhou:'广州',guilin:'桂林',hangzhou:'杭州',harbin:'哈尔滨',kunming:'昆明',lijiang:'丽江',nanjing:'南京',qingdao:'青岛',sanya:'三亚',shanghai:'上海',shenzhen:'深圳',suzhou:'苏州',wuhan:'武汉',xiamen:'厦门',xian:'西安',zhangjiajie:'张家界'};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const buildKw = n => [`${n}三日游路线`,`${n}四天三夜攻略`,`${n}五日游行程`,`${n}两天一夜路线`,`${n}旅游路线推荐`,`${n}经典路线`,`${n}一日游路线`,`${n}深度游攻略`,`${n}自由行攻略`,`${n}保姆级攻略`];

function loadLLM() { let c = {}; try { c = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'config', 'llm.local.json'), 'utf-8').replace(/^\uFEFF/, '')); } catch(e) {} return { apiKey: c.api_key || '', baseUrl: (c.base_url || 'https://api.deepseek.com').replace(/\/+$/, ''), model: c.model || 'deepseek-chat' }; }
function callLLM(l, s, u) { return new Promise(r => { const b = JSON.stringify({ model: l.model, messages: [{ role: 'system', content: s }, { role: 'user', content: u }], temperature: 0.1, max_tokens: 3000 }); const url = new URL(l.baseUrl + '/v1/chat/completions'); const req = https.request({ hostname: url.hostname, port: 443, path: url.pathname, method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + l.apiKey } }, res => { let d = ''; res.on('data', c => d += c); res.on('end', () => { if (res.statusCode !== 200) { r({ error: 'HTTP ' + res.statusCode }); return; } try { r({ text: JSON.parse(d).choices?.[0]?.message?.content?.trim() || '' }); } catch { r({ error: 'parse' }); } }); }); req.on('error', e => r({ error: e.message })); req.setTimeout(60000, () => { req.destroy(); r({ error: 'timeout' }); }); req.write(b); req.end(); }); }
const RP = '你是旅游路线分析专家。从小红书笔记中提取完整行程路线。\n返回JSON: {"days":N,"travel_style":"...","season":"...","budget_hint":"...","itinerary":[{"day":1,"label":"第一天","stops":[{"time_hint":"上午","name":"地点","duration_hint":"...","activity":"...","transport_to_next":"..."}]}],"route_summary":"...","tags":["..."]}\n规则：只提取明确提到的地点，不编造。地点名称保持原文。不完整路线返回null。只返回JSON。';
function pf(c) { return path.join(__dirname, 'route_browser_' + c + '_progress.json'); }
function lp(c) { const f = pf(c); return fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf-8')) : { done: [] }; }
function sp(c, p) { fs.writeFileSync(pf(c), JSON.stringify(p, null, 2)); }

async function main() {
  const args = process.argv.slice(2);
  const runAll = args.includes('--all');
  const cityArg = args.includes('--city') ? args[args.indexOf('--city') + 1] : null;
  const maxNotes = args.includes('--max-notes') ? parseInt(args[args.indexOf('--max-notes') + 1]) : 20;
  const cities = runAll ? ALL_CITIES : (cityArg ? [cityArg] : ['beijing']);
  const llm = loadLLM();

  console.log('\n=== XHS Route Crawler ===');
  console.log('Cities:', cities.length, '| Max/city:', maxNotes, '| LLM:', llm.apiKey ? llm.model : 'OFF');

  // Launch browser
  console.log('\nLaunching browser...');
  const browser = await chromium.launch({ headless: false, args: ['--start-maximized'] });
  const ctx = await browser.newContext({
    viewport: null,
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
  });
  const page = await ctx.newPage();
  await page.goto('https://www.xiaohongshu.com', { waitUntil: 'domcontentloaded' });

  // Wait for login
  console.log('Please LOGIN in the browser window...');
  let ok = false;
  for (let i = 0; i < 60; i++) {
    await sleep(3000);
    const txt = await page.evaluate(() => document.body?.innerText || '');
    if (!txt.includes('登录后') && !txt.includes('扫码')) { ok = true; console.log('Login OK! (' + (i*3) + 's)'); break; }
    if (i % 10 === 0 && i > 0) console.log('Waiting... (' + (i*3) + 's)');
  }
  if (!ok) { console.error('Login timeout'); await browser.close(); process.exit(1); }

  let totalNew = 0;

  for (const city of cities) {
    const cn = CITY_NAMES[city] || city;
    const outFile = path.join(__dirname, '..', 'data', city, 'xhs_routes.json');
    const prog = lp(city);
    console.log('\n' + '='.repeat(50) + '\n' + cn + ' | prev:', prog.done.length);

    let existing = []; if (fs.existsSync(outFile)) try { existing = JSON.parse(fs.readFileSync(outFile, 'utf-8')); } catch(e) {}
    const notes = [];

    console.log('[1/3] Search...');
    for (const kw of buildKw(cn)) {
      if (notes.length >= maxNotes * 2) break;
      let items = [];
      const h = async r => { if (r.url().includes('/api/sns/web/v1/search/notes')) try { const j = await r.json(); if (j.code === 0) items = j.data?.items || []; } catch(e) {} };
      page.on('response', h);
      console.log('  ' + kw);
      await page.goto('https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent(kw) + '&source=web_search_result_notes&type=51', { waitUntil: 'domcontentloaded', timeout: CFG.pageTimeout }).catch(() => {});
      await sleep(CFG.searchWait);
      page.off('response', h);
      const valid = items.filter(i => i.model_type === 'note' && !prog.done.includes(i.id)).slice(0, CFG.maxPerKw);
      console.log('    ' + items.length + ' results, ' + valid.length + ' new');
      for (const v of valid) notes.push({ id: v.id, xt: v.xsec_token || '', title: v.note_card?.display_title || '', likes: v.note_card?.interact_info?.liked_count || '0' });
      await sleep(CFG.kwPause);
    }

    const uniq = []; const seen = new Set();
    for (const n of notes) if (!seen.has(n.id)) { seen.add(n.id); uniq.push(n); }
    console.log('  Unique:', uniq.length);

    console.log('[2/3] Extract...');
    const routes = [];
    for (const note of uniq.slice(0, maxNotes)) {
      console.log('\n  ' + note.title.slice(0, 50));
      let fd = null;
      const fh = async r => { if (r.url().includes('/api/sns/web/v1/feed')) try { fd = await r.json(); } catch(e) {} };
      page.on('response', fh);
      const url = 'https://www.xiaohongshu.com/explore/' + note.id + '?xsec_token=' + encodeURIComponent(note.xt) + '&xsec_source=pc_search';
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: CFG.pageTimeout }).catch(() => {});
      await sleep(CFG.noteWait);
      page.off('response', fh);
      let title = note.title, content = '';
      if (fd?.data?.items?.length > 0) { const nc = fd.data.items[0].note_card || {}; title = nc.title || title; content = nc.desc || ''; }
      if (content.length < 50) { const dom = await page.evaluate(() => ({ d: document.querySelector('#detail-desc,[class*="desc"]')?.textContent?.trim() || '' })); if (dom.d.length > content.length) content = dom.d; }
      console.log('    Content: ' + content.length);
      if (content.length < 80) { prog.done.push(note.id); sp(city, prog); continue; }
      if (llm.apiKey) {
        const r = await callLLM(llm, RP, 'city: ' + cn + '\ntitle: ' + title + '\ncontent:\n' + content.slice(0, 5000));
        if (!r.error) try { const m = r.text.match(/\{[\s\S]*\}/); if (m) { const route = JSON.parse(m[0]); if (route?.itinerary?.length > 0) {
          const stops = route.itinerary.reduce((s, d) => s + (d.stops?.length || 0), 0);
          console.log('    Route: ' + route.days + 'd, ' + stops + ' stops');
          routes.push({ source_note_id: note.id, source_url: url.split('?')[0], source_title: title, source_likes: note.likes, crawled_at: new Date().toISOString(), city, city_name: cn, ...route });
        }}} catch(e) {}
      }
      prog.done.push(note.id); sp(city, prog);
    }

    console.log('\n[3/3] Save...');
    const merged = [...existing]; const ids = new Set(merged.map(r => r.source_note_id)); let nc2 = 0;
    for (const r of routes) if (!ids.has(r.source_note_id)) { merged.push(r); ids.add(r.source_note_id); nc2++; }
    merged.sort((a, b) => (a.days || 99) - (b.days || 99));
    fs.mkdirSync(path.dirname(outFile), { recursive: true });
    fs.writeFileSync(outFile, JSON.stringify(merged, null, 2));
    console.log('  ' + merged.length + ' total (' + nc2 + ' new)');
    totalNew += nc2;
  }

  await browser.close();
  console.log('\n=== Done. Total new: ' + totalNew + ' ===');
}
main().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
