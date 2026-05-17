const { chromium } = require("playwright");
const fs = require("fs");

function existingChromiumExecutable() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);
  return candidates.find((path) => fs.existsSync(path));
}

async function main() {
  const url = process.argv[2] || "http://127.0.0.1:8080/";
  const launchOptions = {};
  const executablePath = existingChromiumExecutable();
  if (executablePath) {
    launchOptions.executablePath = executablePath;
  }
  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto(url, { waitUntil: "networkidle" });
  await page.click("#loadExampleButton");
  await page.click("button.primary-action");
  await page.waitForSelector(".overview-section", { timeout: 10000 });

  await page.click('[data-stage="compare"]');
  await page.waitForSelector(".comparison-panel", { timeout: 10000 });

  await page.click('[data-stage="itinerary"]');
  await page.waitForSelector(".visual-panel", { timeout: 10000 });

  await page.click('[data-stage="debug"]');
  await page.waitForSelector(".debug-panel", { timeout: 10000 });

  await page.click('[data-stage="tools"]');
  await page.waitForSelector(".inspector:not([hidden])", { timeout: 10000 });

  const routeNodes = await page.locator(".route-node").count();
  const timelineStops = await page.locator(".timeline-stop").count();
  const comparisonCards = await page.locator(".comparison-card").count();
  const beamSteps = await page.locator(".beam-step").count();
  const paretoDebugItems = await page.locator(".pareto-debug span").count();
  const diversityMetrics = await page.locator(".diversity-metrics span").count();
  const searchContributionItems = await page.locator("#searchOutput .score-breakdown span").count();

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
  if (beamSteps < 3) {
    throw new Error(`Expected Beam Search debug steps, got ${beamSteps}`);
  }
  if (paretoDebugItems < 1) {
    throw new Error(`Expected Pareto debug evidence, got ${paretoDebugItems}`);
  }
  if (diversityMetrics < 3) {
    throw new Error(`Expected diversity metrics, got ${diversityMetrics}`);
  }
  if (searchContributionItems < 1) {
    throw new Error(`Expected BM25 contribution chips, got ${searchContributionItems}`);
  }
  console.log(`UI verification passed: ${routeNodes} route nodes, ${timelineStops} timeline stops, ${comparisonCards} comparison cards, ${beamSteps} beam steps, ${diversityMetrics} diversity metrics, ${searchContributionItems} search contributions.`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
