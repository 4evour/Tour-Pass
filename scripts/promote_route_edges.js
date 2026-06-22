const fs = require("fs");
const path = require("path");
const { mergeEdges } = require("./merge_route_edges");

function usage() {
  console.log(`Usage: node scripts/promote_route_edges.js --data-dir <path> --routes-dir <path> --out-dir <path> [options]

Promote refreshed routes-v2 edges into a staging data directory.

Options:
  --data-dir <path>     Source production-like data directory (required)
  --routes-dir <path>   Directory containing amap-{city}-routes-v2 outputs (required)
  --out-dir <path>      Staging data directory to write (required)
  --cities <list>       Comma-separated city dirs; default: all dirs in data-dir
  --manifest <path>     Aggregate manifest path (default: <out-dir>/route_promotion_manifest.json)
  --dry-run             Write only aggregate manifest, not staged city files
  --help, -h            Show this help message`);
}

function parseArgs(argv) {
  const args = {
    dataDir: "",
    routesDir: "",
    outDir: "",
    cities: [],
    manifest: "",
    dryRun: false,
    help: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--help" || key === "-h") args.help = true;
    if (key === "--data-dir") args.dataDir = value;
    if (key === "--routes-dir") args.routesDir = value;
    if (key === "--out-dir") args.outDir = value;
    if (key === "--cities") args.cities = String(value || "").split(",").map((city) => city.trim()).filter(Boolean);
    if (key === "--manifest") args.manifest = value;
    if (key === "--dry-run") args.dryRun = true;
    if (key.startsWith("--") && !["--help", "-h", "--dry-run"].includes(key)) i += 1;
  }
  if (args.help) return args;
  if (!args.dataDir) throw new Error("missing --data-dir");
  if (!args.routesDir) throw new Error("missing --routes-dir");
  if (!args.outDir) throw new Error("missing --out-dir");
  if (!args.manifest) args.manifest = path.join(args.outDir, "route_promotion_manifest.json");
  return args;
}

function readJsonArray(filePath, label) {
  const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (!Array.isArray(value)) throw new Error(`${label} must be a JSON array`);
  return value;
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function listCities(dataDir) {
  return fs.readdirSync(dataDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .filter((entry) => fs.existsSync(path.join(dataDir, entry.name, "edges.json")))
    .map((entry) => entry.name)
    .sort();
}

function copyIfExists(srcDir, destDir, fileName) {
  const src = path.join(srcDir, fileName);
  if (!fs.existsSync(src)) return false;
  fs.mkdirSync(destDir, { recursive: true });
  fs.copyFileSync(src, path.join(destDir, fileName));
  return true;
}

function promoteCity({ city, dataDir, routesDir, outDir, dryRun }) {
  const cityDataDir = path.join(dataDir, city);
  const baseEdgesPath = path.join(cityDataDir, "edges.json");
  const patchEdgesPath = path.join(routesDir, `amap-${city}-routes-v2`, "edges.json");
  if (!fs.existsSync(baseEdgesPath)) throw new Error(`missing base edges for ${city}: ${baseEdgesPath}`);
  if (!fs.existsSync(patchEdgesPath)) throw new Error(`missing routes-v2 edges for ${city}: ${patchEdgesPath}`);

  const baseEdges = readJsonArray(baseEdgesPath, `${city} base edges`);
  const patchEdges = readJsonArray(patchEdgesPath, `${city} patch edges`);
  const { edges, manifest } = mergeEdges(baseEdges, patchEdges);
  const cityOutDir = path.join(outDir, city);
  const amapEdges = manifest.source_counts.amap || 0;

  if (!dryRun) {
    fs.mkdirSync(cityOutDir, { recursive: true });
    for (const fileName of ["pois.json", "guidebook.json", "city_guide.json", "xhs_routes.json"]) {
      copyIfExists(cityDataDir, cityOutDir, fileName);
    }
    writeJson(path.join(cityOutDir, "edges.json"), edges);
    writeJson(path.join(cityOutDir, "edges.merge_manifest.json"), manifest);
  }

  return {
    city,
    base_count: manifest.base_count,
    patch_count: manifest.patch_count,
    edge_count: manifest.edge_count,
    replaced_count: manifest.replaced_count,
    inserted_count: manifest.inserted_count,
    unchanged_count: manifest.unchanged_count,
    skipped_count: manifest.skipped_count,
    amap_edges: amapEdges,
    amap_ratio: manifest.edge_count > 0 ? amapEdges / manifest.edge_count : 0,
  };
}

function promoteRoutes(args) {
  const cities = args.cities.length > 0 ? args.cities : listCities(args.dataDir);
  const cityResults = cities.map((city) => promoteCity({
    city,
    dataDir: args.dataDir,
    routesDir: args.routesDir,
    outDir: args.outDir,
    dryRun: args.dryRun,
  }));
  const manifest = {
    generated_at: new Date().toISOString(),
    dry_run: args.dryRun,
    data_dir: args.dataDir,
    routes_dir: args.routesDir,
    out_dir: args.outDir,
    city_count: cityResults.length,
    total_edges: cityResults.reduce((sum, item) => sum + item.edge_count, 0),
    total_patch_edges: cityResults.reduce((sum, item) => sum + item.patch_count, 0),
    total_replaced: cityResults.reduce((sum, item) => sum + item.replaced_count, 0),
    total_inserted: cityResults.reduce((sum, item) => sum + item.inserted_count, 0),
    total_amap_edges: cityResults.reduce((sum, item) => sum + item.amap_edges, 0),
    cities: cityResults,
  };
  writeJson(args.manifest, manifest);
  return manifest;
}

function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    usage();
    return;
  }
  const manifest = promoteRoutes(args);
  console.log(`Route promotion ${args.dryRun ? "dry-run " : ""}prepared: ${manifest.city_count} cities, ${manifest.total_edges} edges`);
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}

module.exports = {
  listCities,
  parseArgs,
  promoteCity,
  promoteRoutes,
};
