const fs = require("fs");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForHealth(baseUrl) {
  let lastError = "";
  for (let i = 0; i < 60; i += 1) {
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) {
        return await response.json();
      }
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error.message;
    }
    await sleep(500);
  }
  throw new Error(`service did not become healthy: ${lastError}`);
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${url} failed with ${response.status}: ${(await response.text()).slice(0, 240)}`);
  }
  return response.json();
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} failed with ${response.status}: ${(await response.text()).slice(0, 240)}`);
  }
  return response.json();
}

async function main() {
  const baseUrl = process.argv[2] || process.env.TOURPASS_BASE_URL || "http://127.0.0.1:8080";
  const health = await waitForHealth(baseUrl);
  if (health.status !== "ok" || !health.data_loaded) {
    throw new Error(`unexpected health response: ${JSON.stringify(health)}`);
  }

  const tripRequest = JSON.parse(fs.readFileSync("docs/sample_candidate_request.json", "utf8"));
  const plan = await postJson(`${baseUrl}/trip/plan`, tripRequest);
  if (!Array.isArray(plan.candidates) || plan.candidates.length === 0) {
    throw new Error("trip plan did not return candidates");
  }

  const search = await getJson(`${baseUrl}/poi/search?q=${encodeURIComponent("历史文化")}&limit=3`);
  if (!Array.isArray(search.data) || search.data.length === 0) {
    throw new Error("poi search did not return data");
  }

  console.log(`Container smoke passed: ${health.poi_count} POIs, ${health.edge_count} edges, ${plan.candidates.length} candidates.`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
