const fs = require("fs");
const { spawn } = require("child_process");
const { performance } = require("perf_hooks");

function parseArgs(argv) {
  const args = {
    app: "bin/tourpass.exe",
    port: 8092,
    iterations: 30,
    warmup: 5,
    report: "docs/performance_report.md",
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--app") args.app = value;
    if (key === "--port") args.port = Number(value);
    if (key === "--iterations") args.iterations = Number(value);
    if (key === "--warmup") args.warmup = Number(value);
    if (key === "--report") args.report = value;
    if (key.startsWith("--")) i += 1;
  }
  return args;
}

function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[index];
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

async function request(baseUrl, endpoint) {
  const start = performance.now();
  const response = await fetch(`${baseUrl}${endpoint.path}`, {
    method: endpoint.method || "GET",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: endpoint.body ? JSON.stringify(endpoint.body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`${endpoint.name} failed with ${response.status}`);
  }
  await response.text();
  return performance.now() - start;
}

async function waitForHealth(baseUrl) {
  for (let i = 0; i < 30; i += 1) {
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }
  throw new Error("service did not become healthy");
}

function formatMs(value) {
  return `${value.toFixed(1)} ms`;
}

function writeReport(path, summaries, args) {
  const lines = [
    "# Tour Pass 性能基准报告",
    "",
    `- 运行时间：${new Date().toISOString()}`,
    `- 样本数：${args.iterations} 次，预热：${args.warmup} 次`,
    `- 服务地址：http://127.0.0.1:${args.port}`,
    "",
    "| 接口 | avg | p50 | p95 | min | max |",
    "| --- | ---: | ---: | ---: | ---: | ---: |",
  ];
  for (const item of summaries) {
    lines.push(`| ${item.name} | ${formatMs(item.avg)} | ${formatMs(item.p50)} | ${formatMs(item.p95)} | ${formatMs(item.min)} | ${formatMs(item.max)} |`);
  }
  lines.push("");
  lines.push("## 说明");
  lines.push("");
  lines.push("- 基准脚本会启动本地服务，强制 `LLM_DISABLED=1`，避免远程 LLM 网络波动污染结果。");
  lines.push("- 当前数据集为演示样例规模，结果主要用于防止算法和 API 响应时间出现明显回退。");
  lines.push("- 面试展示时可结合 Beam Search、BM25 检索和 API 冒烟测试说明工程质量门禁。");
  fs.writeFileSync(path, `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  const args = parseArgs(process.argv);
  const baseUrl = `http://127.0.0.1:${args.port}`;
  const env = { ...process.env, PORT: String(args.port), LLM_DISABLED: "1" };
  const child = spawn(args.app, [], { cwd: process.cwd(), env, stdio: "ignore" });
  const endpoints = [
    { name: "GET /health", path: "/health" },
    { name: "GET /route/shortest", path: "/route/shortest?from=hotel_wuyi&to=yuelu_academy&algorithm=astar" },
    { name: "GET /poi/search", path: "/poi/search?q=%E5%AE%A4%E5%86%85%20%E8%89%BA%E6%9C%AF&type=attraction&limit=5" },
    {
      name: "POST /trip/plan",
      path: "/trip/plan",
      method: "POST",
      body: JSON.parse(fs.readFileSync("docs/sample_candidate_request.json", "utf8")),
    },
  ];

  try {
    await waitForHealth(baseUrl);
    const summaries = [];
    for (const endpoint of endpoints) {
      for (let i = 0; i < args.warmup; i += 1) {
        await request(baseUrl, endpoint);
      }
      const samples = [];
      for (let i = 0; i < args.iterations; i += 1) {
        samples.push(await request(baseUrl, endpoint));
      }
      summaries.push({ name: endpoint.name, ...summarize(samples) });
    }
    writeReport(args.report, summaries, args);
    console.log(`Performance report written to ${args.report}`);
  } finally {
    child.kill();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
