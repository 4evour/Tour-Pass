const fs = require("fs");
const { spawn } = require("child_process");
const { performance } = require("perf_hooks");

function parseArgs(argv) {
  const args = {
    app: "bin/tourpass.exe",
    port: 8110,
    pois: "data/changsha/pois.json",
    edges: "data/changsha/edges.json",
    subset: 9,
    report: "docs/algorithm_quality_report.md",
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--app") args.app = value;
    if (key === "--port") args.port = Number(value);
    if (key === "--pois") args.pois = value;
    if (key === "--edges") args.edges = value;
    if (key === "--subset") args.subset = Number(value);
    if (key === "--report") args.report = value;
    if (key.startsWith("--")) i += 1;
  }
  args.subset = Math.max(4, Math.min(10, Number.isFinite(args.subset) ? Math.floor(args.subset) : 9));
  return args;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function edgeMinutes(edge) {
  if (typeof edge.transit_minutes === "number" && edge.transit_minutes >= 0) return edge.transit_minutes;
  if (typeof edge.taxi_minutes === "number" && edge.taxi_minutes >= 0) return edge.taxi_minutes;
  return edge.walk_minutes;
}

function buildDistances(pois, edges) {
  const index = new Map(pois.map((poi, i) => [poi.id, i]));
  const dist = Array.from({ length: pois.length }, () => Array(pois.length).fill(Number.POSITIVE_INFINITY));
  for (let i = 0; i < pois.length; i += 1) dist[i][i] = 0;
  for (const edge of edges) {
    if (!index.has(edge.from) || !index.has(edge.to)) continue;
    const from = index.get(edge.from);
    const to = index.get(edge.to);
    const minutes = edgeMinutes(edge);
    dist[from][to] = Math.min(dist[from][to], minutes);
    dist[to][from] = Math.min(dist[to][from], minutes);
  }
  for (let k = 0; k < pois.length; k += 1) {
    for (let i = 0; i < pois.length; i += 1) {
      for (let j = 0; j < pois.length; j += 1) {
        if (dist[i][k] + dist[k][j] < dist[i][j]) {
          dist[i][j] = dist[i][k] + dist[k][j];
        }
      }
    }
  }
  return { dist, index };
}

function pickSubset(pois, subsetSize, edges = []) {
  const hotel = pois.find((poi) => poi.type === "hotel") || pois[0];
  const { dist, index } = buildDistances(pois, edges);
  const hotelIndex = index.get(hotel.id);
  const reachable = (type, limit) => pois
    .filter((poi) => poi.id !== hotel.id && poi.type === type && Number.isFinite(dist[hotelIndex]?.[index.get(poi.id)]))
    .sort((left, right) => dist[hotelIndex][index.get(left.id)] - dist[hotelIndex][index.get(right.id)])
    .slice(0, limit);
  const restaurants = reachable("restaurant", 2);
  const nightlife = reachable("nightlife", 1);
  const attractions = reachable("attraction", Math.max(2, subsetSize - restaurants.length - nightlife.length - 1));
  const selected = [hotel, ...attractions, ...restaurants, ...nightlife];
  return selected.filter((poi, index, arr) => arr.findIndex((item) => item.id === poi.id) === index).slice(0, subsetSize);
}

function exactBaseline(pois, edges, subsetSize) {
  const subset = pickSubset(pois, subsetSize, edges);
  const hotel = subset.find((poi) => poi.type === "hotel") || subset[0];
  const candidates = subset.filter((poi) => poi.id !== hotel.id && poi.type !== "hotel" && poi.type !== "transit");
  const { dist, index } = buildDistances(pois, edges);
  const hotelIndex = index.get(hotel.id);
  let best = { score: -Infinity, travel: 0, path: [] };
  const reachableCandidates = candidates.filter((poi) => {
    const poiIndex = index.get(poi.id);
    return Number.isFinite(dist[hotelIndex][poiIndex]);
  });
  const slots = Math.min(4, reachableCandidates.length);

  function visit(path, used, current, travel, score) {
    if (path.length === slots) {
      if (score > best.score || (score === best.score && travel < best.travel)) {
        best = { score, travel, path: [...path] };
      }
      return;
    }
    for (const poi of reachableCandidates) {
      if (used.has(poi.id)) continue;
      const next = index.get(poi.id);
      const minutes = dist[current][next];
      if (!Number.isFinite(minutes)) continue;
      const poiScore = poi.popularity * 10 - poi.price_level * 3 - minutes;
      used.add(poi.id);
      path.push(poi);
      visit(path, used, next, travel + minutes, score + poiScore);
      path.pop();
      used.delete(poi.id);
    }
  }

  visit([], new Set(), hotelIndex, 0, 0);
  return {
    subset,
    allPois: pois,
    hotel,
    stopCount: slots,
    score: Number.isFinite(best.score) ? Math.round(best.score * 10) / 10 : 0,
    travel: best.travel,
    feasible: best.path.length === slots,
    path: best.path.map((poi) => poi.name),
    pathIds: best.path.map((poi) => poi.id),
  };
}

function scorePoi(poi, minutes) {
  return poi.popularity * 10 - poi.price_level * 3 - minutes;
}

function greedyBaselineFromExact(baseline, edges) {
  const subset = baseline.subset;
  const graphPois = baseline.allPois || subset;
  const hotel = baseline.hotel;
  const candidates = subset.filter((poi) => poi.id !== hotel.id && poi.type !== "hotel" && poi.type !== "transit");
  const { dist, index } = buildDistances(graphPois, edges);
  let current = index.get(hotel.id);
  const used = new Set();
  const path = [];
  let travel = 0;
  let score = 0;
  const startedAt = performance.now();

  for (let slot = 0; slot < baseline.stopCount; slot += 1) {
    let best = null;
    for (const poi of candidates) {
      if (used.has(poi.id)) continue;
      const next = index.get(poi.id);
      const minutes = dist[current][next];
      if (!Number.isFinite(minutes)) continue;
      const candidateScore = scorePoi(poi, minutes);
      if (!best || candidateScore > best.score || (candidateScore === best.score && minutes < best.minutes)) {
        best = { poi, next, minutes, score: candidateScore };
      }
    }
    if (!best) break;
    used.add(best.poi.id);
    path.push(best.poi);
    travel += best.minutes;
    score += best.score;
    current = best.next;
  }

  return {
    elapsedMs: performance.now() - startedAt,
    score: Math.round(score * 10) / 10,
    travel,
    feasible: path.length === baseline.stopCount,
    path: path.map((poi) => poi.name),
    pathIds: path.map((poi) => poi.id),
  };
}

function comparableScore(stopNames, subset, edges, hotel, graphPois = subset) {
  const byName = new Map(subset.map((poi) => [poi.name, poi]));
  const { dist, index } = buildDistances(graphPois, edges);
  let current = index.get(hotel.id);
  let score = 0;
  let travel = 0;
  const pathIds = [];
  for (const name of stopNames) {
    const poi = byName.get(name);
    if (!poi || !index.has(poi.id)) continue;
    const next = index.get(poi.id);
    const minutes = dist[current][next];
    if (!Number.isFinite(minutes)) continue;
    score += scorePoi(poi, minutes);
    travel += minutes;
    current = next;
    pathIds.push(poi.id);
  }
  return {
    score: Math.round(score * 10) / 10,
    travel,
    pathIds,
  };
}

async function waitForHealth(baseUrl) {
  for (let i = 0; i < 50; i += 1) {
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) return await response.json();
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }
  throw new Error("service did not become healthy");
}

