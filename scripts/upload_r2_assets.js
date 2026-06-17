const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const DATA_DIR = path.join(process.cwd(), "data");

function parseArgs(argv) {
  const args = {
    city: "",
    dryRun: false,
    onlyAmap: true,
    sampleHead: 0,
    concurrency: 10,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--city") { args.city = value || ""; i += 1; }
    else if (key === "--dry-run") args.dryRun = true;
    else if (key === "--only-amap") args.onlyAmap = true;
    else if (key === "--all-sources") args.onlyAmap = false;
    else if (key === "--sample-head") { args.sampleHead = Number(value || "0"); i += 1; }
    else if (key === "--concurrency") { args.concurrency = Math.max(1, Number(value || "10")); i += 1; }
  }
  return args;
}

function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".png") return "image/png";
  if (ext === ".webp") return "image/webp";
  return "application/octet-stream";
}

function isExternal(url) {
  return /^https?:\/\//i.test(url || "");
}

function localPathForKey(key) {
  const clean = key.replace(/^\/+/, "");
  if (clean.startsWith("images/")) {
    return path.join(DATA_DIR, clean.slice("images/".length));
  }
  return path.join(DATA_DIR, clean);
}

function cityDirs(city) {
  if (city) return [path.join(DATA_DIR, city)];
  return fs.readdirSync(DATA_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(DATA_DIR, entry.name));
}

function collectAssets(args) {
  const assets = new Map();
  const missing = [];

  for (const cityDir of cityDirs(args.city)) {
    const poisPath = path.join(cityDir, "pois.json");
    if (!fs.existsSync(poisPath)) continue;
    const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
    if (!Array.isArray(pois)) continue;

    for (const poi of pois) {
      for (const img of poi.images || []) {
        const url = (img.url || "").trim();
        if (!url || isExternal(url)) continue;
        if (args.onlyAmap && img.source !== "amap") continue;
        const key = url.replace(/^\/+/, "");
        const filePath = localPathForKey(key);
        if (!fs.existsSync(filePath)) {
          missing.push({ key, filePath });
          continue;
        }
        assets.set(key, {
          key,
          filePath,
          bytes: fs.statSync(filePath).size,
          source: img.source || "",
        });
      }
    }
  }

  return { assets: [...assets.values()], missing };
}

function hashHex(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function hmac(key, value, encoding) {
  return crypto.createHmac("sha256", key).update(value).digest(encoding);
}

function encodeS3Key(key) {
  return key.split("/").map(encodeURIComponent).join("/");
}

function r2Config() {
  const accountId = process.env.R2_ACCOUNT_ID;
  const bucket = process.env.R2_BUCKET;
  const accessKey = process.env.R2_ACCESS_KEY_ID;
  const secretKey = process.env.R2_SECRET_ACCESS_KEY;
  const endpoint = process.env.R2_ENDPOINT || (accountId ? `https://${accountId}.r2.cloudflarestorage.com` : "");
  const missing = [];
  if (!accountId && !process.env.R2_ENDPOINT) missing.push("R2_ACCOUNT_ID");
  if (!bucket) missing.push("R2_BUCKET");
  if (!accessKey) missing.push("R2_ACCESS_KEY_ID");
  if (!secretKey) missing.push("R2_SECRET_ACCESS_KEY");
  if (missing.length) throw new Error(`Missing env: ${missing.join(", ")}`);
  return { bucket, accessKey, secretKey, endpoint };
}

async function signedRequest({ method, key, body, type }) {
  const cfg = r2Config();
  const now = new Date();
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, "");
  const dateStamp = amzDate.slice(0, 8);
  const payloadHash = hashHex(body || "");
  const url = new URL(`${cfg.endpoint}/${cfg.bucket}/${encodeS3Key(key)}`);

  const canonicalHeaders = [
    `host:${url.host}`,
    `x-amz-content-sha256:${payloadHash}`,
    `x-amz-date:${amzDate}`,
    "",
  ].join("\n");
  const signedHeaders = "host;x-amz-content-sha256;x-amz-date";
  const canonicalRequest = [
    method,
    url.pathname,
    "",
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");

  const scope = `${dateStamp}/auto/s3/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    scope,
    hashHex(canonicalRequest),
  ].join("\n");
  const kDate = hmac(`AWS4${cfg.secretKey}`, dateStamp);
  const kRegion = hmac(kDate, "auto");
  const kService = hmac(kRegion, "s3");
  const kSigning = hmac(kService, "aws4_request");
  const signature = hmac(kSigning, stringToSign, "hex");

  const headers = {
    Authorization: `AWS4-HMAC-SHA256 Credential=${cfg.accessKey}/${scope}, SignedHeaders=${signedHeaders}, Signature=${signature}`,
    "x-amz-content-sha256": payloadHash,
    "x-amz-date": amzDate,
  };
  if (type) headers["Content-Type"] = type;

  const res = await fetch(url, { method, headers, body });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${method} ${key} failed: ${res.status} ${text.slice(0, 300)}`);
  }
}

async function main() {
  const args = parseArgs(process.argv);
  const { assets, missing } = collectAssets(args);
  const totalBytes = assets.reduce((sum, item) => sum + item.bytes, 0);

  console.log(`R2 asset scan: ${assets.length} files, ${(totalBytes / 1024 / 1024).toFixed(2)} MB`);
  if (missing.length) {
    console.warn(`Missing local files: ${missing.length}`);
    for (const item of missing.slice(0, 10)) console.warn(`- ${item.key}`);
  }
  if (args.dryRun) return;

  let uploaded = 0;
  let failed = 0;
  const concurrency = args.concurrency;
  const startTime = Date.now();
  console.log(`Uploading with concurrency=${concurrency}...`);

  // Concurrent worker pool
  const queue = [...assets];
  const workers = Array.from({ length: concurrency }, async () => {
    while (queue.length > 0) {
      const asset = queue.shift();
      if (!asset) break;
      try {
        const body = fs.readFileSync(asset.filePath);
        await signedRequest({
          method: "PUT",
          key: asset.key,
          body,
          type: contentType(asset.filePath),
        });
        uploaded += 1;
      } catch (err) {
        failed += 1;
        if (failed <= 5) console.error(`Failed: ${asset.key} - ${err.message}`);
      }
      const done = uploaded + failed;
      if (done % 100 === 0 || done === assets.length) {
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        console.log(`Uploaded ${uploaded}/${assets.length} (${failed} failed) [${elapsed}s]`);
      }
    }
  });
  await Promise.all(workers);

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log(`\nDone: ${uploaded} uploaded, ${failed} failed in ${elapsed}s`);

  for (const asset of assets.slice(0, Math.max(0, args.sampleHead))) {
    await signedRequest({ method: "HEAD", key: asset.key, body: "" });
    console.log(`HEAD ok: ${asset.key}`);
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
