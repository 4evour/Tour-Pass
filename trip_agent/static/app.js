const $ = (id) => document.getElementById(id);
const messages = $("messages");
const resultPanel = $("result");
const input = $("input");
const send = $("send");
const statusEl = $("status");
const savedDrawer = $("saved-drawer");
const savedList = $("saved-list");
const tripForm = $("trip-form");
const emptyResultMarkup = resultPanel.innerHTML;
const welcomeMessage = "告诉我这次旅行最在意什么。我会补齐每天的时间轴、交通衔接、住宿锚点和风险提醒。";
let sessionId = localStorage.getItem("tour-pass-active-session");
let authState = null;
let authMode = "login";
let toastTimer = null;

function cookieValue(name) {
  return document.cookie.split("; ").find((item) => item.startsWith(`${name}=`))?.split("=").slice(1).join("=") || "";
}

async function apiFetch(url, options={}) {
  const headers = new Headers(options.headers || {});
  const method = String(options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRF-Token", cookieValue("tp_csrf"));
  return fetch(url, {...options, headers, credentials:"same-origin"});
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 3200);
}

function applyAuthState(data) {
  authState = data;
  $("quota-chip").textContent = `今日 ${data.quota.remaining}/${data.quota.limit} 次`;
  $("auth-button").textContent = data.authenticated ? data.user.username : "登录";
}
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

function setBusy(busy) {
  send.disabled = busy;
  $("structured-submit").disabled = busy;
  $("structured-tab").disabled = busy;
  $("conversation-tab").disabled = busy;
  $("new-trip").disabled = busy;
  $("open-saved").disabled = busy;
  tripForm.querySelectorAll("input, select, textarea").forEach((field) => {
    field.disabled = busy;
  });
}

function switchInputMode(mode) {
  const structured = mode === "structured";
  $("structured-pane").hidden = !structured;
  $("conversation-pane").hidden = structured;
  $("structured-tab").classList.toggle("active", structured);
  $("conversation-tab").classList.toggle("active", !structured);
  $("structured-tab").setAttribute("aria-selected", String(structured));
  $("conversation-tab").setAttribute("aria-selected", String(!structured));
  if (structured) $("destination").focus();
  else input.focus();
}

function setSessionMode(active) {
  $("composer-label").textContent = active ? "继续修改这份行程" : "继续完善行程";
  send.textContent = active ? "更新行程" : "规划行程";
  input.placeholder = active
    ? "例如：第二天改得轻松一些，把下午换成室内活动"
    : "例如：广州三天，住越秀区，带父母，少走路，想看老城和珠江夜景";
}

function closeSavedTrips() {
  savedDrawer.hidden = true;
  $("drawer-backdrop").hidden = true;
}

function openSavedTrips() {
  savedDrawer.hidden = false;
  $("drawer-backdrop").hidden = false;
}

function savedDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "时间未知"
    : new Intl.DateTimeFormat("zh-CN", {month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}).format(date);
}

function renderSavedSessions(items) {
  $("saved-count").textContent = items.length;
  savedList.innerHTML = items.length
    ? items.map((item) => `<button class="saved-item" type="button" data-session="${escapeHtml(item.session_id)}">
        <span>${escapeHtml(item.city || "旅行计划")}</span>
        <b>${escapeHtml(item.title)}</b>
        <small>${escapeHtml(savedDate(item.updated_at))} · ${escapeHtml(item.latest_run_id.slice(0, 8))}</small>
      </button>`).join("")
    : '<div class="saved-empty"><b>还没有保存的行程</b><p>成功生成第一份行程后会自动出现在这里。</p></div>';
}

async function refreshSavedSessions() {
  const response = await apiFetch("/api/sessions?limit=50");
  if (!response.ok) throw new Error("读取已保存行程失败");
  const data = await response.json();
  renderSavedSessions(list(data.sessions));
  return list(data.sessions);
}

