const fs = require("fs");
const http = require("http");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.join(__dirname, "..", "web");
const PORT = 19082;
const savedPayloads = [];

function existingChromiumExecutable() {
  return [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean).find((item) => fs.existsSync(item));
}

function json(res, body) {
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

function startServer() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
    if (url.pathname === "/auth/me") return json(res, { username: "test", role: "guest", query_remaining: 10 });
    if (url.pathname === "/health" || url.pathname === "/agent/health") return json(res, { status: "ok" });
    if (url.pathname === "/cities") return json(res, { default: "广州", cities: [{ name: "广州" }] });
    if (url.pathname === "/poi/search") return json(res, { data: [] });
    if (url.pathname.startsWith("/city/")) return json(res, { city: "广州", sections: {} });

    if (url.pathname === "/api/itineraries/plan") {
      const itinerary = {
        city: "广州",
        days: [{ day: 1, stops: [{ poi_name: "测试景点", poi_type: "attraction", start_time: "09:00", end_time: "10:00" }] }],
      };
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      res.end(`data: ${JSON.stringify({ type: "itinerary", itinerary, session_id: "save-test" })}\n\ndata: {}\n\n`);
      return;
    }

    if (url.pathname === "/trips/save" && req.method === "POST") {
      let body = "";
      req.on("data", (chunk) => { body += chunk; });
      req.on("end", () => {
        savedPayloads.push(JSON.parse(body));
        json(res, { id: savedPayloads.length });
      });
      return;
    }

    const pathname = url.pathname === "/" ? "/index.html" : url.pathname;
    const filePath = path.normalize(path.join(ROOT, pathname));
    if (!filePath.startsWith(ROOT)) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }
    fs.readFile(filePath, (error, data) => {
      if (error) {
        res.writeHead(404);
        res.end("Not found");
        return;
      }
      const ext = path.extname(filePath);
      const types = { ".html": "text/html", ".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png" };
      res.writeHead(200, { "Content-Type": types[ext] || "application/octet-stream" });
      res.end(data);
    });
  });
  return new Promise((resolve) => server.listen(PORT, "127.0.0.1", () => resolve(server)));
}

async function main() {
  const server = await startServer();
  const executablePath = existingChromiumExecutable();
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

  try {
    await page.addInitScript(() => localStorage.setItem("tp_token", "test-token"));
    await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "networkidle" });
    await page.locator('.city-card[data-city="广州"]').click();

    for (let generation = 1; generation <= 2; generation += 1) {
      await page.locator("#formSubmitBtn").click();
      const saveButton = page.locator("#agentSaveTripBtn");
      await saveButton.waitFor({ state: "visible", timeout: 10000 });
      if (await saveButton.isDisabled()) throw new Error(`Generation ${generation} save button should be enabled.`);
      await saveButton.click();
      await page.waitForFunction(() => document.querySelector("#agentSaveTripBtn")?.textContent.includes("已保存"));
    }

    if (savedPayloads.length !== 2) throw new Error(`Expected 2 saved trips, got ${savedPayloads.length}.`);
    for (const payload of savedPayloads) {
      if (payload.request?.city !== "广州") throw new Error("Saved request should preserve the selected city.");
      if (payload.response?.days?.length !== 1) throw new Error("Saved response should contain the generated itinerary.");
    }
    console.log("Agent-generated itineraries can be saved independently.");
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
