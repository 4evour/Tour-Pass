const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const api = fs.readFileSync(path.join(root, "src", "api.cpp"), "utf8");
const readme = fs.readFileSync(path.join(root, "README.md"), "utf8");
const apiDocs = fs.readFileSync(path.join(root, "docs", "api.md"), "utf8");
const renderConfig = fs.readFileSync(path.join(root, "render.yaml"), "utf8");

if (api.includes("shouldAutoPromoteAdmin")) {
  throw new Error("Registration must not auto-promote a user when no admin exists.");
}

const explicitChecks = api.match(/isAdminValue\(std::getenv\("TOURPASS_ADMIN_USERS"\), (username|email)\)/g) || [];
if (explicitChecks.length !== 2) {
  throw new Error("Expected username and email registration to use the explicit admin allowlist.");
}

for (const [name, content] of Object.entries({ readme, apiDocs, renderConfig })) {
  if (!content.includes("TOURPASS_ADMIN_USERS")) {
    throw new Error(`Expected ${name} to document the explicit admin allowlist.`);
  }
}

console.log("Explicit administrator bootstrap contracts are present.");
