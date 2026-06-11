/**
 * XHS Guangzhou Travel Guide Crawler (Browser + API Intercept)
 * Uses Playwright to search XHS, intercepts API for xsec_token, visits notes for images+text
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

const DATA_DIR = path.join(__dirname, '..', 'data', 'guangzhou');
const IMG_DIR = path.join(DATA_DIR, 'images');
const TARGETS_PATH = path.join(__dirname, 'guangzhou_targets.json');
const PROGRESS_PATH = path.join(__dirname, 'image_crawl_progress.json');
const GUIDES_PATH = path.join(DATA_DIR, 'xhs_guides.json');
const POIS_PATH = path.join(DATA_DIR, 'pois.json');

const SEARCH_KEYWORDS = [
  '广州十三行博物馆',
  '广州粤海关博物馆攻略',
  '广州起义纪念馆',
  '广州鲁迅纪念馆',
  '广州三元宫攻略',
  '广州南海神庙攻略',
  '广州仁威祖庙',
  '广州珠江公园攻略',
  '广州兰圃攻略',
  '广州大夫山攻略',
  '广州长洲岛攻略',
  '广州小洲村攻略',
  '广州塱头古村攻略',
  '广州深井古村攻略',
  '广州五羊雕像打卡',
  '广州大鸽饭陶陶居',
  '广州点都德早茶',
  '广州惠食佳攻略',
  '广州达扬炖品攻略',
  '广州夜市美食攻略',
  '广州帽峰山攻略',
  '广州白水寨一日游',
  '广州流溪河森林公园',
  '广州孙中山纪念馆',
];

const CFG = {
  searchWait: 4000,
  noteWait: 3000,
  maxNotesPerKeyword: 5,
  minImageBytes: 20000,
};

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function loadJson(p) { return JSON.parse(fs.readFileSync(p, 'utf-8')); }
function saveJson(p, d) { fs.writeFileSync(p, JSON.stringify(d, null, 2)); }

function downloadImage(url, dest) {
  return new Promise((resolve, reject) => {
    const proto = url.startsWith('https') ? https : http;
    const req = proto.get(url, { headers: { 'Referer': 'https://www.xiaohongshu.com/' }, timeout: 15000 }, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return downloadImage(res.headers.location, dest).then(resolve).catch(reject);
      }
      if (res.statusCode !== 200) { reject(new Error('HTTP ' + res.statusCode)); return; }
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        if (buf.length < CFG.minImageBytes) { reject(new Error('Too small')); return; }
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        fs.writeFileSync(dest, buf);
        resolve(buf.length);
      });
      res.on('error', reject);
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
  });
}

function fuzzyMatch(text, targets) {
  const matched = [];
  for (const t of targets) {
    if (text.includes(t.name)) { matched.push(t); continue; }
    if (t.name.length >= 4 && text.includes(t.name.substring(0, 4))) { matched.push(t); }
  }
  return matched;
}

async function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');

  console.log('=== XHS Browser Crawler (API Intercept) ===');
  console.log('Mode:', dryRun ? 'DRY RUN' : 'LIVE');

  const targets = loadJson(TARGETS_PATH);
  console.log('Targets:', targets.length);

  const prog = fs.existsSync(PROGRESS_PATH) ? loadJson(PROGRESS_PATH) : { done: [], matched: {} };
  console.log('Previously done notes:', prog.done.length);

  if (dryRun) {
    console.log('\nKeywords:', SEARCH_KEYWORDS.length);
    SEARCH_KEYWORDS.forEach(k => console.log('  -', k));
    return;
  }

  // Load cookies
  const envPath = path.join(__dirname, '..', '.env');
  const env = fs.readFileSync(envPath, 'utf-8');
  const ckMatch = env.match(/^XHS_COOKIE=(.+)$/m);
  if (!ckMatch) { console.error('No XHS_COOKIE'); process.exit(1); }
  const rawCookie = ckMatch[1].trim();
  const cookies = rawCookie.split(/;\s*/).map(p => {
    const i = p.indexOf('=');
    return { name: p.substring(0, i).trim(), value: p.substring(i + 1).trim(), domain: '.xiaohongshu.com', path: '/' };
  }).filter(c => c.name && c.value);

  // Launch browser
  console.log('\n[1/4] Launching browser...');
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
    viewport: { width: 1920, height: 1080 },
  });
  await ctx.addCookies(cookies);
  const page = await ctx.newPage();

  const allGuides = [];
  const matchedPois = prog.matched || {};

  console.log('\n[2/4] Searching and extracting...');

  for (const kw of SEARCH_KEYWORDS) {
    console.log('\n  Search:', kw);

    // Intercept search API
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
      await page.goto('https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent(kw) + '&source=web_search_result_notes&type=51', { waitUntil: 'domcontentloaded', timeout: 20000 });
      await sleep(5000);
    } catch(e) {
      console.log('    Nav error:', e.message);
      page.off('response', interceptHandler);
      continue;
    }
    page.off('response', interceptHandler);

    console.log('    Results:', searchItems.length);

    // Take top notes
    const notesToVisit = searchItems.slice(0, CFG.maxNotesPerKeyword);

    for (const item of notesToVisit) {
      const noteId = item.id;
      if (prog.done.includes(noteId)) {
        console.log('    Skip (done):', noteId);
        continue;
      }

      const noteCard = item.note_card || {};
      const title = noteCard.display_title || '';
      const likes = noteCard.interact_info?.liked_count || '0';
      const xsecToken = item.xsec_token || '';

      console.log('    Note:', title.substring(0, 40), '| likes:', likes);

      // Visit note with xsec_token
      const noteUrl = 'https://www.xiaohongshu.com/explore/' + noteId + '?xsec_token=' + encodeURIComponent(xsecToken) + '&xsec_source=pc_search';
      await sleep(CFG.noteWait);

      // Intercept feed API for images
      let feedData = null;
      const feedHandler = async (response) => {
        if (response.url().includes('/api/sns/web/v1/feed')) {
          try { feedData = await response.json(); } catch(e) {}
        }
      };
      page.on('response', feedHandler);

      try {
        await page.goto(noteUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
        await sleep(3000);
      } catch(e) {
        console.log('      Nav error:', e.message);
        page.off('response', feedHandler);
        continue;
      }
      page.off('response', feedHandler);

      // Extract content from page
      const content = await page.evaluate(() => {
        const title = (document.querySelector('#detail-title, [class*="title"]') || {}).textContent || '';
        const desc = (document.querySelector('#detail-desc, [class*="desc"]') || {}).textContent || '';
        const images = [];
        document.querySelectorAll('img').forEach(img => {
          const src = img.src || '';
          if (src.includes('xhscdn.com') && !src.includes('avatar') && !src.includes('icon') && !src.includes('emoji') && !src.includes('platform/')) {
            images.push(src.split('?')[0]);
          }
        });
        // Also try to get images from feed API data (via __INITIAL_STATE__)
        return { title: title.trim(), desc: desc.trim(), images: [...new Set(images)] };
      });

      // Also extract images from feed API response
      let feedImages = [];
      if (feedData?.data?.items) {
        for (const feedItem of feedData.data.items) {
          const note = feedItem.note_card || feedItem;
          const imgList = note.image_list || [];
          for (const img of imgList) {
            const url = img.url_default || img.url || img.info_list?.[0]?.url || '';
            if (url && !url.includes('avatar')) feedImages.push(url.split('?')[0]);
          }
        }
      }

      // Combine images from page and API
      const allImages = [...new Set([...content.images, ...feedImages])];

      const desc = content.desc || content.title;
      console.log('      Images:', allImages.length, '| Desc len:', desc.length);

      // Match POIs
      const fullText = content.title + ' ' + desc;
      const matched = fuzzyMatch(fullText, targets);
      console.log('      POIs matched:', matched.length, matched.map(m => m.name).join(', '));

      // Download images for matched POIs
      for (const poi of matched) {
        if (!matchedPois[poi.id]) matchedPois[poi.id] = { images: [], guideText: '', notes: [] };
        matchedPois[poi.id].guideText = (matchedPois[poi.id].guideText + '\n' + fullText).substring(0, 1000);
        matchedPois[poi.id].notes.push({ url: noteUrl, title: content.title });

        // Download up to 3 images per POI
        const existingCount = matchedPois[poi.id].images.length;
        if (existingCount >= 3) continue;

        for (let i = 0; i < Math.min(allImages.length, 3 - existingCount); i++) {
          const imgUrl = allImages[i];
          const ext = imgUrl.includes('.webp') ? '.webp' : '.png';
          const imgIdx = existingCount + i + 1;
          const dest = path.join(IMG_DIR, poi.id, imgIdx + ext);
          try {
            const size = await downloadImage(imgUrl, dest);
            matchedPois[poi.id].images.push({ url: 'images/guangzhou/' + poi.id + '/' + imgIdx + ext, source: 'xiaohongshu', noteUrl });
            console.log('      DL:', poi.name, 'img' + imgIdx, Math.round(size / 1024) + 'KB');
          } catch(e) {
            // skip
          }
        }
      }

      allGuides.push({ noteId, noteUrl, title: content.title, likes, desc: desc.substring(0, 500), images: allImages.slice(0, 5), matchedPois: matched.map(m => ({ id: m.id, name: m.name })) });
      prog.done.push(noteId);
      prog.matched = matchedPois;
      saveJson(PROGRESS_PATH, prog);
    }
  }

  // Update pois.json
  console.log('\n[3/4] Updating pois.json...');
  if (fs.existsSync(POIS_PATH)) {
    const pois = loadJson(POIS_PATH);
    let updated = 0;
    for (const p of pois) {
      const m = matchedPois[p.id];
      if (m && m.images.length > 0) {
        p.image_url = m.images[0].url;
        p.images = m.images;
        p.guide_text = m.guideText.substring(0, 500);
        p.xhs_notes = m.notes;
        updated++;
      }
    }
    saveJson(POIS_PATH, pois);
    console.log('Updated', updated, 'POIs');
  }

  // Save guides
  saveJson(GUIDES_PATH, allGuides);
  console.log('Saved', allGuides.length, 'guides');

  // Summary
  const totalImgs = Object.values(matchedPois).reduce((s, p) => s + p.images.length, 0);
  const covered = Object.keys(matchedPois).filter(k => matchedPois[k].images.length > 0).length;
  console.log('\n[4/4] Summary:');
  console.log('  Notes:', allGuides.length);
  console.log('  POIs covered:', covered, '/', targets.length);
  console.log('  Images:', totalImgs);

  await browser.close();
  console.log('\nDone!');
}

main().catch(e => { console.error('Fatal:', e); process.exit(1); });
