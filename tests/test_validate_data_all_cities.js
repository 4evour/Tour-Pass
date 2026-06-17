const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..");
const scriptPath = path.join(repoRoot, "scripts", "validate_data.js");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "tourpass-validate-"));

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2), "utf8");
}

try {
  const rootPois = [
    {
      id: "hotel_root",
      name: "Root Hotel",
      type: "hotel",
      lat: 28.2,
      lng: 112.9,
      tags: ["住宿"],
      open_time: "00:00",
      close_time: "23:59",
      visit_duration_minutes: 30,
      popularity: 5,
      price_level: 2,
      description: "hotel",
      area: "root",
    },
    {
      id: "attraction_root",
      name: "Root Attraction",
      type: "attraction",
      lat: 28.21,
      lng: 112.91,
      tags: ["景点"],
      open_time: "08:00",
      close_time: "20:00",
      visit_duration_minutes: 60,
      popularity: 5,
      price_level: 2,
      description: "attraction",
      area: "root",
    },
    {
      id: "restaurant_root",
      name: "Root Restaurant",
      type: "restaurant",
      lat: 28.22,
      lng: 112.92,
      tags: ["餐饮"],
      open_time: "08:00",
      close_time: "22:00",
      visit_duration_minutes: 60,
      popularity: 5,
      price_level: 2,
      description: "restaurant",
      area: "root",
    },
    {
      id: "night_root",
      name: "Root Night",
      type: "nightlife",
      lat: 28.23,
      lng: 112.93,
      tags: ["夜游"],
      open_time: "18:00",
      close_time: "23:59",
      visit_duration_minutes: 60,
      popularity: 5,
      price_level: 2,
      description: "night",
      area: "root",
    },
  ];
  const rootEdges = rootPois.flatMap((from) =>
    rootPois
      .filter((to) => to.id !== from.id)
      .map((to) => ({
        from: from.id,
        to: to.id,
        distance_meters: 100,
        walk_minutes: 10,
        transit_minutes: 8,
        taxi_minutes: 5,
      }))
  );

  writeJson(path.join(tmp, "pois.json"), rootPois);
  writeJson(path.join(tmp, "edges.json"), rootEdges);
  writeJson(path.join(tmp, "broken", "pois.json"), [{ id: "bad" }]);
  writeJson(path.join(tmp, "broken", "edges.json"), []);

  const result = spawnSync(process.execPath, [scriptPath, "--all-cities", "--data-dir", tmp], {
    cwd: repoRoot,
    encoding: "utf8",
  });

  assert.notStrictEqual(result.status, 0, "all-cities validation should fail on an invalid city dataset");
  assert.match(result.stderr + result.stdout, /broken[\\/]+pois\.json/);
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
