// Test: click on note cards in search results to get proper xsec_token
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

  // Go to search page
  await page.goto('https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent('广州三日游攻略') + '&source=web_search_result_notes&type=51', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(3000);

  // Click the first note card
  console.log('Clicking first note card...');
  const noteCards = await page.$$('section.note-item a, [class*="note-item"] a');
  console.log('Found', noteCards.length, 'note card links');

  if (noteCards.length > 0) {
    // Click and wait for new page/popup
    const [newPage] = await Promise.all([
      context.waitForEvent('page', { timeout: 10000 }).catch(() => null),
      noteCards[0].click({ modifiers: ['Control'] }).catch(() => null), // Ctrl+click opens in new tab
    ]);

    const targetPage = newPage || page;
    await targetPage.waitForTimeout(3000);

    // Check current URL
    console.log('URL:', targetPage.url());

    // If we got a new page, check it
    if (newPage) {
      await newPage.waitForTimeout(3000);
      console.log('New page URL:', newPage.url());
      const title = await newPage.title();
      console.log('Title:', title);

      const desc = await newPage.evaluate(() => {
        const el = document.querySelector('#detail-desc, .desc, [class*="desc"]');
        return el ? el.textContent.trim().substring(0, 300) : 'NOT FOUND';
      });
      console.log('Desc:', desc);

      const images = await newPage.evaluate(() => {
        const imgs = [];
        document.querySelectorAll('img').forEach(img => {
          const src = img.src || '';
          if (src.includes('xhscdn.com') && !src.includes('avatar') && !src.includes('icon')) {
            imgs.push(src);
          }
        });
        return imgs.slice(0, 5);
      });
      console.log('Images:', images.length);
      images.forEach(i => console.log('  ', i.substring(0, 80)));
    } else {
      // Maybe it navigated in the same tab
      await page.waitForTimeout(3000);
      console.log('Same tab URL:', page.url());
    }
  }

  await browser.close();
})();
