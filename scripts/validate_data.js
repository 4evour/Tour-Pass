const fs = require("fs");

const errors = [];
const warnings = [];

function parseArgs(argv) {
  const args = {
    poisPath: "data/pois.json",
    edgesPath: "data/edges.json",
    minPois: 1,
    requireEdgeSource: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--pois") args.poisPath = value;
    if (key === "--edges") args.edgesPath = value;
    if (key === "--min-pois") args.minPois = Number(value);
    if (key === "--require-edge-source") args.requireEdgeSource = true;
    if (key.startsWith("--") && key !== "--require-edge-source") i += 1;
  }
  if (!Number.isFinite(args.minPois) || args.minPois < 1) args.minPois = 1;
  return args;
}

function addError(message) {
  errors.push(message);
}

function addWarning(message) {
  warnings.push(message);
}

function readJson(path) {
  try {
    return JSON.parse(fs.readFileSync(path, "utf8"));
  } catch (error) {
    console.error(`Data validation failed: cannot read ${path}: ${error.message}`);
    process.exit(1);
  }
}

function requireString(item, field, context) {
  if (typeof item[field] !== "string" || item[field].trim() === "") {
    addError(`${context} missing string field ${field}`);
    return false;
  }
  return true;
}

function requireNumber(item, field, context) {
  if (typeof item[field] !== "number" || !Number.isFinite(item[field])) {
    addError(`${context} missing number field ${field}`);
    return false;
  }
  return true;
}

function requireStringArray(item, field, context) {
  if (!Array.isArray(item[field]) || item[field].some((value) => typeof value !== "string" || value.trim() === "")) {
    addError(`${context} missing string array field ${field}`);
    return false;
  }
  return true;
}

function validateTime(value, context) {
  if (!/^\d{2}:\d{2}$/.test(value)) {
    addError(`${context} has invalid time ${value}`);
    return null;
  }
  const [hour, minute] = value.split(":").map(Number);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    addError(`${context} has out-of-range time ${value}`);
    return null;
  }
  return hour * 60 + minute;
}

