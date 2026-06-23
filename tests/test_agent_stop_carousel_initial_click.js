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
      res.end(JSON.stringify({ data: [{ name: "长沙" }] }));
      return;
    }
    if (url.pathname === "/slow-missing.jpg") {
      setTimeout(() => {
        res.writeHead(404);
        res.end("missing");
      }, 120);
      return;
    }
    if (url.pathname === "/ok.svg") {
      res.writeHead(200, { "Content-Type": "image/svg+xml" });
      res.end('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="45"><rect width="80" height="45" fill="#146b5d"/></svg>');
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
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });

  try {
    await page.addInitScript(() => localStorage.setItem("tp_token", "test-token"));
    await page.goto(url, { waitUntil: "networkidle" });
    await page.waitForFunction(() => typeof window.renderStopCard === "function");
    await page.evaluate(() => {
      const card = window.renderStopCard({
        poi_id: "p1",
        poi_name: "测试景点",
        poi_type: "attraction",
        image_url: "/first-missing.jpg",
        images: ["/ok.svg"],
      }, { day: 1, stops: [] }, { city: "长沙" });
      document.body.appendChild(card);
      window.__firstCarouselError = document.querySelector(".agent-stop-img").onerror;
    });

    await page.click(".agent-stop-carousel-btn.next");
    await page.evaluate(() => {
      const img = document.querySelector(".agent-stop-img");
      window.__firstCarouselError.call(img);
    });
    await page.waitForTimeout(300);

    const state = await page.evaluate(() => {
      const img = document.querySelector(".agent-stop-img");
      return {
        src: img.getAttribute("src"),
        hasError: img.classList.contains("error"),
        hasPlaceholder: Boolean(document.querySelector(".agent-stop-noimg")),
      };
    });

    if (state.src !== "/ok.svg") {
      throw new Error(`Expected initial next click to keep /ok.svg, got ${state.src}`);
    }
    if (state.hasError || state.hasPlaceholder) {
      throw new Error("Initial next click should not be overwritten by the previous image failure.");
    }

    console.log("Agent stop carousel initial click handles delayed first-image failure.");
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
