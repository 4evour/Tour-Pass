// Quick test: check what URLs the search results actually have
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
  const context = await browser.newContext();
  await context.addCookies(cookies);
  const page = await context.newPage();

  await page.goto('https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent('广州三日游攻略') + '&source=web_search_result_notes&type=51', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(3000);

  // Get all links with their full href
  const links = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll('a').forEach(a => {
      const href = a.getAttribute('href') || '';
      if (href.includes('/explore/') || href.includes('/discovery/item/')) {
        results.push({ href, text: a.textContent.trim().substring(0, 50) });
      }
    });
    return results.slice(0, 10);
  });

  console.log('Found links:');
  links.forEach(l => console.log('  href:', l.href, '| text:', l.text));

  // Also check section.note-item structure
  const noteItems = await page.evaluate(() => {
    const items = [];
    document.querySelectorAll('section.note-item, [class*="note-item"]').forEach(el => {
      const a = el.querySelector('a');
      items.push({
        href: a ? a.getAttribute('href') : 'none',
        html: el.innerHTML.substring(0, 200),
      });
    });
    return items.slice(0, 3);
  });

  console.log('\nNote items:');
  noteItems.forEach(n => console.log('  href:', n.href, '\n  html:', n.html.substring(0, 100)));

  // Test visiting a note with full URL
  if (links.length > 0) {
    const testUrl = links[0].href.startsWith('http') ? links[0].href : 'https://www.xiaohongshu.com' + links[0].href;
    console.log('\nTesting note visit:', testUrl);
    await page.goto(testUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.waitForTimeout(3000);
    const title = await page.title();
    const desc = await page.evaluate(() => {
      const el = document.querySelector('#detail-desc, .desc, .content, [class*="desc"]');
      return el ? el.textContent.trim().substring(0, 200) : 'NOT FOUND';
    });
    console.log('Title:', title);
    console.log('Desc:', desc);
  }

  await browser.close();
})();
