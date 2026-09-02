"use strict";

const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const args = { dataDir: "data", fixtures: "tests/fixtures/grounded-planner/core_places.json", out: "" };
  for (let index = 2; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (key === "--data-dir") args.dataDir = value;
    if (key === "--fixtures") args.fixtures = value;
    if (key === "--out") args.out = value;
    if (key.startsWith("--")) index += 1;
  }
  return args;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function normalizeName(value) {
  let text = String(value || "").toLowerCase().replace(/[\s·•（）()\-—_，,。.]/g, "");
  text = text.replace(/博物院/g, "博物馆").replace(/park/g, "公园");
  for (const suffix of ["风景名胜区", "风景区", "景区", "旅游区", "公园", "博物馆", "文创园", "文创街区"]) {
    if (text.endsWith(suffix) && text.length > suffix.length + 1) {
      text = text.slice(0, -suffix.length);
      break;
    }
  }
  return text;
}

function cityAudit(dataDir, city, coreEntries) {
  const pois = readJson(path.join(dataDir, city, "pois.json"));
  const edges = readJson(path.join(dataDir, city, "edges.json"));
  const attractions = pois.filter((item) => item.type === "attraction" || item.type === "nightlife");
  const names = pois.map((item) => normalizeName(item.name));
  const core = coreEntries.map((entry) => {
    const accepted = [entry.canonical_name, ...(entry.aliases || [])].map(normalizeName);
    const matched = pois.find((item) => accepted.some((name) => name && normalizeName(item.name) === name));
    return { canonical_name: entry.canonical_name, required_local: Boolean(entry.required_local), matched_name: matched ? matched.name : "", present: Boolean(matched) };
  });
  const xhsPath = path.join(dataDir, city, "xhs_routes.json");
  const routes = fs.existsSync(xhsPath) ? readJson(xhsPath) : [];
  const xhsNames = [...new Set(routes.flatMap((route) => (route.itinerary || []).flatMap((day) => (day.stops || []).map((stop) => String(stop.name || "").trim()).filter(Boolean))))];
  const xhsMatched = xhsNames.filter((name) => names.some((local) => local && (local.includes(normalizeName(name)) || normalizeName(name).includes(local))));
  const statusCounts = {};
  for (const edge of edges) statusCounts[edge.amap_status || "missing"] = (statusCounts[edge.amap_status || "missing"] || 0) + 1;
  return {
    city,
    poi_count: pois.length,
    attraction_count: attractions.length,
    default_attraction_hours: attractions.filter((item) => item.open_time === "09:00" && item.close_time === "21:30").length,
    edge_count: edges.length,
    edge_status: statusCounts,
    directed_pair_coverage: pois.length > 1 ? edges.length / (pois.length * (pois.length - 1)) : 0,
    core_local_recall: core.length ? core.filter((item) => item.present).length / core.length : 0,
    required_local_recall: core.filter((item) => item.required_local).every((item) => item.present),
    core,
    xhs_route_count: routes.length,
    xhs_unique_names: xhsNames.length,
    xhs_local_matches: xhsMatched.length,
  };
}

function main() {
  const args = parseArgs(process.argv);
  const fixtures = readJson(args.fixtures);
  const cities = Object.entries(fixtures.cities).map(([city, entries]) => cityAudit(args.dataDir, city, entries));
  const allCityDirs = fs.readdirSync(args.dataDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && fs.existsSync(path.join(args.dataDir, entry.name, "pois.json")))
    .map((entry) => entry.name);
  const totals = allCityDirs.reduce((result, city) => {
    const pois = readJson(path.join(args.dataDir, city, "pois.json"));
    const edges = readJson(path.join(args.dataDir, city, "edges.json"));
    result.poi_count += pois.length;
    result.attraction_count += pois.filter((item) => item.type === "attraction" || item.type === "nightlife").length;
    result.edge_count += edges.length;
    result.partial_edges += edges.filter((edge) => edge.amap_status === "partial").length;
    result.ok_edges += edges.filter((edge) => edge.amap_status === "ok").length;
    return result;
  }, { city_count: allCityDirs.length, poi_count: 0, attraction_count: 0, edge_count: 0, partial_edges: 0, ok_edges: 0 });
  const report = { version: fixtures.version, generated_at: new Date().toISOString(), totals, cities };
  const output = JSON.stringify(report, null, 2) + "\n";
  if (args.out) {
    fs.mkdirSync(path.dirname(args.out), { recursive: true });
    fs.writeFileSync(args.out, output, "utf8");
  }
  process.stdout.write(output);
}

main();
