const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "..", "src", "api.cpp"), "utf8");

const requiredRoutes = [
  'server.Post("/api/xhs/parse", agentProxyHandler)',
  'server.Post("/api/xhs/analyze", agentProxyHandler)',
  'server.Get("/api/xhs/proxy", agentProxyHandler)',
];

for (const route of requiredRoutes) {
  if (!source.includes(route)) {
    throw new Error(`Expected C++ gateway to proxy Python XHS route: ${route}`);
  }
}

if (!source.includes("std::wstring wpath(upstreamPath.begin(), upstreamPath.end())")) {
  throw new Error("Expected WinHTTP proxy path to include query strings for /api/xhs/proxy.");
}

console.log("XHS Python routes are proxied by the C++ gateway.");
