import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "file:///C:/Users/Lenovo/.codex/skills/guizang-social-card-skill/node_modules/playwright/index.mjs";

const root = "D:/Tour Pass";
const runDir = path.join(
  root,
  "artifacts/tour-pass-tianjin-jinan-baseline/20260920T152250Z/runs/01-tianjin-jinan-national-day-handbook",
);
const outputDir = path.join(root, "output/tourpass-baseline-20260920");
const response = JSON.parse(await fs.readFile(path.join(runDir, "response.json"), "utf8"));

await fs.mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
});

async function render(viewport, name, makePdf = false) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:8765/static/index.html", {
    waitUntil: "networkidle",
    timeout: 30_000,
  });
  await page.waitForFunction(() => typeof renderPlan === "function");
  await page.evaluate((payload) => {
    renderPlan({ plan: payload.plan, run_id: payload.run_id });
  }, response);
  await page.screenshot({
    path: path.join(outputDir, `${name}.png`),
    fullPage: true,
  });

  const state = await page.evaluate(() => ({
    title: document.querySelector("#result h1")?.textContent?.trim() || "",
    width: document.documentElement.scrollWidth,
    height: document.documentElement.scrollHeight,
    details: document.querySelectorAll("#result details").length,
    openDetails: document.querySelectorAll("#result details[open]").length,
    links: [...document.querySelectorAll("#result a")].map((link) => link.href),
    textChars: document.querySelector("#result")?.innerText.length || 0,
    horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
  }));

  if (makePdf) {
    await page.emulateMedia({ media: "print" });
    await page.pdf({
      path: path.join(outputDir, `${name}.pdf`),
      format: "A4",
      printBackground: true,
      preferCSSPageSize: true,
      tagged: true,
      outline: true,
    });
  }
  await page.close();
  return { name, ...state, pageErrors: [...new Set(errors)] };
}

try {
  const desktop = await render({ width: 1440, height: 1000 }, "desktop", true);
  const mobile = await render({ width: 390, height: 844 }, "mobile");
  const result = { outputDir, desktop, mobile };
  await fs.writeFile(
    path.join(outputDir, "render-report.json"),
    `${JSON.stringify(result, null, 2)}\n`,
    "utf8",
  );
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
}
