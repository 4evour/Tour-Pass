const state = {
  candidates: [],
  selectedIndex: 0,
  lastPayload: null,
  activeStage: "overview",
  user: null,
  token: localStorage.getItem("tp_token") || null,
};

let planMap = null;
let routeMap = null;

const DAY_COLORS = ["#146b5d", "#c25b1e", "#2563eb", "#9333ea", "#dc2626", "#0d9488", "#d97706"];

function typeIcon(type) {
  const icons = { attraction: "🏛", restaurant: "🍜", hotel: "🏨", nightlife: "🌙", transit: "🚇" };
  return icons[type] || "📍";
}

function leafletReady() {
  return typeof window.L !== "undefined";
}

function renderMap(candidate) {
  const container = $("mapContainer");
  const mapDiv = $("map");
  if (!leafletReady()) {
    container.hidden = true;
    return;
  }
  if (!candidate || !candidate.days) {
    container.hidden = true;
    return;
  }
  const allCoords = [];
  for (const day of candidate.days) {
    for (const stop of day.stops || []) {
      if (stop.lat && stop.lng) allCoords.push([stop.lat, stop.lng]);
    }
  }
  if (allCoords.length === 0) {
    container.hidden = true;
    return;
  }
  container.hidden = false;
  if (planMap) {
    planMap.remove();
    planMap = null;
  }
  planMap = L.map(mapDiv);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    maxZoom: 18,
  }).addTo(planMap);

  const bounds = [];
  candidate.days.forEach((day, dayIndex) => {
    const color = DAY_COLORS[dayIndex % DAY_COLORS.length];
    const dayCoords = [];
    for (const stop of day.stops || []) {
      if (!stop.lat || !stop.lng) continue;
      const coord = [stop.lat, stop.lng];
      bounds.push(coord);
      dayCoords.push(coord);
      const marker = L.circleMarker(coord, {
        radius: 7, fillColor: color, color: "#fff", weight: 2, fillOpacity: 0.9,
      }).addTo(planMap);
      marker.bindPopup(
        `<strong>${escapeHtml(stop.poi_name)}</strong><br>` +
        `${typeIcon(stop.poi_type)} ${escapeHtml(stop.slot)} ${escapeHtml(stop.start_time)}-${escapeHtml(stop.end_time)}<br>` +
        `${escapeHtml(stop.area)} · 评分 ${stop.score}`
      );
    }
    if (dayCoords.length > 1) {
      L.polyline(dayCoords, { color, weight: 3, opacity: 0.7, dashArray: dayIndex > 0 ? "6 4" : null }).addTo(planMap);
    }
  });
  if (bounds.length > 0) {
    planMap.fitBounds(bounds, { padding: [30, 30] });
  }
  setTimeout(() => planMap.invalidateSize(), 50);
}

function renderRouteMap(route) {
  const mapDiv = $("routeMap");
  if (!leafletReady()) {
    mapDiv.innerHTML = "";
    return;
  }
  if (!route || !route.path_coords || route.path_coords.length === 0) {
    mapDiv.innerHTML = "";
    return;
  }
  if (routeMap) {
    routeMap.remove();
    routeMap = null;
  }
  routeMap = L.map(mapDiv);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    maxZoom: 18,
  }).addTo(routeMap);
  const coords = route.path_coords.map((c) => [c.lat, c.lng]);
  const bounds = [];
  coords.forEach((coord, i) => {
    bounds.push(coord);
    L.circleMarker(coord, {
      radius: i === 0 || i === coords.length - 1 ? 8 : 5,
      fillColor: i === 0 ? "#146b5d" : i === coords.length - 1 ? "#dc2626" : "#65706d",
      color: "#fff", weight: 2, fillOpacity: 0.9,
    }).addTo(routeMap).bindPopup(route.path[i] || `节点 ${i + 1}`);
  });
  if (coords.length > 1) {
    L.polyline(coords, { color: "#146b5d", weight: 3, opacity: 0.8 }).addTo(routeMap);
  }
  if (bounds.length > 0) {
    routeMap.fitBounds(bounds, { padding: [20, 20] });
  }
  setTimeout(() => routeMap.invalidateSize(), 50);
}

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

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
    hotel_location: $("hotelLocation").value.trim() || "7天优品酒店(长沙橘子洲五一广场地铁站店)",
    interests: csv($("interests").value),
    pace: $("pace").value,
    must_visit: csv($("mustVisit").value),
    avoid: ["排队太久"],
    candidate_count: Number($("candidateCount").value || 1),
  };
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json; charset=utf-8" };
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  const response = await fetch(path, { headers, ...options });
  const data = await response.json();
  // Update query remaining from response header
  const remaining = response.headers.get("X-Query-Remaining");
  if (remaining !== null) updateQueryCounter(parseInt(remaining));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth")) {
      logout();
      throw new Error("登录已过期，请重新登录");
    }
    throw new Error(data.error?.message || "请求失败");
  }
  return data;
}