async function loadSession(targetSessionId, closeDrawer=true) {
  const response = await apiFetch(`/api/sessions/${encodeURIComponent(targetSessionId)}`);
  if (!response.ok) throw new Error("这份已保存行程无法读取");
  const data = await response.json();
  sessionId = data.session.session_id;
  localStorage.setItem("tour-pass-active-session", sessionId);
  messages.innerHTML = "";
  list(data.messages).forEach((message) => addMessage(message.role, message.content));
  if (!data.messages.length) addMessage("assistant", welcomeMessage);
  if (data.latest) {
    progressState.events = list(data.latest.events);
    progressState.startedAt = Date.now();
    renderPlan(data.latest);
    statusEl.textContent = `已恢复保存行程 · ${data.session.title}`;
  } else {
    resultPanel.innerHTML = emptyResultMarkup;
    statusEl.textContent = "等待补充信息";
  }
  setSessionMode(true);
  switchInputMode("conversation");
  if (closeDrawer) closeSavedTrips();
  input.focus();
}

function startNewTrip() {
  if (send.disabled) return;
  clearInterval(progressState.timer);
  sessionId = null;
  localStorage.removeItem("tour-pass-active-session");
  messages.innerHTML = "";
  addMessage("assistant", welcomeMessage);
  resultPanel.innerHTML = emptyResultMarkup;
  statusEl.textContent = "等待输入";
  setSessionMode(false);
  tripForm.reset();
  switchInputMode("structured");
  closeSavedTrips();
  $("destination").focus();
}

const progressStages = [
  ["接收需求", "建立本次规划运行记录"],
  ["设计查询", "模型选择下一批事实核验任务"],
  ["核验地点与天气", "确认地点实体、开放信息与天气"],
  ["核验逐段交通", "查询活动之间及住宿闭环路线"],
  ["生成完整行程", "基于已核验证据编排每天时间轴"],
  ["结构检查", "解析结果并检查完整度"]
];

const progressState = {
  events: [],
  startedAt: 0,
  activeStage: 0,
  failed: false,
  currentTitle: "准备开始",
  currentDetail: "正在建立规划任务。",
  timer: null
};

