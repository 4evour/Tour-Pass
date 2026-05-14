const state = {
  candidates: [],
  selectedIndex: 0,
};

const $ = (id) => document.getElementById(id);

function csv(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function planPayload() {
  return {
    city: $("city").value.trim() || "长沙",
    days: Number($("days").value || 2),
    start_time: $("startTime").value.trim() || "09:30",
    end_time: $("endTime").value.trim() || "21:30",
    hotel_location: $("hotelLocation").value.trim() || "五一广场酒店",
    interests: csv($("interests").value),
    pace: $("pace").value,
    must_visit: csv($("mustVisit").value),
    avoid: ["排队太久"],
    candidate_count: Number($("candidateCount").value || 1),
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json; charset=utf-8" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error?.message || "请求失败");
  }
  return data;
}

async function loadHealth() {
  try {
    const health = await api("/health");
    $("serviceStatus").textContent = `已连接 · ${health.poi_count} POI`;
    $("serviceStatus").classList.add("ok");
  } catch {
    $("serviceStatus").textContent = "服务未连接";
    $("serviceStatus").classList.remove("ok");
  }
}

function renderTabs() {
  const tabs = $("candidateTabs");
  tabs.innerHTML = "";
  state.candidates.forEach((candidate, index) => {
    const button = document.createElement("button");
    button.className = `tab${index === state.selectedIndex ? " active" : ""}`;
    button.type = "button";
    button.textContent = candidate.variant_name || `候选 ${index + 1}`;
    button.addEventListener("click", () => {
      state.selectedIndex = index;
      renderPlan();
    });
    tabs.appendChild(button);
  });
}

function renderPlan() {
  renderTabs();
  const output = $("planOutput");
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate) {
    output.className = "plan-output empty-state";
    output.textContent = "暂无行程。";
    return;
  }

  output.className = "plan-output";
  output.innerHTML = `
    <div>
      <h2>${candidate.variant_name || "推荐方案"}</h2>
      <p class="day-meta">总评分 ${candidate.total_score} · ${candidate.days.length} 天</p>
    </div>
    ${candidate.days.map(renderDay).join("")}
  `;
}

function renderDay(day) {
  return `
    <section class="day-block">
      <h2>第 ${day.day} 天</h2>
      <p class="day-meta">${day.summary} 通勤 ${day.total_travel_minutes} 分钟，游玩 ${day.total_visit_minutes} 分钟。</p>
      <div class="insight-strip">
        <strong>${day.optimization_summary || "暂无优化摘要"}</strong>
        <span>优化前 ${day.original_travel_minutes || 0} 分钟 · 优化后 ${day.optimized_travel_minutes || day.total_travel_minutes} 分钟</span>
      </div>
      <div class="explain-list">
        ${(day.constraint_explanations || []).slice(0, 4).map((item) => `<span>${item}</span>`).join("")}
        ${(day.unscheduled_reasons || []).slice(0, 2).map((item) => `<span>${item}</span>`).join("")}
      </div>
      <div class="stop-list">
        ${day.stops.map(renderStop).join("")}
      </div>
    </section>
  `;
}

function renderStop(stop) {
  return `
    <article class="stop">
      <div class="slot">${stop.slot}</div>
      <div>
        <div class="stop-title">${stop.poi_name}</div>
        <div class="time">${stop.start_time}-${stop.end_time} · ${stop.area} · 通勤 ${stop.travel_minutes_from_previous} 分钟</div>
        <div class="stop-reason">${stop.reason}</div>
      </div>
      <div class="score">${stop.score}</div>
    </article>
  `;
}

async function generatePlan(event) {
  event.preventDefault();
  $("planOutput").className = "plan-output empty-state";
  $("planOutput").textContent = "正在生成行程...";
  try {
    const data = await api("/trip/plan", {
      method: "POST",
      body: JSON.stringify(planPayload()),
    });
    state.candidates = data.candidates || [data];
    state.selectedIndex = 0;
    renderPlan();
  } catch (error) {
    $("planOutput").textContent = error.message;
  }
}

function loadExample() {
  $("city").value = "长沙";
  $("days").value = "2";
  $("candidateCount").value = "3";
  $("startTime").value = "09:30";
  $("endTime").value = "21:30";
  $("hotelLocation").value = "五一广场酒店";
  $("interests").value = "历史文化, 美食, 夜景";
  $("mustVisit").value = "橘子洲, 湖南博物院";
  $("pace").value = "轻松";
}

async function queryRoute() {
  $("routeOutput").textContent = "查询中...";
  try {
    const from = encodeURIComponent($("routeFrom").value.trim());
    const to = encodeURIComponent($("routeTo").value.trim());
    const route = await api(`/route/shortest?from=${from}&to=${to}&algorithm=astar`);
    $("routeOutput").textContent = `${route.algorithm.toUpperCase()} · ${route.travel_minutes} 分钟\n${route.path.join(" -> ")}`;
  } catch (error) {
    $("routeOutput").textContent = error.message;
  }
}

async function queryAlternatives() {
  $("alternativeOutput").textContent = "查询中...";
  try {
    const data = await api("/trip/alternatives", {
      method: "POST",
      body: JSON.stringify({ scenario: $("scenario").value, limit: 4 }),
    });
    $("alternativeOutput").innerHTML = data.data
      .map((item) => `
        <div class="mini-item">
          <strong>${item.name}</strong>
          <span>${item.area} · ${item.description}</span>
        </div>
      `)
      .join("");
  } catch (error) {
    $("alternativeOutput").textContent = error.message;
  }
}

async function explainPlan() {
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate) {
    $("explainOutput").textContent = "请先生成行程。";
    return;
  }
  $("explainOutput").textContent = "生成解释中...";
  try {
    const data = await api("/itinerary/explain", {
      method: "POST",
      body: JSON.stringify(candidate),
    });
    $("explainOutput").textContent = data.explanation;
  } catch (error) {
    $("explainOutput").textContent = error.message;
  }
}

$("planForm").addEventListener("submit", generatePlan);
$("loadExampleButton").addEventListener("click", loadExample);
$("routeButton").addEventListener("click", queryRoute);
$("alternativeButton").addEventListener("click", queryAlternatives);
$("explainButton").addEventListener("click", explainPlan);

loadHealth();
queryRoute();
queryAlternatives();
