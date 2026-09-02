"use strict";

const $ = (id) => document.getElementById(id);

function setStatus(text, ok = false) {
  $("status").innerHTML = `<span class="dot ${ok ? "ok" : ""}"></span><span>${text}</span>`;
}

document.querySelectorAll(".chips").forEach((group) => {
  group.addEventListener("click", (event) => {
    const button = event.target.closest(".chip");
    if (!button) return;
    group.querySelectorAll(".chip").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    $(group.dataset.target).value = button.dataset.value;
  });
});

$("clear").addEventListener("click", () => {
  $("days").value = "";
  $("dateStart").value = "";
  $("mustVisit").value = "";
  $("hotelArea").value = "";
  $("special").value = "";
  $("result").innerHTML = '<div class="empty"><div><b>01</b>左侧提交后，这里会展示<br>实体、时间、通勤与风险。</div></div>';
  setStatus("等待一次提交");
});

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
}[char]));

function parseSse(text) {
  return text.split(/\n/)
    .filter((line) => line.startsWith("data: "))
    .map((line) => {
      try { return JSON.parse(line.slice(6)); } catch { return null; }
    })
    .filter(Boolean);
}

function render(data) {
  const itinerary = data.itinerary;
  if (!itinerary) {
    $("result").innerHTML = `<div class="error">${escapeHtml(data.error || "规划失败")}</div>`;
    return;
  }
  const assumptions = (itinerary.warnings || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const days = (itinerary.days || []).map((day) => `<article class="day">
    <div class="day-top"><strong>DAY ${day.day}</strong><span>${escapeHtml(day.date || "")} · 通勤 ${day.total_travel_minutes || 0} 分钟</span></div>
    <div class="theme">${escapeHtml(day.theme || "城市探索")}</div>
    <div class="stops">${(day.stops || []).map((stop) => `<div class="stop">
      <div class="time">${escapeHtml(stop.start_time || "")}<br>${escapeHtml(stop.end_time || "")}</div>
      <div><div class="stop-name">${escapeHtml(stop.poi_name)}</div><div class="stop-meta">${escapeHtml(stop.area)} · ${escapeHtml(stop.poi_type)} · ${stop.travel_minutes_from_previous || 0} 分钟通勤</div></div>
      <div class="verified">${escapeHtml(stop.route_source || "route")}</div>
    </div>`).join("")}</div>
    ${day.warnings?.length ? `<div class="risk">${day.warnings.map(escapeHtml).join("；")}</div>` : ""}
  </article>`).join("");
  $("result").innerHTML = `<div class="result-head"><div><h2>${escapeHtml(itinerary.city)} · ${itinerary.days?.length || 0} 天</h2><div class="run-id">run ${escapeHtml(data.planning_run_id || itinerary.planning_run_id || "")}</div></div><span class="badge">HARD CHECK PASSED</span></div>${assumptions ? `<div class="assumptions"><strong>本次采用的假设</strong><ul>${assumptions}</ul></div>` : ""}<div class="days">${days}</div>`;
}

$("planForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("submit");
  button.disabled = true;
  setStatus("正在生成骨架，随后核验地点与路线");
  const payload = {
    city: $("city").value,
    days: $("days").value || null,
    date_start: $("dateStart").value || null,
    pace: $("pace").value,
    strategy: $("strategy").value,
    must_visit: $("mustVisit").value,
    hotel_area: $("hotelArea").value,
    special_requests: $("special").value,
    transport_mode: "driving",
  };
  try {
    const response = await fetch("/api/itineraries/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const events = parseSse(await response.text());
    const result = events.find((item) => item.type === "itinerary");
    const error = events.find((item) => item.type === "error");
    if (!response.ok || !result) throw new Error(error?.content || "规划失败");
    render(result);
    setStatus(`已完成 · ${result.planning_run_id || "run ready"}`, true);
  } catch (error) {
    $("result").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
    setStatus("规划未完成");
  } finally {
    button.disabled = false;
  }
});
