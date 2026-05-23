const fs = require("fs");
const { spawn } = require("child_process");
const { performance } = require("perf_hooks");

function parseList(value, fallback) {
  if (!value) return fallback;
  return value.split(",").map((item) => Number(item.trim())).filter((item) => Number.isFinite(item) && item > 0);
}

function parseArgs(argv) {
  const args = {
    app: "bin/tourpass.exe",
    port: 8092,
    duration: 60,
    warmup: 5,
    concurrency: 8,
    concurrencySteps: [1, 10, 50, 100],
    report: "docs/performance_report.md",
    bypassCache: false,
    jobIterations: 10,
    recordDb: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--app") args.app = value;
    if (key === "--port") args.port = Number(value);
    if (key === "--duration") args.duration = Number(value);
    if (key === "--warmup") args.warmup = Number(value);
    if (key === "--concurrency") args.concurrency = Number(value);
    if (key === "--concurrency-steps") args.concurrencySteps = parseList(value, args.concurrencySteps);
    if (key === "--report") args.report = value;
    if (key === "--job-iterations") args.jobIterations = Number(value);
    if (key === "--bypass-cache") {
      args.bypassCache = true;
    }
    if (key === "--record-db") {
      args.recordDb = true;
    }
    if (key.startsWith("--") && key !== "--bypass-cache" && key !== "--record-db") i += 1;
  }
  args.duration = Math.max(1, args.duration);
  args.warmup = Math.max(0, args.warmup);
  args.concurrency = Math.max(1, args.concurrency);
  args.jobIterations = Math.max(1, args.jobIterations);
  return args;
}

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[index] ?? 0;
}

function summarize(samples, errors, durationMs) {
  const sum = samples.reduce((total, value) => total + value, 0);
  const total = samples.length + errors;
  return {
    count: samples.length,
    errors,
    errorRate: total === 0 ? 0 : errors / total,
    throughput: samples.length / Math.max(0.001, durationMs / 1000),
    avg: samples.length ? sum / samples.length : 0,
    p50: percentile(samples, 50),
    p95: percentile(samples, 95),
    p99: percentile(samples, 99),
    min: samples.length ? Math.min(...samples) : 0,
    max: samples.length ? Math.max(...samples) : 0,
  };
}

