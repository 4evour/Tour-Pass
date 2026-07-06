const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "..", "src", "api.cpp"), "utf8");

const requiredRoutes = [
  'server.Post("/api/xhs/parse", agentProxyHandler)',
  'server.Post("/api/xhs/analyze", agentProxyHandler)',
  'server.Get("/api/xhs/proxy", agentProxyHandler)',
  'server.Post("/agent/modify", agentProxyHandler)',
];

for (const route of requiredRoutes) {
  if (!source.includes(route)) {
    throw new Error(`Expected C++ gateway to proxy Python XHS route: ${route}`);
  }
}

if (!source.includes("std::wstring wpath(upstreamPath.begin(), upstreamPath.end())")) {
  throw new Error("Expected WinHTTP proxy path to include query strings for /api/xhs/proxy.");
}

if (source.includes('req.path.find("/api/") == 0')) {
  throw new Error("Expected auth allowlist not to expose every /api/* route.");
}

if (source.includes('req.path.find("/agent/") == 0')) {
  throw new Error("Expected auth allowlist not to expose every /agent/* route.");
}

const publicPathStart = source.indexOf("bool isPublicPath =");
const publicPathEnd = source.indexOf("// API key bypass", publicPathStart);
if (publicPathStart < 0 || publicPathEnd < 0) {
  throw new Error("Expected to find public path allowlist.");
}
const publicPathBlock = source.slice(publicPathStart, publicPathEnd);
if (!publicPathBlock.includes('req.path == "/api/xhs/parse"')) {
  throw new Error("Expected /api/xhs/parse to remain public.");
}
if (publicPathBlock.includes('req.path == "/api/xhs/analyze"')) {
  throw new Error("Expected /api/xhs/analyze to require auth.");
}

console.log("XHS Python routes are proxied by the C++ gateway.");
