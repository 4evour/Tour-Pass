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

function renderOverviewMap(candidate) {
  const mapDiv = $("map");
  if (!leafletReady() || !mapDiv || !candidate?.days) return;
  const allCoords = [];
  for (const day of candidate.days) {
    for (const stop of day.stops || []) {
      if (stop.lat && stop.lng) allCoords.push([stop.lat, stop.lng]);
    }
  }
  if (allCoords.length === 0) return;
  if (planMap) { planMap.remove(); planMap = null; }
  planMap = L.map(mapDiv);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; OSM', maxZoom: 18,
  }).addTo(planMap);
  const bounds = [];
  let stopIndex = 0;
  candidate.days.forEach((day, dayIndex) => {
    const color = DAY_COLORS[dayIndex % DAY_COLORS.length];
    const dayCoords = [];
    for (const stop of day.stops || []) {
      if (!stop.lat || !stop.lng) continue;
      stopIndex++;
      const coord = [stop.lat, stop.lng];
      bounds.push(coord);
      dayCoords.push(coord);
      // Numbered marker
      const icon = L.divIcon({
        className: "numbered-marker",
        html: `<div style="background:${color};color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.3);">${stopIndex}</div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      });
      L.marker(coord, { icon }).addTo(planMap)
        .bindPopup(`<strong>${escapeHtml(stop.poi_name)}</strong><br>${typeIcon(stop.poi_type)} ${stop.start_time}-${stop.end_time}<br>${escapeHtml(stop.area)}`);
    }
    if (dayCoords.length > 1) {
      L.polyline(dayCoords, { color, weight: 3, opacity: 0.7, dashArray: dayIndex > 0 ? "6 4" : null }).addTo(planMap);
    }
  });
  if (bounds.length > 0) planMap.fitBounds(bounds, { padding: [30, 30] });
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
  if (!el) return;
  if (remaining !== undefined) {
    el.textContent = `今日剩余 ${remaining}/10`;
    el.classList.toggle("warning", remaining <= 3);
  } else {
    el.textContent = "";
    el.classList.remove("warning");
  }
}

function showApp() {
  $("authOverlay").hidden = true;
  $("mainApp").hidden = false;
  $("userBadge").textContent = state.user?.username || "";
  updateQueryCounter(state.user?.query_remaining);
  // Show admin link for admin users
  const adminLink = $("adminLink");
  if (adminLink) adminLink.hidden = state.user?.role !== "admin";
  loadHealth();
  renderHotRecommendations();
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
    <section class="stage-section" data-plan-section="itinerary">
      ${candidate.days.map(renderDay).join("")}
    </section>
    <section class="stage-section" data-plan-section="debug">
      ${renderComparisonTable()}
      ${renderAlgorithmDebug(candidate)}
    </section>
  `;
  bindComparisonCards();
  $("mapContainer").hidden = true;
  renderOverviewMap(candidate);
  initDragDrop();
  // Fetch weather asynchronously
  const city = state.lastPayload?.city || "长沙";
  fetchWeather(city).then(weather => {
    const bar = $("weatherBar");
    if (bar && weather) bar.innerHTML = renderWeatherBar(weather, candidate.days || []);
  });
  // Fetch guidebook
  loadGuidebook(city);
}

// ---- Drag & Drop itinerary editing ----
let dragState = { dayIndex: -1, stopIndex: -1, el: null };

function initDragDrop() {
  document.querySelectorAll(".stop-card[draggable]").forEach(card => {
    card.addEventListener("dragstart", (e) => {
      const stopList = card.closest(".stop-list");
      const dayBlock = card.closest(".day-block");
      const dayIdx = [...document.querySelectorAll(".day-block")].indexOf(dayBlock);
      const stopIdx = [...stopList.querySelectorAll(".stop-card")].indexOf(card);
      dragState = { dayIndex: dayIdx, stopIndex: stopIdx, el: card };
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", "");
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      document.querySelectorAll(".drag-over").forEach(el => el.classList.remove("drag-over"));
      dragState = { dayIndex: -1, stopIndex: -1, el: null };
    });
  });

  document.querySelectorAll(".stop-list").forEach(list => {
    list.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      const afterEl = getDragAfterElement(list, e.clientY);
      const cards = list.querySelectorAll(".stop-card");
      cards.forEach(c => c.classList.remove("drag-over"));
      if (afterEl) afterEl.classList.add("drag-over");
    });

    list.addEventListener("drop", (e) => {
      e.preventDefault();
      document.querySelectorAll(".drag-over").forEach(el => el.classList.remove("drag-over"));
      if (dragState.dayIndex < 0) return;

      const targetDayBlock = list.closest(".day-block");
      const targetDayIdx = [...document.querySelectorAll(".day-block")].indexOf(targetDayBlock);
      const afterEl = getDragAfterElement(list, e.clientY);
      let targetStopIdx = afterEl
        ? [...list.querySelectorAll(".stop-card")].indexOf(afterEl)
        : list.querySelectorAll(".stop-card").length;

      moveStop(dragState.dayIndex, dragState.stopIndex, targetDayIdx, targetStopIdx);
    });
  });
}

function getDragAfterElement(list, y) {
  const cards = [...list.querySelectorAll(".stop-card:not(.dragging)")];
  return cards.reduce((closest, child) => {
    const box = child.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closest.offset) return { offset, element: child };
    return closest;
  }, { offset: Number.NEGATIVE_INFINITY }).element;
}

function moveStop(fromDay, fromStop, toDay, toStop) {
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate?.days) return;
  const srcDay = candidate.days[fromDay];
  const dstDay = candidate.days[toDay];
  if (!srcDay?.stops || !dstDay?.stops) return;
  if (fromDay === toDay && fromStop === toStop) return;

  // Remove from source
  const [moved] = srcDay.stops.splice(fromStop, 1);
  // Adjust target index if same day and moving down
  if (fromDay === toDay && fromStop < toStop) toStop--;
  // Insert at target
  dstDay.stops.splice(toStop, 0, moved);

  // Recalculate times for affected days
  recalcDayTimes(dstDay);
  if (fromDay !== toDay) recalcDayTimes(srcDay);

  // Re-render
  renderPlan();
}

