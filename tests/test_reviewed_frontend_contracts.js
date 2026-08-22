const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");
const editorApp = fs.readFileSync(path.join(root, "web", "editor", "src", "NewEditorApp.tsx"), "utf8");
const routeHook = fs.readFileSync(path.join(root, "web", "editor", "src", "hooks", "useRoute.ts"), "utf8");
const hotelsStep = fs.readFileSync(path.join(root, "web", "editor", "src", "components", "Wizard", "HotelsStep.tsx"), "utf8");

if (/\sonclick\s*=\s*["']/.test(app)) {
  throw new Error("Expected main app dynamic markup to avoid CSP-blocked inline event handlers.");
}
if (!app.includes('data-action="toggle-guide"') || !app.includes("data-xhs-edit-index")) {
  throw new Error("Expected CSP-safe data attributes for delegated actions.");
}
if (!editorApp.includes("useRoute();")) {
  throw new Error("Expected the active NewEditorApp entry to enable route loading.");
}
if (!routeHook.includes("JSON.stringify({ poi_ids: deduped, city })")) {
  throw new Error("Expected batch route requests to include the selected city.");
}
if (!routeHook.includes("if (error.name === 'AbortError') return;")) {
  throw new Error("Expected cancelled route requests to avoid writing stale fallback routes.");
}
if (!hotelsStep.includes("new AbortController()") || !hotelsStep.includes("controller.abort()")) {
  throw new Error("Expected hotel requests to be cancelled when the selected city changes.");
}

console.log("Reviewed frontend interaction contracts are present.");
