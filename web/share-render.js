// share-render.js — renders shared trip data from window.__SHARE_DATA__
(function() {
  var COLORS = ["#146b5d", "#c25b1e", "#2563eb", "#9333ea", "#dc2626", "#0d9488", "#d97706"];
  var ICONS = { attraction: "\u{1F3DB}", restaurant: "\u{1F35C}", hotel: "\u{1F3E8}", nightlife: "\u{1F319}", transit: "\u{1F687}" };
  function icon(t) { return ICONS[t] || "\u{1F4CD}"; }
  function transportIcon(m) { if (m <= 0) return ""; if (m <= 15) return "\u{1F6B6}"; if (m <= 30) return "\u{1F68C}"; return "\u{1F695}"; }
  function esc(t) { var d = document.createElement("div"); d.textContent = t || ""; return d.innerHTML; }
  function estimateCost(stops) {
    var lo = 0, hi = 0;
    for (var i = 0; i < stops.length; i++) {
      var t = stops[i].poi_type || "";
      if (t === "attraction") { lo += 20; hi += 80; }
      else if (t === "restaurant") { lo += 30; hi += 100; }
      else if (t === "nightlife") { lo += 50; hi += 150; }
    }
    var tr = stops.reduce(function(a, s) { return a + (s.travel_minutes_from_previous || 0); }, 0);
    lo += Math.round(tr * 0.5); hi += Math.round(tr * 2);
    return { lo: lo, hi: hi };
  }

  var data = window.__SHARE_DATA__;
  if (!data) {
    document.getElementById("content").innerHTML = '<div class="no-data"><h2>\u{1F615}</h2><p>行程数据加载失败</p></div>';
    return;
  }

  var resp;
  try {
    var rj = data.response_json;
    resp = typeof rj === "string" ? JSON.parse(rj) : (rj || {});
  } catch (e) {
    console.error("Failed to parse response_json:", e);
    resp = {};
  }
  var days = resp.days || [];
  var title = data.title || "旅行行程";
  var totalLo = 0, totalHi = 0, totalStops = 0, totalTravel = 0;
  for (var i = 0; i < days.length; i++) {
    var cost = estimateCost(days[i].stops || []);
    totalLo += cost.lo; totalHi += cost.hi;
    totalStops += (days[i].stops || []).length;
    totalTravel += (days[i].total_travel_minutes || 0);
  }

  var html = '<div class="share-header">'
    + '<h1>\u{1F5FA}️ ' + esc(title) + '</h1>'
    + '<p>由 Tour Pass AI 生成 · ' + days.length + '天行程</p>'
    + '</div>'
    + '<div id="shareMap" class="share-map"></div>'
    + '<div class="legend">' + days.map(function(d, i) {
      return '<span><span class="dot" style="background:' + COLORS[i % COLORS.length] + '"></span>Day ' + d.day + '</span>';
    }).join("") + '</div>'
    + '<div class="stats-row">'
    + '<div class="stat"><strong>' + days.length + '</strong><span>天</span></div>'
    + '<div class="stat"><strong>' + totalStops + '</strong><span>站</span></div>'
    + '<div class="stat"><strong>' + totalTravel + '</strong><span>分钟通勤</span></div>'
    + '<div class="stat"><strong>¥' + totalLo + '-' + totalHi + '</strong><span>预估花费</span></div>'
    + '</div>';

  days.forEach(function(day) {
    var stops = day.stops || [];
    var cost = estimateCost(stops);
    html += '<div class="day-block">'
      + '<div class="day-title">Day ' + day.day + '</div>'
      + '<div class="day-stats">' + stops.length + '站 · ' + (day.total_travel_minutes || 0) + 'min通勤 · ≈¥' + cost.lo + '-' + cost.hi + '</div>';
    stops.forEach(function(stop, j) {
      var tr = stop.travel_minutes_from_previous || 0;
      html += '<div class="stop-card">'
        + (tr > 0 ? '<div class="stop-transport">' + transportIcon(tr) + ' ' + tr + '分钟</div>' : '')
        + '<div class="stop-main">'
        + '<div class="stop-icon">' + icon(stop.poi_type) + '</div>'
        + '<div class="stop-info">'
        + '<div><span class="stop-name">' + esc(stop.poi_name) + '</span><span class="stop-time">' + esc(stop.start_time || "") + '-' + esc(stop.end_time || "") + '</span></div>'
        + '<div class="stop-meta">' + esc(stop.area || "") + '</div>'
        + '<div class="stop-reason">' + esc(stop.reason || "") + '</div>'
        + (stop.recommendation ? '<div class="stop-tip">\u{1F4A1} ' + esc(stop.recommendation) + '</div>' : '')
        + '</div></div></div>';
    });
    html += '</div>';
  });

  html += '<div class="cost-bar">全程预估花费：<strong>¥' + totalLo + '-' + totalHi + '</strong>（含门票、餐饮、交通估算）</div>'
    + '<div class="share-footer">由 <a href="/">Tour Pass</a> AI 旅行规划生成</div>';

  document.getElementById("content").innerHTML = html;

  // Render map
  if (typeof L !== "undefined") {
    var map = L.map("shareMap");
    L.tileLayer("https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}", { subdomains: "1234", maxZoom: 18, attribution: '© 高德地图' }).addTo(map);
    var bounds = [], idx = 0;
    days.forEach(function(day, di) {
      var color = COLORS[di % COLORS.length], coords = [];
      (day.stops || []).forEach(function(stop) {
        if (!stop.lat || !stop.lng) return;
        idx++;
        var c = [stop.lat, stop.lng]; bounds.push(c); coords.push(c);
        var ic = L.divIcon({ className: "", html: '<div style="background:' + color + ';color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.3);">' + idx + '</div>', iconSize: [24, 24], iconAnchor: [12, 12] });
        L.marker(c, { icon: ic }).addTo(map).bindPopup('<strong>' + esc(stop.poi_name) + '</strong><br>' + icon(stop.poi_type) + ' ' + stop.start_time + '-' + stop.end_time + '<br>' + esc(stop.area || ""));
      });
      if (coords.length > 1) L.polyline(coords, { color: color, weight: 3, opacity: 0.7, dashArray: di > 0 ? "6 4" : null }).addTo(map);
    });
    if (bounds.length > 0) map.fitBounds(bounds, { padding: [30, 30] });
  }
})();