function recalcDayTimes(day) {
  if (!day?.stops?.length) return;
  let currentMin = 9 * 60; // Start at 09:00
  day.stops.forEach((stop, i) => {
    const travel = i === 0 ? 0 : (stop.travel_minutes_from_previous || 10);
    currentMin += travel;
    const visit = stop.visit_duration_minutes || 60;
    stop.start_time = minToTime(currentMin);
    currentMin += visit;
    stop.end_time = minToTime(currentMin);
  });
  day.total_travel_minutes = day.stops.reduce((s, st) => s + (st.travel_minutes_from_previous || 0), 0);
}

function minToTime(min) {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function transportIcon(minutes) {
  if (minutes <= 0) return "";
  if (minutes <= 15) return "🚶";
  if (minutes <= 30) return "🚌";
  return "🚕";
}

function estimateCost(priceLevel) {
  const map = { 1: [30, 80], 2: [60, 150], 3: [120, 300] };
  const [lo, hi] = map[priceLevel] || [30, 80];
  return { lo, hi };
}

function estimateDayCost(stops) {
  let totalLo = 0, totalHi = 0;
  for (const stop of stops) {
    const type = stop.poi_type || "";
    if (type === "attraction") { totalLo += 20; totalHi += 80; }
    else if (type === "restaurant") { totalLo += 30; totalHi += 100; }
    else if (type === "nightlife") { totalLo += 50; totalHi += 150; }
  }
  // Add transport estimate
  const travelMin = stops.reduce((s, st) => s + (st.travel_minutes_from_previous || 0), 0);
  totalLo += Math.round(travelMin * 0.5);
  totalHi += Math.round(travelMin * 2);
  return { lo: totalLo, hi: totalHi };
}

function renderOverview(candidate) {
  const days = candidate.days || [];
  const totalLo = days.reduce((s, d) => s + estimateDayCost(d.stops || []).lo, 0);
  const totalHi = days.reduce((s, d) => s + estimateDayCost(d.stops || []).hi, 0);
  const totalStops = days.reduce((s, d) => s + (d.stops || []).length, 0);
  const totalTravel = days.reduce((s, d) => s + (d.total_travel_minutes || 0), 0);

  // Build multi-day summary
  const summaries = days.map(d => d.summary).filter(Boolean);
  const highlights = summaries.length > 1
    ? summaries.map((s, i) => `<p><strong>Day ${i + 1}：</strong>${escapeHtml(s.substring(0, 80))}${s.length > 80 ? "..." : ""}</p>`).join("")
    : `<p>${escapeHtml(summaries[0] || "")}</p>`;

  return `
    <div id="weatherBar"></div>
    <div id="guidebookSection"></div>
    <div class="overview-top-bar">
      <div class="overview-stat"><strong>${days.length}</strong><span>天</span></div>
      <div class="overview-stat"><strong>${totalStops}</strong><span>站</span></div>
      <div class="overview-stat"><strong>${totalTravel}</strong><span>分钟通勤</span></div>
      <div class="overview-stat accent"><strong>¥${totalLo}-${totalHi}</strong><span>预估花费</span></div>
    </div>
    <div class="overview-dual">
      <div class="overview-map-col">
        <div id="overviewMapWrap" class="overview-map-wrap">
          <div id="map"></div>
        </div>
        <div class="map-legend">
          ${days.map((d, i) => `<span><span class="legend-dot" style="background:${DAY_COLORS[i % DAY_COLORS.length]}"></span>Day ${d.day}</span>`).join("")}
        </div>
      </div>
      <div class="overview-cards-col">
        <div class="overview-highlights">${highlights}</div>
        <div class="day-cards">
          ${days.map((day) => {
            const stops = day.stops || [];
            const cost = estimateDayCost(stops);
            const actual = getActualCost(day.day);
            return `
            <div class="day-card">
              <div class="day-card-header">
                <strong>Day ${day.day}</strong>
                <span class="day-card-stats">${stops.length} 站 · ≈¥${cost.lo}-${cost.hi}${actual ? ` · 实际 ¥${actual}` : ""}</span>
              </div>
              <div class="day-card-timeline">
                ${stops.map((stop, j) => `
                  <div class="day-card-stop">
                    <span class="stop-icon">${typeIcon(stop.poi_type)}</span>
                    <span class="stop-time">${stop.start_time || ""}</span>
                    <span class="stop-name">${escapeHtml(stop.poi_name)}</span>
                    ${j > 0 && stop.travel_minutes_from_previous ? `<span class="stop-transport">${transportIcon(stop.travel_minutes_from_previous)} ${stop.travel_minutes_from_previous}min</span>` : ""}
                  </div>
                `).join("")}
              </div>
              <div class="day-cost-track">
                <input type="number" class="cost-input" placeholder="记录实际花费 ¥" value="${actual || ""}" data-day="${day.day}" />
                <span class="cost-estimate">预估 ¥${cost.lo}-${cost.hi}</span>
              </div>
            </div>`;
          }).join("")}
        </div>
      </div>
    </div>
    <div class="overview-actions">
      <button class="primary-action small" id="saveTripBtn" type="button">💾 保存行程</button>
      <button class="secondary-action small" id="shareTripBtn" type="button">🔗 分享</button>
      <button class="secondary-action small" id="exportBtn" type="button">🖨️ 导出/打印</button>
    </div>
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
  const cost = estimateDayCost(day.stops || []);
  return `
    <section class="day-block">
      <div class="day-header">
        <h2>第 ${day.day} 天</h2>
        <div class="day-stats">
          <span>🚶 ${day.total_travel_minutes || 0}min 通勤</span>
          <span>⏱️ ${day.total_visit_minutes || 0}min 游玩</span>
          <span>💰 ≈¥${cost.lo}-${cost.hi}</span>
          <span class="${day.time_window_feasible ? "ok-chip" : "risk-chip"}">${day.time_window_feasible ? "✅ 可行" : "⚠️ 注意"}</span>
        </div>
      </div>
      <p class="day-meta">${escapeHtml(day.summary)}</p>
      <div class="stop-list">
        ${day.stops.map(renderStop).join("")}
      </div>
      <!-- Technical details (collapsed) -->
      <details class="day-tech-details">
        <summary>🔧 算法详情</summary>
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
      </details>
    </section>
  `;
}

function poiImageUrl(name, type) {
  const typeMap = { attraction: "landmark", restaurant: "food", hotel: "hotel building", nightlife: "nightlife city" };
  const q = encodeURIComponent((name || "").split("(")[0].split("（")[0] + " " + (typeMap[type] || "travel"));
  return `https://source.unsplash.com/200x200/?${q}`;
}

function renderStop(stop) {
  const travel = stop.travel_minutes_from_previous || 0;
  const hasRisk = stop.time_window_status && stop.time_window_status !== "ok";
  const imgUrl = poiImageUrl(stop.poi_name, stop.poi_type);
  return `
    <article class="stop-card ${hasRisk ? "stop-risk" : ""}" draggable="true" data-poi-id="${stop.poi_id || ""}">
      ${travel > 0 ? `<div class="stop-transport-bar">${transportIcon(travel)} ${travel} 分钟</div>` : ""}
      <div class="stop-main">
        <img class="stop-poi-img" src="${imgUrl}" alt="" loading="lazy" onerror="this.style.display='none'" />
        <span class="stop-type-icon">${typeIcon(stop.poi_type)}</span>
        <div class="stop-info">
          <div class="stop-name-line">
            <strong>${escapeHtml(stop.poi_name)}</strong>
            <span class="stop-time-badge">${escapeHtml(stop.start_time)}-${escapeHtml(stop.end_time)}</span>
          </div>
          <div class="stop-meta">${escapeHtml(stop.area)}${hasRisk ? ` · ⚠️ ${escapeHtml(timeWindowLabel(stop.time_window_status))}` : ""}</div>
          <div class="stop-reason">${escapeHtml(stop.reason) || ""}</div>
          ${stop.recommendation ? `<div class="stop-tip">💡 ${escapeHtml(stop.recommendation)}</div>` : ""}
        </div>
      </div>
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
    // Load guidebook for selected city
    loadGuidebook(card.dataset.city);
    // Update hotel default
    const hotelDefaults = {
      "长沙": "7天优品酒店(长沙橘子洲五一广场地铁站店)",
      "武汉": "7天优品酒店(武汉江汉路步行街店)",
      "大理": "大理古城客栈",
      "丽江": "丽江古城民宿",
      "南京": "新街口附近酒店",
      "苏州": "观前街附近酒店",
    };
    $("hotelLocation").value = hotelDefaults[card.dataset.city] || "";
  });
});
// Load default city guidebook on page load
setTimeout(() => loadGuidebook("长沙"), 1000);

// Interest tags
document.querySelectorAll(".interest-tags .tag").forEach((tag) => {
  tag.addEventListener("click", () => {
    tag.classList.toggle("active");
    const active = [...document.querySelectorAll(".interest-tags .tag.active")].map(t => t.dataset.val);
    $("interests").value = active.join(", ");
  });
});

// Hotel picker
let allHotels = [];
async function loadHotels() {
  try {
    const data = await api("/poi/search?type=hotel&limit=100");
    allHotels = data.data || [];
    renderHotelList(allHotels);
  } catch {}
}
function renderHotelList(hotels) {
  $("hotelList").innerHTML = hotels.map(h => `
    <div class="hotel-item" data-id="${h.id}" data-name="${escapeHtml(h.name)}">
      <strong>${escapeHtml(h.name)}</strong>
      <span>${escapeHtml(h.area || "")} · ⭐ ${(h.popularity || 0).toFixed(1)}</span>
    </div>
  `).join("") || '<div class="hotel-item"><span>暂无酒店数据</span></div>';
  document.querySelectorAll(".hotel-item").forEach(item => {
    item.addEventListener("click", () => {
      $("hotelLocation").value = item.dataset.name;
      $("hotelDropdown").hidden = true;
    });
  });
}
$("hotelLocation").addEventListener("click", async () => {
  $("hotelDropdown").hidden = !$("hotelDropdown").hidden;
  if (!$("hotelDropdown").hidden && allHotels.length === 0) await loadHotels();
});
$("hotelSearch")?.addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase();
  renderHotelList(allHotels.filter(h => h.name.toLowerCase().includes(q) || (h.area || "").toLowerCase().includes(q)));
});
document.addEventListener("click", (e) => {
  if (!e.target.closest(".hotel-picker-wrap")) $("hotelDropdown").hidden = true;
});

// Save / Share trip
async function saveTrip() {
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate) return;
  try {
    await api("/trips/save", {
      method: "POST",
      body: JSON.stringify({
        title: `${candidate.variant_name || "行程"} ${candidate.days?.length || 0}天`,
        request: state.lastPayload,
        response: candidate,
      }),
    });
    alert("行程已保存！");
  } catch (e) { alert("保存失败：" + e.message); }
}
async function shareTrip() {
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate) return;
  try {
    // Save first, then share
    await api("/trips/save", {
      method: "POST",
      body: JSON.stringify({
        title: `${candidate.variant_name || "行程"} ${candidate.days?.length || 0}天`,
        request: state.lastPayload,
        response: candidate,
      }),
    });
    // Get the latest trip and share it
    const trips = await api("/trips/list");
    if (trips.data && trips.data.length > 0) {
      const tripId = trips.data[0].id;
      const shareData = await api(`/trips/${tripId}/share`, { method: "POST" });
      const url = location.origin + shareData.share_url;
      await navigator.clipboard.writeText(url);
      alert("分享链接已复制到剪贴板：\n" + url);
    }
  } catch (e) { alert("分享失败：" + e.message); }
}

// ---- Itinerary templates ----
const TEMPLATES = [
  { city: "长沙", days: 2, icon: "🏙️", name: "长沙文化之旅", theme: "历史文化",
    msg: "2天长沙行，想去橘子洲和岳麓山，喜欢历史文化", spots: "橘子洲 · 岳麓山 · 湖南省博物馆" },
  { city: "长沙", days: 2, icon: "🍜", name: "长沙美食探索", theme: "美食",
    msg: "2天长沙行，主要吃美食，不要太累", spots: "坡子街 · 太平街 · 文和友" },
  { city: "长沙", days: 3, icon: "🌙", name: "长沙深度游", theme: "文化+美食+夜景",
    msg: "3天长沙行，想去橘子洲、岳麓山、湖南省博物馆，也要吃地道美食，看夜景", spots: "橘子洲 · 岳麓山 · 博物馆 · 解放西" },
  { city: "武汉", days: 2, icon: "🌉", name: "武汉经典游", theme: "历史文化+美食",
    msg: "2天武汉行，想去黄鹤楼和户部巷，尝热干面", spots: "黄鹤楼 · 户部巷 · 东湖" },
  { city: "大理", days: 3, icon: "🏔️", name: "大理风光游", theme: "自然风光+文化",
    msg: "3天大理行，想去洱海和古城，喜欢自然风光", spots: "洱海 · 大理古城 · 崇圣寺三塔" },
  { city: "丽江", days: 3, icon: "🏘️", name: "丽江古城游", theme: "古镇+自然",
    msg: "3天丽江行，想去古城和玉龙雪山", spots: "丽江古城 · 玉龙雪山 · 束河古镇" },
  { city: "南京", days: 2, icon: "🏛️", name: "南京历史游", theme: "历史文化",
    msg: "2天南京行，想去中山陵和夫子庙，喜欢历史文化", spots: "中山陵 · 夫子庙 · 明孝陵" },
  { city: "苏州", days: 2, icon: "🏡", name: "苏州园林游", theme: "园林+古镇",
    msg: "2天苏州行，想去拙政园和虎丘，看看江南园林", spots: "拙政园 · 虎丘 · 平江路" },
];

function renderHotRecommendations() {
  const output = $("planOutput");
  output.className = "plan-output";
  output.innerHTML = `
    <div class="hot-recs">
      <h3>🔥 热门行程模板</h3>
      <p class="hot-rec-subtitle">选择一个模板快速开始，或在上方聊天框描述你的旅行计划</p>
      <div class="hot-rec-grid">
        ${TEMPLATES.map((t, i) => `
          <button class="hot-rec-card" type="button" data-index="${i}">
            <div class="hot-rec-icon">${t.icon}</div>
            <div class="hot-rec-info">
              <strong>${t.city} ${t.days}日 · ${t.name}</strong>
              <span class="hot-rec-theme">${t.theme}</span>
              <span class="hot-rec-spots">${t.spots}</span>
            </div>
          </button>
        `).join("")}
      </div>
    </div>
  `;
  document.querySelectorAll(".hot-rec-card").forEach(card => {
    card.addEventListener("click", () => {
      const tpl = TEMPLATES[parseInt(card.dataset.index)];
      if (!tpl) return;
      // Auto-fill form
      $("city").value = tpl.city;
      $("days").value = tpl.days;
      // Update city cards
      document.querySelectorAll(".city-card").forEach(c => {
        c.classList.toggle("active", c.dataset.city === tpl.city);
      });
      // Set chat input and trigger
      $("chatInput").value = tpl.msg;
      chatPlan();
    });
  });
}

// ---- Dark mode ----
function initTheme() {
  const saved = localStorage.getItem("tp_theme");
  if (saved) document.documentElement.dataset.theme = saved;
  else if (window.matchMedia("(prefers-color-scheme: dark)").matches) document.documentElement.dataset.theme = "dark";
  updateThemeIcon();
}
function toggleTheme() {
  const current = document.documentElement.dataset.theme;
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("tp_theme", next);
  updateThemeIcon();
}
function updateThemeIcon() {
  const btn = $("themeToggle");
  if (btn) btn.textContent = document.documentElement.dataset.theme === "dark" ? "☀️" : "🌙";
}
$("themeToggle")?.addEventListener("click", toggleTheme);
initTheme();

// Event delegation for dynamically rendered buttons
document.addEventListener("click", (e) => {
  if (e.target.id === "saveTripBtn" || e.target.closest?.("#saveTripBtn")) saveTrip();
  if (e.target.id === "shareTripBtn" || e.target.closest?.("#shareTripBtn")) shareTrip();
  if (e.target.id === "exportBtn" || e.target.closest?.("#exportBtn")) exportTrip();
});

function exportTrip() {
  setStage("overview");
  setTimeout(() => window.print(), 300);
}

// ---- Cost tracking (localStorage) ----
function getCostKey() {
  const city = state.lastPayload?.city || "unknown";
  const days = state.lastPayload?.days || 0;
  return `tp_cost_${city}_${days}d`;
}
function getActualCost(day) {
  try { const d = JSON.parse(localStorage.getItem(getCostKey()) || "{}"); return d[day] || 0; } catch { return 0; }
}
function setActualCost(day, amount) {
  try { const d = JSON.parse(localStorage.getItem(getCostKey()) || "{}"); d[day] = amount; localStorage.setItem(getCostKey(), JSON.stringify(d)); } catch {}
}
// Event delegation for cost inputs
document.addEventListener("change", (e) => {
  if (e.target.classList.contains("cost-input")) {
    const day = parseInt(e.target.dataset.day);
    const amount = parseInt(e.target.value) || 0;
    setActualCost(day, amount);
    // Update header display
    const card = e.target.closest(".day-card");
    if (card) {
      const stats = card.querySelector(".day-card-stats");
      const cost = estimateDayCost(state.candidates[state.selectedIndex]?.days?.[day - 1]?.stops || []);
      if (stats) stats.textContent = `${(state.candidates[state.selectedIndex]?.days?.[day - 1]?.stops || []).length} 站 · ≈¥${cost.lo}-${cost.hi}${amount ? ` · 实际 ¥${amount}` : ""}`;
    }
  }
});

// ---- Weather integration (Open-Meteo, free, no key) ----
const CITY_COORDS = {
  "长沙": { lat: 28.23, lon: 112.94 },
  "武汉": { lat: 30.59, lon: 114.31 },
  "changsha": { lat: 28.23, lon: 112.94 },
  "wuhan": { lat: 30.59, lon: 114.31 },
};

const WEATHER_CODES = {
  0: "☀️ 晴", 1: "🌤️ 晴间多云", 2: "⛅ 多云", 3: "☁️ 阴",
  45: "🌫️ 雾", 48: "🌫️ 雾凇", 51: "🌦️ 小雨", 53: "🌧️ 中雨", 55: "🌧️ 大雨",
  61: "🌧️ 小雨", 63: "🌧️ 中雨", 65: "🌧️ 大雨", 71: "🌨️ 小雪", 73: "❄️ 中雪",
  75: "❄️ 大雪", 80: "🌦️ 阵雨", 81: "🌧️ 阵雨", 82: "⛈️ 暴雨",
  95: "⛈️ 雷暴", 96: "⛈️ 雷暴冰雹", 99: "⛈️ 雷暴冰雹"
};

async function fetchWeather(city) {
  const coords = CITY_COORDS[city] || CITY_COORDS[city?.toLowerCase()];
  if (!coords) return null;
  try {
    const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${coords.lat}&longitude=${coords.lon}&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=Asia/Shanghai&forecast_days=7`);
    if (!res.ok) return null;
    const data = await res.json();
    const daily = data.daily;
    return (daily.time || []).map((date, i) => ({
      date,
      code: daily.weathercode?.[i] || 0,
      tempMax: daily.temperature_2m_max?.[i],
      tempMin: daily.temperature_2m_min?.[i],
      rainProb: daily.precipitation_probability_max?.[i] || 0,
    }));
  } catch { return null; }
}

