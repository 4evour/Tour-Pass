const $ = (id) => document.getElementById(id);
const messages = $("messages");
const resultPanel = $("result");
const input = $("input");
const send = $("send");
const statusEl = $("status");
let sessionId = null;

const periodLabels = {morning:"上午",lunch:"午餐",afternoon:"下午",dinner:"晚餐",evening:"晚间"};
const modeLabels = {walking:"步行",transit:"公共交通",driving:"驾车",taxi:"打车",mixed:"混合交通",unknown:"待确认"};
const sourceLabels = {amap:"高德已核验",qweather:"天气已核验",user:"用户确认",model_judgment:"规划建议",unknown:"待核验"};
const list = (value) => Array.isArray(value) ? value : [];
const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
const textOr = (value, fallback="待确认") => value ? escapeHtml(value) : fallback;
const placeKey = (value) => String(value ?? "").toLowerCase().replace(/[\s（）()·\-—]/g, "");
const samePlace = (left, right) => {
  const a = placeKey(left);
  const b = placeKey(right);
  return Boolean(a && b && (a === b || a.includes(b) || b.includes(a)));
};

function addMessage(kind, text) {
  const element = document.createElement("div");
  element.className = `message ${kind}`;
  element.textContent = text;
  messages.appendChild(element);
  messages.scrollTop = messages.scrollHeight;
}

function addToolEvent(text, cacheHit=false) {
  const element = document.createElement("div");
  element.className = `tool-event${cacheHit ? " hit" : ""}`;
  element.textContent = text;
  messages.appendChild(element);
  messages.scrollTop = messages.scrollHeight;
}

function renderTransfer(transfer) {
  if (!transfer) return "";
  const duration = transfer.duration_minutes ? `${transfer.duration_minutes} 分钟` : "耗时待确认";
  const distance = transfer.distance_meters ? `${(transfer.distance_meters / 1000).toFixed(1)} 公里` : "距离待确认";
  return `<div class="transfer"><b>${textOr(modeLabels[transfer.mode], "交通待确认")}</b> · ${duration} · ${distance}<br>${textOr(transfer.from_name)} → ${textOr(transfer.to_name)} · ${textOr(sourceLabels[transfer.source], "待核验")}${transfer.instructions ? `<br>走法建议：${escapeHtml(transfer.instructions)}` : ""}</div>`;
}

function renderScheduleItem(item) {
  const openingClass = item.opening_match === "matched" ? "ok" : item.opening_match === "risk" ? "risk" : "";
  const openingLabel = item.opening_match === "matched" ? "到访时段可用" : item.opening_match === "risk" ? "开放时间有风险" : "开放状态待确认";
  const reservation = object(item.reservation);
  const mapLink = item.location ? `<a class="fact" href="https://uri.amap.com/marker?position=${encodeURIComponent(item.location)}&name=${encodeURIComponent(item.name)}" target="_blank" rel="noreferrer">坐标 ${escapeHtml(item.location)}</a>` : `<span class="fact risk">坐标待确认</span>`;
  return `<div class="timeline-row">
    <div class="clock">${textOr(item.start, "--:--")}<br><small>${textOr(item.end, "--:--")}</small></div>
    <div class="route-axis"><i class="route-dot"></i></div>
    <div class="stop-content">
      <div class="stop-top"><div><h3>${textOr(item.name, "未命名活动")}</h3><p>${textOr(item.reason, "暂无体验说明")}</p></div><span class="period">${textOr(periodLabels[item.period], "时段")}</span></div>
      <div class="fact-row">
        <span class="fact">停留 ${item.duration_minutes || "?"} 分钟</span>
        <span class="fact ${openingClass}">${openingLabel}${item.opening_hours ? ` · ${escapeHtml(item.opening_hours)}` : ""}</span>
        <span class="fact">${textOr(reservation.status, "预约待确认")}</span>
        <span class="fact">${textOr(item.area, "区域待确认")}</span>
        ${mapLink}
        <span class="fact">${textOr(sourceLabels[item.source], "规划建议")}</span>
      </div>
    </div>
  </div>`;
}