function hasDuplicateValues(values) {
  return new Set(values).size !== values.length;
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function printSummary(pois, edges, typeCounts, edgeSourceCounts = new Map(), isolatedIds = []) {
  for (const warning of warnings) {
    console.warn(`Data validation warning: ${warning}`);
  }
  if (errors.length > 0) {
    console.error(`Data validation failed with ${errors.length} error(s):`);
    for (const error of errors) {
      console.error(`- ${error}`);
    }
    process.exit(1);
  }

  const typeSummary = [...typeCounts.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([type, count]) => `${type}=${count}`)
    .join(", ");
  const warningSuffix = warnings.length > 0 ? `, ${warnings.length} warning(s)` : "";
  const sourceSummary = [...edgeSourceCounts.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([source, count]) => `${source}=${count}`)
    .join(", ");
  const sourceSuffix = sourceSummary ? `, edge_sources: ${sourceSummary}` : "";
  const isolatedSuffix = isolatedIds.length > 0 ? `, isolated=${isolatedIds.length}` : "";
  console.log(`Data validation passed: ${pois.length} POIs, ${edges.length} edges, connected graph, ${typeSummary}${sourceSuffix}${isolatedSuffix}${warningSuffix}.`);
}

const args = parseArgs(process.argv);
const pois = readJson(args.poisPath);
const edges = readJson(args.edgesPath);
if (!Array.isArray(pois)) {
  addError(`${args.poisPath} must be an array`);
}
if (!Array.isArray(edges)) {
  addError(`${args.edgesPath} must be an array`);
}
if (errors.length > 0) {
  printSummary(Array.isArray(pois) ? pois : [], Array.isArray(edges) ? edges : [], new Map());
}
if (pois.length < args.minPois) {
  addError(`${args.poisPath} must contain at least ${args.minPois} POIs`);
}

const ids = new Set();
const validTypes = new Set(["attraction", "restaurant", "hotel", "transit", "nightlife"]);
const requiredTypes = ["attraction", "restaurant", "hotel", "nightlife"];
const typeCounts = new Map();
pois.forEach((poi, index) => {
  if (!isObject(poi)) {
    addError(`poi at index ${index} must be an object`);
    return;
  }
  const context = typeof poi.id === "string" && poi.id.trim() !== "" ? `poi ${poi.id}` : "poi";
  const hasId = requireString(poi, "id", "poi");
  requireString(poi, "name", context);
  const hasType = requireString(poi, "type", context);
  const hasLat = requireNumber(poi, "lat", context);
  const hasLng = requireNumber(poi, "lng", context);
  const hasTags = requireStringArray(poi, "tags", context);
  const hasOpenTime = requireString(poi, "open_time", context);
  const hasCloseTime = requireString(poi, "close_time", context);
  const hasVisitDuration = requireNumber(poi, "visit_duration_minutes", context);
  const hasPopularity = requireNumber(poi, "popularity", context);
  const hasPriceLevel = requireNumber(poi, "price_level", context);
  requireString(poi, "description", context);
  requireString(poi, "area", context);

  if (hasType) {
    if (!validTypes.has(poi.type)) {
      addError(`${context} has invalid type ${poi.type}`);
    } else {
      typeCounts.set(poi.type, (typeCounts.get(poi.type) || 0) + 1);
    }
  }
  if (hasId) {
    if (ids.has(poi.id)) {
      addError(`duplicate poi id ${poi.id}`);
    }
    ids.add(poi.id);
  }
  if (hasLat && (poi.lat < -90 || poi.lat > 90)) {
    addError(`${context} lat must be between -90 and 90`);
  }
  if (hasLng && (poi.lng < -180 || poi.lng > 180)) {
    addError(`${context} lng must be between -180 and 180`);
  }
  if (hasTags) {
    const normalizedTags = poi.tags.map((tag) => tag.trim());
    if (hasDuplicateValues(normalizedTags)) {
      addWarning(`${context} has duplicate tags`);
    }
    if (normalizedTags.some((tag) => tag.length > 16)) {
      addWarning(`${context} has unusually long tags`);
    }
  }
  const openMinutes = hasOpenTime ? validateTime(poi.open_time, context) : null;
  const closeMinutes = hasCloseTime ? validateTime(poi.close_time, context) : null;
  if (openMinutes !== null && closeMinutes !== null && closeMinutes <= openMinutes) {
    addError(`${context} close_time must be later than open_time for same-day demo data`);
  }
  if (hasVisitDuration) {
    if (poi.visit_duration_minutes <= 0) {
      addError(`${context} visit duration must be positive`);
    }
    if (openMinutes !== null && closeMinutes !== null && poi.visit_duration_minutes > closeMinutes - openMinutes) {
      addWarning(`${context} visit duration exceeds available opening window`);
    }
  }
  if (hasPopularity && (poi.popularity < 0 || poi.popularity > 10)) {
    addError(`${context} popularity must be 0..10`);
  }
  if (hasPriceLevel && (poi.price_level < 1 || poi.price_level > 5)) {
    addError(`${context} price_level must be 1..5`);
  }
});
for (const type of requiredTypes) {
  if ((typeCounts.get(type) || 0) < 1) {
    addError(`${args.poisPath} must contain at least one ${type} POI`);
  }
}

const adjacency = new Map();
for (const id of ids) adjacency.set(id, []);
const edgeKeys = new Set();
const edgeSourceCounts = new Map();
edges.forEach((edge, index) => {
  if (!isObject(edge)) {
    addError(`edge at index ${index} must be an object`);
    return;
  }
  const context = `edge ${edge.from || "?"}->${edge.to || "?"}`;
  const hasFrom = requireString(edge, "from", "edge");
  const hasTo = requireString(edge, "to", context);
  const hasDistance = requireNumber(edge, "distance_meters", context);
  if (hasFrom && !ids.has(edge.from)) {
    addError(`edge references unknown from poi ${edge.from}`);
  }
  if (hasTo && !ids.has(edge.to)) {
    addError(`edge references unknown to poi ${edge.to}`);
  }
  if (hasFrom && hasTo && edge.from === edge.to) {
    addError(`${context} must not be a self-loop`);
  }
  if (hasDistance && edge.distance_meters <= 0) {
    addError(`${context} distance_meters must be positive`);
  }
  const travelFields = ["walk_minutes", "transit_minutes", "taxi_minutes"];
  const usableTravelFields = travelFields.filter((field) => typeof edge[field] === "number" && Number.isFinite(edge[field]) && edge[field] >= 0);
  for (const field of travelFields) {
    if (field in edge && (typeof edge[field] !== "number" || !Number.isFinite(edge[field]) || edge[field] < 0)) {
      addError(`${context} ${field} must be a non-negative finite number when present`);
    }
  }
  if (usableTravelFields.length === 0) {
    addError(`${context} has no usable travel minutes`);
  }
  if ("source" in edge) {
    if (typeof edge.source !== "string" || edge.source.trim() === "") {
      addError(`${context} source must be a non-empty string when present`);
    } else {
      edgeSourceCounts.set(edge.source, (edgeSourceCounts.get(edge.source) || 0) + 1);
    }
  } else if (args.requireEdgeSource) {
    addError(`${context} missing source field`);
  }
  if (hasFrom && hasTo && ids.has(edge.from) && ids.has(edge.to)) {
    const edgeKey = [edge.from, edge.to].sort().join("<->");
    if (edgeKeys.has(edgeKey)) {
      addWarning(`${context} duplicates an existing undirected edge`);
    }
    edgeKeys.add(edgeKey);
    adjacency.get(edge.from).push(edge.to);
    adjacency.get(edge.to).push(edge.from);
  }
});

const isolatedIds = [...adjacency.entries()]
  .filter(([, neighbors]) => neighbors.length === 0)
  .map(([id]) => id);
for (const id of isolatedIds) {
  addWarning(`poi ${id} is isolated`);
}

if (errors.length === 0 && pois.length > 0) {
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
    addError(`poi graph is disconnected; unreachable ids: ${missing.join(", ")}`);
  }
}

printSummary(pois, edges, typeCounts, edgeSourceCounts, isolatedIds);
