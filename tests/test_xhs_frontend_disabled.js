const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const indexHtml = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const appSource = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");
const cppApi = fs.readFileSync(path.join(root, "src", "api.cpp"), "utf8");
const agentApi = fs.readFileSync(path.join(root, "api_multi_agent.py"), "utf8");

if (/data-route="xhs"/.test(indexHtml)) {
  throw new Error("XHS must not have a visible sidebar navigation entry.");
}
if (!/<div[^>]+data-panel="xhsPanel"[^>]+hidden/.test(indexHtml)) {
  throw new Error("XHS panel must remain hidden in the frontend.");
}
if (/xhs:\s*\{/.test(appSource)) {
  throw new Error("Disabled XHS route must not be exposed by the frontend router.");
}
for (const route of ["/api/xhs/parse", "/api/xhs/analyze", "/api/xhs/proxy"]) {
  if (!cppApi.includes(route) || !agentApi.includes(route)) {
    throw new Error(`Backend XHS route must remain available: ${route}`);
  }
}

console.log("XHS frontend is disabled while backend routes remain available.");
