/**
 * Convert resume HTML to A4 PDF using Playwright.
 * Usage: node scripts/md_to_pdf.js
 */
const { chromium } = require('playwright');
const path = require('path');

const HTML_FILE = path.join(__dirname, '..', 'docs', 'resume_v3.0.html');
const OUT_FILE = path.join(__dirname, '..', 'docs', 'resume_v3.0.pdf');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file:///' + HTML_FILE.replace(/\\/g, '/'), { waitUntil: 'networkidle' });

  await page.pdf({
    path: OUT_FILE,
    format: 'A4',
    printBackground: true,
    margin: { top: 0, bottom: 0, left: 0, right: 0 },
    preferCSSPageSize: true,
  });

  await browser.close();
  console.log(`PDF saved to: ${OUT_FILE}`);
})();
