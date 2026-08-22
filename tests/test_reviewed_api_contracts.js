const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const cmake = fs.readFileSync(path.join(root, "CMakeLists.txt"), "utf8");
const api = fs.readFileSync(path.join(root, "src", "api.cpp"), "utf8");
const app = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");

if (!cmake.includes("$<$<CXX_COMPILER_ID:MSVC>:/utf-8>")) {
  throw new Error("Expected MSVC builds to compile UTF-8 source files with /utf-8.");
}

const getCityStart = api.indexOf("CityBundle* getCity(");
const getCityEnd = api.indexOf("CityBundle* findCityExact", getCityStart);
const getCityBlock = api.slice(getCityStart, getCityEnd);
if (getCityStart < 0 || getCityEnd < 0 || getCityBlock.includes("defaultCity") || getCityBlock.includes("cities.begin()")) {
  throw new Error("Expected getCity to reject unknown cities instead of falling back to another city.");
}

const cityGuideStart = api.indexOf('server.Get("/api/city-guide"');
const cityGuideEnd = api.indexOf("// ── Agent API: List available cities", cityGuideStart);
const cityGuideBlock = api.slice(cityGuideStart, cityGuideEnd);
if (!cityGuideBlock.includes("context.findCityExact(cityName)")) {
  throw new Error("Expected city guide requests to validate the city before constructing a file path.");
}

function assertUnknownCityResponse(routeStart, routeEnd, label) {
  const start = api.indexOf(routeStart);
  const end = api.indexOf(routeEnd, start);
  const block = api.slice(start, end);
  if (start < 0 || end < 0 || !block.includes("CITY_NOT_FOUND") || !block.includes("404")) {
    throw new Error(`Expected ${label} to return HTTP 404 with CITY_NOT_FOUND for an unknown city.`);
  }
}

assertUnknownCityResponse(
  'server.Post("/trip/alternatives"',
  'server.Get("/poi/search"',
  "/trip/alternatives",
);
assertUnknownCityResponse(
  'server.Post("/itinerary/explain"',
  'server.Post("/trip/chat"',
  "/itinerary/explain",
);

const browseStart = api.indexOf('server.Get("/poi/browse"');
const browseEnd = api.indexOf("// GET /poi/areas", browseStart);
const browseBlock = api.slice(browseStart, browseEnd);
for (const field of ["open_minutes", "close_minutes", "visit_duration"]) {
  if (!browseBlock.includes(`{"${field}"`)) {
    throw new Error(`Expected /poi/browse to include ${field}.`);
  }
}

if (!app.includes("health.total_poi_count ?? health.poi_count ?? 0")) {
  throw new Error("Expected the service status to read the multi-city total_poi_count field.");
}

console.log("Reviewed build and API contracts are present.");
