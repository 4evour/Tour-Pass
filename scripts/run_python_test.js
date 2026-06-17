const { spawnSync } = require("child_process");

const testArgs = process.argv.slice(2);
if (testArgs.length === 0) {
  console.error("Usage: node scripts/run_python_test.js <test-file> [args...]");
  process.exit(1);
}

const candidates = process.platform === "win32"
  ? [
      { command: "python", args: [] },
      { command: "py", args: ["-3"] },
    ]
  : [
      { command: "python3", args: [] },
      { command: "python", args: [] },
    ];

for (const candidate of candidates) {
  const version = spawnSync(candidate.command, [...candidate.args, "--version"], {
    encoding: "utf8",
    stdio: "pipe",
  });
  if (version.status !== 0) continue;

  const result = spawnSync(candidate.command, [...candidate.args, ...testArgs], {
    encoding: "utf8",
    stdio: "inherit",
  });
  process.exit(result.status ?? 1);
}

console.error("Python 3 was not found. Install Python or enable the Windows py launcher.");
process.exit(1);
