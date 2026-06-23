const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const files = [
  path.join(repoRoot, "data", "changsha", "pois.json"),
  path.join(repoRoot, "data", "pois.json"),
];

const blockedNameTerms = ["研究院", "研究所", "婚庆"];
const allowedExactNames = new Set([]);

for (const file of files) {
  const pois = JSON.parse(fs.readFileSync(file, "utf8"));
  const badAttractions = pois.filter((poi) => {
    if (!["attraction", "nightlife"].includes(poi.type)) return false;
    if (allowedExactNames.has(poi.name)) return false;
    return blockedNameTerms.some((term) => String(poi.name || "").includes(term));
  });

  if (badAttractions.length > 0) {
    throw new Error(
      `${path.relative(repoRoot, file)} contains low-value attraction POIs: ` +
      badAttractions.map((poi) => poi.name).join(", ")
    );
  }
}

console.log("Changsha POI quality gate passed.");