// ---- City guidebook ----
const CITY_KEY_MAP = { "长沙": "changsha", "武汉": "wuhan", "大理": "dali", "丽江": "lijiang", "南京": "nanjing", "苏州": "suzhou",
  "changsha": "changsha", "wuhan": "wuhan", "dali": "dali", "lijiang": "lijiang", "nanjing": "nanjing", "suzhou": "suzhou" };

async function loadGuidebook(city) {
  const key = CITY_KEY_MAP[city] || city?.toLowerCase();
  if (!key) return;
  try {
    const data = await fetch(`/city/${key}/guidebook`).then(r => r.ok ? r.json() : null);
    if (!data) return;
    const html = renderGuidebook(data);
    // Show in form section (always visible)
    const formEl = $("formGuidebook");
    if (formEl) formEl.innerHTML = html;
    // Also show in overview if it exists
    const overviewEl = $("guidebookSection");
    if (overviewEl) overviewEl.innerHTML = html;
  } catch {}
}

function renderGuidebook(data) {
  const sections = data.sections || {};
  const items = [
    { key: "overview", icon: "📖", title: "城市简介" },
    { key: "activities", icon: "🎯", title: "推荐活动" },
    { key: "nightlife", icon: "🌙", title: "夜生活" },
    { key: "accommodation", icon: "🏨", title: "住宿建议" },
    { key: "safety", icon: "🛡️", title: "安全提示" },
  ].filter(s => sections[s.key]);
  if (!items.length) return "";
  return `
    <details class="guidebook-panel">
      <summary>📘 ${data.city || ""} 旅行攻略 <small>（来源 Wikivoyage）</small></summary>
      <div class="guidebook-content">
        ${items.map(s => `
          <div class="guidebook-section">
            <h4>${s.icon} ${s.title}</h4>
            <p>${escapeHtml(sections[s.key]).substring(0, 300)}${sections[s.key].length > 300 ? "..." : ""}</p>
          </div>
        `).join("")}
      </div>
    </details>
  `;
}

