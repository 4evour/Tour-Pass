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
    if (url.pathname === "/trips/list") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ data: [] }));
      return;
    }
    if (url.pathname === "/cities") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ data: [{ name: "广州" }] }));
      return;
    }
    if (url.pathname === "/favicon.ico") {
      res.writeHead(204);
      res.end();
      return;
    }
    if (url.pathname === "/editor/index.html") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end("<!doctype html><title>Editor mock</title><main>Editor loaded</main>");
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
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  try {
    await page.addInitScript(() => localStorage.setItem("tp_token", "test-token"));
    await page.goto(url, { waitUntil: "networkidle" });
    await page.waitForSelector("#mainApp:not([hidden])", { timeout: 5000 });

    const routes = [
      ["plan", "planPanel"],
      ["trips", "tripsPanel"],
      ["editor", "editorPanel"],
      ["xhs", "xhsPanel"],
      ["profile", "profilePanel"],
      ["contact", "contactPanel"],
    ];

    for (const [route, panel] of routes) {
      await page.click(`#sidebar a[data-route="${route}"]`);
      await page.waitForFunction((expected) => location.hash === `#/${expected}`, route);
      await page.waitForTimeout(100);

      const state = await page.evaluate(({ route, panel }) => ({
        mainHidden: document.getElementById("mainApp").hidden,
        panelHidden: document.querySelector(`[data-panel="${panel}"]`).hidden,
        active: document.querySelector(`#sidebar a[data-route="${route}"]`).classList.contains("active"),
      }), { route, panel });

      if (state.mainHidden) {
        throw new Error(`${route} sidebar navigation should keep the main app shell visible.`);
      }
      if (state.panelHidden) {
        throw new Error(`${route} sidebar navigation should show ${panel}.`);
      }
      if (!state.active) {
        throw new Error(`${route} sidebar navigation should mark the matching item active.`);
      }
    }

    if (errors.length > 0) {
      throw new Error(`Browser console errors: ${errors.join(" | ")}`);
    }

    console.log("Sidebar hash routing keeps the app shell visible and switches every panel.");
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