// ---- Auth ----

function updateQueryCounter(remaining) {
  const el = $("queryCounter");
  if (el) el.textContent = remaining !== undefined ? `今日剩余 ${remaining}/10` : "";
}

function showApp() {
  $("authOverlay").hidden = true;
  $("mainApp").hidden = false;
  $("userBadge").textContent = state.user?.username || "";
  updateQueryCounter(state.user?.query_remaining);
  loadHealth();
}

function showAuth() {
  $("authOverlay").hidden = false;
  $("mainApp").hidden = true;
  state.token = null;
  state.user = null;
  localStorage.removeItem("tp_token");
}

function logout() {
  showAuth();
}

async function doLogin() {
  const username = $("authUsername").value.trim();
  const password = $("authPassword").value;
  const errEl = $("authError");
  errEl.hidden = true;
  if (!username || !password) { errEl.textContent = "请输入用户名和密码"; errEl.hidden = false; return; }
  try {
    $("authLoginBtn").disabled = true;
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("tp_token", data.token);
    showApp();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.hidden = false;
  } finally {
    $("authLoginBtn").disabled = false;
  }
}

async function doRegister() {
  const username = $("regUsername").value.trim();
  const password = $("regPassword").value;
  const errEl = $("regError");
  errEl.hidden = true;
  if (!username || !password) { errEl.textContent = "请输入用户名和密码"; errEl.hidden = false; return; }
  try {
    $("authRegisterBtn").disabled = true;
    const data = await api("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("tp_token", data.token);
    showApp();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.hidden = false;
  } finally {
    $("authRegisterBtn").disabled = false;
  }
}

async function checkAuth() {
  if (!state.token) { showAuth(); return; }
  try {
    const data = await api("/auth/me");
    state.user = data;
    showApp();
  } catch {
    showAuth();
  }
}

// ---- Feedback ----

function initFeedback() {
  $("feedbackBtn").addEventListener("click", () => {
    $("feedbackModal").hidden = false;
    $("fbSuccess").hidden = true;
    $("fbError").hidden = true;
  });
  $("fbClose").addEventListener("click", () => { $("feedbackModal").hidden = true; });
  $("fbSubmit").addEventListener("click", async () => {
    const content = $("fbContent").value.trim();
    if (content.length < 10) { $("fbError").textContent = "内容至少10个字"; $("fbError").hidden = false; return; }
    try {
      await api("/feedback", {
        method: "POST",
        body: JSON.stringify({
          category: $("fbCategory").value,
          content,
          contact: $("fbContact").value.trim(),
          page_url: location.href,
        }),
      });
      $("fbSuccess").hidden = false;
      $("fbError").hidden = true;
      $("fbContent").value = "";
      setTimeout(() => { $("feedbackModal").hidden = true; }, 2000);
    } catch (e) {
      $("fbError").textContent = e.message;
      $("fbError").hidden = false;
    }
  });
}

// ---- Easter egg ----

function initEasterEgg() {
  $("easterEgg").addEventListener("click", async () => {
    try {
      const data = await api("/easter-egg");
      showFireworks();
      setTimeout(() => {
        $("easterMessage").textContent = "🎉 " + data.message + " +5 次查询";
        $("easterMessage").hidden = false;
        if (state.user) {
          state.user.query_remaining = (state.user.query_remaining || 0) + 5;
          updateQueryCounter(state.user.query_remaining);
        }
      }, 1500);
      setTimeout(() => {
        $("easterMessage").hidden = true;
        $("fireworksCanvas").hidden = true;
      }, 5000);
    } catch (e) {
      if (e.message.includes("已领取")) {
        $("easterMessage").textContent = "🎁 今日彩蛋已领取，明天再来~";
        $("easterMessage").hidden = false;
        setTimeout(() => { $("easterMessage").hidden = true; }, 3000);
      }
    }
  });
}

function showFireworks() {
  const canvas = $("fireworksCanvas");
  canvas.hidden = false;
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  const ctx = canvas.getContext("2d");
  const particles = [];
  const colors = ["#ff0", "#f0f", "#0ff", "#f00", "#0f0", "#ff6b35", "#146b5d"];

  function burst(x, y) {
    for (let i = 0; i < 40; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 2 + Math.random() * 4;
      particles.push({
        x, y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        life: 60 + Math.random() * 40,
        color: colors[Math.floor(Math.random() * colors.length)],
        size: 2 + Math.random() * 2,
      });
    }
  }

  // Launch several bursts
  const bursts = [
    { x: canvas.width * 0.3, y: canvas.height * 0.3, delay: 0 },
    { x: canvas.width * 0.7, y: canvas.height * 0.25, delay: 300 },
    { x: canvas.width * 0.5, y: canvas.height * 0.4, delay: 600 },
    { x: canvas.width * 0.2, y: canvas.height * 0.5, delay: 900 },
    { x: canvas.width * 0.8, y: canvas.height * 0.45, delay: 1200 },
  ];
  bursts.forEach(b => setTimeout(() => burst(b.x, b.y), b.delay));

  let frame = 0;
  function animate() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.05;
      p.life--;
      if (p.life <= 0) { particles.splice(i, 1); continue; }
      ctx.globalAlpha = Math.min(1, p.life / 30);
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    frame++;
    if (frame < 180 && particles.length > 0) requestAnimationFrame(animate);
    else { ctx.clearRect(0, 0, canvas.width, canvas.height); canvas.hidden = true; }
  }
  requestAnimationFrame(animate);
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
      <strong>${escapeHtml(selected.variant_name) || "推荐方案"}</strong>
      <span>${escapeHtml(selected.days?.[0]?.summary) || "等待生成可解释摘要。"}</span>
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
    <section class="stage-section overview-section" data-plan-section="overview">
      ${renderOverview(candidate)}
    </section>
    <section class="stage-section" data-plan-section="compare">
      ${renderComparisonTable()}
    </section>
    <section class="stage-section" data-plan-section="itinerary">
      ${renderRouteVisual(candidate)}
      ${candidate.days.map(renderDay).join("")}
    </section>
    <section class="stage-section" data-plan-section="debug">
      ${renderAlgorithmDebug(candidate)}
    </section>
  `;
  bindComparisonCards();
  renderMap(candidate);
}

function renderOverview(candidate) {
  const firstDay = candidate.days?.[0] || {};
  const firstStops = (firstDay.stops || []).slice(0, 4);
  const comparison = candidate.comparison || {};
  return `
    <div class="overview-grid">
      <section class="overview-hero" aria-label="推荐方案概览">
        <div class="panel-heading">
          <h2>${escapeHtml(candidate.variant_name) || "推荐方案"}</h2>
          <span>${escapeHtml(strategyLabel(candidate.strategy))}策略 · Pareto L${comparison.pareto_rank || 1}</span>
        </div>
        <p>${escapeHtml(firstDay.summary) || "生成后这里会展示第一天的核心路线摘要。"}</p>
        <div class="plan-kpis" aria-label="方案关键指标">
          <div><strong>${candidate.total_score}</strong><span>综合评分</span></div>
          <div><strong>${candidate.days.length}</strong><span>行程天数</span></div>
          <div><strong>${totalTravel(candidate)}</strong><span>总通勤分钟</span></div>
        </div>
      </section>
      <section class="overview-list" aria-label="讲解重点">
        <div class="panel-heading">
          <h2>演示重点</h2>
          <span>先讲价值，再展开细节</span>
        </div>
        <div class="talk-track">
          <span>候选方案不是简单排序，会解释评分、通勤、风险和必去覆盖之间的取舍。</span>
          <span>路线明细单独展示，避免时间轴和站点列表挤在首页。</span>
          <span>Beam Search、Pareto、BM25 等算法证据放到算法解释页，需要时再展开。</span>
        </div>
      </section>
    </div>
    <section class="overview-stops" aria-label="首日路线预览">
      <div class="panel-heading">
        <h2>首日路线预览</h2>
        <span>${firstDay.total_travel_minutes || 0} 分钟通勤</span>
      </div>
      <div class="route-preview">
        ${firstStops.length ? firstStops.map((stop, index) => `
          <article>
            <span>${index + 1}</span>
            <strong>${escapeHtml(stop.poi_name)}</strong>
            <small>${escapeHtml(stop.start_time)}-${escapeHtml(stop.end_time)} · ${escapeHtml(stop.area)}</small>
          </article>
        `).join("") : `<article><span>0</span><strong>暂无站点</strong><small>请先生成行程</small></article>`}
      </div>
    </section>
  `;
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
            <p>${escapeHtml(comparison.tradeoff_summary) || "暂无多目标解释。"}</p>
            ${(comparison.pareto_debug || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
          </div>
          <h3>多样性指标</h3>
          <div class="diversity-debug">
            <div class="diversity-metrics">
              <span><strong>${formatPercent(comparison.poi_overlap_with_baseline)}</strong>POI 重合</span>
              <span><strong>${formatPercent(comparison.area_overlap_with_baseline)}</strong>区域重合</span>
              <span><strong>${comparison.unique_poi_count ?? 0}</strong>独有 POI</span>
            </div>
            <p>${escapeHtml(comparison.diversity_summary) || "暂无候选多样性说明。"}</p>
            <div class="diversity-tags">
              ${(comparison.diversity_tags || []).map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}
            </div>
            ${(comparison.unique_pois || []).length ? `<div class="unique-pois">${comparison.unique_pois.slice(0, 4).map((poi) => `<code>${escapeHtml(poi)}</code>`).join("")}</div>` : ""}
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
        <strong>${escapeHtml(step.slot)}</strong>
        <span>${step.input_states} 入 · ${step.expanded_states} 展开 · ${step.kept_states} 留</span>
      </div>
      <p>${escapeHtml(step.decision)}</p>
      <div class="beam-state-list">
        ${(step.kept_state_summaries || []).map((item) => `<code>${escapeHtml(item)}</code>`).join("")}
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
            <strong>${escapeHtml(area)}</strong>
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
    <div class="timeline-stop" style="left:${left.toFixed(2)}%;width:${Math.min(width, 100 - left).toFixed(2)}%;" title="${escapeHtml(stop.start_time)}-${escapeHtml(stop.end_time)} ${escapeHtml(stop.poi_name)}">
      <span>${escapeHtml(stop.slot)}</span>
      <strong>${escapeHtml(stop.poi_name)}</strong>
    </div>
  `;
}