function renderWeatherBar(weather, days) {
  if (!weather || !weather.length) return "";
  const dayWeathers = weather.slice(0, days.length);
  const hasRain = dayWeathers.some(w => w.rainProb > 40 || [51,53,55,61,63,65,80,81,82,95,96,99].includes(w.code));
  return `
    <div class="weather-bar">
      ${dayWeathers.map((w, i) => `
        <div class="weather-day">
          <span class="weather-icon">${WEATHER_CODES[w.code] || "🌤️"}</span>
          <span class="weather-temp">${Math.round(w.tempMin)}~${Math.round(w.tempMax)}°C</span>
          <span class="weather-date">Day ${i + 1}</span>
        </div>
      `).join("")}
      ${hasRain ? '<div class="weather-alert">🌧️ 部分日期有雨，已为您推荐室内备选方案</div>' : ""}
    </div>
  `;
}

// ---- Guest mode ----
async function doGuestLogin() {
  const errEl = $("authError");
  errEl.hidden = true;
  try {
    const data = await api("/auth/guest", { method: "POST" });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("tp_token", data.token);
    showApp();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.hidden = false;
  }
}

// ---- Email registration ----
async function sendCode() {
  const email = $("regEmail").value.trim();
  const errEl = $("regEmailError");
  errEl.hidden = true;
  if (!email || !email.includes("@")) { errEl.textContent = "请输入有效的邮箱地址"; errEl.hidden = false; return; }
  try {
    $("sendCodeBtn").disabled = true;
    $("sendCodeBtn").textContent = "发送中...";
    await api("/auth/send-code", { method: "POST", body: JSON.stringify({ email }) });
    $("sendCodeBtn").textContent = "已发送 (60s)";
    let countdown = 60;
    const timer = setInterval(() => {
      countdown--;
      if (countdown <= 0) { clearInterval(timer); $("sendCodeBtn").textContent = "发送验证码"; $("sendCodeBtn").disabled = false; }
      else $("sendCodeBtn").textContent = `${countdown}s 后重发`;
    }, 1000);
  } catch (e) {
    errEl.textContent = e.message;
    errEl.hidden = false;
    $("sendCodeBtn").textContent = "发送验证码";
    $("sendCodeBtn").disabled = false;
  }
}

