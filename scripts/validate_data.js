const fs = require("fs");

function fail(message) {
  console.error(`Data validation failed: ${message}`);
  process.exit(1);
}

function readJson(path) {
  try {
    return JSON.parse(fs.readFileSync(path, "utf8"));
  } catch (error) {
    fail(`cannot read ${path}: ${error.message}`);
  }
}

function requireString(item, field, context) {
  if (typeof item[field] !== "string" || item[field].trim() === "") {
    fail(`${context} missing string field ${field}`);
  }
}

function requireNumber(item, field, context) {
  if (typeof item[field] !== "number" || !Number.isFinite(item[field])) {
    fail(`${context} missing number field ${field}`);
  }
}

function requireStringArray(item, field, context) {
  if (!Array.isArray(item[field]) || item[field].some((value) => typeof value !== "string" || value.trim() === "")) {
    fail(`${context} missing string array field ${field}`);
  }
}

function validateTime(value, context) {
  if (!/^\d{2}:\d{2}$/.test(value)) {
    fail(`${context} has invalid time ${value}`);
  }
  const [hour, minute] = value.split(":").map(Number);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    fail(`${context} has out-of-range time ${value}`);
  }
}

const pois = readJson("data/pois.json");
const edges = readJson("data/edges.json");
if (!Array.isArray(pois)) fail("data/pois.json must be an array");
if (!Array.isArray(edges)) fail("data/edges.json must be an array");

const ids = new Set();
const validTypes = new Set(["attraction", "restaurant", "hotel", "transit", "nightlife"]);
for (const poi of pois) {
  requireString(poi, "id", "poi");
  requireString(poi, "name", `poi ${poi.id}`);
  requireString(poi, "type", `poi ${poi.id}`);
  requireNumber(poi, "lat", `poi ${poi.id}`);
  requireNumber(poi, "lng", `poi ${poi.id}`);
  requireStringArray(poi, "tags", `poi ${poi.id}`);
  requireString(poi, "open_time", `poi ${poi.id}`);
  requireString(poi, "close_time", `poi ${poi.id}`);
  requireNumber(poi, "visit_duration_minutes", `poi ${poi.id}`);
  requireNumber(poi, "popularity", `poi ${poi.id}`);
  requireNumber(poi, "price_level", `poi ${poi.id}`);
  requireString(poi, "description", `poi ${poi.id}`);
  requireString(poi, "area", `poi ${poi.id}`);
  if (!validTypes.has(poi.type)) fail(`poi ${poi.id} has invalid type ${poi.type}`);
  if (ids.has(poi.id)) fail(`duplicate poi id ${poi.id}`);
  ids.add(poi.id);
  validateTime(poi.open_time, `poi ${poi.id}`);
  validateTime(poi.close_time, `poi ${poi.id}`);
  if (poi.visit_duration_minutes <= 0) fail(`poi ${poi.id} visit duration must be positive`);
  if (poi.popularity < 0 || poi.popularity > 10) fail(`poi ${poi.id} popularity must be 0..10`);
  if (poi.price_level < 1 || poi.price_level > 5) fail(`poi ${poi.id} price_level must be 1..5`);
}

const adjacency = new Map();
for (const id of ids) adjacency.set(id, []);
for (const edge of edges) {
  requireString(edge, "from", "edge");
  requireString(edge, "to", `edge ${edge.from}`);
  requireNumber(edge, "distance_meters", `edge ${edge.from}->${edge.to}`);
  if (!ids.has(edge.from)) fail(`edge references unknown from poi ${edge.from}`);
  if (!ids.has(edge.to)) fail(`edge references unknown to poi ${edge.to}`);
  const hasTravel = ["walk_minutes", "transit_minutes", "taxi_minutes"].some((field) => typeof edge[field] === "number" && edge[field] >= 0);
  if (!hasTravel) fail(`edge ${edge.from}->${edge.to} has no usable travel minutes`);
  adjacency.get(edge.from).push(edge.to);
  adjacency.get(edge.to).push(edge.from);
}

if (pois.length > 0) {
  const visited = new Set();
  const queue = [pois[0].id];
  visited.add(pois[0].id);
  while (queue.length > 0) {
    const id = queue.shift();
    for (const next of adjacency.get(id)) {
      if (!visited.has(next)) {
        visited.add(next);
        queue.push(next);
      }
    }
  }
  if (visited.size !== pois.length) {
    const missing = pois.map((poi) => poi.id).filter((id) => !visited.has(id));
    fail(`poi graph is disconnected; unreachable ids: ${missing.join(", ")}`);
  }
}

console.log(`Data validation passed: ${pois.length} POIs, ${edges.length} edges, connected graph.`);