function renderComparisonTable() {
  if (state.candidates.length <= 1) {
    return `<div class="empty-state compact-empty">生成多个候选后展示对比。</div>`;
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
      <strong>${escapeHtml(candidate.variant_name) || `候选 ${index + 1}`}</strong>
      <span>策略 ${escapeHtml(strategyLabel(candidate.strategy))}</span>
      <span>Pareto L${metrics.pareto_rank || 1}${metrics.dominated ? " · 被支配" : " · 前沿"}</span>
      <span>评分 ${metrics.total_score ?? candidate.total_score ?? 0}</span>
      <span>通勤 ${metrics.total_travel_minutes ?? totalTravel(candidate)} 分钟</span>
      <span>POI 重合 ${formatPercent(metrics.poi_overlap_with_baseline)}</span>
      <span>独有 ${metrics.unique_poi_count ?? 0} 个</span>
      <span>必去 ${metrics.must_visit_covered ?? 0}/${state.lastPayload?.must_visit?.length || 0}</span>
      <span>风险 ${metrics.open_time_risks ?? 0} · 未安排 ${metrics.unscheduled_count ?? 0}</span>
      <em>${escapeHtml(metrics.tradeoff_summary) || "多目标指标用于解释方案取舍。"}</em>
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
      <p class="day-meta">${escapeHtml(day.summary)}</p>
      <div class="day-metrics" aria-label="当日指标">
        <span>通勤 ${day.total_travel_minutes} 分钟</span>
        <span>游玩 ${day.total_visit_minutes} 分钟</span>
        <span>兴趣分 ${Math.round(day.interest_score || 0)}</span>
        <span class="${day.time_window_feasible ? "ok-chip" : "risk-chip"}">${day.time_window_feasible ? "时间窗可行" : "时间窗风险"}</span>
      </div>
      <div class="insight-strip">
        <strong>${escapeHtml(day.optimization_summary) || "暂无优化摘要"}</strong>
        <span>优化前 ${day.original_travel_minutes || 0} 分钟 · 优化后 ${day.optimized_travel_minutes || day.total_travel_minutes} 分钟</span>
      </div>
      <div class="explain-grid">
        <div>
          <h3>约束命中</h3>
          <div class="explain-list">
            ${(day.constraint_explanations || []).slice(0, 5).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
          </div>
        </div>
        <div>
          <h3>时间窗复核</h3>
          <div class="explain-list ${day.time_window_feasible ? "" : "warn-list"}">
            ${(day.time_window_diagnostics || []).slice(0, 5).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
          </div>
        </div>
        <div>
          <h3>未安排说明</h3>
          <div class="explain-list warn-list">
            ${(day.unscheduled_reasons || []).slice(0, 3).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
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
      <div class="slot">${escapeHtml(stop.slot)}</div>
      <div>
        <div class="stop-title">${escapeHtml(stop.poi_name)}</div>
        <div class="time">${escapeHtml(stop.start_time)}-${escapeHtml(stop.end_time)} · ${escapeHtml(stop.area)} · 通勤 ${stop.travel_minutes_from_previous} 分钟</div>
        <div class="time-window-note">${escapeHtml(timeWindowLabel(stop.time_window_status))} · ${escapeHtml(stop.time_window_reason) || "时间窗复核通过。"}</div>
        <div class="stop-reason">${escapeHtml(stop.reason)}</div>
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
      ${useful.map((item) => `<span title="${escapeHtml(item.reason)}">${escapeHtml(item.label)} ${Number(item.value).toFixed(1)}</span>`).join("")}
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
    updateStageVisibility();
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
  $("hotelLocation").value = "7天优品酒店(长沙橘子洲五一广场地铁站店)";
  $("interests").value = "历史文化, 美食, 夜景";
  $("mustVisit").value = "橘子洲风景名胜区, 湖南省博物馆";
  $("pace").value = "轻松";
}

async function queryRoute() {
  $("routeOutput").textContent = "查询中...";
  try {
    const from = encodeURIComponent($("routeFrom").value.trim());
    const to = encodeURIComponent($("routeTo").value.trim());
    const route = await api(`/route/shortest?from=${from}&to=${to}&algorithm=astar`);
    $("routeOutput").textContent = `${route.algorithm.toUpperCase()} · ${route.travel_minutes} 分钟\n${route.path.join(" -> ")}`;
    renderRouteMap(route);
  } catch (error) {
    $("routeOutput").textContent = `查询失败：${error.message}`;
    renderRouteMap(null);
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
          <strong>${escapeHtml(item.name)}</strong>
          <span>${escapeHtml(item.area)} · ${escapeHtml(item.description)}</span>
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
      <strong>${escapeHtml(item.name)} <small>${Number(item.score || 0).toFixed(1)}</small></strong>
      <span>${escapeHtml(item.area)} · ${escapeHtml(item.score_explanation)}</span>
      <div class="score-breakdown">
        ${contributions.map((part) => `<span title="${escapeHtml(part.reason)}">${escapeHtml(part.label)} ${Number(part.value).toFixed(1)}</span>`).join("")}
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
$("routeButton").addEventListener("click", queryRoute);
$("alternativeButton").addEventListener("click", queryAlternatives);
$("searchButton").addEventListener("click", querySearch);
$("explainButton").addEventListener("click", explainPlan);
$("explainToolButton").addEventListener("click", explainPlan);

function showLoading() {
  $("loadingOverlay").hidden = false;
  $("chatOutput").hidden = true;
  const steps = ["loadStep1", "loadStep2", "loadStep3"];
  steps.forEach(id => { $(id).className = "loading-step"; });
  // Progress through steps
  setTimeout(() => { $(steps[0]).className = "loading-step done"; $(steps[1]).className = "loading-step active"; }, 2000);
  setTimeout(() => { $(steps[1]).className = "loading-step done"; $(steps[2]).className = "loading-step active"; }, 5000);
}
function hideLoading() {
  $("loadingOverlay").hidden = true;
}

async function chatPlan() {
  const message = $("chatInput").value.trim();
  if (!message) return;
  $("chatBtnText").hidden = true;
  $("chatBtnLoading").hidden = false;
  $("chatButton").disabled = true;
  showLoading();
  try {
    const data = await api("/trip/chat", {
      method: "POST",
      body: JSON.stringify({ message, context: [] }),
    });
    hideLoading();
    let html = "";
    if (data.reply) {
      html += `<p>${escHtml(data.reply)}</p>`;
    }
    if (data.suggestions && data.suggestions.length > 0) {
      html += data.suggestions.map(s => `<p style="color:var(--warn);font-size:13px;">⚠️ ${escHtml(s)}</p>`).join("");
    }
    if (data.candidates && data.candidates.length > 0) {
      state.candidates = data.candidates;
      state.selectedIndex = 0;
      state.lastPayload = { candidates: data.candidates };
      renderPlan();
      setStage("overview");
      html += `<p style="font-size:13px;color:var(--muted);">已生成 ${data.candidates.length} 个方案，切换查看详情。</p>`;
    }
    $("chatOutput").innerHTML = html || "规划完成。";
    $("chatOutput").hidden = false;
  } catch (error) {
    hideLoading();
    $("chatOutput").innerHTML = `<p style="color:#c0392b;">${escHtml(error.message)}</p>`;
    $("chatOutput").hidden = false;
  } finally {
    $("chatButton").disabled = false;
    $("chatBtnText").hidden = false;
    $("chatBtnLoading").hidden = true;
  }
}

function escHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

$("chatButton").addEventListener("click", chatPlan);
$("chatInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) chatPlan();
});

function setStage(stage) {
  state.activeStage = stage;
  updateStageVisibility();
}

function updateStageVisibility() {
  document.body.dataset.activeStage = state.activeStage;
  document.querySelectorAll(".stage-tab").forEach((button) => {
    const active = button.dataset.stage === state.activeStage;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  // main panel: visible for overview and itinerary
  // tools/debug panel: visible only for debug
  document.querySelectorAll("[data-stage-panel]").forEach((panel) => {
    if (panel.dataset.stagePanel === "tools") {
      panel.hidden = state.activeStage !== "debug";
    } else {
      panel.hidden = state.activeStage === "debug";
    }
  });
}

document.querySelectorAll(".stage-tab").forEach((button) => {
  button.addEventListener("click", () => setStage(button.dataset.stage));
});

updateStageVisibility();

// City cards
document.querySelectorAll(".city-card").forEach((card) => {
  card.addEventListener("click", () => {
    document.querySelectorAll(".city-card").forEach(c => c.classList.remove("active"));
    card.classList.add("active");
    $("city").value = card.dataset.city;
    // Update hotel default based on city
    if (card.dataset.city === "武汉") {
      $("hotelLocation").value = "7天优品酒店(武汉江汉路步行街店)";
    } else {
      $("hotelLocation").value = "7天优品酒店(长沙橘子洲五一广场地铁站店)";
    }
  });
});

// Interest tags
document.querySelectorAll(".interest-tags .tag").forEach((tag) => {
  tag.addEventListener("click", () => {
    tag.classList.toggle("active");
    const active = [...document.querySelectorAll(".interest-tags .tag.active")].map(t => t.dataset.val);
    $("interests").value = active.join(", ");
  });
});

// Auth event listeners
$("authLoginBtn").addEventListener("click", doLogin);
$("authPassword").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
$("authRegisterBtn").addEventListener("click", doRegister);
$("authShowRegister").addEventListener("click", (e) => { e.preventDefault(); $("authLoginForm").hidden = true; $("authRegisterForm").hidden = false; });
$("authShowLogin").addEventListener("click", (e) => { e.preventDefault(); $("authRegisterForm").hidden = true; $("authLoginForm").hidden = false; });
$("logoutBtn").addEventListener("click", logout);

initFeedback();
initEasterEgg();
checkAuth();

// Load tools data (works without auth since these are read-only)
queryRoute();
queryAlternatives();
querySearch();