async function fetchBeamPlan(baseUrl, baseline) {
  const subsetIds = new Set(baseline.subset.map((poi) => poi.id));
  const avoid = baseline.allPois
    .filter((poi) => !subsetIds.has(poi.id))
    .flatMap((poi) => [poi.name, poi.id]);
  const body = {
    city: "长沙",
    days: 1,
    start_time: "09:30",
    end_time: "21:30",
    hotel_location: baseline.hotel.name,
    interests: ["历史文化", "美食", "夜景"],
    pace: "标准",
    must_visit: baseline.path.slice(0, 1),
    avoid,
    candidate_count: 1,
  };
  const startedAt = performance.now();
  const response = await fetch(`${baseUrl}/trip/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`beam plan failed with ${response.status}: ${(await response.text()).slice(0, 160)}`);
  }
  const json = await response.json();
  const day = json.days?.[0] || {};
  return {
    elapsedMs: performance.now() - startedAt,
    totalScore: json.total_score || 0,
    travel: day.total_travel_minutes || 0,
    feasible: day.time_window_feasible !== false,
    stops: (day.stops || []).map((stop) => stop.poi_name),
    stopIds: (day.stops || []).map((stop) => stop.poi_id).filter(Boolean),
    beamTrace: day.beam_trace || [],
  };
}

function overlapRatio(leftIds, rightIds) {
  if (!leftIds.length || !rightIds.length) return 0;
  const right = new Set(rightIds);
  const shared = leftIds.filter((id) => right.has(id)).length;
  return shared / Math.max(leftIds.length, rightIds.length);
}

function writeReport(filePath, args, health, baseline, greedy, beam, comparableBeam) {
  const exactPath = baseline.path.join(" -> ");
  const greedyPath = greedy.path.join(" -> ");
  const beamPath = beam.stops.join(" -> ");
  const travelGap = comparableBeam.travel - baseline.travel;
  const beamVsGreedyScore = comparableBeam.score - greedy.score;
  const beamGreedyOverlap = overlapRatio(comparableBeam.pathIds, greedy.pathIds);
  const lines = [
    "# Tour Pass 算法质量报告",
    "",
    "本报告用小规模 POI 子集做精确枚举基线，并用同一候选子集补充贪心 baseline，用于解释 Beam Search 的近似质量。它不是生产路线质量评测，也不包含真实用户反馈。",
    "",
    "## 运行口径",
    "",
    `- POI 数据：\`${args.pois}\``,
    `- Edge 数据：\`${args.edges}\``,
    `- 子集规模：${baseline.subset.length} POI，精确枚举 stop_count=${baseline.stopCount}`,
    `- Beam 参数：TOURPASS_BEAM_WIDTH=${process.env.TOURPASS_BEAM_WIDTH || "5"}，TOURPASS_BRANCH_FACTOR=${process.env.TOURPASS_BRANCH_FACTOR || "6"}`,
    `- 服务健康：poi=${health.poi_count}，edges=${health.edge_count}，distance_cache=${health.distance_cache?.mode || "unknown"}`,
    "",
    "## 小规模对比",
    "",
    "| 方法 | 分数/目标 | 通勤分钟 | 可行性 | 耗时 | 路线 |",
    "| --- | ---: | ---: | --- | ---: | --- |",
    `| 精确枚举基线 | ${baseline.score} | ${baseline.travel} | ${baseline.feasible ? "yes" : "no"} | - | ${exactPath} |`,
    `| 贪心 baseline | ${greedy.score} | ${greedy.travel} | ${greedy.feasible ? "yes" : "no"} | ${greedy.elapsedMs.toFixed(1)} ms | ${greedyPath} |`,
    `| Beam Search 服务输出 | ${comparableBeam.score.toFixed(1)} | ${comparableBeam.travel} | ${beam.feasible ? "yes" : "no"} | ${beam.elapsedMs.toFixed(1)} ms | ${beamPath} |`,
    "",
    "## 结论",
    "",
    `- Beam 请求耗时：${beam.elapsedMs.toFixed(1)} ms；表中 Beam 分数按 exact/greedy 的同一简化目标函数重算。`,
    `- 通勤差值：${travelGap >= 0 ? "+" : ""}${travelGap} 分钟。`,
    `- Beam 相比贪心分数差：${beamVsGreedyScore >= 0 ? "+" : ""}${beamVsGreedyScore.toFixed(1)}；路线重合度：${(beamGreedyOverlap * 100).toFixed(1)}%。`,
    "- 精确枚举只在 8-10 个候选点子集上可接受；真实 200+ POI 场景必须先做候选召回、时间窗过滤和近似搜索。",
    "- 面试表达应说 Beam Search 是工程近似策略，不声称全局最优。",
    "",
  ];
  fs.writeFileSync(filePath, `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  const args = parseArgs(process.argv);
  const pois = readJson(args.pois);
  const edges = readJson(args.edges);
  const baseline = exactBaseline(pois, edges, args.subset);
  const greedy = greedyBaselineFromExact(baseline, edges);
  const baseUrl = `http://127.0.0.1:${args.port}`;
  const env = {
    ...process.env,
    PORT: String(args.port),
    LLM_DISABLED: "1",
    TOURPASS_POIS_PATH: args.pois,
    TOURPASS_EDGES_PATH: args.edges,
  };
  const child = spawn(args.app, [], { cwd: process.cwd(), env, stdio: "ignore" });
  try {
    const health = await waitForHealth(baseUrl);
    const beam = await fetchBeamPlan(baseUrl, baseline);
    const comparableBeam = comparableScore(beam.stops, baseline.subset, edges, baseline.hotel, baseline.allPois);
    writeReport(args.report, args, health, baseline, greedy, beam, comparableBeam);
    console.log(`Algorithm quality report written to ${args.report}`);
  } finally {
    child.kill();
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}

module.exports = {
  exactBaseline,
  greedyBaselineFromExact,
  parseArgs,
};
