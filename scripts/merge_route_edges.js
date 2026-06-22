const fs = require("fs");
const path = require("path");

function usage() {
  console.log(`Usage: node scripts/merge_route_edges.js --base-edges <path> --patch-edges <path> --out <path> [options]

Merge refreshed AMap route edges into an existing edges.json copy.

Options:
  --base-edges <path>   Existing edges JSON array (required)
  --patch-edges <path>  Refreshed/patch edges JSON array (required)
  --out <path>          Output merged edges JSON path (required)
  --manifest <path>     Output manifest path (default: <out>.manifest.json)
  --dry-run             Write only manifest, not merged edges
  --help, -h            Show this help message`);
}

function parseArgs(argv) {
  const args = {
    baseEdges: "",
    patchEdges: "",
    out: "",
    manifest: "",
    dryRun: false,
    help: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--help" || key === "-h") args.help = true;
    if (key === "--base-edges") args.baseEdges = value;
    if (key === "--patch-edges") args.patchEdges = value;
    if (key === "--out") args.out = value;
    if (key === "--manifest") args.manifest = value;
    if (key === "--dry-run") args.dryRun = true;
    if (key.startsWith("--") && !["--help", "-h", "--dry-run"].includes(key)) i += 1;
  }
  if (args.help) return args;
  if (!args.baseEdges) throw new Error("missing --base-edges");
  if (!args.patchEdges) throw new Error("missing --patch-edges");
  if (!args.out) throw new Error("missing --out");
  if (!args.manifest) args.manifest = `${args.out.replace(/\.json$/i, "")}.manifest.json`;
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

function edgeKey(edge) {
  const from = edge.from || edge.source || "";
  const to = edge.to || edge.target || "";
  if (!from || !to) return "";
  return [from, to].sort().join("<->");
}

function isAmap(edge) {
  return String(edge.provider || edge.source || "").toLowerCase() === "amap";
}

function mergeEdges(baseEdges, patchEdges) {
  const merged = baseEdges.map((edge) => ({ ...edge }));
  const indexByKey = new Map();
  merged.forEach((edge, index) => {
    const key = edgeKey(edge);
    if (key && !indexByKey.has(key)) indexByKey.set(key, index);
  });

  let insertedCount = 0;
  let replacedCount = 0;
  let unchangedCount = 0;
  let skippedCount = 0;

  for (const patch of patchEdges) {
    const key = edgeKey(patch);
    if (!key) {
      skippedCount += 1;
      continue;
    }
    const existingIndex = indexByKey.get(key);
    if (existingIndex === undefined) {
      indexByKey.set(key, merged.length);
      merged.push({ ...patch });
      insertedCount += 1;
      continue;
    }
    const existing = merged[existingIndex];
    if (isAmap(existing) && !isAmap(patch)) {
      unchangedCount += 1;
      continue;
    }
    merged[existingIndex] = { ...existing, ...patch };
    replacedCount += 1;
  }

  const sourceCounts = merged.reduce((acc, edge) => {
    const source = edge.source || "unknown";
    acc[source] = (acc[source] || 0) + 1;
    return acc;
  }, {});

  return {
    edges: merged,
    manifest: {
      generated_at: new Date().toISOString(),
      base_count: baseEdges.length,
      patch_count: patchEdges.length,
      edge_count: merged.length,
      inserted_count: insertedCount,
      replaced_count: replacedCount,
      unchanged_count: unchangedCount,
      skipped_count: skippedCount,
      source_counts: sourceCounts,
    },
  };
}

function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    usage();
    return;
  }
  const baseEdges = readJsonArray(args.baseEdges, "--base-edges");
  const patchEdges = readJsonArray(args.patchEdges, "--patch-edges");
  const { edges, manifest } = mergeEdges(baseEdges, patchEdges);
  writeJson(args.manifest, manifest);
  if (!args.dryRun) writeJson(args.out, edges);
  console.log(`Merged route edges: ${manifest.edge_count} edges, replaced=${manifest.replaced_count}, inserted=${manifest.inserted_count}`);
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
  edgeKey,
  isAmap,
  mergeEdges,
  parseArgs,
};
