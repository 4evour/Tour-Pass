const fs = require("fs");
const { spawn } = require("child_process");
const { performance } = require("perf_hooks");

function parseArgs(argv) {
  const args = {
    app: "bin/tourpass.exe",
    port: 8092,
    iterations: 30,
    warmup: 5,
    concurrency: 8,
    report: "docs/performance_report.md",
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--app") args.app = value;
    if (key === "--port") args.port = Number(value);
    if (key === "--iterations") args.iterations = Number(value);
    if (key === "--warmup") args.warmup = Number(value);
    if (key === "--concurrency") args.concurrency = Number(value);
    if (key === "--report") args.report = value;
    if (key.startsWith("--")) i += 1;
  }
  args.iterations = Math.max(1, args.iterations);
  args.warmup = Math.max(0, args.warmup);
  args.concurrency = Math.max(1, args.concurrency);
  return args;
}

function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[index] ?? 0;
}

function summarize(samples) {
  const sum = samples.reduce((total, value) => total + value, 0);
  return {
    avg: sum / samples.length,
    p50: percentile(samples, 50),
    p95: percentile(samples, 95),
    min: Math.min(...samples),
    max: Math.max(...samples),
  };
}

async function timedRequest(baseUrl, endpoint) {
  const start = performance.now();
  const response = await fetch(`${baseUrl}${endpoint.path}`, {
    method: endpoint.method || "GET",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: endpoint.body ? JSON.stringify(endpoint.body) : undefined,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${endpoint.name} failed with ${response.status}: ${text.slice(0, 160)}`);
  }
  const text = await response.text();
  return { ms: performance.now() - start, text, headers: response.headers };
}

async function requestJson(baseUrl, endpoint) {
  const result = await timedRequest(baseUrl, endpoint);
  return JSON.parse(result.text);
}

async function waitForHealth(baseUrl) {
  for (let i = 0; i < 40; i += 1) {
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }
  throw new Error("service did not become healthy");
}

async function runSequential(baseUrl, endpoint, args) {
  for (let i = 0; i < args.warmup; i += 1) {
    await timedRequest(baseUrl, endpoint);
  }
  const samples = [];
  for (let i = 0; i < args.iterations; i += 1) {
    samples.push((await timedRequest(baseUrl, endpoint)).ms);
  }
  return samples;
}

async function runConcurrent(baseUrl, endpoint, args) {
  const samples = [];
  let next = 0;
  async function worker() {
    while (next < args.iterations) {
      next += 1;
      samples.push((await timedRequest(baseUrl, endpoint)).ms);
    }
  }
  await Promise.all(Array.from({ length: Math.min(args.concurrency, args.iterations) }, () => worker()));
  return samples;
}

async function runAsyncJobScenario(baseUrl, body, args) {
  const samples = [];
  for (let i = 0; i < args.iterations; i += 1) {
    const start = performance.now();
    const created = await requestJson(baseUrl, {
      name: "POST /trip/jobs",
      path: "/trip/jobs",
      method: "POST",
      body,
    });
    for (let poll = 0; poll < 80; poll += 1) {
      const job = await requestJson(baseUrl, {
        name: "GET /trip/jobs/{id}",
        path: `/trip/jobs/${created.job_id}`,
      });
      if (job.status === "SUCCEEDED") {
        samples.push(performance.now() - start);
        break;
      }
      if (job.status === "FAILED") {
        throw new Error(`async job failed: ${JSON.stringify(job.error)}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    if (samples.length !== i + 1) {
      throw new Error("async job did not finish before timeout");
    }
  }
  return samples;
}

function formatMs(value) {
  return `${value.toFixed(1)} ms`;
}

function writeReport(path, summaries, args, metrics) {
  const lines = [
    "# Tour Pass 性能基准报告",
    "",
    `- 运行时间：${new Date().toISOString()}`,
    `- 样本数：${args.iterations} 次，预热：${args.warmup} 次，并发：${args.concurrency}`,
    `- 服务地址：http://127.0.0.1:${args.port}`,
    "",
    "| 场景 | avg | p50 | p95 | min | max |",
    "| --- | ---: | ---: | ---: | ---: | ---: |",
  ];
  for (const item of summaries) {
    lines.push(`| ${item.name} | ${formatMs(item.avg)} | ${formatMs(item.p50)} | ${formatMs(item.p95)} | ${formatMs(item.min)} | ${formatMs(item.max)} |`);
  }
  lines.push("");
  lines.push("## 服务端指标快照");
  lines.push("");
  lines.push("```json");
  lines.push(JSON.stringify(metrics, null, 2));
  lines.push("```");
  lines.push("");
  lines.push("## 说明");
  lines.push("");
  lines.push("- 基准脚本会启动本地服务，强制 `LLM_DISABLED=1`，避免远程 LLM 网络波动污染结果。");
  lines.push("- 冷缓存场景使用首次请求，热缓存场景复用相同查询并检查服务端缓存命中。");
  lines.push("- 并发场景用于验证线程池下的吞吐和 p95 延迟，异步任务场景用于验证规划任务削峰链路。");
  fs.writeFileSync(path, `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  const args = parseArgs(process.argv);
  const baseUrl = `http://127.0.0.1:${args.port}`;
  const env = { ...process.env, PORT: String(args.port), LLM_DISABLED: "1" };
  const child = spawn(args.app, [], { cwd: process.cwd(), env, stdio: "ignore" });
  const tripBody = JSON.parse(fs.readFileSync("docs/sample_candidate_request.json", "utf8"));
  const endpoints = [
    { name: "GET /health", path: "/health" },
    { name: "GET /route/shortest cold", path: "/route/shortest?from=hotel_wuyi&to=yuelu_academy&algorithm=astar&bench=cold" },
    { name: "GET /route/shortest hot", path: "/route/shortest?from=hotel_wuyi&to=yuelu_academy&algorithm=astar" },
    { name: "GET /poi/search hot", path: "/poi/search?q=%E5%AE%A4%E5%86%85%20%E8%89%BA%E6%9C%AF&type=attraction&limit=5" },
    {
      name: "POST /trip/plan sequential",
      path: "/trip/plan",
      method: "POST",
      body: tripBody,
    },
  ];

  try {
    await waitForHealth(baseUrl);
    const summaries = [];
    for (const endpoint of endpoints) {
      const samples = await runSequential(baseUrl, endpoint, args);
      summaries.push({ name: endpoint.name, ...summarize(samples) });
    }
    const concurrentSamples = await runConcurrent(baseUrl, {
      name: "POST /trip/plan concurrent",
      path: "/trip/plan",
      method: "POST",
      body: tripBody,
    }, args);
    summaries.push({ name: `POST /trip/plan concurrent x${args.concurrency}`, ...summarize(concurrentSamples) });

    const asyncSamples = await runAsyncJobScenario(baseUrl, tripBody, { ...args, iterations: Math.min(args.iterations, 10) });
    summaries.push({ name: "POST /trip/jobs end-to-end", ...summarize(asyncSamples) });

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