function renderRisks(risks) {
  if (!risks.length) return "";
  return `<div class="surface"><div class="section-label"><span>风险与应对</span><span>${risks.length} 项</span></div><div class="risk-grid">${risks.map((risk) => `<article class="risk ${risk.level === "info" ? "info" : ""}"><b>${textOr(risk.title)}</b><p>${textOr(risk.detail, "暂无详情")}${risk.mitigation ? `<br>建议：${escapeHtml(risk.mitigation)}` : ""}<br><small>来源：${textOr(sourceLabels[risk.source], "规划建议")}</small></p></article>`).join("")}</div></div>`;
}

function renderDay(day) {
  const schedule = list(day.schedule);
  const transfers = list(day.transfers);
  const cluster = object(day.area_cluster);
  const usedTransfers = new Set();
  const timelineParts = [];
  schedule.forEach((item) => {
    const leadingIndex = transfers.findIndex((transfer, index) =>
      !usedTransfers.has(index) && samePlace(transfer.to_name, item.name));
    if (leadingIndex >= 0) {
      timelineParts.push(renderTransfer(transfers[leadingIndex]));
      usedTransfers.add(leadingIndex);
    }
    timelineParts.push(renderScheduleItem(item));
  });
  transfers.forEach((transfer, index) => {
    if (!usedTransfers.has(index)) timelineParts.push(renderTransfer(transfer));
  });
  const timeline = timelineParts.join("");
  return `<article class="day-card">
    <header class="day-head">
      <div class="day-number">DAY ${day.day}</div>
      <div class="day-title"><span class="kicker">${textOr(day.date || day.weekday, "日期待定")}</span><h2>${textOr(day.theme, "城市探索")}</h2><p>${textOr(day.summary, "当天路线说明待补充")}</p></div>
      <div class="day-hours">${textOr(day.start_time, "--:--")} — ${textOr(day.end_time, "--:--")}</div>
    </header>
    <div class="day-context">
      <div class="context-item"><span>出发锚点</span><b>${textOr(object(day.start_anchor).name)}</b></div>
      <div class="context-item"><span>区域组合</span><b>${textOr(cluster.primary_area)}${list(cluster.secondary_areas).length ? ` + ${escapeHtml(list(cluster.secondary_areas).join(" / "))}` : ""}</b></div>
      <div class="context-item"><span>结束锚点</span><b>${textOr(object(day.end_anchor).name)}</b></div>
    </div>
    <div class="timeline">${timeline || "<p>时间轴待补充</p>"}</div>
    ${list(day.risks).length ? `<div style="padding:0 24px 24px">${renderRisks(list(day.risks))}</div>` : ""}
  </article>`;
}

function renderComparison(comparison) {
  const areas = list(object(comparison).areas);
  return `<section class="surface"><div class="section-label"><span>候选区域比较</span><span>模型取舍</span></div><div class="comparison-grid">${areas.map((area) => `<article class="area-option ${area.selected ? "selected" : ""}"><header><h3>${textOr(area.name)}</h3><strong>${area.fit_score || 0}</strong></header><p><b>优势：</b>${textOr(list(area.highlights).join("、"), "待补充")}</p><p><b>代价：</b>${textOr(list(area.tradeoffs).join("、"), "待补充")}</p></article>`).join("") || "<p>候选比较待补充</p>"}</div><p>${textOr(comparison.selection_reason, "区域选择理由待补充")}</p></section>`;
}

function renderMap(mapData) {
  const points = list(object(mapData).points);
  return `<section class="surface"><div class="section-label"><span>地图坐标与路线</span><span>${points.length} 个点</span></div><div class="map-points">${points.map((point) => `<a class="map-point" href="https://uri.amap.com/marker?position=${encodeURIComponent(point.location)}&name=${encodeURIComponent(point.name)}" target="_blank" rel="noreferrer"><b>D${point.day}.${point.order}</b><span>${textOr(point.name)}<br><small>${textOr(point.location)}</small></span></a>`).join("") || "<p>地图坐标待补充</p>"}</div><p>${textOr(mapData.route_overview, "整体移动路线待补充")}</p></section>`;
}

function renderQuality(completeness) {
  const report = object(completeness);
  return `<section class="surface"><div class="section-label"><span>完整度检查</span><span>${report.passed || 0}/${report.total || 0}</span></div><div class="quality-grid">${list(report.checks).map((check) => `<div class="quality-check ${check.status}"><i></i><div><b>${textOr(check.name)}</b><br><span>${textOr(check.detail)}</span></div></div>`).join("")}</div></section>`;
}

