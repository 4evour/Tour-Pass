const fs = require("fs");
const path = require("path");

const dockerfile = fs.readFileSync(path.join(__dirname, "..", "Dockerfile"), "utf8");

if (/python3 -c [^\r\n]+\|\|\s*echo\s+["']?WARN/.test(dockerfile)) {
  throw new Error("Expected Agent import verification failures to stop the Docker build.");
}

const healthcheck = dockerfile.match(/HEALTHCHECK[\s\S]*?(?=\n\n|\nCMD\s)/)?.[0] || "";
if (!healthcheck.includes("http://localhost:8080/health")) {
  throw new Error("Expected the container health check to verify the C++ service.");
}
if (!healthcheck.includes("http://localhost:8090/agent/ping")) {
  throw new Error("Expected the container health check to verify the Python Agent.");
}
if (!/8080\/health[^\r\n]*&&[^\r\n]*8090\/agent\/ping/.test(healthcheck)) {
  throw new Error("Expected both service health checks to be required.");
}

console.log("Reviewed Docker build and health contracts are present.");
