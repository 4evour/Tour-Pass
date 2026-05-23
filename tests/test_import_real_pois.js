const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const root = path.resolve(__dirname, "..");
const fixture = path.join(root, "tests", "fixtures", "real_pois_sample.csv");
const outDir = path.join(root, "output", "test-real-import");

fs.rmSync(outDir, { recursive: true, force: true });

const importResult = spawnSync(process.execPath, [
  "scripts/import_real_pois.js",
  "--input", fixture,
  "--out-dir", outDir,
  "--neighbors", "2",
], {
  cwd: root,
  encoding: "utf8",
});

assert.strictEqual(importResult.status, 0, importResult.stderr || importResult.stdout);

const pois = JSON.parse(fs.readFileSync(path.join(outDir, "pois.json"), "utf8"));
const edges = JSON.parse(fs.readFileSync(path.join(outDir, "edges.json"), "utf8"));

assert.strictEqual(pois.length, 4, "imports every fixture POI");
assert.ok(pois.every((poi) => poi.id && poi.name && poi.type), "normalizes required POI fields");
assert.ok(pois.some((poi) => poi.type === "hotel"), "keeps hotel type");
assert.ok(pois.some((poi) => poi.tags.includes("历史文化")), "splits tags into arrays");
assert.ok(edges.length >= 4, "generates nearest-neighbor commute edges");
assert.ok(edges.every((edge) => edge.distance_meters > 0 && edge.transit_minutes >= 0), "edges include commute estimates");

const validateResult = spawnSync(process.execPath, [
  "scripts/validate_data.js",
  "--pois", path.join(outDir, "pois.json"),
  "--edges", path.join(outDir, "edges.json"),
], {
  cwd: root,
  encoding: "utf8",
});

assert.strictEqual(validateResult.status, 0, validateResult.stderr || validateResult.stdout);
assert.ok(validateResult.stdout.includes("4 POIs"), "validates the imported dataset, not the default data files");

fs.rmSync(outDir, { recursive: true, force: true });
console.log("Real POI import test passed.");
