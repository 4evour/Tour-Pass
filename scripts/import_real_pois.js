const fs = require("fs");
const path = require("path");

const VALID_TYPES = new Set(["attraction", "restaurant", "hotel", "transit", "nightlife"]);

function parseArgs(argv) {
  const args = {
    input: "",
    outDir: "output/real-import",
    neighbors: 4,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--input") args.input = value;
    if (key === "--out-dir") args.outDir = value;
    if (key === "--neighbors") args.neighbors = Number(value);
    if (key.startsWith("--")) i += 1;
  }
  if (!args.input) {
    throw new Error("missing --input");
  }
  args.neighbors = Math.max(1, Math.min(12, Number.isFinite(args.neighbors) ? Math.floor(args.neighbors) : 4));
  return args;
}

function splitCsvLine(line) {
  const values = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    const next = line[i + 1];
    if (char === '"' && inQuotes && next === '"') {
      current += '"';
      i += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      values.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  values.push(current);
  return values.map((value) => value.trim());
}

function readCsv(filePath) {
  const text = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
  const lines = text.split(/\r?\n/).filter((line) => line.trim() !== "");
  if (lines.length < 2) {
    throw new Error("CSV input must contain a header and at least one row");
  }
  const headers = splitCsvLine(lines[0]).map((header) => header.trim());
  return lines.slice(1).map((line, index) => {
    const values = splitCsvLine(line);
    const row = {};
    headers.forEach((header, column) => {
      row[header] = values[column] ?? "";
    });
    row.__row = index + 2;
    return row;
  });
}

function readInput(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".json") {
    const data = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!Array.isArray(data)) {
      throw new Error("JSON input must be an array of POI objects");
    }
    return data.map((item, index) => ({ ...item, __row: index + 1 }));
  }
  if (ext === ".csv") {
    return readCsv(filePath);
  }
  throw new Error("input must be .csv or .json");
}

function slugify(value, fallback) {
  const ascii = String(value || "")
    .normalize("NFKD")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, "_")
    .replace(/_+/g, "_");
  return ascii || fallback;
}

function parseNumber(value, fallback, field, row) {
  if (value === undefined || value === null || value === "") return fallback;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`row ${row} has invalid number for ${field}`);
  }
  return parsed;
}

function normalizeType(value, row) {
  const type = String(value || "attraction").trim().toLowerCase();
  if (!VALID_TYPES.has(type)) {
    throw new Error(`row ${row} has invalid type ${value}`);
  }
  return type;
}

function defaultOpenTime(type) {
  if (type === "hotel") return "00:00";
  if (type === "nightlife") return "18:00";
  return "09:00";
}

function defaultCloseTime(type) {
  if (type === "hotel") return "23:59";
  if (type === "nightlife") return "23:00";
  return "21:30";
}

function defaultDuration(type) {
  if (type === "hotel") return 30;
  if (type === "restaurant") return 60;
  if (type === "nightlife") return 90;
  return 90;
}

function normalizeTags(value, type) {
  const tags = String(value || "")
    .split(/[|;，、]/)
    .map((tag) => tag.trim())
    .filter(Boolean);
  if (tags.length > 0) {
    return Array.from(new Set(tags));
  }
  if (type === "hotel") return ["酒店", "交通便利"];
  if (type === "restaurant") return ["美食"];
  if (type === "nightlife") return ["夜景"];
  return ["城市游览"];
}

function normalizePoi(row, index, usedIds) {
  const type = normalizeType(row.type, row.__row);
  const name = String(row.name || "").trim();
  if (!name) {
    throw new Error(`row ${row.__row} missing name`);
  }
  const idBase = slugify(row.id || name, `poi_${index}`);
  let id = idBase;
  let suffix = 2;
  while (usedIds.has(id)) {
    id = `${idBase}_${suffix}`;
    suffix += 1;
  }
  usedIds.add(id);

  const lat = parseNumber(row.lat, NaN, "lat", row.__row);
  const lng = parseNumber(row.lng, NaN, "lng", row.__row);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    throw new Error(`row ${row.__row} missing lat/lng`);
  }

  return {
    id,
    name,
    type,
    lat: Number(lat.toFixed(6)),
    lng: Number(lng.toFixed(6)),
    area: String(row.area || "未分区").trim(),
    open_time: String(row.open_time || defaultOpenTime(type)).trim(),
    close_time: String(row.close_time || defaultCloseTime(type)).trim(),
    visit_duration_minutes: parseNumber(row.visit_duration_minutes, defaultDuration(type), "visit_duration_minutes", row.__row),
    tags: normalizeTags(row.tags, type),
    popularity: parseNumber(row.popularity, 6.5, "popularity", row.__row),
    price_level: parseNumber(row.price_level, type === "hotel" ? 3 : 2, "price_level", row.__row),
    description: String(row.description || `${name}，由真实 POI 导入脚本标准化生成。`).trim(),
  };
}

function distanceMeters(a, b) {
  const dx = (a.lat - b.lat) * 111000;
  const dy = (a.lng - b.lng) * 91000;
  return Math.round(Math.sqrt(dx * dx + dy * dy));
}

function timeForDistance(distance, multiplier) {
  return Math.max(5, Math.round((distance / 1000) * multiplier));
}

function generateNearestNeighborEdges(pois, neighbors) {
  const edgeMap = new Map();
  for (const poi of pois) {
    const nearest = pois
      .filter((other) => other.id !== poi.id)
      .map((other) => ({ other, distance: distanceMeters(poi, other) }))
      .sort((left, right) => left.distance - right.distance)
      .slice(0, neighbors);
    for (const item of nearest) {
      const key = [poi.id, item.other.id].sort().join("<->");
      if (edgeMap.has(key)) continue;
      edgeMap.set(key, {
        from: poi.id,
        to: item.other.id,
        distance_meters: Math.max(1, item.distance),
        walk_minutes: timeForDistance(item.distance, 12),
        transit_minutes: timeForDistance(item.distance, 4.5),
        taxi_minutes: timeForDistance(item.distance, 2.8),
      });
    }
  }
  return [...edgeMap.values()];
}

function main() {
  const args = parseArgs(process.argv);
  const rows = readInput(args.input);
  const usedIds = new Set();
  const pois = rows.map((row, index) => normalizePoi(row, index, usedIds));
  const edges = generateNearestNeighborEdges(pois, args.neighbors);

  fs.mkdirSync(args.outDir, { recursive: true });
  fs.writeFileSync(path.join(args.outDir, "pois.json"), `${JSON.stringify(pois, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(args.outDir, "edges.json"), `${JSON.stringify(edges, null, 2)}\n`, "utf8");
  console.log(`Real POI import written: ${pois.length} POIs, ${edges.length} nearest-neighbor edges -> ${args.outDir}`);
}

try {
  main();
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
