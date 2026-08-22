const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const apiHeader = fs.readFileSync(path.join(root, "include", "tourpass", "api.h"), "utf8");
const api = fs.readFileSync(path.join(root, "src", "api.cpp"), "utf8");
const loader = fs.readFileSync(path.join(root, "src", "data_loader.cpp"), "utf8");

if (!apiHeader.includes("mutable std::shared_mutex dataMutex")) {
  throw new Error("Expected each city bundle to protect POI reads and writes with a shared mutex.");
}

const updateStart = api.indexOf('server.Put(R"(/admin/pois/([^/]+))"');
const updateEnd = api.indexOf("// PUT /admin/pois/:id/image", updateStart);
const updateBlock = api.slice(updateStart, updateEnd);
for (const contract of [
  "std::unique_lock<std::shared_mutex>",
  "Poi updated = *poi",
  "savePois(city->poisPath, updatedPois)",
  "city->search.rebuild()",
  "context.cache.clear()",
]) {
  if (!updateBlock.includes(contract)) {
    throw new Error(`Expected transactional POI update contract: ${contract}`);
  }
}

if (!loader.includes("MoveFileExW") || !loader.includes("MOVEFILE_REPLACE_EXISTING")) {
  throw new Error("Expected Windows POI saves to atomically replace the target file.");
}

console.log("POI admin persistence and synchronization contracts are present.");
