#!/usr/bin/env node
/**
 * XHS Guangzhou Travel Guide Crawler
 * Searches Xiaohongshu for travel guides, extracts images + tips + routes
 * Downloads images to data/guangzhou/images/{poi_id}/
 * Updates pois.json with image_url/images/guide_text fields
 *
 * Usage:
 *   node scripts/crawl_xhs_guides.js --city guangzhou
 *   node scripts/crawl_xhs_guides.js --city guangzhou --dry-run
 *   XHS_COOKIE="cookie" node scripts/crawl_xhs_guides.js --city guangzhou
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const vm = require('vm');

// ============ Config ============
const CFG = {
  searchIntervalMin: 15000, searchIntervalMax: 25000,
  detailIntervalMin: 10000, detailIntervalMax: 15000,
  maxRequestsPerDay: 80, minLikes: 100, topNNotes: 3,
  minImageSize: 30 * 1024,
  userAgents: [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
  ],
};

const SEARCH_KEYWORDS = [
  '广州老城区一日游攻略',
  '广州三日游攻略',
  '广州必去景点合集',
  '广州美食攻略',
  '广州天河珠江新城攻略',
  '广州番禺一日游',
  '广州白云山攻略',
  '广州沙面永庆坊攻略',
  '广州博物馆攻略',
  '广州寺庙攻略',
  '广州旅游路线推荐',
  '广州小众景点推荐',
];

// ============ Signing Engine ============
const SIGN_DIR = path.join(__dirname, 'xhs_sign');
let xsCtx = null, xrayCtx = null;

function loadSignEngine() {
  const xsPath = path.join(SIGN_DIR, 'xhs_xs_xsc_56.js');
  const xrayPath = path.join(SIGN_DIR, 'xhs_xray.js');
  if (!fs.existsSync(xsPath)) throw new Error('Signing engine not found: ' + xsPath);
  if (!fs.existsSync(xrayPath)) throw new Error('Xray engine not found: ' + xrayPath);

  // Use require() directly — suppress signing module debug output
  const _origWrite = process.stdout.write.bind(process.stdout);
  process.stdout.write = function() {};
  const _origLog = console.log;
  console.log = function() {};
  xsCtx = require(xsPath);
  console.log = _origLog;
  process.stdout.write = _origWrite;

  // xray needs require path fixup for pack files
  let xrayCode = fs.readFileSync(xrayPath, 'utf-8');
  const p1 = path.join(SIGN_DIR, 'xhs_xray_pack1.js').replace(/\\/g, '/');
  const p2 = path.join(SIGN_DIR, 'xhs_xray_pack2.js').replace(/\\/g, '/');
  xrayCode = xrayCode.replace(/require\(['"].*?xhs_xray_pack1\.js['"]\)/g, "require('" + p1 + "')");
  xrayCode = xrayCode.replace(/require\(['"].*?xhs_xray_pack2\.js['"]\)/g, "require('" + p2 + "')");
  // Write temp file and require it
  const tmpPath = path.join(SIGN_DIR, '_xray_temp.js');
  fs.writeFileSync(tmpPath, xrayCode, 'utf-8');
  xrayCtx = require(tmpPath);
  // Clean up
  try { fs.unlinkSync(tmpPath); } catch(e) {}

  console.log('[XHS_SIGN] Signing engine loaded');
}

function hexRandom(len) {
  const c = 'abcdef0123456789';
  let s = '';
  for (let i = 0; i < len; i++) s += c[Math.floor(Math.random() * 16)];
  return s;
}

function transCookies(str) {
  const ck = {};
  for (const item of str.split(/;\s*/)) {
    const idx = item.indexOf('=');
    if (idx > 0) ck[item.slice(0, idx).trim()] = item.slice(idx + 1).trim();
  }
  return ck;
}

function genHeaders(cookieStr, api, data, method) {
  const ck = transCookies(cookieStr);
  const a1 = ck.a1 || '';
  const ret = xsCtx.get_request_headers_params(api, data || '', a1, method || 'POST');
  const ua = CFG.userAgents[Math.floor(Math.random() * CFG.userAgents.length)];
  const traceId = xrayCtx && xrayCtx.traceId ? xrayCtx.traceId() : hexRandom(16);
  return {
    headers: {
      'authority': 'edith.xiaohongshu.com',
      'accept': 'application/json, text/plain, */*',
      'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
      'content-type': 'application/json;charset=UTF-8',
      'origin': 'https://www.xiaohongshu.com',
      'referer': 'https://www.xiaohongshu.com/',
      'user-agent': ua,
      'x-b3-traceid': hexRandom(16),
      'x-s': ret.xs, 'x-t': String(ret.xt), 'x-s-common': ret.xs_common,
      'x-xray-traceid': traceId,
    },
    cookies: ck,
  };
}