function renderPlan(data) {
  if (!data.plan) return;
  const plan = data.plan;
  const narrative = object(plan.narrative);
  const profile = object(plan.trip_profile);
  const hotel = object(plan.hotel);
  const completeness = object(plan.completeness);
  const score = Math.max(0, Math.min(100, Number(completeness.score) || 0));
  const highlights = list(narrative.highlights);
  resultPanel.innerHTML = `
    <header class="plan-hero">
      <span class="kicker">${textOr(plan.city)} · ${list(plan.days).length} 天成品行程</span>
      <h1>${textOr(plan.title, `${textOr(plan.city)}旅行计划`)}</h1>
      <p>${textOr(plan.overview, narrative.summary || "行程总览待补充")}</p>
      <div class="hero-meta">
        <span>${textOr(profile.pace, "节奏待定")}</span>
        <span>${textOr(profile.transport_preference, "交通待定")}</span>
        <span>${textOr(profile.travelers, "同行人待定")}</span>
        <span>run ${escapeHtml(data.run_id.slice(0, 10))}</span>
      </div>
    </header>
    <div class="plan-body">
      <div class="summary-grid">
        <section class="surface narrative">
          <div class="section-label"><span>体验叙事</span><span>旅行顾问方案</span></div>
          <h2>${textOr(narrative.headline, "这趟旅行怎么走")}</h2>
          <p>${textOr(narrative.summary, plan.overview || "叙事说明待补充")}</p>
          <div class="tags">${highlights.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>
        </section>
        <section class="surface">
          <div class="section-label"><span>行程完整度</span><span>非硬门禁</span></div>
          <div class="score-ring" style="--score:${score}%"><div><b>${score}</b><small>/ 100</small></div></div>
          <div class="score-copy">模型先完整表达，缺项在这里透明显示</div>
        </section>
      </div>
      <section class="surface hotel-card">
        <div class="hotel-icon">宿</div>
        <div><div class="section-label"><span>住宿与每日锚点</span><span>${textOr(hotel.status)}</span></div><h3>${textOr(hotel.name)}</h3><p>${textOr(hotel.area)} · ${textOr(hotel.reason, "住宿选择理由待补充")}</p></div>
      </section>
      ${list(plan.days).map(renderDay).join("")}
      <div class="lower-grid">
        ${renderComparison(object(plan.candidate_comparison))}
        ${renderMap(object(plan.map))}
      </div>
      <div style="margin-top:14px">${renderQuality(completeness)}</div>
      ${list(plan.warnings).length ? `<div style="margin-top:14px">${renderRisks(list(plan.warnings).map((warning) => ({level:"warning",title:"全局提醒",detail:warning})))}</div>` : ""}
    </div>`;
}

function renderEvents(events) {
  for (const event of list(events)) {
    if (event.type === "tool_started") addToolEvent(`正在查询 ${event.tool} · ${JSON.stringify(event.arguments)}`);
    if (event.type === "tool_finished") addToolEvent(event.error ? `${event.tool} 查询失败：${event.error}` : `${event.tool} 查询完成${event.cache_hit ? " · 使用缓存" : ""}`, event.cache_hit);
    if (event.type === "tool_rejected") addToolEvent(`${event.tool} 未执行 · 工具预算已用完`);
    if (event.type === "plan_rejected") addToolEvent(`输出结构需要修正 · ${event.error}`);
  }
}

$("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  addMessage("user", message);
  input.value = "";
  send.disabled = true;
  statusEl.textContent = "正在查地点并编排行程…";
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message, session_id: sessionId})
    });
    const raw = await response.text();
    let data;
    try { data = JSON.parse(raw); } catch { data = {detail: raw || `HTTP ${response.status}`}; }
    if (!response.ok) throw new Error(data.detail || "规划请求失败");
    sessionId = data.session_id;
    renderEvents(data.events);
    addMessage("assistant", data.reply);
    renderPlan(data);
    statusEl.textContent = data.plan ? `行程已生成 · 完整度 ${data.plan.completeness?.score || 0}` : "等待补充信息";
  } catch (error) {
    addMessage("assistant", `本次规划未完成：${error.message}`);
    statusEl.textContent = "规划失败，请调整需求后重试";
  } finally {
    send.disabled = false;
    input.focus();
  }
});
