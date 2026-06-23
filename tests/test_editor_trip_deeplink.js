const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "web", "editor", "src", "NewEditorApp.tsx"),
  "utf8"
);

const expectations = [
  [source.includes("new URLSearchParams(window.location.search)"), "editor should read tripId from query params"],
  [source.includes("api(`/trips/${tripId}`)"), "editor should fetch the saved trip by tripId"],
  [source.includes("deserializeTrip"), "editor should deserialize saved trip data into editable days"],
  [source.includes("setWizardStep('plan')"), "editor should open the planning step after deep-link import"],
];

const failure = expectations.find(([passed]) => !passed);
if (failure) throw new Error(failure[1]);

console.log("Editor tripId deep-link import hook is present.");
