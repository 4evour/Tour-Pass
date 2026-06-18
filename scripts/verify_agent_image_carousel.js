const { chromium } = require("playwright");
const fs = require("fs");
const http = require("http");
const path = require("path");

const ROOT = path.join(__dirname, "..", "web");
const PORT = 19081;

function existingChromiumExecutable() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);
  return candidates.find((item) => fs.existsSync(item));
}

function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return {
    ".css": "text/css",
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
  }[ext] || "application/octet-stream";
}

function startServer() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
    if (url.pathname === "/auth/me") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ username: "test", role: "guest", query_remaining: 10 }));
      return;
    }
    if (url.pathname === "/health" || url.pathname === "/agent/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "ok" }));
      return;
    }
    if (url.pathname === "/cities") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ default: "\u5E7F\u5DDE", cities: [{ name: "\u5E7F\u5DDE" }] }));
      return;
    }
    if (url.pathname === "/poi/search") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ data: [] }));
      return;
    }
    if (url.pathname.startsWith("/city/")) {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ city: "\u5E7F\u5DDE", sections: {} }));
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
      res.writeHead(200, { "Content-Type": contentType(filePath) });
      res.end(data);
    });
  });

  return new Promise((resolve) => {
    server.listen(PORT, "127.0.0.1", () => resolve(server));
  });
}

function svgDataUrl(fill) {
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="${fill}"/></svg>`
  )}`;
}

async function main() {
  const server = await startServer();
  const launchOptions = {};
  const executablePath = existingChromiumExecutable();
  if (executablePath) {
    launchOptions.executablePath = executablePath;
  }
  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({ viewport: { width: 973, height: 912 } });
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  try {
    await page.addInitScript(() => {
      localStorage.setItem("tp_token", "test-token");
    });
    await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "networkidle" });
    await page.waitForSelector("#mainApp:not([hidden])", { timeout: 10000 });

    const first = svgDataUrl("#146b5d");
    const second = svgDataUrl("#c25b1e");
    const third = svgDataUrl("#2563eb");
    await page.evaluate(({ first, second, third }) => {
      renderAgentResult({
        city: "\u5E7F\u5DDE",
        days: [{
          day: 1,
          stops: [{
            poi_name: "\u6D4B\u8BD5\u666F\u70B9",
            poi_type: "attraction",
            area: "\u6D4B\u8BD5\u533A",
            start_time: "09:00",
            end_time: "10:00",
            image_url: first,
            images: [
              { url: first },
              { url: second },
              { url: third },
            ],
          }],
        }],
      });
    }, { first, second, third });

    await page.waitForSelector(".agent-stop-img", { timeout: 10000 });
    const next = page.locator(".agent-stop-carousel-btn.next");
    const prev = page.locator(".agent-stop-carousel-btn.prev");
    if (await next.count() !== 1 || await prev.count() !== 1) {
      throw new Error("Expected previous and next carousel buttons for multi-image stop");
    }

    const img = page.locator(".agent-stop-img").first();
    const initialSrc = await img.getAttribute("src");
    await next.click();
    const nextSrc = await img.getAttribute("src");
    if (nextSrc === initialSrc || !nextSrc.includes(encodeURIComponent("#c25b1e"))) {
      throw new Error("Expected next button to switch to the second image");
    }

    await prev.click();
    const prevSrc = await img.getAttribute("src");
    if (prevSrc !== initialSrc) {
      throw new Error("Expected previous button to switch back to the first image");
    }

    await next.click();
    await next.click();
    const thirdSrc = await img.getAttribute("src");
    if (thirdSrc === initialSrc || !thirdSrc.includes(encodeURIComponent("#2563eb"))) {
      throw new Error("Expected repeated next clicks to reach the third image");
    }

    const imagesOnlyFirst = svgDataUrl("#9333ea");
    const imagesOnlySecond = svgDataUrl("#dc2626");
    await page.evaluate(({ imagesOnlyFirst, imagesOnlySecond }) => {
      renderAgentResult({
        city: "\u5E7F\u5DDE",
        days: [{
          day: 1,
          stops: [{
            poi_name: "\u4EC5 images \u666F\u70B9",
            poi_type: "attraction",
            area: "\u6D4B\u8BD5\u533A",
            start_time: "10:00",
            end_time: "11:00",
            images: [
              { url: imagesOnlyFirst },
              { url: imagesOnlySecond },
            ],
          }],
        }],
      });
    }, { imagesOnlyFirst, imagesOnlySecond });

    const imagesOnlySrc = await page.locator(".agent-stop-img").first().getAttribute("src");
    if (!imagesOnlySrc || !imagesOnlySrc.includes(encodeURIComponent("#9333ea"))) {
      throw new Error("Expected images array to render when image_url is missing");
    }

    if (errors.length > 0) {
      throw new Error(`Browser console errors: ${errors.join(" | ")}`);
    }
    console.log("Agent image carousel verification passed.");
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