async function doEmailRegister() {
  const email = $("regEmail").value.trim();
  const code = $("regCode").value.trim();
  const password = $("regEmailPassword").value;
  const errEl = $("regEmailError");
  errEl.hidden = true;
  if (!email || !code || !password) { errEl.textContent = "请填写完整信息"; errEl.hidden = false; return; }
  if (password.length < 6) { errEl.textContent = "密码至少 6 位"; errEl.hidden = false; return; }
  try {
    $("authEmailRegisterBtn").disabled = true;
    const data = await api("/auth/register-email", {
      method: "POST",
      body: JSON.stringify({ email, code, password }),
    });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("tp_token", data.token);
    showApp();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.hidden = false;
  } finally {
    $("authEmailRegisterBtn").disabled = false;
  }
}

// Auth event listeners
$("authLoginBtn").addEventListener("click", doLogin);
$("authPassword").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
$("authRegisterBtn").addEventListener("click", doRegister);
$("authShowRegister").addEventListener("click", (e) => { e.preventDefault(); $("authLoginForm").hidden = true; $("authRegisterForm").hidden = true; $("authEmailForm").hidden = false; });
$("authShowLogin").addEventListener("click", (e) => { e.preventDefault(); $("authRegisterForm").hidden = true; $("authEmailForm").hidden = true; $("authLoginForm").hidden = false; });
$("guestBtn")?.addEventListener("click", doGuestLogin);
$("sendCodeBtn")?.addEventListener("click", sendCode);
$("authEmailRegisterBtn")?.addEventListener("click", doEmailRegister);
$("logoutBtn").addEventListener("click", logout);

initFeedback();
initEasterEgg();
checkAuth();

// Load tools data (works without auth since these are read-only)
queryRoute();
queryAlternatives();
querySearch();
