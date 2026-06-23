const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const indexHtml = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const styles = fs.readFileSync(path.join(root, "web", "styles.css"), "utf8");
const sidebarStyles = fs.readFileSync(path.join(root, "web", "css", "sidebar.css"), "utf8");

const expectations = [
  [indexHtml.includes("auth-topbar"), "login page should include the Tour-AI style top bar"],
  [indexHtml.includes("auth-sidebar"), "login page should include the Tour-AI style side navigation"],
  [styles.includes("--app-bg: #f3f4f6"), "global tokens should use the light gray app workspace background"],
  [sidebarStyles.includes("--sidebar-width: 244px"), "sidebar should match the target layout width"],
  [sidebarStyles.includes(".sidebar-shell-topbar"), "main app should have a fixed top brand bar"],
];

const failure = expectations.find(([passed]) => !passed);
if (failure) {
  throw new Error(failure[1]);
}

console.log("Tour-AI layout markup and tokens are present.");
