const fs = require("fs");
const path = require("path");

const apiPath = path.join(__dirname, "..", "src", "api.cpp");
const apiSource = fs.readFileSync(apiPath, "utf8");

if (!apiSource.includes('req.path.find("/css/") == 0')) {
  throw new Error("Expected /css/ static assets to be public so layout styles load before auth.");
}

console.log("Public static path whitelist includes /css/.");