function formatDuration(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes} 分 ${String(seconds % 60).padStart(2, "0")} 秒` : `${seconds} 秒`;
}

function toolLabel(tool) {
  return ({search_places:"地点搜索",place_detail:"地点详情",route:"真实路线",weather:"天气",batch:"并行查询"})[tool] || tool || "外部工具";
}

function describeTool(tool, args={}) {
  if (tool === "search_places") return `搜索 ${args.city || ""}「${args.keywords || "地点"}」`;
  if (tool === "place_detail") return `确认地点 ${args.place_id || ""}`;
  if (tool === "weather") return `查询 ${args.city || ""} ${args.days || ""} 天天气`;
  if (tool === "route") return `计算 ${args.city || ""} 一段真实交通`;
  return toolLabel(tool);
}

function batchCalls(event) {
  if (event.tool !== "batch") return [];
  return list(object(event.arguments).calls).filter((call) => call && typeof call === "object");
}

function eventCopy(event) {
  if (event.type === "run_started") return ["请求已接收", "规划运行已经建立"];
  if (event.type === "session_restored") return ["已恢复原行程上下文", `${event.previous_title || event.previous_city || "已保存行程"} · ${event.message_count || 0} 条历史消息`];
  if (event.type === "model_started") {
    const labels = {
      evidence_planning: "模型正在设计证据查询",
      route_planning: "模型正在补齐真实交通",
      final_planning: "模型正在生成完整行程"
    };
    return [labels[event.phase] || "模型正在规划下一步", event.detail || "正在读取已有证据和用户约束"];
  }
  if (event.type === "model_finished") {
    const actions = {tool:"决定调用外部工具", ask:"决定向用户补充提问", plan:"已生成结构化行程"};
    return ["模型本轮处理完成", actions[event.action] || `返回 ${event.action || "未知"} 动作`];
  }
  if (event.type === "model_stream") {
    const copies = {
      connected: ["模型服务已连接", `HTTP ${event.http_status || "已连接"} · ${event.model_elapsed_ms || 0} 毫秒`],
      first_event: ["模型开始处理", `首个流事件等待 ${event.model_elapsed_ms || 0} 毫秒 · ${event.event_type || "响应事件"}`],
      first_text: ["模型开始输出正文", `首段可见文本等待 ${formatDuration(event.model_elapsed_ms || 0)}`]
    };
    return copies[event.milestone] || ["模型流状态更新", event.milestone || ""];
  }
  if (event.type === "model_retry") return ["模型输出需要重试", `第 ${event.attempt || "?"} 次生成 · ${event.reason || "格式错误"}`];
  if (event.type === "tool_started") {
    const calls = batchCalls(event);
    return [
      calls.length ? `并行核验 ${calls.length} 项事实` : `正在调用${toolLabel(event.tool)}`,
      calls.length ? calls.map((call) => describeTool(call.tool, object(call.arguments))).join("；") : describeTool(event.tool, object(event.arguments))
    ];
  }
  if (event.type === "tool_finished") {
    return event.error
      ? [`${toolLabel(event.tool)}失败`, event.error]
      : [`${toolLabel(event.tool)}完成`, event.cache_hit ? "命中本地缓存" : "已取得新的外部证据"];
  }
  if (event.type === "tool_rejected") return ["工具调用未执行", event.error || "调用不符合当前预算或阶段要求"];
  if (event.type === "decision_rejected") return ["规划动作需要修正", list(event.fields).join("、") || event.action || "动作无效"];
  if (event.type === "plan_rejected") return ["行程结构需要修正", event.error || "未通过结构解析"];
  if (event.type === "plan_validation_started") return ["正在检查行程结构", "解析时间轴、地点证据和完整度字段"];
  if (event.type === "plan_validation_finished") return ["行程结构检查完成", `耗时 ${event.validation_elapsed_ms || 0} 毫秒`];
  if (event.type === "persistence_started") return ["正在保存本次对话", event.has_plan ? "写入行程、消息和生成轨迹" : "写入对话消息"];
  if (event.type === "persistence_finished") return ["本次对话已持久化", event.has_plan ? "行程已自动保存，可以继续修改" : "对话已保存"];
  if (event.type === "plan_ready") return ["行程结构已经就绪", `已使用 ${event.tool_count || 0} 次工具核验，完整度 ${event.completeness_score || 0}`];
  if (event.type === "run_error") return ["规划运行未完成", event.error || "达到运行限制"];
  if (event.type === "run_finished") return [event.success ? "全流程完成" : "全流程结束但未生成行程", `运行 ${event.run_id ? event.run_id.slice(0, 10) : ""}`];
  return [event.type || "规划事件", ""];
}

function stageFor(event) {
  if (event.type === "run_started") return 0;
  if (event.type === "model_started") {
    return ({evidence_planning:1,route_planning:3,final_planning:4})[event.phase] ?? 1;
  }
  if (event.type === "tool_started") {
    const includesRoute = event.tool === "route" || batchCalls(event).some((call) => call.tool === "route");
    return includesRoute ? 3 : 2;
  }
  if (event.type === "plan_ready") return 5;
  if (["plan_validation_started", "plan_validation_finished", "persistence_started", "persistence_finished"].includes(event.type)) return 5;
  if (event.type === "run_finished" && event.success) return progressStages.length;
  return progressState.activeStage;
}

function eventRows() {
  return progressState.events.map((event) => {
    const [title, detail] = eventCopy(event);
    const calls = batchCalls(event);
    const nested = calls.length
      ? `<ul>${calls.map((call) => `<li>${escapeHtml(describeTool(call.tool, object(call.arguments)))}</li>`).join("")}</ul>`
      : "";
    return `<div class="trace-row">
      <time>${formatDuration(event.elapsed_ms || 0)}</time>
      <i></i>
      <div><b>${escapeHtml(title)}</b>${detail ? `<p>${escapeHtml(detail)}</p>` : ""}${nested}</div>
    </div>`;
  }).join("");
}

function progressStats() {
  const modelCalls = progressState.events.filter((event) => event.type === "model_started").length;
  const toolCalls = progressState.events
    .filter((event) => event.type === "tool_started")
    .reduce((total, event) => total + Math.max(1, batchCalls(event).length), 0);
  const lastEvent = progressState.events.at(-1);
  const elapsed = lastEvent?.type === "run_finished"
    ? lastEvent.elapsed_ms
    : Date.now() - progressState.startedAt;
  return {modelCalls, toolCalls, elapsed};
}

function renderProgress() {
  const stats = progressStats();
  resultPanel.innerHTML = `<section class="progress-board" aria-live="polite">
    <header class="progress-hero">
      <div><span class="kicker">LIVE PLANNING TRACE</span><h2>${progressState.failed ? "规划在当前步骤停止" : "正在把想法变成可执行路线"}</h2><p>这里只展示系统动作、工具调用和确定性结果，不展示模型内部推理。</p></div>
      <div class="elapsed"><span>已运行</span><b>${formatDuration(stats.elapsed)}</b></div>
    </header>
    <div class="progress-metrics">
      <div><span>模型轮次</span><b>${stats.modelCalls}</b></div>
      <div><span>事实查询</span><b>${stats.toolCalls}</b></div>
      <div><span>进度事件</span><b>${progressState.events.length}</b></div>
    </div>
    <div class="progress-grid">
      <section class="stage-panel">
        <div class="section-label"><span>完整流程</span><span>${Math.min(progressState.activeStage + 1, progressStages.length)}/${progressStages.length}</span></div>
        <div class="stage-list">${progressStages.map(([title, detail], index) => {
          const state = index < progressState.activeStage ? "done" : index === progressState.activeStage ? (progressState.failed ? "failed" : "active") : "waiting";
          return `<div class="stage ${state}"><i>${index < progressState.activeStage ? "✓" : index + 1}</i><div><b>${title}</b><p>${detail}</p></div><span>${state === "done" ? "完成" : state === "active" ? "进行中" : state === "failed" ? "停止" : "等待"}</span></div>`;
        }).join("")}</div>
      </section>
      <section class="activity-panel">
        <div class="section-label"><span>当前工作</span><span>${progressState.failed ? "ERROR" : "LIVE"}</span></div>
        <div class="current-work ${progressState.failed ? "failed" : ""}"><i></i><div><h3>${escapeHtml(progressState.currentTitle)}</h3><p>${escapeHtml(progressState.currentDetail)}</p></div></div>
        <div class="trace-list">${eventRows() || '<p class="trace-empty">等待第一个运行事件…</p>'}</div>
      </section>
    </div>
  </section>`;
}

function startProgress() {
  progressState.events = [];
  progressState.startedAt = Date.now();
  progressState.activeStage = 0;
  progressState.failed = false;
  progressState.currentTitle = "正在提交需求";
  progressState.currentDetail = "等待服务端建立规划运行。";
  clearInterval(progressState.timer);
  progressState.timer = setInterval(renderProgress, 1000);
  renderProgress();
}

function acceptProgress(event) {
  progressState.events.push(event);
  progressState.activeStage = Math.max(progressState.activeStage, stageFor(event));
  const [title, detail] = eventCopy(event);
  progressState.currentTitle = title;
  progressState.currentDetail = detail;
  renderProgress();
}

function failProgress(message) {
  progressState.failed = true;
  progressState.currentTitle = "规划请求未完成";
  progressState.currentDetail = message;
  clearInterval(progressState.timer);
  renderProgress();
}

function renderTraceSummary() {
  if (!progressState.events.length) return "";
  const stats = progressStats();
  return `<details class="run-trace">
    <summary><span>查看完整生成轨迹</span><b>${formatDuration(stats.elapsed)} · ${stats.modelCalls} 轮模型 · ${stats.toolCalls} 次事实查询</b></summary>
    <div class="trace-list">${eventRows()}</div>
  </details>`;
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

function renderPlan(data, publicView=false) {
  if (!data.plan) return;
  const plan = data.plan;
  const narrative = object(plan.narrative);
  const profile = object(plan.trip_profile);
  const hotel = object(plan.hotel);
  const completeness = object(plan.completeness);
  const score = Math.max(0, Math.min(100, Number(completeness.score) || 0));
  const highlights = list(narrative.highlights);
  const runLabel = String(data.run_id || "published").slice(0, 10);
  const actions = publicView
    ? '<button class="plan-action" data-action="print">导出 PDF</button><a class="plan-action" href="/">生成我的行程</a>'
    : '<button class="plan-action" data-action="share">分享行程</button><button class="plan-action" data-action="print">导出 PDF</button>';
  resultPanel.innerHTML = `${publicView ? '<div class="public-notice">这是已发布行程的只读快照；开放时间、天气和交通请在出发前再次确认。</div>' : ""}
    <header class="plan-hero">
      <span class="kicker">${textOr(plan.city)} · ${list(plan.days).length} 天成品行程</span>
      <h1>${textOr(plan.title, `${textOr(plan.city)}旅行计划`)}</h1>
      <p>${textOr(plan.overview, narrative.summary || "行程总览待补充")}</p>
      <div class="hero-meta">
        <span>${textOr(profile.pace, "节奏待定")}</span>
        <span>${textOr(profile.transport_preference, "交通待定")}</span>
        <span>${textOr(profile.travelers, "同行人待定")}</span>
        <span>run ${escapeHtml(runLabel)}</span>
      </div>
      <div class="plan-actions">${actions}</div>
    </header>
    <div class="plan-body">
      ${renderTraceSummary()}
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

