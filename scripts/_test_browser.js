// Test: use Playwright to search XHS directly in browser (no API signing needed)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  // Load cookies from .env
  const env = fs.readFileSync(path.join(__dirname, '..', '.env'), 'utf-8');
  const match = env.match(/^XHS_COOKIE=(.+)$/m);
  if (!match) { console.log('No XHS_COOKIE'); process.exit(1); }
  const rawCookie = match[1].trim();

  // Parse cookie string into array of cookie objects
  const cookies = rawCookie.split(/;\s*/).map(pair => {
    const idx = pair.indexOf('=');
    return {
      name: pair.substring(0, idx).trim(),
      value: pair.substring(idx + 1).trim(),
      domain: '.xiaohongshu.com',
      path: '/',
    };
  }).filter(c => c.name && c.value);

  console.log('Launching browser...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  await context.addCookies(cookies);
  const page = await context.newPage();

  console.log('Navigating to XHS search...');
  try {
    await page.goto('https://www.xiaohongshu.com/search_result?keyword=广州旅游&source=web_search_result_notes', {
      waitUntil: 'networkidle',
      timeout: 30000,
    });
  } catch(e) {
    console.log('Navigation timeout, continuing...');
  }

  // Wait for content
  await page.waitForTimeout(3000);

  // Check page title and content
  const title = await page.title();
  console.log('Page title:', title);

  // Try to find note cards
  const noteCards = await page.$$('.note-item, .feeds-page .note-item, [class*="note"]');
  console.log('Note cards found:', noteCards.length);

  // Get page content sample
  const text = await page.evaluate(() => document.body.innerText.substring(0, 1000));
  console.log('\nPage text (first 1000 chars):');
  console.log(text);

  // Check if we got redirected to login
  const url = page.url();
  console.log('\nCurrent URL:', url);
  if (url.includes('login') || url.includes('passport')) {
    console.log('REDIRECTED TO LOGIN - Cookie is invalid or expired');
  }

  await browser.close();
})();
