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

async function postJson(url, body, token = "") {
  const headers = { "Content-Type": "application/json; charset=utf-8" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${url} failed with ${response.status}: ${(await response.text()).slice(0, 240)}`);
  }
  return response.json();
}

async function getJson(url, token = "") {
  const headers = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`${url} failed with ${response.status}: ${(await response.text()).slice(0, 240)}`);
  }
  return response.json();
}

async function waitForAgentHealth(baseUrl) {
  let lastError = "";
  for (let i = 0; i < 30; i += 1) {
    try {
      const response = await fetch(`${baseUrl}/agent/health`);
      if (response.ok) {
        return { ok: true, data: await response.json() };
      }
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error.message;
    }
    await sleep(1000);
  }
  return { ok: false, error: lastError };
}

async function main() {
  const baseUrl = process.argv[2] || process.env.TOURPASS_BASE_URL || "http://127.0.0.1:8080";
  const health = await waitForHealth(baseUrl);
  if (health.status !== "ok") {
    throw new Error(`unexpected health response: ${JSON.stringify(health)}`);
  }

  // Agent health check (non-fatal in CI where LLM may not be available)
  const agentHealth = await waitForAgentHealth(baseUrl);
  if (agentHealth.ok) {
    console.log(`Agent health: ${agentHealth.data.agent || "unknown"} v${agentHealth.data.version || "?"}`);
  } else {
    console.warn(`Agent health check failed (non-fatal): ${agentHealth.error}`);
  }

  const auth = await postJson(`${baseUrl}/auth/register`, {
    username: "container_smoke_user",
    password: "container_smoke_password",
  });
  if (!auth.token) {
    throw new Error("auth smoke did not return a token");
  }

  const tripRequest = JSON.parse(fs.readFileSync("docs/sample_candidate_request.json", "utf8"));
  const plan = await postJson(`${baseUrl}/trip/plan`, tripRequest, auth.token);
  if (!Array.isArray(plan.candidates) || plan.candidates.length === 0) {
    throw new Error("trip plan did not return candidates");
  }

  const search = await getJson(`${baseUrl}/poi/search?q=${encodeURIComponent("历史文化")}&limit=3`, auth.token);
  if (!Array.isArray(search.data) || search.data.length === 0) {
    throw new Error("poi search did not return data");
  }

  console.log(`Container smoke passed: ${health.total_poi_count} POIs, ${Object.values(health.cities || {})[0]?.edge_count || 0} edges, ${plan.candidates.length} candidates.`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