async function consumeEventStream(response) {
  if (!response.ok) {
    const raw = await response.text();
    let error;
    try { error = JSON.parse(raw); } catch { error = {detail: raw}; }
    throw new Error(error.detail || `规划请求失败（HTTP ${response.status}）`);
  }
  if (!response.body) throw new Error("浏览器未提供流式响应内容");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;

  const consumeFrame = (frame) => {
    const data = frame.split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) return;
    const payload = JSON.parse(data);
    if (payload.type === "progress") acceptProgress(payload.event);
    if (payload.type === "result") result = payload.result;
    if (payload.type === "error") throw new Error(payload.error?.message || "规划请求失败");
  };

  while (true) {
    const {value, done} = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || "";
    frames.forEach(consumeFrame);
    if (done) break;
  }
  if (buffer.trim()) consumeFrame(buffer);
  if (!result) throw new Error("规划流已结束，但没有返回最终结果");
  return result;
}

function buildStructuredMessage() {
  const data = new FormData(tripForm);
  const city = String(data.get("destination") || "").trim();
  const days = String(data.get("days") || "3");
  const parts = [`请为我规划${city}${days}天行程`];
  const optional = [
    ["start_date", "出发日期"],
    ["hotel_area", "住宿地点或区域"],
    ["travelers", "同行人"],
    ["pace", "旅行节奏"],
    ["transport", "主要交通方式"],
    ["budget", "预算偏好"],
    ["must_visits", "必去地点"],
    ["notes", "其他要求"]
  ];
  optional.forEach(([name, label]) => {
    const value = String(data.get(name) || "").trim();
    if (value) parts.push(`${label}：${value}`);
  });
  const dayStart = String(data.get("day_start") || "").trim();
  const dayEnd = String(data.get("day_end") || "").trim();
  if (dayStart || dayEnd) parts.push(`每日游玩时段：${dayStart || "不限"}至${dayEnd || "不限"}`);
  const interests = data.getAll("interest").map(String);
  if (interests.length) parts.push(`感兴趣的体验：${interests.join("、")}`);
  parts.push("请补齐每天时间轴、真实交通衔接、住宿闭环和风险提醒");
  return `${parts.join("；")}。`;
}

