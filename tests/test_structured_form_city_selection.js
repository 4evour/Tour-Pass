const { chromium } = require("playwright");
const fs = require("fs");
const http = require("http");
const path = require("path");

function existingChromiumExecutable() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate));
}

function contentType(filePath) {
  if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
  if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
  if (filePath.endsWith(".js")) return "application/javascript; charset=utf-8";
  return "application/octet-stream";
}

function startServer() {
  const webRoot = path.join(__dirname, "..", "web");
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    if (url.pathname === "/auth/me") {
      res.writeHead(200, { "Content-Type": "application/json", "X-Query-Remaining": "8" });
      res.end(JSON.stringify({ id: "u1", username: "tester", role: "guest", query_remaining: 8 }));
      return;
    }
    if (url.pathname === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
      return;
    }
    if (url.pathname === "/cities") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ default: "长沙", cities: [{ name: "长沙" }, { name: "广州" }] }));
      return;
    }
    if (url.pathname === "/favicon.ico") {
      res.writeHead(204);
      res.end();
      return;
    }

    const relativePath = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/+/, "");
    const filePath = path.normalize(path.join(webRoot, relativePath));
    if (!filePath.startsWith(webRoot) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      res.writeHead(404);
      res.end("Not found");
      return;
    }
    res.writeHead(200, { "Content-Type": contentType(filePath) });
    fs.createReadStream(filePath).pipe(res);
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({ server, url: `http://127.0.0.1:${port}/` });
    });
  });
}

async function main() {
  const { server, url } = await startServer();
  const launchOptions = {};
  const executablePath = existingChromiumExecutable();
  if (executablePath) launchOptions.executablePath = executablePath;
  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({ viewport: { width: 1155, height: 912 } });

  try {
    await page.addInitScript(() => localStorage.setItem("tp_token", "test-token"));
    await page.goto(url, { waitUntil: "networkidle" });
    await page.waitForSelector("#mainApp:not([hidden])", { timeout: 5000 });
    await page.waitForSelector("#planModeForm:visible", { timeout: 5000 });
    await page.waitForSelector('#formCityGrid .city-card[data-city="长沙"]', { timeout: 5000 });

    const removedEntryPointCounts = await page.evaluate(() => ({
      modeToggle: document.querySelectorAll(".plan-mode-toggle").length,
      textMode: document.querySelectorAll("#planModeText").length,
      quickPrompts: document.querySelectorAll(".chat-hero-hints").length,
      keywordBar: document.querySelectorAll("#keywordBar").length,
    }));
    if (Object.values(removedEntryPointCounts).some((count) => count !== 0)) {
      throw new Error("Natural-language planning entry points should not be rendered");
    }

    const initialState = await page.evaluate(() => ({
      value: document.getElementById("formCity").value,
      selectedCount: document.querySelectorAll("#formCityGrid .city-card.selected").length,
      activeCount: document.querySelectorAll("#formCityGrid .city-card.active").length,
    }));
    if (initialState.value !== "" || initialState.selectedCount !== 0 || initialState.activeCount !== 0) {
      throw new Error(`Structured form city should start unselected, got ${JSON.stringify(initialState)}`);
    }

    await page.click('#formCityGrid .city-card[data-city="长沙"]');
    const selectedValue = await page.$eval("#formCity", (el) => el.value);
    if (selectedValue !== "长沙") {
      throw new Error(`Expected selecting Changsha to set formCity, got ${selectedValue}`);
    }

    await page.click('#formCityGrid .city-card[data-city="长沙"]');
    const finalState = await page.evaluate(() => ({
      value: document.getElementById("formCity").value,
      selectedCount: document.querySelectorAll("#formCityGrid .city-card.selected").length,
    }));
    if (finalState.value !== "" || finalState.selectedCount !== 0) {
      throw new Error(`Clicking selected city again should clear it, got ${JSON.stringify(finalState)}`);
    }

    console.log("Structured form city selection starts empty and can be cleared.");
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
