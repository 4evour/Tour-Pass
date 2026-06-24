const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const indexHtml = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const appSource = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");
const apiSource = fs.readFileSync(path.join(root, "api_multi_agent.py"), "utf8");

const requiredMarkup = [
  'id="xhsImageInput"',
  'type="file"',
  'accept="image/png,image/jpeg,image/webp"',
  'multiple',
  'id="xhsImagePreview"',
];

for (const snippet of requiredMarkup) {
  if (!indexHtml.includes(snippet)) {
    throw new Error(`Expected XHS image upload markup to include ${snippet}.`);
  }
}

const requiredAppHooks = [
  "xhsSelectedImages",
  "function xhsReadImageFiles",
  "function xhsRenderImagePreview",
  "imageDataUrls: xhsSelectedImages.map",
  'url.indexOf("data:image/") === 0',
  'String(url).indexOf("data:image/") !== 0',
];

for (const snippet of requiredAppHooks) {
  if (!appSource.includes(snippet)) {
    throw new Error(`Expected XHS app code to include ${snippet}.`);
  }
}

if (!apiSource.includes("imageDataUrls: list[str]")) {
  throw new Error("Expected XHS parse request to accept uploaded image data URLs.");
}

if (!apiSource.includes("async def _ocr_xhs_image_data_url")) {
  throw new Error("Expected backend OCR helper for uploaded image data URLs.");
}

console.log("XHS image upload markup and hooks are present.");
