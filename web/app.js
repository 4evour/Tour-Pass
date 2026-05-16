const state = {
  candidates: [],
  selectedIndex: 0,
  lastPayload: null,
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
    $("serviceStatus").textContent = `已连接 · ${health.poi_count} POI · ${health.llm_configured ? "LLM 已配置" : "模板兜底"}`;
    $("serviceStatus").classList.add("ok");
  } catch {
    $("serviceStatus").textContent = "服务未连接";
    $("serviceStatus").classList.remove("ok");
  }
}

function renderTabs() {
  const tabs = $("candidateTabs");
  tabs.innerHTML = "";
  $("candidateSummary").innerHTML = "";
  if (!state.candidates.length) {
    return;
  }
  const selected = state.candidates[state.selectedIndex];
  $("candidateSummary").innerHTML = `
    <div>
      <strong>${selected.variant_name || "推荐方案"}</strong>
      <span>${selected.days?.[0]?.summary || "等待生成可解释摘要。"}</span>
    </div>
    <div class="metric-row">
      <span>评分 ${selected.total_score ?? 0}</span>
      <span>${selected.days?.length || 0} 天</span>
      <span>${totalTravel(selected)} 分钟通勤</span>
    </div>
  `;
  state.candidates.forEach((candidate, index) => {
    const button = document.createElement("button");
    button.className = `tab${index === state.selectedIndex ? " active" : ""}`;
    button.type = "button";
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", index === state.selectedIndex ? "true" : "false");
    button.textContent = candidate.variant_name || `候选 ${index + 1}`;
    button.addEventListener("click", () => {
      state.selectedIndex = index;
      renderPlan();
    });
    tabs.appendChild(button);
  });
}

function totalTravel(candidate) {
  return (candidate.days || []).reduce((sum, day) => sum + Number(day.total_travel_minutes || 0), 0);
}

