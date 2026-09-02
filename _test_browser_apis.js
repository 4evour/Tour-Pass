const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const envPath = path.join(__dirname, '.env');
  const env = fs.readFileSync(envPath, 'utf-8');
  const m = env.match(/XHS_COOKIE\s*=\s*(.+?)$/m);
  const rawCookie = m ? m[1].trim() : '';
  const cookies = rawCookie.split(/;\s*/).map(p => {
    const i = p.indexOf('=');
    return { name: p.substring(0, i).trim(), value: p.substring(i + 1).trim(), domain: '.xiaohongshu.com', path: '/' };
  }).filter(c => c.name && c.value);

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
    viewport: { width: 1920, height: 1080 },
  });
  await ctx.addCookies(cookies);
  const page = await ctx.newPage();

  // Intercept all API responses
  const apiResults = [];
  page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('/api/sns/')) {
      try {
        const json = await response.json();
        const items = json.data?.items || json.data?.notes || [];
        apiResults.push({ url: url.split('?')[0], code: json.code, items: items.length });
      } catch(e) {
        apiResults.push({ url: url.split('?')[0], code: response.status(), items: 0 });
      }
    }
  });

  // Test 1: Search page
  console.log('--- Test: Search page ---');
  await page.goto('https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent('北京三日游路线') + '&source=web_search_result_notes&type=51', {
    waitUntil: 'networkidle', timeout: 20000
  }).catch(e => console.log('Nav error:', e.message));
  await new Promise(r => setTimeout(r, 3000));

  const bodyText = await page.evaluate(() => document.body?.innerText?.slice(0, 300) || '');
  console.log('Body preview:', bodyText.slice(0, 200));

  // Test 2: Explore page
  console.log('\n--- Test: Explore page ---');
  apiResults.length = 0;
  await page.goto('https://www.xiaohongshu.com/explore', {
    waitUntil: 'domcontentloaded', timeout: 20000
  }).catch(e => console.log('Nav error:', e.message));
  await new Promise(r => setTimeout(r, 5000));

  const exploreText = await page.evaluate(() => document.body?.innerText?.slice(0, 300) || '');
  console.log('Body preview:', exploreText.slice(0, 200));
  console.log('API calls intercepted:', apiResults.length);
  for (const r of apiResults) {
    console.log('  ', r.url, '-> code=' + r.code + ', items=' + r.items);
  }

  // Test 3: POI page (Beijing)
  console.log('\n--- Test: POI/Location page ---');
  apiResults.length = 0;
  await page.goto('https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent('北京旅游') + '&source=web_search_result_notes&type=51', {
    waitUntil: 'networkidle', timeout: 20000
  }).catch(e => console.log('Nav error:', e.message));
  await new Promise(r => setTimeout(r, 3000));

  console.log('API calls:', apiResults.length);
  for (const r of apiResults) {
    if (r.items > 0) console.log('  ', r.url, '-> code=' + r.code + ', items=' + r.items);
  }

  await browser.close();
})();
