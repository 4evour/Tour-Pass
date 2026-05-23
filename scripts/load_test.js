const fs = require("fs");
const http = require("http");
const https = require("https");
const { performance } = require("perf_hooks");

function parseArgs(argv) {
  const args = {
    url: "http://127.0.0.1:8080/health",
    concurrency: 100,
    duration: 30,
    report: "docs/load_test_report.md",
    method: "GET",
    bodyFile: "",
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--url") args.url = value;
    if (key === "--concurrency") args.concurrency = Number(value);
    if (key === "--duration") args.duration = Number(value);
    if (key === "--report") args.report = value;
    if (key === "--method") args.method = value.toUpperCase();
    if (key === "--body-file") args.bodyFile = value;
    if (key.startsWith("--")) i += 1;
  }
  args.concurrency = Math.max(1, Math.min(1000, Number.isFinite(args.concurrency) ? Math.floor(args.concurrency) : 100));
  args.duration = Math.max(1, Number.isFinite(args.duration) ? args.duration : 30);
  return args;
}

function percentile(sorted, p) {
  if (sorted.length === 0) return 0;
  const index = Math.max(0, Math.ceil(sorted.length * p) - 1);
  return sorted[Math.min(sorted.length - 1, index)];
}

async function requestOnce(args, body) {
  const started = performance.now();
  return new Promise((resolve) => {
    const headers = { Connection: "keep-alive" };
    if (body) {
      headers["Content-Type"] = "application/json; charset=utf-8";
      headers["Content-Length"] = Buffer.byteLength(body);
    }
    const options = {
      protocol: args.parsedUrl.protocol,
      hostname: args.parsedUrl.hostname,
      port: args.parsedUrl.port,
      path: `${args.parsedUrl.pathname}${args.parsedUrl.search}`,
      method: args.method,
      headers,
      agent: args.agent,
      timeout: 10000,
    };
    const client = args.parsedUrl.protocol === "https:" ? https : http;
    const req = client.request(options, (res) => {
      res.resume();
      res.on("end", () => {
        const status = res.statusCode || 0;
        resolve({ ok: status >= 200 && status < 300, status, ms: performance.now() - started });
      });
    });
    req.on("timeout", () => {
      req.destroy(new Error("request timeout"));
    });
    req.on("error", (error) => {
      resolve({ ok: false, status: 0, ms: performance.now() - started, error: error.message });
    });
    if (body) req.write(body);
    req.end();
  });
}

async function worker(args, body, deadline, samples, statuses, errors) {
  while (performance.now() < deadline) {
    const result = await requestOnce(args, body);
    samples.push(result.ms);
    statuses[result.status] = (statuses[result.status] || 0) + 1;
    if (!result.ok) {
      errors.count += 1;
      if (result.error && errors.examples.length < 3) {
        errors.examples.push(result.error);
      }
    }
  }
}

function writeReport(args, summary) {
  const runtimeEnv = [
    `LLM_DISABLED=${process.env.LLM_DISABLED || "(unset)"}`,
    `TOURPASS_DB_DISABLED=${process.env.TOURPASS_DB_DISABLED || "(unset)"}`,
    `TOURPASS_WORKERS=${process.env.TOURPASS_WORKERS || "(unset)"}`,
    `TOURPASS_MAX_QUEUE=${process.env.TOURPASS_MAX_QUEUE || "(unset)"}`,
    `TOURPASS_MAX_IN_FLIGHT=${process.env.TOURPASS_MAX_IN_FLIGHT || "(unset)"}`,
  ];
  const lines = [
    "# Tour Pass Load Test Report",
    "",
    "本报告使用本地 HTTP 压测脚本生成，用于工程回归和面试展示；不代表生产 SLA。",
    "",
    "## 运行口径",
    "",
    `- URL：\`${args.url}\``,
    `- 方法：\`${args.method}\``,
    `- 并发：\`${args.concurrency}\``,
    `- 持续时间：\`${args.duration}s\``,
    `- 运行环境变量：\`${runtimeEnv.join(" ")}\``,
    `- 客户端：\`node ${process.version} ${process.platform}/${process.arch} http/https keep-alive\``,
    "- 推荐环境：`LLM_DISABLED=1`，默认长沙样例数据；如要测试 HTTP 承载上限，应显式记录 worker、队列和 in-flight 参数。",
    "- 缓存口径：按被测 URL 决定；`/health` 不代表规划热路径，`/trip/plan` 应说明是否复用相同请求。",
    "",
    "## 结果",
    "",
    "| requests | errors | error rate | QPS | avg | p50 | p95 | p99 | max |",
    "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    `| ${summary.requests} | ${summary.errors} | ${(summary.errorRate * 100).toFixed(2)}% | ${summary.qps.toFixed(2)} | ${summary.avg.toFixed(2)} ms | ${summary.p50.toFixed(2)} ms | ${summary.p95.toFixed(2)} ms | ${summary.p99.toFixed(2)} ms | ${summary.max.toFixed(2)} ms |`,
    "",
    "## 状态码",
    "",
  ];
  for (const [status, count] of Object.entries(summary.statuses).sort()) {
    lines.push(`- \`${status}\`: ${count}`);
  }
  lines.push("");
  lines.push("## 边界说明");
  lines.push("");
  lines.push("- 这是本地或容器环境压测，不包含真实用户网络、真实地图 API 或外部 LLM 延迟。");
  lines.push("- 如果状态码 `0` 或错误率偏高，优先按客户端连接失败/短连接压力/本机资源限制处理，并在 Docker/Linux 环境复测后再对外展示。");
  lines.push("- 若测试 `/trip/plan`，需要区分热缓存、冷缓存和绕过缓存。");
  lines.push("- `cpp-httplib` 在本项目中用于演示级 HTTP 承载，不作为生产级网关能力包装。");
  fs.writeFileSync(args.report, `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  const args = parseArgs(process.argv);
  args.parsedUrl = new URL(args.url);
  args.agent = args.parsedUrl.protocol === "https:"
    ? new https.Agent({ keepAlive: true, maxSockets: args.concurrency, maxFreeSockets: args.concurrency })
    : new http.Agent({ keepAlive: true, maxSockets: args.concurrency, maxFreeSockets: args.concurrency });
  const body = args.bodyFile ? fs.readFileSync(args.bodyFile, "utf8") : "";
  const samples = [];
  const statuses = {};
  const errors = { count: 0, examples: [] };
  const started = performance.now();
  const deadline = started + args.duration * 1000;

  await Promise.all(Array.from({ length: args.concurrency }, () => worker(args, body, deadline, samples, statuses, errors)));

  const elapsedSeconds = (performance.now() - started) / 1000;
  const sorted = samples.slice().sort((a, b) => a - b);
  const total = sorted.reduce((sum, value) => sum + value, 0);
  const summary = {
    requests: sorted.length,
    errors: errors.count,
    errorRate: sorted.length === 0 ? 1 : errors.count / sorted.length,
    qps: sorted.length / elapsedSeconds,
    avg: sorted.length === 0 ? 0 : total / sorted.length,
    p50: percentile(sorted, 0.50),
    p95: percentile(sorted, 0.95),
    p99: percentile(sorted, 0.99),
    max: sorted[sorted.length - 1] || 0,
    statuses,
  };
  writeReport(args, summary);
  console.log(`Load test complete: ${summary.requests} requests, ${summary.qps.toFixed(2)} QPS, p95 ${summary.p95.toFixed(2)} ms -> ${args.report}`);
  if (errors.examples.length > 0) {
    console.log(`Sample errors: ${errors.examples.join(" | ")}`);
  }
  args.agent.destroy();
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