async function submitPlanning(message) {
  addMessage("user", message);
  setBusy(true);
  statusEl.textContent = sessionId
    ? "正在基于已保存行程重新核验并修改"
    : "规划运行中，可在右侧查看完整进度";
  startProgress();
  try {
    const response = await apiFetch("/chat/stream", {
      method: "POST",
      headers: {"Content-Type": "application/json", "Accept":"text/event-stream"},
      body: JSON.stringify({message, session_id: sessionId})
    });
    const remaining = Number(response.headers.get("X-Query-Remaining"));
    if (authState && Number.isFinite(remaining)) {
      applyAuthState({...authState, quota:{...authState.quota, remaining}});
    }
    const data = await consumeEventStream(response);
    clearInterval(progressState.timer);
    sessionId = data.session_id;
    localStorage.setItem("tour-pass-active-session", sessionId);
    setSessionMode(true);
    addMessage("assistant", data.reply);
    renderPlan(data);
    statusEl.textContent = data.plan ? `行程已自动保存 · 完整度 ${data.plan.completeness?.score || 0}` : "等待补充信息";
    await refreshSavedSessions();
  } catch (error) {
    failProgress(error.message);
    addMessage("assistant", `本次规划未完成：${error.message}`);
    statusEl.textContent = "规划失败，可在右侧查看停止位置";
  } finally {
    clearInterval(progressState.timer);
    setBusy(false);
    input.focus();
  }
}

