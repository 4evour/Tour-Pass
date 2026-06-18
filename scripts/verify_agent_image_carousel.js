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

    const manualPlannerLinkCount = await page.locator('a[href="/editor"]').count();
    if (manualPlannerLinkCount !== 0) {
      throw new Error(`Expected manual planner entry to be removed, got ${manualPlannerLinkCount}`);
    }
    const manualPreferenceCount = await page.locator("#formSection, #planForm").count();
    if (manualPreferenceCount !== 0) {
      throw new Error(`Expected manual preference form to be removed, got ${manualPreferenceCount}`);
    }
    const agentButtonCount = await page.locator("#chatButton").count();
    if (agentButtonCount !== 1) {
      throw new Error(`Expected AI agent planner entry to remain available, got ${agentButtonCount}`);
    }

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

    const imageBox = await img.boundingBox();
    if (!imageBox) {
      throw new Error("Expected carousel image to have a visible bounding box");
    }
    await page.mouse.move(imageBox.x + imageBox.width * 0.25, imageBox.y + imageBox.height * 0.5);
    await page.mouse.down();
    await page.mouse.move(imageBox.x + imageBox.width * 0.80, imageBox.y + imageBox.height * 0.5, { steps: 6 });
    await page.mouse.up();
    const swipedPrevSrc = await img.getAttribute("src");
    if (!swipedPrevSrc.includes(encodeURIComponent("#c25b1e"))) {
      throw new Error("Expected right swipe on the image to switch to the previous image");
    }

    await page.mouse.move(imageBox.x + imageBox.width * 0.80, imageBox.y + imageBox.height * 0.5);
    await page.mouse.down();
    await page.mouse.move(imageBox.x + imageBox.width * 0.25, imageBox.y + imageBox.height * 0.5, { steps: 6 });
    await page.mouse.up();
    const swipedNextSrc = await img.getAttribute("src");
    if (!swipedNextSrc.includes(encodeURIComponent("#2563eb"))) {
      throw new Error("Expected left swipe on the image to switch to the next image");
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

    const duplicateText = "\u6B27\u5F0F\u5EFA\u7B51\u7FA4\u4E0E\u767E\u5E74\u53E4\u6811\u4EA4\u7EC7\u7684\u65F6\u5149\u96A7\u9053\u3002\u5EFA\u8BAE\u508D\u665A\u53BB\uFF0C\u5149\u5F71\u900F\u8FC7\u6995\u6811\u53F6\u6D12\u5728\u77F3\u677F\u8DEF\u4E0A\u6700\u51FA\u7247\u3002";
    await page.evaluate((duplicateText) => {
      renderAgentResult({
        city: "\u5E7F\u5DDE",
        days: [{
          day: 1,
          stops: [{
            poi_name: "\u6C99\u9762\u516C\u56ED",
            poi_type: "attraction",
            area: "\u8354\u6E7E\u533A",
            start_time: "09:00",
            end_time: "10:30",
            reason: duplicateText,
            guide_text: "\u6C99\u9762\u516C\u56ED\u85CF\u5728\u5E7F\u5DDE\u8354\u6E7E\u7684\u6B27\u5F0F\u5EFA\u7B51\u7FA4\u91CC\uFF0C\u6EE1\u773C\u767E\u5E74\u53E4\u6811\u548C\u6D0B\u697C\u3002",
            recommendation: duplicateText,
          }],
        }],
      });
    }, duplicateText);

    const duplicateVisibleCount = await page.locator(`text=${duplicateText}`).count();
    if (duplicateVisibleCount !== 1) {
      throw new Error(`Expected duplicate recommendation text to render once, got ${duplicateVisibleCount}`);
    }

    await page.setViewportSize({ width: 390, height: 820 });
    const wrappingGuideText = "\u7075\u9690\u5BFA\u85CF\u5728\u897F\u6E56\u897F\u9762\u7684\u5C71\u6797\u91CC\uFF0C\u9999\u706B\u65FA\u3001\u53E4\u6728\u53C2\u5929\uFF0C\u98DE\u6765\u5CF0\u77F3\u523B\u548C\u4E91\u6797\u7985\u5BFA\u533E\u989D\u90FD\u503C\u5F97\u770B\u3002\u5EFA\u8BAE\u4E00\u65E9\u53BB\u907F\u5F00\u4EBA\u6F6E\uFF0C\u987A\u8DEF\u722C\u5317\u9AD8\u5CF0\uFF0C\u611F\u53D7\u6668\u949F\u66AE\u9F13\u7684\u7985\u610F\u3002";
    if (wrappingGuideText.length > 120) {
      throw new Error("Guide layout fixture must stay below the old length-based toggle threshold");
    }
    await page.evaluate((wrappingGuideText) => {
      renderAgentResult({
        city: "\u676D\u5DDE",
        days: [{
          day: 1,
          stops: [{
            poi_name: "\u7075\u9690\u5BFA",
            poi_type: "attraction",
            area: "\u897F\u6E56\u533A",
            start_time: "09:00",
            end_time: "10:30",
            guide_text: wrappingGuideText,
          }],
        }],
      });
    }, wrappingGuideText);

    const guideTextBox = await page.locator(".agent-stop-guide-text").first().evaluate((el) => ({
      clientHeight: el.clientHeight,
      scrollHeight: el.scrollHeight,
    }));
    const guideToggleCount = await page.locator(".agent-stop-guide-toggle").count();
    if (guideTextBox.scrollHeight > guideTextBox.clientHeight + 1 && guideToggleCount === 0) {
      throw new Error("Expected wrapped guide text to either fit its box or show an expand control");
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
