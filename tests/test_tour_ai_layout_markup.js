const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const indexHtml = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const styles = fs.readFileSync(path.join(root, "web", "styles.css"), "utf8");
const sidebarStyles = fs.readFileSync(path.join(root, "web", "css", "sidebar.css"), "utf8");

function extractLabels(scopePattern, labelPattern) {
  const scope = indexHtml.match(scopePattern)?.[1] || "";
  return [...scope.matchAll(labelPattern)].map(match => match[1].trim());
}

const authSidebarLabels = extractLabels(
  /<aside class="auth-sidebar"[\s\S]*?>([\s\S]*?)<\/aside>/,
  /<a[^>]*>([^<]+)<\/a>/g
);
const appSidebarLabels = extractLabels(
  /<nav id="sidebar"[\s\S]*?>([\s\S]*?)<\/nav>/,
  /<span class="sidebar-label">([^<]+)<\/span>/g
);
const launchedSidebarLabels = ["AI 助手", "我的行程", "路线规划", "个人中心", "联系我们"];

const expectations = [
  [indexHtml.includes("auth-topbar"), "login page should include the Tour-AI style top bar"],
  [indexHtml.includes("auth-sidebar"), "login page should include the Tour-AI style side navigation"],
  [JSON.stringify(authSidebarLabels) === JSON.stringify(launchedSidebarLabels), "login sidebar should only show launched features"],
  [JSON.stringify(appSidebarLabels) === JSON.stringify(launchedSidebarLabels), "login and app sidebars should show the same features in the same order"],
  [styles.includes("--app-bg: #f3f4f6"), "global tokens should use the light gray app workspace background"],
  [sidebarStyles.includes("--sidebar-width: 244px"), "sidebar should match the target layout width"],
  [sidebarStyles.includes(".sidebar-shell-topbar"), "main app should have a fixed top brand bar"],
];

const failure = expectations.find(([passed]) => !passed);
if (failure) {
  throw new Error(failure[1]);
}

console.log("Tour-AI layout markup and tokens are present.");