async function refreshExplore() {
  const params = new URLSearchParams();
  const city = $("explore-city").value.trim();
  const days = $("explore-days").value;
  if (city) params.set("city", city);
  if (days) params.set("days", days);
  const response = await apiFetch(`/api/public/itineraries?${params}`);
  if (!response.ok) throw new Error("公开行程读取失败");
  const data = await response.json();
  const items = list(data.items);
  $("explore-list").innerHTML = items.length
    ? items.map((item) => `<a class="public-item" href="/p/${encodeURIComponent(item.slug)}"><small>${escapeHtml(item.city)} · ${item.days} 天</small><b>${escapeHtml(item.title)}</b><span>${escapeHtml(savedDate(item.published_at))}</span></a>`).join("")
    : '<div class="saved-empty"><b>暂无匹配行程</b><p>换一个城市或天数试试。</p></div>';
}

async function openExplore() {
  closeSavedTrips();
  $("explore-drawer").hidden = false;
  $("drawer-backdrop").hidden = false;
  try {
    await refreshExplore();
  } catch (error) {
    $("explore-list").innerHTML = `<p class="saved-error">${escapeHtml(error.message)}</p>`;
  }
}

function closeExplore() {
  $("explore-drawer").hidden = true;
  $("drawer-backdrop").hidden = true;
}

function configureAuthDialog(mode) {
  authMode = mode;
  const registering = mode === "register";
  $("auth-title").textContent = registering ? "注册账号" : "登录";
  $("auth-submit").textContent = registering ? "注册并保存当前行程" : "登录";
  $("auth-switch").textContent = registering ? "已有账号？登录" : "没有账号？注册";
  $("auth-password").autocomplete = registering ? "new-password" : "current-password";
  $("auth-error").hidden = true;
}

async function publishCurrent() {
  if (!sessionId) return;
  const response = await apiFetch(`/api/sessions/${encodeURIComponent(sessionId)}/publish`, {method:"POST"});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "分享失败");
  const url = `${location.origin}/p/${payload.slug}`;
  try {
    await navigator.clipboard.writeText(url);
    showToast(payload.visibility === "public" ? "公开链接已复制，并已加入发现页" : "私密分享链接已复制；登录后可加入发现页");
  } catch {
    window.prompt("复制分享链接", url);
  }
}

