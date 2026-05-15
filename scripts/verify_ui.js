const { chromium } = require("playwright");

async function main() {
  const url = process.argv[2] || "http://127.0.0.1:8080/";
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto(url, { waitUntil: "networkidle" });
  await page.click("#loadExampleButton");
  await page.click("button.primary-action");
  await page.waitForSelector(".visual-panel", { timeout: 10000 });

  const routeNodes = await page.locator(".route-node").count();
  const timelineStops = await page.locator(".timeline-stop").count();
  const comparisonCards = await page.locator(".comparison-card").count();

  await browser.close();

  if (errors.length > 0) {
    throw new Error(`Browser console errors: ${errors.join(" | ")}`);
  }
  if (routeNodes < 2) {
    throw new Error(`Expected route visualization nodes, got ${routeNodes}`);
  }
  if (timelineStops < 4) {
    throw new Error(`Expected timeline stops, got ${timelineStops}`);
  }
  if (comparisonCards < 2) {
    throw new Error(`Expected candidate comparison cards, got ${comparisonCards}`);
  }
  console.log(`UI verification passed: ${routeNodes} route nodes, ${timelineStops} timeline stops, ${comparisonCards} comparison cards.`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
