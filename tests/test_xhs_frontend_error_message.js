const fs = require("fs");
const path = require("path");
const vm = require("vm");

const appSource = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const start = appSource.indexOf("function xhsErrorMessage");
const end = appSource.indexOf("async function xhsParseLink");

if (start < 0 || end < 0 || end <= start) {
  throw new Error("Expected xhsErrorMessage helper before xhsParseLink.");
}

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(appSource.slice(start, end), sandbox);

if (typeof sandbox.xhsErrorMessage !== "function") {
  throw new Error("xhsErrorMessage should be defined.");
}

const validationMessage = sandbox.xhsErrorMessage({
  detail: [
    { loc: ["body", "link"], msg: "Field required", type: "missing" },
  ],
}, "解析失败");

if (validationMessage.includes("[object Object]")) {
  throw new Error("Validation error objects should not render as [object Object].");
}
if (!validationMessage.includes("Field required")) {
  throw new Error(`Expected validation message to include backend msg, got: ${validationMessage}`);
}

const objectError = sandbox.xhsErrorMessage({
  error: { message: "Agent service unavailable" },
}, "解析失败");

if (objectError !== "Agent service unavailable") {
  throw new Error(`Expected nested error.message, got: ${objectError}`);
}

const stringDetail = sandbox.xhsErrorMessage({ detail: "帖子不存在" }, "解析失败");
if (stringDetail !== "帖子不存在") {
  throw new Error(`Expected string detail to pass through, got: ${stringDetail}`);
}

console.log("XHS frontend error messages are human-readable.");
