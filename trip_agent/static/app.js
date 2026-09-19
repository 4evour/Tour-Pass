const $ = (id) => document.getElementById(id);
const messages = $("messages");
const resultPanel = $("result");
const input = $("input");
const send = $("send");
const statusEl = $("status");
const savedDrawer = $("saved-drawer");
const savedList = $("saved-list");
const tripForm = $("trip-form");
const workspace = document.querySelector(".workspace");
const assistantPanel = $("assistant-panel");
const panelToggle = $("toggle-panel");
const emptyResultMarkup = resultPanel.innerHTML;
const welcomeMessage = "告诉我想去哪里就可以开始。没有特殊要求时，我会按第一次到访的热门主路线，直接给你一版能照着走的行程。";
let sessionId = localStorage.getItem("tour-pass-active-session");
let authState = null;
let authMode = "login";
let toastTimer = null;
let selectedModel = localStorage.getItem("tour-pass-model") || "deepseek-flash";

function activeModel() {
  const custom = $("custom-model")?.value.trim();
  return custom || $("llm-model")?.value || selectedModel;
}

async function loadModels() {
  try {
    const response = await apiFetch("/api/llm/models");
    if (!response.ok) return;
    const data = await response.json();
    const select = $("llm-model");
    const models = Array.isArray(data.models) ? data.models : [];
    select.innerHTML = models.map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join("");
    select.value = models.includes(selectedModel) ? selectedModel : (data.default || models[0] || selectedModel);
    selectedModel = select.value;
  } catch {
    // Keep the built-in fallback if the model list endpoint is unavailable.
  }
}

function cookieValue(name) {
  return document.cookie.split("; ").find((item) => item.startsWith(`${name}=`))?.split("=").slice(1).join("=") || "";
}