// ============ HTTP ============
function httpReq(url, opts) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const mod = u.protocol === 'https:' ? https : http;
    const req = mod.request(url, opts, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(body);
        else reject(new Error('HTTP ' + res.statusCode + ': ' + body.slice(0, 200)));
      });
    });
    req.on('error', reject);
    if (opts.timeout) req.setTimeout(opts.timeout, () => { req.destroy(); reject(new Error('timeout')); });
    if (opts.body) req.write(opts.body);
    req.end();
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function randSleep(min, max) { return sleep(min + Math.random() * (max - min)); }

// ============ XHS API ============
const XHS = 'https://edith.xiaohongshu.com';

async function searchNotes(ck, keyword, page, size, sort) {
  const api = '/api/sns/web/v1/search/notes';
  const sortMap = { 0: 'general', 1: 'time_descending', 2: 'popularity_descending' };
  const data = {
    keyword, page: page || 1, page_size: size || 20,
    search_id: hexRandom(21), sort: 'general', note_type: 0, ext_flags: [],
    filters: [
      { tags: [sortMap[sort || 0]], type: 'sort_type' },
      { tags: ['not limited'], type: 'filter_note_type' },
      { tags: ['not limited'], type: 'filter_note_time' },
      { tags: ['not limited'], type: 'filter_note_range' },
      { tags: ['not limited'], type: 'filter_pos_distance' },
    ],
    geo: '', image_formats: ['jpg', 'webp', 'avif'],
  };
  const { headers, cookies } = genHeaders(ck, api, data, 'POST');
  const cookieStr = Object.entries(cookies).map(([k, v]) => k + '=' + v).join('; ');
  const body = await httpReq(XHS + api, {
    method: 'POST', headers: { ...headers, cookie: cookieStr },
    body: JSON.stringify(data), timeout: 15000,
  });
  return JSON.parse(body);
}

async function getNoteDetail(ck, noteId, xsecToken) {
  const api = '/api/sns/web/v1/feed';
  const data = {
    source_note_id: noteId, image_formats: ['jpg', 'webp', 'avif'],
    extra: { need_body_topic: 1 }, xsec_source: 'pc_search', xsec_token: xsecToken || '',
  };
  const { headers, cookies } = genHeaders(ck, api, data, 'POST');
  const cookieStr = Object.entries(cookies).map(([k, v]) => k + '=' + v).join('; ');
  const body = await httpReq(XHS + api, {
    method: 'POST', headers: { ...headers, cookie: cookieStr },
    body: JSON.stringify(data), timeout: 15000,
  });
  return JSON.parse(body);
}

// ============ Image Download ============
function downloadImage(url, dest) {
  return new Promise((resolve, reject) => {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    const u = new URL(url);
    const mod = u.protocol === 'https:' ? https : http;
    mod.get(url, { headers: { 'User-Agent': CFG.userAgents[0] }, timeout: 30000 }, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        downloadImage(res.headers.location, dest).then(resolve).catch(reject);
        return;
      }
      if (res.statusCode !== 200) { reject(new Error('HTTP ' + res.statusCode)); return; }
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        if (buf.length < CFG.minImageSize) { reject(new Error('Too small: ' + buf.length)); return; }
        fs.writeFileSync(dest, buf);
        resolve({ size: buf.length, path: dest });
      });
      res.on('error', reject);
    }).on('error', reject);
  });
}

// ============ POI Matching ============
function matchSpot(name, targets) {
  const n = name.replace(/\s+/g, '').toLowerCase();
  for (const t of targets) { if (t.name === name) return t; }
  for (const t of targets) {
    const tn = t.name.replace(/\s+/g, '').toLowerCase();
    if (tn.includes(n) || n.includes(tn)) return t;
  }
  for (const t of targets) {
    const tn = t.name.replace(/\s+/g, '').toLowerCase();
    for (const w of n.split(/[，,、\s]+/).filter(w => w.length >= 2)) {
      if (tn.includes(w)) return t;
    }
  }
  return null;
}

function simpleExtract(content, targets) {
  return targets.filter(t => content.includes(t.name)).map(t => ({
    name: t.name, matched_poi_id: t.id, matched_poi_name: t.name, tips: '',
  }));
}

