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

  await page.goto('https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent('广州三日游攻略') + '&source=web_search_result_notes&type=51', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(3000);

  // Click first note (regular click, not ctrl+click)
  console.log('Clicking first note...');
  const firstNote = await page.$('section.note-item a, [class*="note-item"] a');
  if (firstNote) {
    await firstNote.click();
    await page.waitForTimeout(4000);

    // Check URL - XHS might open notes in a modal or navigate to /explore/ URL
    console.log('URL after click:', page.url());

    // Check for modal/side panel
    const modalContent = await page.evaluate(() => {
      // Check for note detail modal
      const detail = document.querySelector('.note-detail, [class*="detail"], .modal, [class*="modal"], [class*="overlay"]');
      if (detail) return { found: true, text: detail.textContent.trim().substring(0, 500) };

      // Check for any new content
      const desc = document.querySelector('#detail-desc, [class*="desc"]');
      if (desc) return { found: true, text: desc.textContent.trim().substring(0, 500) };

      return { found: false, bodyText: document.body.textContent.trim().substring(0, 300) };
    });

    console.log('Modal:', JSON.stringify(modalContent, null, 2));

    // Take screenshot for debugging
    await page.screenshot({ path: path.join(__dirname, '_screenshot.png'), fullPage: false });
    console.log('Screenshot saved to scripts/_screenshot.png');
  }

  await browser.close();
})();
