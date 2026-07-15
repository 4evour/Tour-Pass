const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "web", "editor", "src", "NewEditorApp.tsx"),
  "utf8"
);
const appSource = fs.readFileSync(
  path.join(__dirname, "..", "web", "app.js"),
  "utf8"
);

const expectations = [
  [source.includes("new URLSearchParams(window.location.search)"), "editor should read tripId from query params"],
  [source.includes("api(`/trips/${tripId}`)"), "editor should fetch the saved trip by tripId"],
  [source.includes("deserializeTrip"), "editor should deserialize saved trip data into editable days"],
  [source.includes("setWizardStep('plan')"), "editor should open the planning step after deep-link import"],
  [source.includes("api(`/trips/${loadedTripId}`,"), "editor should save changes back to the selected trip"],
  [!source.includes("返回首页"), "editor should not render a home link inside the iframe"],
  [appSource.includes("navigateTo(`editor?tripId=${editBtn.dataset.tripId}`)"), "my trips should open the selected trip in the editor"],
  [appSource.includes("编辑路线"), "my trips should expose an explicit edit action"],
  [appSource.includes("new URLSearchParams(hashParts[1] || \"\").get(\"tripId\")"), "main app should forward the selected tripId to the editor iframe"],
];

const failure = expectations.find(([passed]) => !passed);
if (failure) throw new Error(failure[1]);

console.log("Editor tripId deep-link import hook is present.");