async function apiFetch(url, options={}) {
  const headers = new Headers(options.headers || {});
  const method = String(options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRF-Token", cookieValue("tp_csrf"));
  return fetch(url, {...options, headers, credentials:"same-origin"});
}

function setPlanningPanelCollapsed(collapsed) {
  const value = Boolean(collapsed);
  workspace.classList.toggle("panel-collapsed", value);
  assistantPanel.classList.toggle("collapsed", value);
  panelToggle.setAttribute("aria-expanded", String(!value));
  panelToggle.setAttribute("aria-label", value ? "展开规划面板" : "收起规划面板");
  panelToggle.title = value ? "展开规划面板" : "收起规划面板";
  $("panel-toggle-icon").textContent = value ? "›" : "‹";
  $("panel-toggle-text").textContent = value ? "展开规划面板" : "收起规划面板";
  localStorage.setItem("tour-pass-panel-collapsed", String(value));
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
const periodLabels = {breakfast:"早餐",morning:"上午",lunch:"午餐",afternoon:"下午",dinner:"晚餐",evening:"晚上"};
const visitScaleLabels = {quick_stop:"顺路短停",standard:"留出一段完整时间",half_day:"预留半天",full_day:"当天主要安排"};
const modeLabels = {walking:"步行",transit:"公共交通",public_transit:"公共交通",driving:"驾车",taxi:"打车",mixed:"混合交通",unknown:"待确认"};
const sourceLabels = {amap:"高德数据",qweather:"和风天气数据",user:"用户确认",model_judgment:"规划建议",unknown:"待核验"};
const list = (value) => Array.isArray(value) ? value : [];
const splitValues = (value) => String(value || "")
  .split(/[、，,；;\n]+/)
  .map((item) => item.trim())
  .filter(Boolean);
const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
const textOr = (value, fallback="待确认") => value ? escapeHtml(value) : fallback;
const placeKey = (value) => String(value ?? "").toLowerCase().replace(/[\s（）()·\-—]/g, "");
const samePlace = (left, right) => {
  const a = placeKey(left);
  const b = placeKey(right);
  return Boolean(a && b && (a === b || a.includes(b) || b.includes(a)));
};

function compactNarrative(plan, narrative, days) {
  const routeRuns = [];
  days.forEach((day) => {
    const destination = String(day.destination || plan.city || "当地").trim();
    const previous = routeRuns[routeRuns.length - 1];
    if (previous && previous.name === destination) previous.days += 1;
    else routeRuns.push({name: destination, days: 1});
  });
  const route = routeRuns.length
    ? routeRuns.map((item) => `${item.name}${item.days}天`).join("，随后")
    : `${String(plan.city || "当地").trim()}路线`;
  const themes = [...new Set(days.map((day) => String(day.theme || "").trim()).filter(Boolean))];
  const summaryFallback = `这是一条${route}的路线，${themes.length ? `主线围绕${themes.slice(0, 2).join("、")}展开；` : ""}${routeRuns.length > 1 ? "换城日和返程日留出缓冲。" : "每天围绕相邻片区推进，留出用餐和休息时间。"}`;
  const sourceSummary = String(narrative.summary || "").trim();
  const repeatedDays = (sourceSummary.match(/第\d+天/g) || []).length > 1;
  const noisySummary = /早餐|午餐|晚餐|按上述时间轴|最终返回|办理入住/.test(sourceSummary)
    || repeatedDays || sourceSummary.length > 220;
  const summary = sourceSummary && !noisySummary ? sourceSummary : summaryFallback;
  const highlights = list(narrative.highlights)
    .map((item) => String(item || "").trim().replace(/[；;。]+$/, ""))
    .filter((item) => item && item.length <= 56)
    .filter((item) => !/早餐|午餐|晚餐|晚上|按上述时间轴|最终返回|办理入住/.test(item));
  const compactHighlights = [...new Set(highlights)].slice(0, 4);
  if (compactHighlights.length) return {summary, highlights: compactHighlights};
  const derived = [];
  days.forEach((day) => {
    const destination = String(day.destination || plan.city || "当地").trim();
    const theme = String(day.theme || "").trim();
    const label = theme ? `${destination} · ${theme}` : destination;
    if (!derived.includes(label)) derived.push(label);
  });
  days.forEach((day) => {
    const leg = object(day.intercity_leg);
    if (leg.from && leg.to) {
      const label = `换城：${leg.from} → ${leg.to}`;
      if (!derived.includes(label)) derived.push(label);
    }
  });
  return {summary, highlights: derived.slice(0, 4)};
}

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
  switchInputMode("conversation");
  closeSavedTrips();
  input.focus();
}

const progressStages = [
  ["整理需求", "确认目的地、天数和需要照顾的事项"],
  ["找地点和路线", "查找代表性景点、住宿区域和可行的交通"],
  ["排好每天顺序", "把同片区的安排串成一条顺路路线"],
  ["检查能否走通", "检查时间、路线和出发前需要确认的事项"]
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
  return ({search_places:"地点搜索", route:"真实路线", weather:"天气"})[tool] || tool || "外部工具";
}

function describeTool(tool, args={}) {
  if (tool === "search_places") return `搜索 ${args.city || ""}「${args.keywords || "地点"}」`;
  if (tool === "weather") return `查询 ${args.city || ""} ${args.days || ""} 天天气`;
  if (tool === "route") return `计算 ${args.city || ""} 一段真实交通`;
  return toolLabel(tool);
}


function eventCopy(event) {
  if (event.type === "run_started") return ["请求已接收", "规划运行已经建立"];
  if (event.type === "session_restored") return ["已恢复原行程上下文", `${event.previous_title || event.previous_city || "已保存行程"} · ${event.message_count || 0} 条历史消息`];
  if (event.type === "model_started") {
    const labels = {
      skeleton: "正在排出一版主路线"
    };
    return [labels[event.phase] || "正在安排路线", "根据目的地、天数和已填写的要求整理顺序"];
  }
  if (event.type === "model_finished") {
    if (event.error) return ["模型结构化输出无效", event.message || event.error];
    return event.phase === "skeleton"
      ? ["行程骨架生成完成", "下一步由程序批量核验地点并计算路线"]
      : ["模型处理完成", `${list(event.tool_calls).length} 个工具调用`];
  }
  if (event.type === "prompt_cache") {
    const cached = Number(event.cached_tokens || 0);
    const total = Number(event.input_tokens || 0);
    return [
      cached ? "模型提示缓存已命中" : "模型提示缓存未命中",
      `${cached.toLocaleString()} / ${total.toLocaleString()} 输入 Token 使用缓存计费`
    ];
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
    return [
      event.tool === "route" ? "正在核对路上要花多久" : event.tool === "weather" ? "正在看出发日天气" : "正在确认地点信息",
      event.tool === "route" ? "检查景点之间和住宿往返是否顺路" : event.tool === "weather" ? "把天气和穿着提醒补进行程" : "确认名称、位置和可用的地图信息"
    ];
  }
  if (event.type === "tool_finished") {
    return event.error
      ? [`${toolLabel(event.tool)}失败`, event.error]
      : [
          `${toolLabel(event.tool)}完成`,
          event.reused ? "复用本轮已核验证据" : event.cache_hit ? "命中 Provider 缓存" : "已取得新的外部证据",
        ];
  }
  if (event.type === "plan_validation_started") return ["正在执行硬校验", "检查用户约束、实体、时间轴、路线证据和住宿闭环"];
  if (event.type === "plan_repair_applied") return ["已执行确定性修复", `${list(event.repairs).length} 处结构或时间轴调整`];
  if (event.type === "plan_validation_finished") {
    const failures = list(event.hard_failure_codes);
    return event.passed
      ? ["硬校验通过", `耗时 ${event.validation_elapsed_ms || 0} 毫秒 · ${list(event.warning_codes).length} 项提示`]
      : ["硬校验未通过", failures.join("、") || "候选行程需要修复"];
  }
  if (event.type === "persistence_started") return ["正在保存本次对话", event.has_plan ? "写入行程、消息和生成轨迹" : "写入对话消息"];
  if (event.type === "persistence_finished") return ["本次对话已持久化", event.has_plan ? "行程已自动保存，可以继续修改" : "对话已保存"];
  if (event.type === "plan_ready") return ["行程结构已经就绪", `已使用 ${event.tool_count || 0} 次工具核验，完整度 ${event.completeness_score || 0}`];
  if (event.type === "run_error") return ["规划运行未完成", event.error || "达到运行限制"];
  if (event.type === "run_finished") return [event.success ? "全流程完成" : "全流程结束但未生成行程", `运行 ${event.run_id ? event.run_id.slice(0, 10) : ""}`];
  return [event.type || "规划事件", ""];
}

function stageFor(event) {
  if (event.type === "run_started") return 0;
  if (event.type === "model_started") return 1;
  if (event.type === "tool_started") return event.tool === "route" ? 2 : 1;
  if (event.type === "plan_ready") return 4;
  if (["plan_repair_applied", "plan_validation_started", "plan_validation_finished", "persistence_started", "persistence_finished"].includes(event.type)) return 3;
  if (event.type === "run_finished" && event.success) return progressStages.length;
  return progressState.activeStage;
}

function eventRows() {
  return progressState.events.map((event) => {
    const [title, detail] = eventCopy(event);
    return `<div class="trace-row">
      <time>${formatDuration(event.elapsed_ms || 0)}</time>
      <i></i>
      <div><b>${escapeHtml(title)}</b>${detail ? `<p>${escapeHtml(detail)}</p>` : ""}</div>
    </div>`;
  }).join("");
}

function progressStats() {
  const modelCalls = progressState.events.filter((event) => event.type === "model_started").length;
  const toolEvents = progressState.events.filter((event) => event.type === "tool_started");
  const placeChecks = toolEvents.filter((event) => ["search_places", "search_area"].includes(event.tool)).length;
  const routeChecks = toolEvents.filter((event) => event.tool === "route").length;
  const lastEvent = progressState.events.at(-1);
  const elapsed = lastEvent?.type === "run_finished"
    ? lastEvent.elapsed_ms
    : Date.now() - progressState.startedAt;
  return {modelCalls, placeChecks, routeChecks, elapsed};
}

function renderProgress() {
  const stats = progressStats();
  resultPanel.innerHTML = `<section class="progress-board" aria-live="polite">
    <header class="progress-hero">
      <div><span class="kicker">TOUR PASS</span><h2>${progressState.failed ? "这次规划停在了一个步骤" : "正在为你排好一趟顺路的旅行"}</h2><p>你只需要等结果；地点、路线和时间会在后台逐项核对。</p></div>
      <div class="elapsed"><span>已运行</span><b>${formatDuration(stats.elapsed)}</b></div>
    </header>
    <div class="progress-metrics">
      <div><span>已查地点</span><b>${stats.placeChecks}</b></div>
      <div><span>已核路线</span><b>${stats.routeChecks}</b></div>
      <div><span>运行时间</span><b>${formatDuration(stats.elapsed)}</b></div>
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
        <div class="section-label"><span>现在进行到</span><span>${progressState.failed ? "需要处理" : "进行中"}</span></div>
        <div class="current-work ${progressState.failed ? "failed" : ""}"><i></i><div><h3>${escapeHtml(progressState.currentTitle)}</h3><p>${escapeHtml(progressState.currentDetail)}</p></div></div>
        <details class="progress-details"><summary>查看后台核验进度</summary><div class="trace-list">${eventRows() || '<p class="trace-empty">等待第一个运行事件…</p>'}</div></details>
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
    <summary><span>查看完整生成轨迹</span><b>${formatDuration(stats.elapsed)} · ${stats.modelCalls} 次规划 · ${stats.placeChecks + stats.routeChecks} 次核验</b></summary>
    <div class="trace-list">${eventRows()}</div>
  </details>`;
}

function renderTransfer(transfer) {
  if (!transfer) return "";
  const mode = textOr(modeLabels[transfer.mode], "交通待确认");
  const duration = transfer.duration_minutes ? `${transfer.duration_minutes} 分钟` : "耗时待确认";
  const distance = transfer.distance_meters ? `${(transfer.distance_meters / 1000).toFixed(1)} 公里` : "距离待确认";
  return `<div class="transfer route-hop">
    <span class="hop-symbol" aria-hidden="true">↳</span>
    <div class="hop-copy">
      <div><b>${mode}</b><span>${textOr(transfer.start, "时间待定")}–${textOr(transfer.end, "待定")} · ${duration} · ${distance}</span></div>
      <p>${textOr(transfer.from_name)} → ${textOr(transfer.to_name)}</p>
      ${transfer.instructions ? `<small>${escapeHtml(transfer.instructions)}</small>` : ""}
    </div>
  </div>`;
}

function renderScheduleItem(item) {
  const openingHours = String(item.opening_hours || "").trim();
  const openingDetail = openingHours.length > 96 ? `${openingHours.slice(0, 96)}…` : openingHours;
  const openingClass = item.opening_match === "risk" ? "risk" : "ok";
  const type = String(item.type || "visit");
  const typeLabel = type === "meal" ? "吃" : type === "hotel" ? "住" : ["free", "free_time"].includes(type) ? "闲" : "游";
  const mapLink = item.location ? `<a class="map-link" href="https://uri.amap.com/marker?position=${encodeURIComponent(item.location)}&name=${encodeURIComponent(item.name)}" target="_blank" rel="noreferrer">地图 ↗</a>` : "";
  const rhythm = type === "visit" ? textOr(visitScaleLabels[item.visit_scale], "按现场节奏游览") : type === "meal" ? "按当天路线就近安排" : "";
  const guide = object(item.guide);
  const sentences = String(item.reason || "").split(/[。！？!?]+/).map((part) => part.trim()).filter(Boolean);
  const highlight = guide.highlight || sentences[0] || "这站值得留出一段完整时间。";
  const how = guide.how || sentences.slice(1).join("；") || rhythm || "按现场状态慢慢逛，不必追求全部打卡。";
  const reminder = [guide.reminder, ...list(item.practical_tips)]
    .map((value) => String(value || "").trim())
    .find((value) => value && !/热门时段.*排队.*取号或预约|建议按当天开放、预约和人流情况|开放、预约和现场排队情况以出发当天为准|出发前确认开放和预约要求/.test(value)) || "";
  const verified = item.source === "amap" && item.place_id && item.location;
  const factLabel = verified ? "地点已定位" : "地点待核验";
  const factClass = verified ? "verified" : "pending";
  return `<div class="timeline-row stop-${escapeHtml(type)}">
    <div class="route-axis"><i class="route-dot"></i></div>
    <div class="stop-content">
      <div class="stop-top">
        <span class="stop-kind">${typeLabel}</span>
        <div class="stop-copy">
          <div class="stop-heading"><h3>${textOr(item.name, "未命名活动")}</h3>${mapLink}</div>
          <p class="stop-reason">${textOr(item.reason, "体验说明待补充")}</p>
          <div class="guide-triptych${reminder ? "" : " without-reminder"}" aria-label="导游说明">
            <div><b>看点</b><span>${escapeHtml(highlight)}</span></div>
            <div><b>玩法</b><span>${escapeHtml(how)}</span></div>
            ${reminder ? `<div><b>提醒</b><span>${escapeHtml(reminder)}</span></div>` : ""}
          </div>
          <div class="stop-facts"><span class="stop-clock">${textOr(item.start, "时间待定")}–${textOr(item.end, "待定")}</span>${rhythm ? `<span>${escapeHtml(rhythm)}</span>` : ""}</div>
          <div class="fact-statuses"><span class="fact-status ${factClass}">${factLabel}</span><span class="fact-status ${item.opening_match === "matched" ? "verified" : "pending"}">${item.opening_match === "matched" ? "时段已匹配" : "开放待确认"}</span></div>
          ${list(item.practical_tips).length ? `<p class="stop-practical">${list(item.practical_tips).map(escapeHtml).join("；")}</p>` : ""}
          ${openingHours ? `<p class="stop-opening ${openingClass}" title="${escapeHtml(openingHours)}"><b>${item.opening_match === "unknown" ? "地图常规时间 · 当日待确认" : "开放时间"}</b>${escapeHtml(openingDetail)}</p>` : ""}
        </div>
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
  const transfers = list(day.transfers).toSorted((left, right) => String(left.start || "").localeCompare(String(right.start || "")));
  const fallback = object(day.fallback);
  const intercity = object(day.intercity_leg);
  const usedTransfers = new Set();
  const timelineParts = [];
  let currentPeriod = "";
  schedule.forEach((item) => {
    const period = String(item.period || "afternoon");
    if (period !== currentPeriod) {
      currentPeriod = period;
      timelineParts.push(`<div class="period-divider"><span>${textOr(periodLabels[period], "行程")}</span></div>`);
    }
    transfers.forEach((transfer, index) => {
      const precedes = transfer.end && item.start
        ? transfer.end <= item.start
        : samePlace(transfer.to_name, item.name);
      if (!usedTransfers.has(index) && precedes) {
        timelineParts.push(renderTransfer(transfer));
        usedTransfers.add(index);
      }
    });
    timelineParts.push(renderScheduleItem(item));
  });
  transfers.forEach((transfer, index) => {
    if (!usedTransfers.has(index)) timelineParts.push(renderTransfer(transfer));
  });
  const routeNames = schedule
    .filter((item) => item.type !== "meal" && item.type !== "hotel")
    .map((item) => textOr(item.name))
    .join(" → ");
  const tone = ((Number(day.day) || 1) - 1) % 5 + 1;
  return `<article class="day-card guide-day day-tone-${tone}" id="day-${Number(day.day) || 1}">
    <header class="day-head">
      <div class="day-number"><b>DAY</b><strong>${Number(day.day) || 1}</strong></div>
      <div class="day-title">
        <span class="kicker">${textOr(day.date || day.weekday, "日期待定")}</span>
        <h2>${textOr(day.theme, "城市探索")}</h2>
        <p>${textOr(day.summary, "当天路线说明待补充")}</p>
      </div>
    </header>
    <div class="day-route"><span>这一天怎么走</span><b>${routeNames || "路线待补充"}</b></div>
    ${object(day.effort).transfer_count ? `<div class="day-effort"><span>行动负荷</span><b>${Number(day.effort.walking_distance_meters) ? `${(Number(day.effort.walking_distance_meters) / 1000).toFixed(1)} 公里接驳步行` : "接驳步行待核验"}</b><small>${Number(day.effort.rest_minutes) || 0} 分钟休息 · 最长游览 ${Number(day.effort.longest_visit_minutes) || 0} 分钟</small></div>` : ""}
    ${intercity.summary ? `<div class="intercity-callout"><b>跨城移动</b><span>${textOr(intercity.summary)}</span><small>${textOr(intercity.departure_hint, "出发时间待核验")} → ${textOr(intercity.arrival_hint, "抵达时间待核验")}${intercity.price ? ` · ${textOr(intercity.seat_type, "参考席别")} ${money(intercity.price)}` : ""}${intercity.status === "verified_schedule" ? " · 12306 时刻已核验" : ""}</small></div>` : ""}
    <div class="timeline">${timelineParts.join("") || "<p>时间轴待补充</p>"}</div>
    ${fallback.notes ? `<aside class="day-fallback"><b>晚点 / 雨天兜底</b><p>${textOr(fallback.notes)}</p>${list(fallback.late_drop_order).length ? `<small>优先删减 ${list(fallback.late_drop_order).length} 个可选项</small>` : ""}</aside>` : ""}
    ${list(day.risks).length ? `<aside class="day-alerts"><b>当天提醒</b>${list(day.risks).map((risk) => `<p><strong>${textOr(risk.title, "行程提醒")}</strong>${textOr(risk.detail, "暂无详情")}${risk.mitigation ? ` · ${escapeHtml(risk.mitigation)}` : ""}</p>`).join("")}</aside>` : ""}
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

function renderReview(review) {
  const report = object(review);
  const issues = list(report.issues);
  if (!Object.keys(report).length) return "";
  const verdict = report.verdict === "pass" ? "通过" : report.verdict === "revise" ? "建议调整" : "未执行";
  const mode = report.shadow ? "影子审查，不阻断交付" : "交付前审查";
  return `<section class="surface"><div class="section-label"><span>独立质量审查</span><span>${verdict} · ${mode}</span></div><p>${textOr(report.summary, "暂无审查说明")}</p>${issues.length ? `<div class="risk-grid">${issues.map((issue) => `<article class="risk ${issue.severity === "info" ? "info" : ""}"><b>${textOr(issue.code, "质量建议")}</b><p>${textOr(issue.message, "暂无详情")}${issue.suggestion ? `<br>建议：${escapeHtml(issue.suggestion)}` : ""}</p></article>`).join("")}</div>` : ""}</section>`;
}

function renderTripStats(plan, days, profile) {
  const schedules = days.flatMap((day) => list(day.schedule));
  const transfers = days.flatMap((day) => list(day.transfers));
  const visitCount = schedules.filter((item) => item.type === "visit").length;
  const mealCount = schedules.filter((item) => item.type === "meal").length;
  const transferMinutes = transfers.reduce((total, item) => total + (Number(item.duration_minutes) || 0), 0);
  const distanceMeters = transfers.reduce((total, item) => total + (Number(item.distance_meters) || 0), 0);
  const dates = object(plan.date_range);
  const dateLabel = dates.start
    ? `${escapeHtml(String(dates.start).slice(5))}${dates.end && dates.end !== dates.start ? ` — ${escapeHtml(String(dates.end).slice(5))}` : ""}`
    : "日期待定";
  const planningContext = object(plan.planning_context);
  const budgetRange = object(planningContext.budget_range);
  const budget = profile.budget
    || planningContext.budget
    || (budgetRange.per_person ? `人均 ¥${Number(budgetRange.per_person).toLocaleString("zh-CN")}` : "")
    || (budgetRange.total_max ? `总计 ¥${Number(budgetRange.total_max).toLocaleString("zh-CN")}` : "")
    || "未设置";
  const windows = [...new Set(days.map(day => day.start_time && day.end_time ? `${day.start_time}–${day.end_time}` : "时间待定"))];
  return `<section class="trip-statbar" aria-label="行程关键数据">
    <div><span>日期 / 天数</span><b>${dateLabel}</b><small>${days.length} 天</small></div>
    <div><span>行程规模</span><b>${visitCount} 个游览点</b><small>${mealCount} 次用餐安排</small></div>
    <div><span>计划时段</span><b>${windows.length === 1 ? escapeHtml(windows[0]) : "按日查看"}</b><small>含已列交通与缓冲，非实时班次</small></div>
    <div><span>路线核验</span><b>${distanceMeters ? `${(distanceMeters / 1000).toFixed(1)} 公里` : "待核验"}</b><small>${transfers.length} 段 · 约 ${transferMinutes} 分钟</small></div>
    <div><span>预算偏好</span><b>${escapeHtml(String(budget))}</b><small>${budget === "未设置" ? "不生成虚假费用" : "按偏好规划"}</small></div>
  </section>`;
}

function renderMobilitySummary(plan, profile) {
  const mobility = object(plan.mobility_summary);
  if (!list(profile.mobility_needs).length && !mobility.transfer_count) return "";
  const distance = Number(mobility.walking_distance_meters) || 0;
  const unknown = Number(mobility.walking_distance_unknown) || 0;
  const rest = Number(mobility.rest_minutes) || 0;
  const longest = Number(mobility.longest_visit_minutes) || 0;
  const status = mobility.status === "high" ? "需要优先调整" : mobility.status === "partial" ? "部分未知" : "已测路线";
  const detail = distance ? `${(distance / 1000).toFixed(1)} 公里` : "步行距离待核验";
  return `<section class="mobility-strip ${mobility.status === "high" ? "high" : ""}" aria-label="行动负荷">
    <div><b>行动负荷 · ${status}</b><p>${list(profile.mobility_needs).length ? escapeHtml(list(profile.mobility_needs).join("、")) : "按当前路线估算"}</p></div>
    <dl><div><dt>接驳步行</dt><dd>${detail}</dd></div><div><dt>休息</dt><dd>${rest ? `${rest} 分钟` : "未单列"}</dd></div><div><dt>最长游览</dt><dd>${longest ? `${longest} 分钟` : "待定"}</dd></div></dl>
    <small>${unknown ? `${unknown} 段步行距离未核验；` : "步行数据来自已列地图路线；"}景区内部、餐厅门口和实际酒店门口不在统计内。</small>
  </section>`;
}

function renderWeather(weather) {
  const report = object(weather);
  const days = list(report.days);
  if (!days.length) {
    return `<section class="manual-card weather-card unavailable"><header><b>天气与穿着</b><span>待日期</span></header><p>尚未提供准确出发日期，因此不展示可能过期的天气预报。确定日期后重新生成即可补齐。</p><ul><li>出发前 24 小时复核降雨、温度和紫外线。</li><li>随身准备饮用水、折叠伞和舒适步行鞋。</li></ul></section>`;
  }
  return `<section class="manual-card weather-card"><header><b>天气与穿着</b><span>${textOr(sourceLabels[report.provider], "天气数据")}</span></header><div class="weather-days">${days.map((day) => `<div><span>${textOr(day.date, "日期待定")}</span><b>${textOr(day.condition, "天气待确认")}</b><small>${textOr(day.low === null || day.low === undefined ? "" : String(day.low), "?")}—${textOr(day.high === null || day.high === undefined ? "" : String(day.high), "?")}℃${day.wind ? ` · ${escapeHtml(day.wind)}` : ""}</small></div>`).join("")}</div><p>临近出发仍应复核短时降雨、体感温度和景区临时通知。</p></section>`;
}

function money(value, currency="CNY") {
  return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value)) ? `${currency === "CNY" ? "¥" : `${currency} `}${Number(value).toLocaleString("zh-CN")}` : "待核价";
}

