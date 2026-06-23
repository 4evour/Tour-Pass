const fs = require("fs");
const path = require("path");

const appSource = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");

if (!appSource.includes('document.querySelector(".shell-menu-btn")?.addEventListener("click"')) {
  throw new Error("Expected the fixed shell menu button to toggle the mobile sidebar.");
}

console.log("Shell menu button binding is present.");
