const fs = require("fs");
const { spawn, spawnSync } = require("child_process");
const { performance } = require("perf_hooks");

function parseArgs(argv) {
  const args = {
    app: "bin/tourpass.exe",
    port: 8100,
    dataset: "synthetic",
    pois: "",
    edges: "",
    sizes: [25, 100, 500],
    iterations: 5,
    report: "docs/scale_experiment_report.md",
    jsonReport: "",
    cacheMode: process.env.TOURPASS_DISTANCE_CACHE_MODE || "auto",
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--app") args.app = value;
    if (key === "--port") args.port = Number(value);
    if (key === "--dataset") args.dataset = value;
    if (key === "--pois") args.pois = value;
    if (key === "--edges") args.edges = value;
    if (key === "--sizes") args.sizes = value.split(",").map(Number).filter((item) => item > 0);
    if (key === "--iterations") args.iterations = Number(value);
    if (key === "--report") args.report = value;
    if (key === "--json-report") args.jsonReport = value;
    if (key === "--cache-mode") args.cacheMode = value;
    if (key.startsWith("--")) i += 1;
  }
  if (args.dataset !== "synthetic" && args.dataset !== "real") {
    throw new Error("--dataset must be synthetic or real");
  }
  if (args.dataset === "real" && (!args.pois || !args.edges)) {
    throw new Error("--dataset real requires --pois and --edges");
  }
  return args;
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

async function timedPlan(baseUrl, body, iteration) {
  const start = performance.now();
  const response = await fetch(`${baseUrl}/trip/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify({ ...body, benchmark_nonce: `${Date.now()}_${iteration}` }),
  });
  if (!response.ok) {
    throw new Error(`plan failed with ${response.status}: ${(await response.text()).slice(0, 160)}`);
  }
  await response.text();
  return performance.now() - start;
}

function summarize(samples) {
  if (samples.length === 0) {
    return { avg: 0, p95: 0, max: 0 };
  }
  const sorted = [...samples].sort((a, b) => a - b);
  const sum = sorted.reduce((total, value) => total + value, 0);
  return {
    avg: sum / sorted.length,
    p95: sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1)],
    p99: sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.99) - 1)],
    max: sorted[sorted.length - 1],
  };
}

function writeReport(path, rows, args, environment) {
  const command = args.dataset === "real"
    ? `node scripts/scale_experiment.js --dataset real --pois ${args.pois} --edges ${args.edges} --sizes ${rows.map((row) => row.requestedSize).join(",")} --iterations ${rows[0]?.iterations ?? 0}`
    : `node scripts/scale_experiment.js --sizes ${rows.map((row) => row.requestedSize).join(",")} --iterations ${rows[0]?.iterations ?? 0}`;
  const lines = [
    "# Tour Pass Scale Experiment",
    "",
    args.dataset === "real"
      ? "真实 POI 数据用于观察项目在真实地点清单上的规划热路径表现；若通勤边包含 geo_estimated，仍不代表真实路网或生产压测。"
      : "Synthetic 数据用于观察规划热路径随 POI 数量增长的趋势，不代表真实地图数据、真实路网或生产压测。",
    "",
    "## 运行口径",
    "",
    `- 命令：\`${command}\``,
    `- 数据集：\`${args.dataset}\``,
    `- 缓存模式：\`${args.cacheMode}\``,
    "- LLM：`LLM_DISABLED=1`，不包含外部 LLM 网络延迟。",
    args.dataset === "real"
      ? `- 数据：\`${args.pois}\` 与 \`${args.edges}\` 通过 \`TOURPASS_POIS_PATH\` / \`TOURPASS_EDGES_PATH\` 注入服务。`
      : "- 数据：脚本生成 synthetic POI/edges，再通过 `TOURPASS_POIS_PATH` 和 `TOURPASS_EDGES_PATH` 注入服务。",
    "- 目标：验证最短路缓存、候选池裁剪和评分复用后的本地趋势；失败会记录为失败数，不包装成成功性能。",
    `- 环境：platform=${environment.platform}, node=${environment.node}, cpu=${environment.cpu}`,
    "",
    "| POI | Edges | amap edge ratio | cache mode | startup | distance cache entries | iterations | failures | avg | p95 | p99 | max | note |",
    "| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
  ];
  for (const row of rows) {
    const note = row.failures > 0 ? row.failureReason.replace(/\|/g, "/").slice(0, 120) : "ok";
    lines.push(`| ${row.pois} | ${row.edges} | ${(row.amapRatio * 100).toFixed(1)}% | ${row.cacheMode} | ${row.startupMs} ms | ${row.distanceCacheEntries} | ${row.iterations} | ${row.failures} | ${row.avg.toFixed(1)} ms | ${row.p95.toFixed(1)} ms | ${row.p99.toFixed(1)} ms | ${row.max.toFixed(1)} ms | ${note} |`);
  }
  lines.push("");
  lines.push("## 解释边界");
  lines.push("");
  lines.push("- 默认长沙样例仍是演示数据；synthetic 结果只说明本地算法趋势和瓶颈。");
  lines.push("- 500 POI 若出现失败或秒级耗时，应按瓶颈解释，不能写成生产实时能力。真实数据若边来源包含 geo_estimated，也不能等同真实路网。");
  lines.push("- SQLite、HTTP 线程池和背压不参与证明大规模路线质量，只用于本地服务可复盘和稳定性演示。");
  fs.writeFileSync(path, `${lines.join("\n")}\n`, "utf8");
}

function takeFirstN(inputPath, outputPath, count) {
  const data = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  let selected = data.slice(0, count);
  if (selected.length > 0 && !selected.some((poi) => poi.type === "hotel")) {
    const hotel = data.find((poi) => poi.type === "hotel");
    if (hotel) {
      selected = [...selected.slice(0, Math.max(0, count - 1)), hotel];
    }
  }
  fs.writeFileSync(outputPath, `${JSON.stringify(selected, null, 2)}\n`, "utf8");
}

function filterEdges(inputPath, outputPath, allowedIds) {
  const edges = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  const filtered = edges.filter((edge) => allowedIds.has(edge.from) && allowedIds.has(edge.to));
  fs.writeFileSync(outputPath, `${JSON.stringify(filtered, null, 2)}\n`, "utf8");
  return filtered;
}

function edgeSourceStats(edges) {
  const sourceCounts = edges.reduce((acc, edge) => {
    const source = edge.source || "unknown";
    acc[source] = (acc[source] || 0) + 1;
    return acc;
  }, {});
  const total = edges.length || 0;
  return {
    sourceCounts,
    amapRatio: total === 0 ? 0 : (sourceCounts.amap || 0) / total,
  };
}

function environmentSnapshot() {
  const os = require("os");
  return {
    platform: `${process.platform}-${process.arch}`,
    node: process.version,
    cpu: os.cpus()[0]?.model || "unknown",
  };
}

async function main() {
  const args = parseArgs(process.argv);
  const body = JSON.parse(fs.readFileSync("docs/sample_candidate_request.json", "utf8"));
  const rows = [];
  const environment = environmentSnapshot();

  for (const size of args.sizes) {
    const outDir = `output/synthetic-${size}`;
    let poisPath = `${outDir}/pois.json`;
    let edgesPath = `${outDir}/edges.json`;
    if (args.dataset === "synthetic") {
      const generated = spawnSync(process.execPath, ["scripts/generate_synthetic_data.js", "--pois", String(size), "--out-dir", outDir], {
        cwd: process.cwd(),
        stdio: "inherit",
      });
      if (generated.status !== 0) throw new Error(`failed to generate synthetic data for ${size}`);
    } else {
      fs.mkdirSync(outDir, { recursive: true });
      takeFirstN(args.pois, poisPath, size);
      const allowedIds = new Set(JSON.parse(fs.readFileSync(poisPath, "utf8")).map((poi) => poi.id));
      filterEdges(args.edges, edgesPath, allowedIds);
    }
    const sourceStats = edgeSourceStats(JSON.parse(fs.readFileSync(edgesPath, "utf8")));

    const port = args.port + rows.length;
    const baseUrl = `http://127.0.0.1:${port}`;
    const env = {
      ...process.env,
      PORT: String(port),
      LLM_DISABLED: "1",
      TOURPASS_POIS_PATH: poisPath,
      TOURPASS_EDGES_PATH: edgesPath,
      TOURPASS_DISTANCE_CACHE_MODE: args.cacheMode,
    };
    const child = spawn(args.app, [], { cwd: process.cwd(), env, stdio: "ignore" });
    let health = { poi_count: size, edge_count: 0, distance_cache: { entries: 0 } };
    const samples = [];
    let failures = 0;
    let failureReason = "";
    try {
      health = await waitForHealth(baseUrl);
      for (let i = 0; i < args.iterations; i += 1) {
        try {
          samples.push(await timedPlan(baseUrl, body, i));
        } catch (error) {
          failures += 1;
          failureReason = error.message;
        }
      }
    } catch (error) {
      failures = args.iterations;
      failureReason = error.message;
    } finally {
      child.kill();
    }
    rows.push({
      requestedSize: size,
      pois: health.poi_count,
      edges: health.edge_count,
      sourceCounts: sourceStats.sourceCounts,
      amapRatio: sourceStats.amapRatio,
      cacheMode: health.distance_cache?.mode ?? "unknown",
      startupMs: health.distance_cache?.startup_ms ?? 0,
      distanceCacheEntries: health.distance_cache?.entries ?? 0,
      iterations: args.iterations,
      failures,
      failureReason,
      avg: 0,
      p95: 0,
      p99: 0,
      max: 0,
      ...summarize(samples),
    });
  }

  writeReport(args.report, rows, args, environment);
  if (args.jsonReport) {
    fs.writeFileSync(args.jsonReport, `${JSON.stringify({ args, environment, rows }, null, 2)}\n`, "utf8");
  }
  console.log(`Scale experiment report written to ${args.report}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