function timeToMinutes(value) {
  const [hour, minute] = String(value || "00:00").split(":").map(Number);
  return hour * 60 + minute;
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
    ${renderComparisonTable()}
    <div class="plan-kpis" aria-label="方案关键指标">
      <div><strong>${candidate.total_score}</strong><span>综合评分</span></div>
      <div><strong>${candidate.days.length}</strong><span>行程天数</span></div>
      <div><strong>${totalTravel(candidate)}</strong><span>总通勤分钟</span></div>
    </div>
    ${renderAlgorithmDebug(candidate)}
    ${renderRouteVisual(candidate)}
    ${candidate.days.map(renderDay).join("")}
  `;
  bindComparisonCards();
}

function renderAlgorithmDebug(candidate) {
  const comparison = candidate.comparison || {};
  const firstDay = candidate.days?.[0] || {};
  const beamTrace = firstDay.beam_trace || [];
  return `
    <section class="debug-panel" aria-label="算法调试输出">
      <div class="section-heading">
        <h2>算法调试</h2>
        <span>展示 Beam Search、Pareto 和候选多样性的可解释中间结果</span>
      </div>
      <div class="debug-grid">
        <div>
          <h3>Beam Search 保留状态</h3>
          <div class="beam-steps">
            ${beamTrace.length ? beamTrace.map(renderBeamStep).join("") : `<div class="debug-empty">暂无 Beam Trace</div>`}
          </div>
        </div>
        <div>
          <h3>Pareto 分层依据</h3>
          <div class="pareto-debug">
            <strong>L${comparison.pareto_rank || 1} · ${comparison.dominated ? "被支配候选" : "非支配前沿"}</strong>
            <p>${comparison.tradeoff_summary || "暂无多目标解释。"}</p>
            ${(comparison.pareto_debug || []).map((item) => `<span>${item}</span>`).join("")}
          </div>
          <h3>多样性指标</h3>
          <div class="diversity-debug">
            <div class="diversity-metrics">
              <span><strong>${formatPercent(comparison.poi_overlap_with_baseline)}</strong>POI 重合</span>
              <span><strong>${formatPercent(comparison.area_overlap_with_baseline)}</strong>区域重合</span>
              <span><strong>${comparison.unique_poi_count ?? 0}</strong>独有 POI</span>
            </div>
            <p>${comparison.diversity_summary || "暂无候选多样性说明。"}</p>
            <div class="diversity-tags">
              ${(comparison.diversity_tags || []).map((tag) => `<span>${tag}</span>`).join("")}
            </div>
            ${(comparison.unique_pois || []).length ? `<div class="unique-pois">${comparison.unique_pois.slice(0, 4).map((poi) => `<code>${poi}</code>`).join("")}</div>` : ""}
          </div>
        </div>
      </div>
    </section>
  `;
}

function renderBeamStep(step) {
  return `
    <article class="beam-step">
      <div>
        <strong>${step.slot}</strong>
        <span>${step.input_states} 入 · ${step.expanded_states} 展开 · ${step.kept_states} 留</span>
      </div>
      <p>${step.decision}</p>
      <div class="beam-state-list">
        ${(step.kept_state_summaries || []).map((item) => `<code>${item}</code>`).join("")}
      </div>
    </article>
  `;
}

function renderRouteVisual(candidate) {
  const days = candidate.days || [];
  const areas = [];
  for (const day of days) {
    for (const stop of day.stops || []) {
      if (stop.area && areas[areas.length - 1] !== stop.area) {
        areas.push(stop.area);
      }
    }
  }
  const routeAreas = areas.slice(0, 8);
  return `
    <section class="visual-panel" aria-label="路线与时间轴">
      <div class="section-heading">
        <h2>路线与时间轴</h2>
        <span>按区域移动和每日时间窗展示路线结构</span>
      </div>
      <div class="route-strip" aria-label="区域路线">
        ${routeAreas.length ? routeAreas.map((area, index) => `
          <div class="route-node">
            <span>${index + 1}</span>
            <strong>${area}</strong>
          </div>
        `).join("") : `<div class="route-node"><span>0</span><strong>暂无路线</strong></div>`}
      </div>
      <div class="timeline-grid">
        ${days.map(renderTimelineDay).join("")}
      </div>
    </section>
  `;
}

function renderTimelineDay(day) {
  const stops = day.stops || [];
  const start = Math.min(...stops.map((stop) => timeToMinutes(stop.start_time)), 9 * 60);
  const end = Math.max(...stops.map((stop) => timeToMinutes(stop.end_time)), 21 * 60);
  const span = Math.max(1, end - start);
  return `
    <article class="timeline-day">
      <div class="timeline-title">
        <strong>第 ${day.day} 天</strong>
        <span>${day.total_travel_minutes || 0} 分钟通勤</span>
      </div>
      <div class="timeline-track" aria-label="第 ${day.day} 天时间轴">
        ${stops.map((stop) => renderTimelineStop(stop, start, span)).join("")}
      </div>
    </article>
  `;
}

function renderTimelineStop(stop, start, span) {
  const left = Math.max(0, ((timeToMinutes(stop.start_time) - start) / span) * 100);
  const width = Math.max(7, ((timeToMinutes(stop.end_time) - timeToMinutes(stop.start_time)) / span) * 100);
  return `
    <div class="timeline-stop" style="left:${left.toFixed(2)}%;width:${Math.min(width, 100 - left).toFixed(2)}%;" title="${stop.start_time}-${stop.end_time} ${stop.poi_name}">
      <span>${stop.slot}</span>
      <strong>${stop.poi_name}</strong>
    </div>
  `;
}

function renderComparisonTable() {
  if (state.candidates.length <= 1) {
    return "";
  }
  return `
    <section class="comparison-panel" aria-label="候选方案对比">
      <div class="section-heading">
        <h2>候选对比</h2>
        <span>多目标指标用于解释方案取舍</span>
      </div>
      <div class="comparison-grid">
        ${state.candidates.map((candidate, index) => renderComparisonCard(candidate, index)).join("")}
      </div>
    </section>
  `;
}

function renderComparisonCard(candidate, index) {
  const metrics = candidate.comparison || {};
  return `
    <button class="comparison-card${index === state.selectedIndex ? " active" : ""}" type="button" data-candidate-index="${index}">
      <strong>${candidate.variant_name || `候选 ${index + 1}`}</strong>
      <span>策略 ${strategyLabel(candidate.strategy)}</span>
      <span>Pareto L${metrics.pareto_rank || 1}${metrics.dominated ? " · 被支配" : " · 前沿"}</span>
      <span>评分 ${metrics.total_score ?? candidate.total_score ?? 0}</span>
      <span>通勤 ${metrics.total_travel_minutes ?? totalTravel(candidate)} 分钟</span>
      <span>POI 重合 ${formatPercent(metrics.poi_overlap_with_baseline)}</span>
      <span>独有 ${metrics.unique_poi_count ?? 0} 个</span>
      <span>必去 ${metrics.must_visit_covered ?? 0}/${state.lastPayload?.must_visit?.length || 0}</span>
      <span>风险 ${metrics.open_time_risks ?? 0} · 未安排 ${metrics.unscheduled_count ?? 0}</span>
      <em>${metrics.tradeoff_summary || "多目标指标用于解释方案取舍。"}</em>
    </button>
  `;
}

function strategyLabel(strategy) {
  const labels = {
    low_travel: "少走路",
    compact: "紧凑",
    culture: "文化",
    food: "美食",
    rainy: "雨天",
    balanced: "平衡",
  };
  return labels[strategy] || strategy || "平衡";
}

function formatPercent(value) {
  if (typeof value !== "number") {
    return "--";
  }
  return `${Math.round(value * 100)}%`;
}

function bindComparisonCards() {
  document.querySelectorAll("[data-candidate-index]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedIndex = Number(button.getAttribute("data-candidate-index"));
      renderPlan();
    });
  });
}

function renderDay(day) {
  return `
    <section class="day-block">
      <h2>第 ${day.day} 天</h2>
      <p class="day-meta">${day.summary}</p>
      <div class="day-metrics" aria-label="当日指标">
        <span>通勤 ${day.total_travel_minutes} 分钟</span>
        <span>游玩 ${day.total_visit_minutes} 分钟</span>
        <span>兴趣分 ${Math.round(day.interest_score || 0)}</span>
        <span class="${day.time_window_feasible ? "ok-chip" : "risk-chip"}">${day.time_window_feasible ? "时间窗可行" : "时间窗风险"}</span>
      </div>
      <div class="insight-strip">
        <strong>${day.optimization_summary || "暂无优化摘要"}</strong>
        <span>优化前 ${day.original_travel_minutes || 0} 分钟 · 优化后 ${day.optimized_travel_minutes || day.total_travel_minutes} 分钟</span>
      </div>
      <div class="explain-grid">
        <div>
          <h3>约束命中</h3>
          <div class="explain-list">
            ${(day.constraint_explanations || []).slice(0, 5).map((item) => `<span>${item}</span>`).join("")}
          </div>
        </div>
        <div>
          <h3>时间窗复核</h3>
          <div class="explain-list ${day.time_window_feasible ? "" : "warn-list"}">
            ${(day.time_window_diagnostics || []).slice(0, 5).map((item) => `<span>${item}</span>`).join("")}
          </div>
        </div>
        <div>
          <h3>未安排说明</h3>
          <div class="explain-list warn-list">
            ${(day.unscheduled_reasons || []).slice(0, 3).map((item) => `<span>${item}</span>`).join("")}
          </div>
        </div>
      </div>
      <div class="stop-list">
        ${day.stops.map(renderStop).join("")}
      </div>
    </section>
  `;
}

function renderStop(stop) {
  return `
    <article class="stop ${stop.time_window_status && stop.time_window_status !== "ok" ? "stop-risk" : ""}">
      <div class="slot">${stop.slot}</div>
      <div>
        <div class="stop-title">${stop.poi_name}</div>
        <div class="time">${stop.start_time}-${stop.end_time} · ${stop.area} · 通勤 ${stop.travel_minutes_from_previous} 分钟</div>
        <div class="time-window-note">${timeWindowLabel(stop.time_window_status)} · ${stop.time_window_reason || "时间窗复核通过。"}</div>
        <div class="stop-reason">${stop.reason}</div>
        ${renderScoreBreakdown(stop.score_breakdown || [])}
      </div>
      <div class="score">${stop.score}</div>
    </article>
  `;
}

function timeWindowLabel(status) {
  const labels = {
    ok: "可行",
    wait: "需等待",
    closed: "闭馆风险",
    meal_window: "餐饮窗口风险",
    sequence: "顺序风险",
    day_end: "超出当日",
    missing_poi: "数据缺失",
  };
  return labels[status] || "时间窗";
}

function renderScoreBreakdown(breakdown) {
  const useful = breakdown
    .filter((item) => Math.abs(Number(item.value || 0)) > 0.01)
    .slice(0, 4);
  if (!useful.length) {
    return "";
  }
  return `
    <div class="score-breakdown" aria-label="评分拆解">
      ${useful.map((item) => `<span title="${item.reason || ""}">${item.label} ${Number(item.value).toFixed(1)}</span>`).join("")}
    </div>
  `;
}

async function generatePlan(event) {
  event.preventDefault();
  const payload = planPayload();
  state.lastPayload = payload;
  $("planOutput").className = "plan-output empty-state";
  $("candidateSummary").innerHTML = "";
  $("candidateTabs").innerHTML = "";
  $("planOutput").textContent = `正在生成 ${payload.candidate_count} 个候选行程...`;
  try {
    const data = await api("/trip/plan", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.candidates = data.candidates || [data];
    state.selectedIndex = 0;
    renderPlan();
  } catch (error) {
    state.candidates = [];
    $("planOutput").className = "plan-output empty-state error-state";
    $("planOutput").textContent = `生成失败：${error.message}`;
  }
}

function loadExample() {
  $("city").value = "长沙";
  $("days").value = "2";
  $("candidateCount").value = "5";
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
    $("routeOutput").textContent = `查询失败：${error.message}`;
  }
}

async function queryAlternatives() {
  $("alternativeOutput").textContent = "查询中...";
  try {
    const data = await api("/trip/alternatives", {
      method: "POST",
      body: JSON.stringify({ scenario: $("scenario").value, limit: 4 }),
    });
    $("alternativeOutput").innerHTML = data.data.length
      ? data.data.map((item) => `
        <div class="mini-item">
          <strong>${item.name}</strong>
          <span>${item.area} · ${item.description}</span>
        </div>
      `)
      .join("")
      : `<div class="mini-item"><strong>暂无结果</strong><span>可以换一个场景或放宽关键词。</span></div>`;
  } catch (error) {
    $("alternativeOutput").textContent = `查询失败：${error.message}`;
  }
}

async function querySearch() {
  $("searchOutput").textContent = "检索中...";
  try {
    const query = encodeURIComponent($("searchQuery").value.trim());
    const type = encodeURIComponent($("searchType").value);
    const data = await api(`/poi/search?q=${query}&type=${type}&limit=4`);
    $("searchOutput").innerHTML = data.data.length
      ? data.data.map(renderSearchResult).join("")
      : `<div class="mini-item"><strong>暂无结果</strong><span>可以换一个关键词或类型。</span></div>`;
  } catch (error) {
    $("searchOutput").textContent = `检索失败：${error.message}`;
  }
}

function renderSearchResult(item) {
  const contributions = (item.score_contributions || [])
    .filter((part) => Math.abs(Number(part.value || 0)) > 0.01)
    .slice(0, 4);
  return `
    <div class="mini-item search-item">
      <strong>${item.name} <small>${Number(item.score || 0).toFixed(1)}</small></strong>
      <span>${item.area} · ${item.score_explanation}</span>
      <div class="score-breakdown">
        ${contributions.map((part) => `<span title="${part.reason || ""}">${part.label} ${Number(part.value).toFixed(1)}</span>`).join("")}
      </div>
    </div>
  `;
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
    $("explainOutput").textContent = `解释失败：${error.message}`;
  }
}

$("planForm").addEventListener("submit", generatePlan);
$("loadExampleButton").addEventListener("click", loadExample);
$("routeButton").addEventListener("click", queryRoute);
$("alternativeButton").addEventListener("click", queryAlternatives);
$("searchButton").addEventListener("click", querySearch);
$("explainButton").addEventListener("click", explainPlan);

loadHealth();
queryRoute();
queryAlternatives();
querySearch();
