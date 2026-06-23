const fs = require("fs");
const path = require("path");
const vm = require("vm");

const appSource = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const start = appSource.indexOf("function xhsDurationToMinutes");
const end = appSource.indexOf("async function xhsParseLink");

if (start < 0 || end < 0 || end <= start) {
  throw new Error("Expected XHS save transform helpers before xhsParseLink.");
}

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(appSource.slice(start, end), sandbox);

if (typeof sandbox.xhsToSavedTripPayload !== "function") {
  throw new Error("xhsToSavedTripPayload should be defined.");
}

const payload = sandbox.xhsToSavedTripPayload({
  id: "note123",
  city: "成都",
  summary: "成都两日路线",
  source_title: "成都攻略",
  data: [
    {
      day: 1,
      places: [
        { name: "宽窄巷子", type: "文化", duration: "2小时", tips: "早上人少" },
        { name: "建设路", type: "美食", duration: "90分钟", description: "小吃街" },
      ],
    },
    {
      day: 2,
      places: [
        { name: "太古里", type: "购物", duration: "半天" },
        { name: "酒店", type: "住宿" },
      ],
    },
  ],
});

if (payload.title !== "成都·小红书解析 2日游") {
  throw new Error(`Unexpected title: ${payload.title}`);
}
if (payload.request.source !== "xhs" || payload.request.note_id !== "note123") {
  throw new Error("Expected request metadata to preserve XHS source and note id.");
}
if (payload.response.city !== "成都" || payload.response.days.length !== 2) {
  throw new Error("Expected response to preserve city and days.");
}

const [first, second] = payload.response.days[0].stops;
const third = payload.response.days[1].stops[0];
const fourth = payload.response.days[1].stops[1];

if (first.poi_type !== "attraction" || second.poi_type !== "restaurant") {
  throw new Error("Expected Chinese XHS types to map to editor POI types.");
}
if (third.visit_duration_minutes !== 240) {
  throw new Error(`Expected 半天 to map to 240 minutes, got ${third.visit_duration_minutes}.`);
}
if (fourth.poi_type !== "hotel" || fourth.visit_duration_minutes !== 60) {
  throw new Error("Expected lodging type and default duration mapping.");
}
if (!first.recommendation.includes("早上人少")) {
  throw new Error("Expected tips to be preserved in recommendation.");
}

console.log("XHS save transform maps parsed notes into saved trip payloads.");
