const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const indexHtml = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const appSource = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");

const requiredMarkup = [
  "xhsInputView",
  "xhsLinkInput",
  "xhsParseBtn",
  "xhsSteps",
  "xhsResultView",
  "xhsTimeline",
  "xhsPlaceModal",
  "xhsLightbox",
];

for (const id of requiredMarkup) {
  if (!indexHtml.includes(`id="${id}"`)) {
    throw new Error(`Expected XHS panel markup to include #${id}.`);
  }
}

if (!indexHtml.includes('placeholder="粘贴小红书帖子全文或分享文案..."')) {
  throw new Error("XHS input should tell users they can paste full note text.");
}

if (!indexHtml.includes('maxlength="5000"')) {
  throw new Error("XHS input should allow pasted note text up to 5000 characters.");
}

if (indexHtml.includes("功能开发中，敬请期待")) {
  throw new Error("XHS panel should not render the placeholder copy.");
}

const requiredAppHooks = [
  "function xhsToSavedTripPayload",
  "async function xhsSaveAsTrip",
  "async function xhsExportToEditor",
];

for (const snippet of requiredAppHooks) {
  if (!appSource.includes(snippet)) {
    throw new Error(`Expected XHS app code to include ${snippet}.`);
  }
}

console.log("XHS panel markup and app hooks are present.");
