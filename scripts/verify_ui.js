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

  const fixtureItinerary = {
    city: "长沙",
    summary: "UI smoke fixture",
    days: [1, 2].map((day) => ({
      day,
      summary: `第 ${day} 天`,
      stops: [1, 2].map((stop) => ({
        poi_id: `ui-smoke-${day}-${stop}`,
        poi_name: `测试地点 ${day}-${stop}`,
        poi_type: stop === 1 ? "attraction" : "restaurant",
        area: "测试区域",
        start_time: stop === 1 ? "09:00" : "12:00",
        end_time: stop === 1 ? "10:30" : "13:00",
        visit_duration_minutes: stop === 1 ? 90 : 60,
        travel_minutes_from_previous: stop === 1 ? 0 : 15,
      })),
    })),
  };
  await page.route("**/agent/plan-structured", async (route) => {
    const stream = [
      `data: ${JSON.stringify({ type: "session", session_id: "ui-smoke-session" })}`,
      `data: ${JSON.stringify({ type: "itinerary", itinerary: fixtureItinerary })}`,
      "",
    ].join("\n");
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream; charset=utf-8",
      body: stream,
    });
  });

  let city = "";
  let dayCount = 0;
  let stopCount = 0;
  let sidebarItemCount = 0;
  let serviceStatus = "";
  try {
    await page.goto(url, { waitUntil: "networkidle" });
    await page.click("#guestBtn");
    await page.waitForSelector("#mainApp:not([hidden])", { timeout: 10000 });
    await page.waitForSelector("#formCityGrid .city-card", { timeout: 10000 });
    const changsha = page.locator('#formCityGrid .city-card[data-city="长沙"]');
    const cityCard = await changsha.count()
      ? changsha
      : page.locator("#formCityGrid .city-card").first();
    city = await cityCard.getAttribute("data-city") || "";
    await cityCard.click();
    await page.click('#formDaysGroup .day-btn[data-value="2"]');
    const planResponse = page.waitForResponse(
      (response) => response.url().includes("/agent/plan-structured"),
      { timeout: 60000 },
    );
    await page.click("#formSubmitBtn");
    const response = await planResponse;
    if (!response.ok()) {
      throw new Error(`Structured planning request failed with HTTP ${response.status()}`);
    }
    await page.waitForSelector("#agentResult:not([hidden]) .agent-day", { timeout: 60000 });
    dayCount = await page.locator("#agentResult .agent-day").count();
    stopCount = await page.locator("#agentResult .agent-stop").count();
    sidebarItemCount = await page.locator("#sidebar .sidebar-item").count();
    serviceStatus = await page.locator("#serviceStatus").innerText();
  } finally {
    await browser.close();
  }

  if (errors.length > 0) {
    throw new Error(`Browser console errors: ${errors.join(" | ")}`);
  }
  if (!city) {
    throw new Error("Expected at least one selectable city");
  }
  if (dayCount !== 2) {
    throw new Error(`Expected 2 itinerary days, got ${dayCount}`);
  }
  if (stopCount < 4) {
    throw new Error(`Expected at least 4 itinerary stops, got ${stopCount}`);
  }
  if (sidebarItemCount !== 5) {
    throw new Error(`Expected 5 sidebar entries, got ${sidebarItemCount}`);
  }
  if (!serviceStatus.includes("POI")) {
    throw new Error(`Expected POI service status, got ${serviceStatus}`);
  }
  console.log(`UI verification passed: guest planning for ${city}, ${dayCount} days, ${stopCount} stops, ${sidebarItemCount} sidebar entries.`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