async function loadPublicPage(slug) {
  const response = await apiFetch(`/api/public/itineraries/${encodeURIComponent(slug)}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "公开行程不存在");
  renderPlan({plan:payload.plan, run_id:payload.run_id}, true);
  document.title = `${payload.title} · Tour Pass`;
}

resultPanel.addEventListener("click", async (event) => {
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "print") {
    window.print();
    return;
  }
  if (action === "share") {
    try {
      await publishCurrent();
    } catch (error) {
      showToast(error.message);
    }
  }
});

tripForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!tripForm.reportValidity()) return;
  const message = buildStructuredMessage();
  switchInputMode("conversation");
  await submitPlanning(message);
});

$("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  await submitPlanning(message);
});

$("structured-tab").addEventListener("click", () => switchInputMode("structured"));
$("conversation-tab").addEventListener("click", () => switchInputMode("conversation"));

$("open-saved").addEventListener("click", async () => {
  if (send.disabled) return;
  openSavedTrips();
  try {
    await refreshSavedSessions();
  } catch (error) {
    savedList.innerHTML = `<div class="saved-empty"><b>读取失败</b><p>${escapeHtml(error.message)}</p></div>`;
  }
});
$("close-saved").addEventListener("click", closeSavedTrips);
$("close-explore").addEventListener("click", closeExplore);
$("drawer-backdrop").addEventListener("click", () => { closeSavedTrips(); closeExplore(); });
$("new-trip").addEventListener("click", startNewTrip);
savedList.addEventListener("click", async (event) => {
  const item = event.target.closest(".saved-item");
  if (!item) return;
  try {
    await loadSession(item.dataset.session);
  } catch (error) {
    savedList.insertAdjacentHTML("afterbegin", `<p class="saved-error">${escapeHtml(error.message)}</p>`);
  }
});
$("open-explore").addEventListener("click", async (event) => {
  event.preventDefault();
  history.pushState({}, "", "/explore");
  await openExplore();
});
$("explore-filter").addEventListener("submit", async (event) => {
  event.preventDefault();
  await refreshExplore();
});
$("auth-button").addEventListener("click", async () => {
  if (authState?.authenticated) {
    if (!window.confirm(`退出账号 ${authState.user.username}？`)) return;
    const response = await apiFetch("/api/auth/logout", {method:"POST"});
    applyAuthState(await response.json());
    startNewTrip();
    await refreshSavedSessions();
    showToast("已退出，当前浏览器仍可匿名规划");
    return;
  }
  configureAuthDialog("login");
  $("auth-dialog").showModal();
  $("auth-username").focus();
});
$("auth-switch").addEventListener("click", () => configureAuthDialog(authMode === "login" ? "register" : "login"));
$("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    $("auth-dialog").close();
    return;
  }
  const username = $("auth-username").value.trim();
  const password = $("auth-password").value;
  const error = $("auth-error");
  error.hidden = true;
  $("auth-submit").disabled = true;
  try {
    const response = await apiFetch(`/api/auth/${authMode}`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({username, password})
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "账号操作失败");
    applyAuthState(payload);
    $("auth-dialog").close();
    $("auth-password").value = "";
    await refreshSavedSessions();
    showToast(authMode === "register" ? "注册成功，当前行程已归入账号" : "登录成功");
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally {
    $("auth-submit").disabled = false;
  }
});


(async function bootstrap() {
  try {
    const authResponse = await apiFetch("/api/auth/session");
    applyAuthState(await authResponse.json());
    const publicMatch = location.pathname.match(/^\/p\/([a-f0-9]{20})$/);
    if (publicMatch) {
      await loadPublicPage(publicMatch[1]);
      return;
    }
    if (location.pathname === "/explore") await openExplore();
    await refreshSavedSessions();
    if (sessionId) await loadSession(sessionId, false);
    else switchInputMode("structured");
  } catch (error) {
    sessionId = null;
    localStorage.removeItem("tour-pass-active-session");
    setSessionMode(false);
    switchInputMode("structured");
    showToast(error.message || "页面初始化失败");
  }
})();