// ============ LLM Extraction ============
async function extractSpots(title, content, targets) {
  const cfgPath = path.join(__dirname, '..', 'config', 'llm.local.json');
  let llm = {};
  if (fs.existsSync(cfgPath)) llm = JSON.parse(fs.readFileSync(cfgPath, 'utf-8'));
  const apiKey = llm.apiKey || process.env.DEEPSEEK_API_KEY || process.env.LLM_API_KEY || '';
  if (!apiKey) return simpleExtract(content, targets);

  const baseUrl = (llm.baseUrl || process.env.LLM_BASE_URL || 'https://api.deepseek.com').replace(/\/+$/, '');
  const model = llm.model || process.env.LLM_MODEL || 'deepseek-chat';
  const targetNames = targets.map(t => t.name).join(', ');

  const sys = 'You are a travel guide analyzer. Extract attractions and restaurants mentioned in the text. Return JSON array with objects: {name, tips, photos_mentioned}. Only return the JSON array.';
  const usr = 'Target list: ' + targetNames + '\n\nTitle: ' + title + '\nContent:\n' + content.slice(0, 3000) + '\n\nReturn JSON array.';

  try {
    const body = await httpReq(baseUrl + '/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + apiKey },
      body: JSON.stringify({ model, messages: [{ role: 'system', content: sys }, { role: 'user', content: usr }], temperature: 0.1, max_tokens: 2000 }),
      timeout: 30000,
    });
    const resp = JSON.parse(body);
    const text = resp.choices?.[0]?.message?.content || '';
    const m = text.match(/\[[\s\S]*\]/);
    if (m) {
      return JSON.parse(m[0]).map(item => {
        const matched = matchSpot(item.name, targets);
        return matched ? { ...item, matched_poi_id: matched.id, matched_poi_name: matched.name } : item;
      }).filter(i => i.matched_poi_id);
    }
  } catch (e) {
    console.log('[LLM] Failed: ' + e.message + ', using simple text match');
  }
  return simpleExtract(content, targets);
}

// ============ Progress ============
const PROG_FILE = path.join(__dirname, 'image_crawl_progress.json');
function loadProgress() {
  if (fs.existsSync(PROG_FILE)) return JSON.parse(fs.readFileSync(PROG_FILE, 'utf-8'));
  return { completedNotes: [], completedTargets: [], requestCount: 0, date: new Date().toISOString().split('T')[0] };
}
function saveProgress(p) { fs.writeFileSync(PROG_FILE, JSON.stringify(p, null, 2), 'utf-8'); }

// ============ Review HTML ============
function genReviewHtml(city, coverage, imagesDir) {
  const targets = JSON.parse(fs.readFileSync(path.join(__dirname, city + '_targets.json'), 'utf-8'));
  let h = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Image Review - ' + city + '</title>';
  h += '<style>body{font-family:sans-serif;padding:20px;background:#f5f5f5}';
  h += '.card{background:#fff;border-radius:8px;padding:16px;margin-bottom:16px;box-shadow:0 2px 4px rgba(0,0,0,.1)}';
  h += '.hdr{display:flex;align-items:center;gap:12px;margin-bottom:12px}';
  h += '.nm{font-size:18px;font-weight:bold}.ar{color:#666;font-size:14px}';
  h += '.gd{background:#f0f7ff;padding:8px 12px;border-radius:4px;margin-bottom:12px;font-size:14px}';
  h += '.imgs{display:flex;gap:12px;flex-wrap:wrap}';
  h += '.imgs img{width:200px;height:150px;object-fit:cover;border-radius:4px;cursor:pointer}';
  h += '.imgs img:hover{transform:scale(1.5);z-index:10}';
  h += '.no{color:#999;font-style:italic}</style></head><body>';
  h += '<h1>Image Review - ' + city + '</h1>';
  h += '<div style="position:fixed;top:10px;right:10px;background:#fff;padding:12px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.15)">';
  h += 'Coverage: ' + Object.keys(coverage).length + ' / ' + targets.length + '</div>';

  for (const t of targets) {
    const c = coverage[t.id];
    h += '<div class="card"><div class="hdr"><span class="nm">' + t.name + '</span><span class="ar">' + t.area + ' / ' + t.popularity + '</span></div>';
    if (c?.guideText) h += '<div class="gd">' + c.guideText + '</div>';
    if (c?.images?.length) {
      h += '<div class="imgs">';
      for (const img of c.images) {
        const p = path.join(imagesDir, t.id, path.basename(img.url));
        if (fs.existsSync(p)) h += '<img src="' + p + '" />';
      }
      h += '</div>';
    } else {
      h += '<div class="no">No images</div>';
    }
    h += '</div>';
  }
  h += '</body></html>';
  fs.writeFileSync(path.join(__dirname, 'image_review.html'), h, 'utf-8');
}

