const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const env = fs.readFileSync(path.join(__dirname, '..', '.env'), 'utf-8');
  const cookieMatch = env.match(/^XHS_COOKIE=(.+)$/m);
  const rawCookie = cookieMatch[1].trim();
  const cookies = rawCookie.split(/;\s*/).map(pair => {
    const idx = pair.indexOf('=');
    return { name: pair.substring(0, idx).trim(), value: pair.substring(idx + 1).trim(), domain: '.xiaohongshu.com', path: '/' };
  }).filter(c => c.name && c.value);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  await context.addCookies(cookies);
  const page = await context.newPage();

  // Intercept API responses
  const apiData = [];
  page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('/api/sns/web/v1/search/notes') || url.includes('/api/sns/web/v2/search/notes')) {
      try {
        const json = await response.json();
        apiData.push(json);
        console.log('Intercepted search API response, items:', json.data?.items?.length || 0);
      } catch(e) {}
    }
  });

  await page.goto('https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent('广州三日游攻略') + '&source=web_search_result_notes&type=51', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  console.log('Intercepted', apiData.length, 'API responses');

  if (apiData.length > 0) {
    const data = apiData[0];
    const items = data.data?.items || [];
    console.log('Items:', items.length);

    for (const item of items.slice(0, 3)) {
      const note = item.note_card || item;
      console.log('\n--- Note ---');
      console.log('ID:', note.note_id || item.id);
      console.log('Title:', note.display_title || note.title || '');
      console.log('xsec_token:', item.xsec_token || 'NONE');
      console.log('Likes:', note.interact_info?.liked_count || '0');
      console.log('Type:', item.model_type);
      // Check for images
      const imgs = note.image_list || [];
      console.log('Images:', imgs.length);
      if (imgs.length > 0) {
        console.log('  First img URL:', imgs[0].url_default || imgs[0].url || '');
      }
    }
  }

  await browser.close();
})();