function withCacheBypass(endpoint, enabled) {
  if (!enabled) return endpoint;
  const nonce = `bench_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  const separator = endpoint.path.includes("?") ? "&" : "?";
  const body = endpoint.body ? { ...endpoint.body, benchmark_nonce: nonce } : undefined;
  return { ...endpoint, path: `${endpoint.path}${separator}benchmark_nonce=${nonce}`, body };
}

function withFixedNonce(endpoint, label) {
  const separator = endpoint.path.includes("?") ? "&" : "?";
  const body = endpoint.body ? { ...endpoint.body, benchmark_nonce: label } : undefined;
  return { ...endpoint, path: `${endpoint.path}${separator}benchmark_nonce=${label}`, body };
}

async function timedRequest(baseUrl, endpoint) {
  const start = performance.now();
  const response = await fetch(`${baseUrl}${endpoint.path}`, {
    method: endpoint.method || "GET",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: endpoint.body ? JSON.stringify(endpoint.body) : undefined,
  });
  const text = await response.text();
  return {
    ok: response.ok,
    status: response.status,
    ms: performance.now() - start,
    text,
    headers: response.headers,
  };
}

async function requestJson(baseUrl, endpoint) {
  const result = await timedRequest(baseUrl, endpoint);
  if (!result.ok) {
    throw new Error(`${endpoint.name} failed with ${result.status}: ${result.text.slice(0, 160)}`);
  }
  return JSON.parse(result.text);
}

async function recordBenchmarkRun(baseUrl, summaries, args, startedAt) {
  const payload = {
    started_at: startedAt,
    duration_seconds: args.duration,
    concurrency_steps_json: JSON.stringify(args.concurrencySteps),
    summary_json: JSON.stringify(summaries),
    report_path: args.report,
  };
  await requestJson(baseUrl, {
    name: "POST /benchmark/runs",
    path: "/benchmark/runs",
    method: "POST",
    body: payload,
  });
}

async function waitForHealth(baseUrl) {
  for (let i = 0; i < 50; i += 1) {
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }
  throw new Error("service did not become healthy");
}

async function warmupEndpoint(baseUrl, endpoint, warmup) {
  for (let i = 0; i < warmup; i += 1) {
    await timedRequest(baseUrl, endpoint);
  }
}

async function runDurationScenario(baseUrl, endpoint, options) {
  await warmupEndpoint(baseUrl, endpoint, options.warmup);
  const samples = [];
  let errors = 0;
  let stop = false;
  const startedAt = performance.now();
  const deadline = startedAt + options.duration * 1000;

  async function worker() {
    while (!stop && performance.now() < deadline) {
      const currentEndpoint = withCacheBypass(endpoint, options.bypassCache);
      try {
        const result = await timedRequest(baseUrl, currentEndpoint);
        if (result.ok) {
          samples.push(result.ms);
        } else {
          errors += 1;
        }
      } catch {
        errors += 1;
      }
    }
  }

  await Promise.all(Array.from({ length: options.concurrency }, () => worker()));
  stop = true;
  return summarize(samples, errors, performance.now() - startedAt);
}

async function runAsyncJobScenario(baseUrl, body, options) {
  const samples = [];
  let errors = 0;
  const startedAt = performance.now();

  async function oneJob() {
    const start = performance.now();
    const created = await requestJson(baseUrl, {
      name: "POST /trip/jobs",
      path: "/trip/jobs",
      method: "POST",
      body: options.bypassCache ? { ...body, benchmark_nonce: `${Date.now()}_${Math.random()}` } : body,
    });
    for (let poll = 0; poll < 120; poll += 1) {
      const job = await requestJson(baseUrl, {
        name: "GET /trip/jobs/{id}",
        path: `/trip/jobs/${created.job_id}`,
      });
      if (job.status === "SUCCEEDED") {
        samples.push(performance.now() - start);
        return;
      }
      if (job.status === "FAILED") {
        throw new Error(`async job failed: ${JSON.stringify(job.error)}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error("async job timeout");
  }

  let next = 0;
  async function worker() {
    while (next < options.jobIterations) {
      next += 1;
      try {
        await oneJob();
      } catch {
        errors += 1;
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(options.concurrency, options.jobIterations) }, () => worker()));
  return summarize(samples, errors, performance.now() - startedAt);
}

function formatMs(value) {
  return `${value.toFixed(1)} ms`;
}

function formatRate(value) {
  return `${value.toFixed(2)}/s`;
}

function formatPct(value) {
  return `${(value * 100).toFixed(2)}%`;
}

