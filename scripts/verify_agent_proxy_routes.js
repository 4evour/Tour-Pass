const fs = require("fs");
const path = require("path");

const apiPath = path.join(__dirname, "..", "src", "api.cpp");
const source = fs.readFileSync(apiPath, "utf8");

const requiredRoutes = [
  'server.Post("/agent/plan-structured", agentProxyHandler)',
];

const missing = requiredRoutes.filter((route) => !source.includes(route));
if (missing.length > 0) {
  throw new Error(`Missing agent proxy routes: ${missing.join(", ")}`);
}

console.log("Agent proxy route verification passed.");
