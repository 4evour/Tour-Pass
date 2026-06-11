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

  // Intercept search API
  const searchResults = [];
  page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('/api/sns/web/v1/search/notes') || url.includes('/api/sns/web/v2/search/notes')) {
      try {
        const json = await response.json();
        const items = json.data?.items || [];
        searchResults.push(...items);
      } catch(e) {}
    }
  });

  await page.goto('https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent('广州三日游攻略') + '&source=web_search_result_notes&type=51', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(5000);

  console.log('Total search results:', searchResults.length);

  // Print first 3 notes with full detail
  for (const item of searchResults.slice(0, 3)) {
    const note = item.note_card || {};
    console.log('\n=== Note ===');
    console.log('ID:', item.id);
    console.log('Title:', note.display_title || '');
    console.log('xsec_token:', (item.xsec_token || '').substring(0, 30) + '...');
    console.log('Likes:', note.interact_info?.liked_count || '0');
    console.log('Type:', item.model_type);

    // Images from search result
    const imgs = note.image_list || [];
    console.log('Images in search:', imgs.length);
    if (imgs.length > 0) {
      console.log('  URL:', (imgs[0].url_default || imgs[0].url || '').substring(0, 80));
    }
  }

  // Now test visiting a note with xsec_token
  if (searchResults.length > 0) {
    const first = searchResults[0];
    const noteUrl = 'https://www.xiaohongshu.com/explore/' + first.id + '?xsec_token=' + encodeURIComponent(first.xsec_token || '') + '&xsec_source=pc_search';
    console.log('\n\nTesting note visit with token:', noteUrl.substring(0, 80));

    // Intercept the note detail API
    let noteDetail = null;
    page.on('response', async (response) => {
      if (response.url().includes('/api/sns/web/v1/feed')) {
        try { noteDetail = await response.json(); } catch(e) {}
      }
    });

    await page.goto(noteUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.waitForTimeout(5000);

    console.log('Page URL:', page.url());
    console.log('Page title:', await page.title());

    // Extract content
    const content = await page.evaluate(() => {
      const desc = document.querySelector('#detail-desc, [class*="desc"], .content');
      const title = document.querySelector('#detail-title, [class*="title"]');
      const images = [];
      document.querySelectorAll('img').forEach(img => {
        const src = img.src || '';
        if (src.includes('xhscdn.com') && !src.includes('avatar') && !src.includes('icon') && !src.includes('emoji')) {
          images.push(src);
        }
      });
      return {
        title: title ? title.textContent.trim() : '',
        desc: desc ? desc.textContent.trim().substring(0, 300) : '',
        imageCount: images.length,
        images: images.slice(0, 3),
      };
    });

    console.log('Extracted title:', content.title);
    console.log('Extracted desc:', content.desc.substring(0, 100));
    console.log('Images found:', content.imageCount);
    content.images.forEach(i => console.log('  img:', i.substring(0, 80)));
  }

  await browser.close();
})();