function writeReport(path, summaries, args, metrics) {
  const lines = [
    "# Tour Pass 性能回归基准报告",
    "",
    `- 运行时间：${new Date().toISOString()}`,
    `- 单轮持续时间：${args.duration}s，预热请求：${args.warmup}，并发梯度：${args.concurrencySteps.join(", ")}`,
    `- 服务地址：http://127.0.0.1:${args.port}`,
    "",
    "> 这份报告用于本地性能回归检查，不代表生产压测。当前默认数据是长沙样例图，不包含真实地图 API、数据库 IO、外部 LLM 网络延迟或真实用户流量。",
    "",
    "| 场景 | 并发 | 成功数 | 吞吐量 | 错误率 | avg | p50 | p95 | p99 | max |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
  ];
  for (const item of summaries) {
    lines.push(`| ${item.name} | ${item.concurrency} | ${item.count} | ${formatRate(item.throughput)} | ${formatPct(item.errorRate)} | ${formatMs(item.avg)} | ${formatMs(item.p50)} | ${formatMs(item.p95)} | ${formatMs(item.p99)} | ${formatMs(item.max)} |`);
  }
  lines.push("");
  lines.push("## 服务端指标快照");
  lines.push("");
  lines.push("```json");
  lines.push(JSON.stringify(metrics, null, 2));
  lines.push("```");
  lines.push("");
  lines.push("## 口径说明");
  lines.push("");
  lines.push("- `LLM_DISABLED=1`：基准只测结构化算法规划和本地模板兜底，不测外部 LLM 网络延迟。");
  lines.push("- `cold-cache` 场景使用一次性固定 benchmark nonce 观察首轮未命中后的表现；`hot-cache` 场景复用固定请求；`bypass-cache` 场景为每次请求注入 benchmark nonce，三者必须分开解读。");
  lines.push("- `/trip/jobs` 端到端耗时包含提交、排队、执行和轮询等待，适合观察削峰链路，不等同于分布式任务调度。");
  lines.push("- 若要做生产压测，应使用 wrk/JMeter/k6、至少 1 分钟持续时长、真实请求分布、P95/P99、吞吐量和错误率。");
  fs.writeFileSync(path, `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  const args = parseArgs(process.argv);
  const baseUrl = `http://127.0.0.1:${args.port}`;
  const env = { ...process.env, PORT: String(args.port), LLM_DISABLED: "1" };
  const child = spawn(args.app, [], { cwd: process.cwd(), env, stdio: "ignore" });
  const tripBody = JSON.parse(fs.readFileSync("docs/sample_candidate_request.json", "utf8"));
  const startedAt = new Date().toISOString();
  const scenarios = [
    { name: "GET /health", path: "/health" },
    { name: "GET /route/shortest hot-cache", path: "/route/shortest?from=hotel_wuyi&to=yuelu_academy&algorithm=astar" },
    { name: "GET /route/shortest cold-cache", path: "/route/shortest?from=hotel_wuyi&to=yuelu_academy&algorithm=astar", coldCache: true, warmup: 0 },
    { name: "GET /poi/search hot-cache", path: "/poi/search?q=%E5%AE%A4%E5%86%85%20%E8%89%BA%E6%9C%AF&type=attraction&limit=5" },
    { name: "GET /poi/search cold-cache", path: "/poi/search?q=%E5%AE%A4%E5%86%85%20%E8%89%BA%E6%9C%AF&type=attraction&limit=5", coldCache: true, warmup: 0 },
    { name: "POST /trip/plan hot-cache", path: "/trip/plan", method: "POST", body: tripBody },
    { name: "POST /trip/plan cold-cache", path: "/trip/plan", method: "POST", body: tripBody, coldCache: true, warmup: 0 },
    { name: "POST /trip/plan bypass-cache", path: "/trip/plan", method: "POST", body: tripBody, bypassCache: true },
  ];

  try {
    await waitForHealth(baseUrl);
    const summaries = [];
    for (const concurrency of args.concurrencySteps) {
      for (const scenario of scenarios) {
        const endpoint = scenario.coldCache
          ? withFixedNonce(scenario, `cold_${scenario.name.replace(/[^A-Za-z0-9]+/g, "_")}_${concurrency}_${Date.now()}`)
          : scenario;
        const summary = await runDurationScenario(baseUrl, endpoint, {
          duration: args.duration,
          warmup: scenario.warmup ?? args.warmup,
          concurrency,
          bypassCache: args.bypassCache || Boolean(scenario.bypassCache),
        });
        summaries.push({ name: scenario.name, concurrency, ...summary });
      }
      const jobSummary = await runAsyncJobScenario(baseUrl, tripBody, {
        concurrency,
        jobIterations: args.jobIterations,
        bypassCache: true,
      });
      summaries.push({ name: "POST /trip/jobs end-to-end", concurrency, ...jobSummary });
    }

    if (args.recordDb) {
      await recordBenchmarkRun(baseUrl, summaries, args, startedAt);
    }
    const metrics = await requestJson(baseUrl, { name: "GET /metrics", path: "/metrics" });
    writeReport(args.report, summaries, args, metrics);
    console.log(`Performance report written to ${args.report}`);
  } finally {
    child.kill();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