function renderExecutionModules(plan) {
  const hotels = list(plan.hotel_options);
  const transport = object(plan.transport_options);
  const intercity = list(transport.intercity);
  const local = list(transport.local);
  const localStrategy = object(transport.local_strategy);
  const dining = list(plan.dining_options);
  const bookings = list(plan.booking_tasks);
  const budget = object(plan.budget);
  const safety = object(plan.safety);
  const unknowns = list(plan.unknowns);
  const categoryRows = list(budget.categories);
  const safetyItems = [
    ...list(safety.destination_alerts),
    ...list(safety.medical),
    ...list(safety.transport_risks),
    ...list(safety.food_safety),
    ...list(safety.altitude_notes),
    ...list(safety.special_population_notes),
  ];
  const selectedMode = localStrategy.selected || object(plan.trip_profile).transport_preference;
  return `<section class="decision-modules">
    <header class="manual-title"><div><span>DECISIONS & ACTIONS</span><h2>选择、费用与待办</h2></div><p>把可比较选项、未核实信息和出发前动作拆开呈现。</p></header>
    <div class="decision-grid">
      <section class="decision-card module-hotels">
        <header><b>住宿选项</b><span>${hotels.length} 个</span></header>
        <div class="choice-list">${hotels.map((hotel) => `<article class="${hotel.selected ? "selected" : ""}">
          <div><strong>${textOr(hotel.name, "住宿待确认")}</strong>${hotel.selected ? "<i>当前锚点</i>" : "<i>候选</i>"}</div>
          <p>${textOr(hotel.destination)} · ${textOr(hotel.address || hotel.area, "位置待确认")}</p>
          <small>${textOr(hotel.reason, "房型、库存、价格与取消政策待核验")}</small>
          <div class="choice-facts"><span>${money(hotel.price_per_night, budget.currency)}</span><span>${hotel.cancellation ? escapeHtml(String(hotel.cancellation)) : "取消政策待核验"}</span></div>
        </article>`).join("") || "<p>住宿选项待补充</p>"}</div>
      </section>
      <section class="decision-card module-transport">
        <header><b>交通选项</b><span>${local.length} 段市内 · ${intercity.length} 段城际</span></header>
        <p class="module-lead">市内偏好：${textOr(modeLabels[selectedMode], "待确认")}；${textOr(list(localStrategy.notes).join("；"), "逐段耗时以日程中的地图路线为准。")}</p>
        <div class="choice-list compact">${intercity.map((item) => `<article>
          <div><strong>D${item.day} ${textOr(item.from)} → ${textOr(item.to)}</strong><i>${textOr(modeLabels[item.mode], textOr(item.mode, "待选"))}</i></div>
          <p>${textOr(item.train_code, "班次待核验")} · ${textOr(item.departure_hint, "出发时段待核验")} → ${textOr(item.arrival_hint, "抵达时段待核验")}</p>
          <small>${item.status === "verified_schedule" || item.status === "stale_schedule" ? `${textOr(item.seat_type, "参考席别")} ${money(item.price)}；时刻与参考票价来自 12306，余票未接入` : "班次、票价与余票待核验"}</small>
        </article>`).join("") || `<p>${local.length ? `已形成 ${local.length} 段市内路线；没有跨城移动。` : "交通方案待补充"}</p>`}</div>
      </section>
      <section class="decision-card module-dining">
        <header><b>餐饮选项</b><span>${dining.length} 餐</span></header>
        <div class="task-list">${dining.map((item) => `<div>
          <b>D${item.day} · ${textOr(periodLabels[item.period], "用餐")}</b>
          <span><strong>${textOr(item.name, "餐厅待确认")}</strong><small>${textOr(item.description, "当天按路线和口味就近选择。")}</small>${item.area ? `<em>${textOr(item.area)}</em>` : ""}${list(item.alternatives).length ? `<em>备选：${list(item.alternatives).map((alt) => textOr(alt.name)).join("、")}</em>` : ""}</span>
        </div>`).join("") || "<p>餐饮点待补充</p>"}</div>
      </section>
      <section class="decision-card module-bookings">
        <header><b>预订与核对清单</b><span>${bookings.length} 项</span></header>
        <div class="task-list">${bookings.map((task) => `<div>
          <b>D${task.day}</b><span><strong>${textOr(task.target_name, "项目待确认")}</strong><small>${textOr(task.action, "出发前核对")}</small></span><i class="${task.status === "action_required" ? "urgent" : ""}">${task.status === "action_required" ? "需预约" : "待核实"}</i>
        </div>`).join("") || "<p>当前没有待办；仍建议出发前复核开放状态。</p>"}</div>
      </section>
      <section class="decision-card module-budget">
        <header><b>预算分配</b><span>${textOr(budget.coverage, "未估算")}</span></header>
        <div class="budget-total"><span>用户预算上限</span><strong>${money(object(budget.user_limit).total_max || budget.planning_ceiling, budget.currency)}</strong><small>不是实时价格报价</small></div>
        <div class="budget-bars">${categoryRows.map((item) => `<div><span>${textOr(item.label)}</span><b>${money(item.planning_cap, budget.currency)}</b></div>`).join("") || "<p>未提供金额，无法可靠拆分预算。</p>"}</div>
        <ul>${list(budget.assumptions).map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>
      </section>
      <section class="decision-card module-safety">
        <header><b>安全与特殊人群</b><span>${textOr(safety.source_status, "unavailable")}</span></header>
        ${safetyItems.length ? `<ul>${safetyItems.map((item) => `<li>${textOr(object(item).note || object(item).detail || item)}</li>`).join("")}</ul>` : "<p>未接入官方目的地安全信息；不要把空白理解为没有风险。</p>"}
        ${unknowns.length ? `<details><summary>当前未知项 ${unknowns.length} 条</summary><ul>${unknowns.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul></details>` : ""}
      </section>
    </div>
  </section>`;
}

function renderEvidence(evidence) {
  const records = list(evidence);
  if (!records.length) return "";
  return `<section class="surface"><div class="section-label"><span>事实来源</span><span>${records.length} 条证据</span></div><div class="evidence-list">${records.map((item) => {
    const title = `<b>${textOr(item.title, "来源记录")}</b><small>${textOr(sourceLabels[item.provider], textOr(item.provider, "未知来源"))} · 置信度 ${textOr(item.confidence, "unknown")}</small>`;
    return item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${title}<span>打开 ↗</span></a>` : `<div>${title}<span>内部响应指纹</span></div>`;
  }).join("")}</div></section>`;
}


function renderTravelManual(plan, days, hotel, profile) {
  const schedules = days
    .flatMap((day) => list(day.schedule).map((item) => ({...item, day:day.day})))
    .filter((item) => item.type === "visit" || object(item.reservation).required === true);
  const transfers = days.flatMap((day) => list(day.transfers));
  const verifiedRoutes = transfers.filter((item) => item.source === "amap").length;
  const estimatedRoutes = transfers.length - verifiedRoutes;
  const hotelMap = hotel.location ? `<a href="https://uri.amap.com/marker?position=${encodeURIComponent(hotel.location)}&name=${encodeURIComponent(hotel.name)}" target="_blank" rel="noreferrer">打开住宿地图 ↗</a>` : "";
  const assumptions = list(profile.assumptions).slice(0, 4);
  const checklist = [
    "身份证件、优惠证件与同行人联系方式",
    "酒店、门票和交通订单的离线截图",
    "充电器、移动电源与常用药品",
    "折叠伞、防晒用品、饮用水和舒适鞋",
    "保存住宿地址及每天最后一段返程路线",
    "出发前复核营业时间、预约状态与末班交通",
  ];
  return `<section class="travel-manual">
    <header class="manual-title"><div><span>TRAVEL NOTES</span><h2>行前手册</h2></div><p>把会影响当天执行的信息集中放在这里，不用逐段翻找。</p></header>
    <div class="manual-grid">
      <section class="manual-card stay-transit-card">
        <header><b>住宿与交通</b><span>${verifiedRoutes}/${transfers.length} 段已核验</span></header>
        <h3>${textOr(hotel.name, "住宿区域待确认")}</h3>
        <p>${textOr(hotel.address || hotel.area, "住宿地址待确认")}</p>
        <dl><div><dt>主要交通</dt><dd>${textOr(modeLabels[profile.transport_preference], "待确认")}</dd></div><div><dt>地图查询路线</dt><dd>${verifiedRoutes} 段</dd></div><div><dt>保守估算</dt><dd>${estimatedRoutes} 段</dd></div></dl>
        ${hotelMap}
      </section>
      ${renderWeather(plan.weather)}
    </div>
    <section class="reservation-board">
      <header><b>预约与营业核对</b><span>${schedules.length} 项</span></header>
      <div class="reservation-list">${schedules.map((item) => {
        const reservation = object(item.reservation);
        const reservationLabel = reservation.required === true ? "必须预约" : reservation.required === false ? "无需预约" : "预约待确认";
        const openingLabel = item.opening_match === "matched" ? "时段可用" : item.opening_match === "risk" ? "时间冲突" : "开放待确认";
        return `<div><b>D${Number(item.day) || 1}</b><span>${textOr(item.name, "地点待确认")}</span><em>${openingLabel}</em><i>${reservationLabel}</i></div>`;
      }).join("")}</div>
    </section>
    <div class="manual-grid compact">
      <section class="manual-card packing-card"><header><b>随身清单</b><span>通用</span></header><ul>${checklist.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>
      <section class="manual-card assumptions-card"><header><b>规划边界</b><span>${assumptions.length || 1} 项</span></header>${assumptions.length ? `<ul>${assumptions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : "<p>票价、排队时间和临时闭园不会在没有实时证据时写死；请以出发当天官方信息为准。</p>"}</section>
    </div>
  </section>`;
}

function renderFeedback(runId) {
  if (!runId || runId === "published") return "";
  return `<section class="feedback-card" data-feedback-run="${escapeHtml(runId)}" aria-label="行程反馈">
    <div><span class="section-label">帮我们校准下一版</span><h2>这份行程现在能直接照着走吗？</h2><p>只记录这一版的结果，不会公开你的行程内容。</p></div>
    <div class="feedback-actions"><button type="button" data-feedback="direct_use">可以，直接照着走</button><button type="button" data-feedback="needs_changes">需要再调整</button><button type="button" data-feedback="inaccurate">有信息不准确</button></div>
  </section>`;
}

function renderQuickStart(days) {
  const firstDay = object(days[0]);
  const firstVisit = list(firstDay.schedule).find((item) => item.type === "visit") || list(firstDay.schedule)[0];
  if (!firstDay.day && !firstVisit) return "";
  const firstName = firstVisit?.name || "当天第一站";
  const firstTime = firstVisit?.start && firstVisit?.end ? `${firstVisit.start}–${firstVisit.end}` : "按当天节奏出发";
  return `<section class="quick-start" aria-label="从这里开始">
    <div><span class="section-label">从这里开始</span><h2>先照着第一天走，其他天按需调整</h2><p>D${Number(firstDay.day) || 1} · ${textOr(firstDay.theme, "城市探索")} · ${escapeHtml(firstName)} · ${escapeHtml(firstTime)}</p></div>
    <a class="quick-start-link" href="#day-${Number(firstDay.day) || 1}">查看第一天 <span aria-hidden="true">↓</span></a>
  </section>`;
}

function renderPlan(data, publicView=false) {
  if (!data.plan) return;
  const plan = data.plan;
  const days = list(plan.days);
  const narrative = object(plan.narrative);
  const narrativeView = compactNarrative(plan, narrative, days);
  const profile = object(plan.trip_profile);
  const hotel = object(plan.hotel);
  const completeness = object(plan.completeness);
  const validationWarnings = list(object(plan.validation).warnings);
  const globalWarnings = list(plan.warnings);
  const score = Math.max(0, Math.min(100, Number(completeness.score) || 0));
  const highlights = narrativeView.highlights;
  const runLabel = String(data.run_id || "published").slice(0, 10);
  const paceLabel = ({relaxed:"松弛慢游",balanced:"松弛有序",intensive:"行程充实",packed:"行程充实"})[profile.pace] || textOr(profile.pace, "节奏待定");
  const transportLabel = modeLabels[profile.transport_preference] || textOr(profile.transport_preference, "交通待定");
  const hotelStatusLabel = ({confirmed:"已确认",recommended_area:"推荐住宿区域",unknown:"待确认"})[hotel.status] || textOr(hotel.status, "待确认");
  const requestedParty = object(object(plan.planning_context).party);
  const travelerLabel = profile.travelers && profile.travelers !== "未指定" ? profile.travelers
    : [requestedParty.adults ? `${requestedParty.adults} 位成人` : "", requestedParty.children ? `${requestedParty.children} 位儿童` : ""].filter(Boolean).join(" · ") || "同行人待定";
  const visits = days.flatMap(day => list(day.schedule)).filter(item => item.type === "visit");
  const routes = days.flatMap(day => list(day.transfers));
  const locatedVisits = visits.filter(item => item.place_id && item.location && list(item.evidence_refs).length).length;
  const checkedRoutes = routes.filter(item => item.source === "amap" && list(item.evidence_refs).length).length;
  const pendingBookings = list(plan.booking_tasks).filter(item => item.status === "needs_verification").length;
  const actions = publicView
    ? '<button class="plan-action" data-action="image">保存长图</button><button class="plan-action" data-action="print">导出 PDF</button><a class="plan-action" href="/">生成我的行程</a>'
    : '<button class="plan-action" data-action="share">分享行程</button><button class="plan-action" data-action="image">保存长图</button><button class="plan-action" data-action="print">导出 PDF</button>';
  const dayNav = days.map((day) => `<a href="#day-${Number(day.day) || 1}" class="day-jump day-jump-${((Number(day.day) || 1) - 1) % 5 + 1}"><b>D${Number(day.day) || 1}</b><span>${textOr(day.theme, "城市探索")}</span></a>`).join("");
  const rawWarnings = [
    ...globalWarnings,
    ...validationWarnings.map((warning) => warning.message || "开放、预约或交通信息请在出发前再次确认"),
  ].map((warning) => String(warning || "").trim()).filter(Boolean);
  const dateWarnings = rawWarnings.filter((warning) => /出发日期|天气/.test(warning));
  const routeWarnings = rawWarnings.filter((warning) => /路线.*未核验|交通.*未核验/.test(warning));
  const openingWarnings = rawWarnings.filter((warning) => /开放时间未知|开放状态.*未核验|开放.*待确认/.test(warning));
  const groupedWarnings = rawWarnings.filter((warning) =>
    !dateWarnings.includes(warning) && !routeWarnings.includes(warning) && !openingWarnings.includes(warning));
  const allWarnings = [...new Set([...dateWarnings, ...groupedWarnings])];
  if (openingWarnings.length) allWarnings.push(`${openingWarnings.length} 条开放或预约信息需要在出发前复核。`);
  if (routeWarnings.length) allWarnings.push(`${routeWarnings.length} 处交通衔接尚未核验，包含餐厅位置未定的接驳；出发前请重新导航。`);
  resultPanel.innerHTML = `${publicView ? '<div class="public-notice">这是已发布行程的只读快照；开放时间、天气和交通请在出发前再次确认。</div>' : ""}
    <header class="plan-hero guide-cover">
      <div class="cover-copy">
        <span class="kicker">TOUR PASS · ${textOr(plan.city)} · ${days.length} DAYS</span>
        <h1>${textOr(plan.title, `${textOr(plan.city)}旅行计划`)}</h1>
        <details class="cover-overview"><summary>路线说明与规划假设</summary><p>${textOr(narrativeView.summary, "行程总览待补充")}</p></details>
        <div class="hero-meta">
          <span>${paceLabel}</span>
          <span>${transportLabel}</span>
          <span>${textOr(travelerLabel)}</span>
        </div>
      </div>
      <div class="guide-stamp" aria-label="行程完整度">
        <strong>${score}</strong><span>完整度</span><small>${days.length} 日路线</small>
      </div>
      <div class="plan-actions">${actions}</div>
    </header>
    ${renderQuickStart(days)}
    <details class="evidence-drawer">
      <summary><b>核验状态</b><span>地点 ${locatedVisits}/${visits.length} · 路线 ${checkedRoutes}/${routes.length} · 待确认 ${pendingBookings}</span></summary>
      <section class="evidence-strip" aria-label="本次核验范围">
        <div><b>已生成 · 出发前仍需确认</b><p>地点坐标与路线查询不代表开放、预约或无障碍条件已确认。完整度分数只反映信息结构。</p></div>
        <small>餐厅与酒店未确定时，区域接驳还需复核；天气以具体出行日期为准。</small>
      </section>
    </details>
    <div class="plan-body guide-sheet">
      ${renderTraceSummary()}
      ${renderTripStats(plan, days, profile)}
      ${renderMobilitySummary(plan, profile)}
      <nav class="day-jumpbar" aria-label="按天查看行程">${dayNav}</nav>
      <section class="guide-intro">
        <div><span class="section-label">这趟怎么玩</span><h2>${textOr(narrative.headline, "一眼看懂这趟旅程")}</h2><p>${textOr(narrativeView.summary, "行程说明待补充")}</p></div>
        <div class="guide-highlights">${highlights.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
      </section>
      <section class="stay-card">
        <div class="stay-mark" aria-hidden="true">⌂</div>
        <div><span>住宿据点 · ${hotelStatusLabel}</span><h3>${textOr(hotel.name)}</h3><p>${textOr(hotel.area)} · ${textOr(hotel.reason, "住宿选择理由待补充")}</p></div>
      </section>
      ${days.map(renderDay).join("")}
      ${renderExecutionModules(plan)}
      ${renderTravelManual(plan, days, hotel, profile)}
      ${renderFeedback(data.run_id)}
      ${allWarnings.length ? `<section class="travel-notes"><header><b>出发前再看一眼</b><span>${allWarnings.length} 项</span></header><ul>${allWarnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></section>` : ""}
      <details class="guide-drawer">
        <summary><span><b>规划依据与完整度</b><small>地图坐标、候选区域、质量检查和技术审查</small></span><i><span class="drawer-expand">展开</span><span class="drawer-collapse">收起</span></i></summary>
        <div class="guide-drawer-body">
          <div class="lower-grid">
            ${renderComparison(object(plan.candidate_comparison))}
            ${renderMap(object(plan.map))}
          </div>
          <div class="drawer-section">${renderEvidence(plan.evidence)}</div>
          <div class="drawer-section">${renderQuality(completeness)}</div>
          <div class="drawer-section">${renderReview(object(plan.review))}</div>
          ${validationWarnings.length ? `<div class="drawer-section">${renderRisks(validationWarnings.map((warning) => ({level:"warning",title:warning.code === "OPENING_UNVERIFIED" ? "开放状态待确认" : "校验提示",detail:warning.message,source:"unknown"})))}</div>` : ""}
        </div>
      </details>
      <footer class="guide-footer"><span>TOUR PASS · 行程快照</span><span>run ${escapeHtml(runLabel)}</span></footer>
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

function parseDestinationPlan(value, fallback) {
  const raw = String(value || "").trim();
  const source = raw || String(fallback || "");
  const parts = source.split(/[、，,;；→]/).map((item) => item.trim()).filter(Boolean);
  if (parts.length < 2 && !raw) return [];
  return parts.map((part) => {
    const match = part.match(/^(.+?)(?:\s*[:：]?\s*(\d+)\s*天?)?$/);
    const result = {name: String(match?.[1] || part).trim()};
    if (match?.[2]) result.days = Number(match[2]);
    return result;
  }).filter((item) => item.name);
}

function addDays(dateValue, count) {
  if (!dateValue) return null;
  const value = new Date(`${dateValue}T12:00:00`);
  value.setDate(value.getDate() + Math.max(Number(count) - 1, 0));
  return value.toISOString().slice(0, 10);
}

function optionalNumber(value) {
  const raw = String(value ?? "").trim();
  return raw === "" ? null : Number(raw);
}

function endpointPeriod(time) {
  if (!time) return "";
  const hour = Number(String(time).slice(0, 2));
  if (hour < 6 || hour >= 22) return "late_night";
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}


function buildStructuredMessage() {
  const data = new FormData(tripForm);
  const city = String(data.get("destination") || "").trim();
  const days = optionalNumber(data.get("days"));
  const parts = [
    days
      ? `请为我规划${city}${days}天行程`
      : `请为我规划${city}行程，天数和目的地数量请按合理体验安排`
  ];
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
  const displayValues = {
    pace: $("pace").selectedOptions[0]?.textContent || "",
    transport: $("transport").selectedOptions[0]?.textContent || ""
  };
  optional.forEach(([name, label]) => {
    const value = String(displayValues[name] || data.get(name) || "").trim();
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

function buildStructuredRequest() {
  const data = new FormData(tripForm);
  const destination = String(data.get("destination") || "").trim();
  const days = optionalNumber(data.get("days"));
  const startDate = String(data.get("start_date") || "").trim();
  const destinationPlan = String(data.get("destination_plan") || "").trim();
  const arrivalTime = String(data.get("arrival_time") || "").trim();
  const departureTime = String(data.get("departure_time") || "").trim();
  const budgetMin = optionalNumber(data.get("budget_min"));
  const budgetMax = optionalNumber(data.get("budget_max"));
  const budgetPerPerson = optionalNumber(data.get("budget_per_person"));
  const includesTransport = String(data.get("includes_major_transport") || "");
  const rooms = optionalNumber(data.get("rooms"));
  const budgetRange = [budgetMin, budgetMax, budgetPerPerson].some((value) => value !== null) || includesTransport
    ? {
        total_min: budgetMin,
        total_max: budgetMax,
        per_person: budgetPerPerson,
        currency: "CNY",
        includes_major_transport: includesTransport === "" ? null : includesTransport === "true"
      }
    : null;
  return {
    destination,
    destinations: parseDestinationPlan(destinationPlan, destination),
    days,
    nights: days === null ? null : Math.max(days - 1, 0),
    date_range: {
      start: startDate || null,
      end: days === null ? null : addDays(startDate, days)
    },
    arrival: {
      date: String(data.get("arrival_date") || "").trim() || startDate || null,
      time: arrivalTime || null,
      period: endpointPeriod(arrivalTime),
      city: "",
      station: String(data.get("arrival_station") || "").trim()
    },
    departure: {
      date: String(data.get("departure_date") || "").trim() || (days === null ? null : addDays(startDate, days)),
      time: departureTime || null,
      period: endpointPeriod(departureTime),
      city: "",
      station: String(data.get("departure_station") || "").trim()
    },
    hotel_area: String(data.get("hotel_area") || "").trim(),
    hotel_preferences: String(data.get("hotel_preferences") || "").trim(),
    travellers: String(data.get("travelers") || "").trim(),
    party: {
      adults: Number(data.get("adults") || 1),
      children_ages: splitValues(data.get("children_ages")).map(Number).filter(Number.isFinite),
      seniors: Number(data.get("seniors") || 0),
      rooms,
      bed_requirement: String(data.get("bed_requirement") || "").trim()
    },
    pace: String(data.get("pace") || "balanced"),
    transport_preference: String(data.get("transport") || "mixed"),
    intercity_preferences: splitValues(data.get("intercity_preferences")),
    budget: String(data.get("budget") || "").trim(),
    budget_range: budgetRange,
    must_visits: splitValues(data.get("must_visits")),
    notes: String(data.get("notes") || "").trim(),
    interests: data.getAll("interest").map(String),
    dietary_requirements: splitValues(data.get("dietary_requirements")),
    mobility_needs: splitValues(data.get("mobility_needs")),
    booking_preferences: String(data.get("booking_preferences") || "").trim(),
    daily_window: {
      start: String(data.get("day_start") || "09:00"),
      end: String(data.get("day_end") || "20:00")
    }
  };
}

async function submitPlanning(message, trip=null) {
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
      body: JSON.stringify({message, trip, session_id: sessionId, model: activeModel()})
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

function collectPageCss() {
  return Array.from(document.styleSheets).map((sheet) => {
    try {
      return Array.from(sheet.cssRules).map((rule) => rule.cssText).join("\n");
    } catch {
      return "";
    }
  }).join("\n");
}

async function exportPlanImage(trigger) {
  const title = resultPanel.querySelector(".guide-cover h1")?.textContent?.trim() || "Tour-Pass-行程";
  const width = window.matchMedia("(max-width: 760px)").matches ? 720 : 1080;
  const exportRoot = document.createElement("div");
  exportRoot.className = "trip-export-frame";
  exportRoot.setAttribute("xmlns", "http://www.w3.org/1999/xhtml");
  Object.assign(exportRoot.style, {
    position: "fixed",
    left: "-20000px",
    top: "0",
    width: `${width}px`,
    padding: "24px",
    background: "#eaf0eb",
    zIndex: "-1",
  });
  [resultPanel.querySelector(".guide-cover"), resultPanel.querySelector(".evidence-strip"), resultPanel.querySelector(".guide-sheet")]
    .filter(Boolean)
    .forEach((node) => exportRoot.append(node.cloneNode(true)));
  exportRoot.querySelectorAll(".plan-actions,.run-trace,.day-jumpbar,.guide-drawer").forEach((node) => node.remove());
  exportRoot.querySelectorAll("details").forEach((node) => { node.open = true; });
  document.body.append(exportRoot);
  const previousLabel = trigger?.textContent;
  if (trigger) {
    trigger.disabled = true;
    trigger.textContent = "正在生成…";
  }
  try {
    await document.fonts.ready;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const height = Math.ceil(exportRoot.getBoundingClientRect().height);
    const style = document.createElement("style");
    style.textContent = collectPageCss();
    exportRoot.prepend(style);
    const renderRoot = exportRoot.cloneNode(true);
    Object.assign(renderRoot.style, {position:"static", left:"auto", top:"auto", width:`${width}px`, zIndex:"auto"});
    const markup = new XMLSerializer().serializeToString(renderRoot);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><foreignObject width="100%" height="100%">${markup}</foreignObject></svg>`;
    const svgDataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    const image = new Image();
    image.decoding = "sync";
    image.src = svgDataUrl;
    await image.decode();
    const scale = Math.max(1, Math.min(2, 30000 / height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("当前浏览器无法创建图片画布");
    context.scale(scale, scale);
    context.drawImage(image, 0, 0, width, height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("浏览器未能生成 PNG");
    const imageUrl = URL.createObjectURL(blob);
    const download = document.createElement("a");
    download.href = imageUrl;
    download.download = `${title.replace(/[\\/:*?"<>|]/g, "-")}-长图.png`;
    download.click();
    setTimeout(() => URL.revokeObjectURL(imageUrl), 1000);
    showToast(`高清长图已生成：${canvas.width} × ${canvas.height}`);
  } finally {
    exportRoot.remove();
    if (trigger) {
      trigger.disabled = false;
      trigger.textContent = previousLabel;
    }
  }
}

resultPanel.addEventListener("click", async (event) => {
  const feedback = event.target.closest("[data-feedback]");
  if (feedback) {
    const buttons = resultPanel.querySelectorAll("[data-feedback]");
    buttons.forEach((button) => { button.disabled = true; });
    try {
      const response = await apiFetch("/api/feedback", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
        kind: feedback.dataset.feedback,
        run_id: resultPanel.querySelector("[data-feedback-run]")?.dataset.feedbackRun || "unknown",
        session_id: sessionId,
      })});
      if (!response.ok) throw new Error("反馈暂时未送达");
      feedback.classList.add("selected");
      showToast("收到，这会帮助我们改进行程建议");
    } catch (error) {
      buttons.forEach((button) => { button.disabled = false; });
      showToast(error.message);
    }
    return;
  }
  const trigger = event.target.closest("[data-action]");
  const action = trigger?.dataset.action;
  if (action === "print") {
    window.print();
    return;
  }
  if (action === "image") {
    try {
      await exportPlanImage(trigger);
    } catch (error) {
      showToast(`长图生成失败：${error.message}`);
    }
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
  const trip = buildStructuredRequest();
  switchInputMode("conversation");
  await submitPlanning(message, trip);
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
$("use-example").addEventListener("click", () => {
  input.value = $("full-example").textContent.trim();
  input.focus();
});


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


$("llm-model")?.addEventListener("change", (event) => {
  selectedModel = event.target.value;
  localStorage.setItem("tour-pass-model", selectedModel);
  $("custom-model").value = "";
});
$("custom-model")?.addEventListener("change", (event) => {
  const value = event.target.value.trim();
  if (value) localStorage.setItem("tour-pass-model", value);
});

panelToggle.addEventListener("click", () => {
  setPlanningPanelCollapsed(!assistantPanel.classList.contains("collapsed"));
});
setPlanningPanelCollapsed(localStorage.getItem("tour-pass-panel-collapsed") === "true");

(async function bootstrap() {
  try {
    await loadModels();
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
    else switchInputMode("conversation");
  } catch (error) {
    sessionId = null;
    localStorage.removeItem("tour-pass-active-session");
    setSessionMode(false);
    switchInputMode("conversation");
    showToast(error.message || "页面初始化失败");
  }
})();