// ============ Main ============
async function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');
  const city = 'guangzhou';

  console.log('\n=== XHS Guide Crawler ===');
  console.log('City: ' + city + '  Mode: ' + (dryRun ? 'DRY RUN' : 'LIVE'));

  loadSignEngine();

  // Read cookie
  let cookie = process.env.XHS_COOKIE || '';
  if (!cookie) {
    const envPath = path.join(__dirname, '..', '.env');
    if (fs.existsSync(envPath)) {
      const env = fs.readFileSync(envPath, 'utf-8');
      const m = env.match(/XHS_COOKIE\s*=\s*["']?(.+?)["']?\s*$/m);
      if (m) cookie = m[1].trim();
    }
  }
  if (!cookie) { console.error('No XHS_COOKIE configured'); process.exit(1); }
  console.log('Cookie: ' + cookie.slice(0, 20) + '...');

  const targetsPath = path.join(__dirname, city + '_targets.json');
  const targets = JSON.parse(fs.readFileSync(targetsPath, 'utf-8'));
  console.log('Targets: ' + targets.length);

  const prog = loadProgress();
  console.log('Done: ' + prog.completedTargets.length + ' targets, ' + prog.completedNotes.length + ' notes');

  if (dryRun) {
    console.log('\n[DRY RUN] Keywords:');
    SEARCH_KEYWORDS.forEach(k => console.log('  - ' + k));
    console.log('Est. requests: ' + (SEARCH_KEYWORDS.length * 4));
    return;
  }

  const imagesDir = path.join(__dirname, '..', 'data', city, 'images');
  fs.mkdirSync(imagesDir, { recursive: true });
  const coverage = {};
  const allGuides = [];
  let reqCount = prog.requestCount;

  // 1. Validate cookie
  console.log('\n[1/7] Validating cookie...');
  try {
    const r = await searchNotes(cookie, '广州旅游', 1, 1);
    if (r.code === 300011 || r.code === -100) { console.error('Cookie invalid/banned'); process.exit(1); }
    if (!r.data?.items) { console.error('Validation response: ' + JSON.stringify(r).substring(0, 800)); process.exit(1); }
    console.log('Cookie OK');
    reqCount++;
  } catch (e) { console.error('Validation error: ' + e.message); process.exit(1); }

  // 2. Search notes
  console.log('\n[2/7] Searching notes...');
  const allNotes = [];
  for (const kw of SEARCH_KEYWORDS) {
    if (reqCount >= CFG.maxRequestsPerDay) { console.log('Daily limit reached'); break; }
    console.log('  Search: ' + kw);
    await randSleep(CFG.searchIntervalMin, CFG.searchIntervalMax);
    try {
      const r = await searchNotes(cookie, kw, 1, 20, 2);
      reqCount++;
      if (r.code === 300011 || r.code === -100) { console.error('Banned! Stopping.'); break; }
      const notes = (r.data?.items || [])
        .filter(i => i.model_type === 'note')
        .map(i => ({ id: i.id, xsecToken: i.xsec_token || '', title: i.note_card?.display_title || '', likes: i.note_card?.interact_info?.liked_count || '0' }))
        .filter(n => parseInt(n.likes) >= CFG.minLikes || String(n.likes).includes('wan'));
      console.log('    Found ' + notes.length + ' high-likes notes');
      allNotes.push(...notes.slice(0, CFG.topNNotes));
    } catch (e) { console.log('    Error: ' + e.message); }
  }

  const uniqueNotes = [];
  const seen = new Set();
  for (const n of allNotes) {
    if (!seen.has(n.id) && !prog.completedNotes.includes(n.id)) { seen.add(n.id); uniqueNotes.push(n); }
  }
  console.log('  Unique new notes: ' + uniqueNotes.length);

  // 3. Get note details
  console.log('\n[3/7] Getting note details...');
  const details = [];
  for (const note of uniqueNotes) {
    if (reqCount >= CFG.maxRequestsPerDay) break;
    console.log('  Detail: ' + note.title + ' (' + note.id + ')');
    await randSleep(CFG.detailIntervalMin, CFG.detailIntervalMax);
    try {
      const d = await getNoteDetail(cookie, note.id, note.xsecToken);
      reqCount++;
      if (d.code === 300011 || d.code === -100) { console.error('Banned!'); break; }
      const items = d.data?.items || [];
      if (items.length > 0) {
        const nc = items[0].note_card || {};
        const imgs = (nc.image_list || []).map(img => {
          const info = img.info_list || [];
          return info.length > 1 ? info[info.length - 1].url : (info[0]?.url || img.url_default || img.url_pre || img.url || '');
        }).filter(Boolean);
        details.push({ id: note.id, title: nc.title || note.title, likes: note.likes, content: nc.desc || '', imageUrls: imgs, url: 'https://www.xiaohongshu.com/explore/' + note.id });
        console.log('    OK ' + imgs.length + ' images');
      }
    } catch (e) { console.log('    Error: ' + e.message); }
    prog.requestCount = reqCount;
    prog.completedNotes.push(note.id);
    saveProgress(prog);
  }

  // 4. Extract spots with LLM
  console.log('\n[4/7] Extracting spots...');
  for (const note of details) {
    console.log('  Analyzing: ' + note.title);
    const spots = await extractSpots(note.title, note.content, targets);
    note.matchedSpots = spots;
    console.log('    Matched ' + spots.length + ' targets');
    allGuides.push({ note_id: note.id, note_url: note.url, title: note.title, likes: note.likes, spots });
    await sleep(1000);
  }

  // 5. Download images
  console.log('\n[5/7] Downloading images...');
  let dlCount = 0;
  for (const note of details) {
    const spots = (note.matchedSpots || []).filter(s => s.matched_poi_id);
    if (!spots.length) continue;
    for (let i = 0; i < spots.length; i++) {
      const spot = spots[i];
      const pid = spot.matched_poi_id;
      if (!coverage[pid]) coverage[pid] = { images: [], guideText: '', notes: [] };
      const imgIdx = i % note.imageUrls.length;
      const imgUrl = note.imageUrls[imgIdx];
      if (!imgUrl || coverage[pid].images.some(img => img.sourceUrl === imgUrl)) continue;
      const existing = fs.existsSync(path.join(imagesDir, pid)) ? fs.readdirSync(path.join(imagesDir, pid)) : [];
      const num = existing.length + 1;
      const ext = imgUrl.includes('.webp') ? '.webp' : '.jpg';
      const dest = path.join(imagesDir, pid, num + ext);
      try {
        const r = await downloadImage(imgUrl, dest);
        coverage[pid].images.push({ url: 'images/' + city + '/' + pid + '/' + num + ext, source: 'xiaohongshu', note_url: note.url, sourceUrl: imgUrl, size: r.size });
        dlCount++;
        console.log('    OK ' + spot.matched_poi_name + ': img ' + num + ' (' + r.size + ' bytes)');
      } catch (e) { console.log('    FAIL ' + spot.matched_poi_name + ': ' + e.message); }
      await sleep(500);
    }
    for (const spot of spots) {
      const pid = spot.matched_poi_id;
      if (!coverage[pid]) coverage[pid] = { images: [], guideText: '', notes: [] };
      if (spot.tips && spot.tips.length > (coverage[pid].guideText || '').length) coverage[pid].guideText = spot.tips;
      coverage[pid].notes.push({ url: note.url, title: note.title });
    }
  }
  console.log('  Downloaded: ' + dlCount + ' images');

  // 6. Update pois.json
  console.log('\n[6/7] Updating pois.json...');
  const poisPath = path.join(__dirname, '..', 'data', city, 'pois.json');
  const pois = JSON.parse(fs.readFileSync(poisPath, 'utf-8'));
  let updCount = 0;
  for (const poi of pois) {
    const c = coverage[poi.id];
    if (!c) continue;
    if (c.images.length > 0) {
      poi.image_url = c.images[0].url;
      poi.images = c.images.map(i => ({ url: i.url, source: i.source, note_url: i.note_url }));
    }
    if (c.guideText) poi.guide_text = c.guideText;
    if (c.notes.length > 0) poi.xhs_notes = c.notes;
    updCount++;
  }
  fs.writeFileSync(poisPath, JSON.stringify(pois, null, 2), 'utf-8');
  console.log('  Updated ' + updCount + ' POIs');

  // 7. Save guides + review
  console.log('\n[7/7] Saving guides...');
  fs.writeFileSync(path.join(__dirname, '..', 'data', city, 'xhs_guides.json'), JSON.stringify(allGuides, null, 2), 'utf-8');
  genReviewHtml(city, coverage, imagesDir);

  console.log('\n=== Done ===');
  console.log('Requests: ' + reqCount);
  console.log('Notes: ' + details.length);
  console.log('Images: ' + dlCount);
  console.log('Coverage: ' + updCount + ' / ' + targets.length);
  console.log('Review: scripts/image_review.html');

  prog.requestCount = reqCount;
  prog.completedTargets = [...new Set([...prog.completedTargets, ...Object.keys(coverage)])];
  saveProgress(prog);
}

main().catch(e => { console.error('Fatal: ' + e.message); console.error(e.stack); process.exit(1); });
