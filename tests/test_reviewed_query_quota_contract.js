const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const api = fs.readFileSync(path.join(root, "src", "api.cpp"), "utf8");
const store = fs.readFileSync(path.join(root, "include", "tourpass", "data_store.h"), "utf8");
const sqlite = fs.readFileSync(path.join(root, "src", "sqlite_store.cpp"), "utf8");
const postgres = fs.readFileSync(path.join(root, "src", "pg_store.cpp"), "utf8");

if (!store.includes("tryConsumeQuery") || !store.includes("refundQuery")) {
  throw new Error("Expected query usage to support atomic reservation and refund.");
}
if (!api.includes("context.store->tryConsumeQuery(authUserId, limit + bonus)")) {
  throw new Error("Expected user quota to be reserved before request handling.");
}
if (!api.includes("refundReservedQuery(context, meta.userId)")) {
  throw new Error("Expected failed query requests to refund their reservation.");
}
if (!api.includes('res.headers.erase("X-Query-Remaining")')) {
  throw new Error("Expected refunded responses to replace the reserved remaining-quota header.");
}
if (api.includes("incrementQueryCount(meta.userId)")) {
  throw new Error("Expected successful requests to keep the reservation instead of incrementing again.");
}
for (const [name, implementation] of Object.entries({ sqlite, postgres })) {
  if (!implementation.includes("WHERE query_usage.query_count <")) {
    throw new Error(`Expected ${name} quota reservation to enforce the limit in its atomic write.`);
  }
}

console.log("Atomic query quota reservation and refund contracts are present.");
