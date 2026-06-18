const state = {
  candidates: [],
  selectedIndex: 0,
  lastPayload: null,
  activeStage: "overview",
  user: null,
  token: localStorage.getItem("tp_token") || null,
  tripSaved: false,
  savedTripId: null,
  planAbortController: null,
};

let planMap = null;
let routeMap = null;
let mapDayLayers = []; // Array of { markers: L.LayerGroup, polyline: L.Polyline } per day
let mapMarkerByPoiId = {}; // poiId -> L.Marker for card-marker interaction
let searchResultMarkers = null; // L.LayerGroup for search result markers

// ---- Session state persistence (temporary, will be replaced by Hash routing in Phase 4) ----
function saveTripState() {
  try {
    sessionStorage.setItem("tp_candidates", JSON.stringify(state.candidates));
    sessionStorage.setItem("tp_selectedIndex", String(state.selectedIndex));
    sessionStorage.setItem("tp_lastPayload", JSON.stringify(state.lastPayload));
    sessionStorage.setItem("tp_activeStage", state.activeStage);
    sessionStorage.setItem("tp_tripSaved", String(state.tripSaved));
    sessionStorage.setItem("tp_savedTripId", String(state.savedTripId || ""));
  } catch (e) { /* quota exceeded or private browsing */ }
}

function restoreTripState() {
  try {
    const candidates = sessionStorage.getItem("tp_candidates");
    if (!candidates) return false;
    const parsed = JSON.parse(candidates);
    if (!Array.isArray(parsed) || parsed.length === 0) return false;
    state.candidates = parsed;
    state.selectedIndex = parseInt(sessionStorage.getItem("tp_selectedIndex") || "0", 10);
    state.lastPayload = JSON.parse(sessionStorage.getItem("tp_lastPayload") || "null");
    state.activeStage = sessionStorage.getItem("tp_activeStage") || "overview";
    state.tripSaved = sessionStorage.getItem("tp_tripSaved") === "true";
    const savedId = sessionStorage.getItem("tp_savedTripId");
    state.savedTripId = savedId && savedId !== "null" ? savedId : null;
    return true;
  } catch (e) { return false; }
}

// ---- Toast notifications ----
function toast(message, type = "info", actionHtml = "") {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span class="toast-msg">${message}</span>${actionHtml ? `<span class="toast-actions">${actionHtml}</span>` : ""}`;
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.add("toast-show"));
  setTimeout(() => {
    el.classList.remove("toast-show");
    el.addEventListener("transitionend", () => el.remove());
  }, 4000);
}

const DAY_COLORS = ["#146b5d", "#c25b1e", "#2563eb", "#9333ea", "#dc2626", "#0d9488", "#d97706"];

function typeIcon(type) {
  const icons = { attraction: "🏛", restaurant: "🍜", hotel: "🏨", nightlife: "🌙", transit: "🚇" };
  return icons[type] || "📍";
}

function leafletReady() {
  return typeof window.L !== "undefined";
}

function addBaseTileLayer(map) {
  // OSM as default (no API key required, ToS compliant)
  var osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  });
  osm.addTo(map);
  // Amap light tiles as optional overlay (requires Amap JS API key for production use)
  var amapLight = L.tileLayer("https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}", {
    subdomains: "1234", maxZoom: 18, attribution: '&copy; 高德地图'
  });
  L.control.layers({"OpenStreetMap": osm, "高德极简": amapLight}, null, {position: "topright"}).addTo(map);
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
  mapMarkerByPoiId = {};
  if (planMap) { planMap.remove(); planMap = null; }
  planMap = L.map(mapDiv, {
    zoomControl: true,
    attributionControl: true,
    // 禁止通过点击地图添加任何内容
    tap: true,
  });
  addBaseTileLayer(planMap);

  const bounds = [];
  mapDayLayers = [];

  candidate.days.forEach((day, dayIndex) => {
    const color = DAY_COLORS[dayIndex % DAY_COLORS.length];
    const dayCoords = [];
    const markerGroup = L.layerGroup();
    let dayStopIndex = 0;

    for (const stop of day.stops || []) {
      if (!stop.lat || !stop.lng) continue;
      dayStopIndex++;
      const coord = [stop.lat, stop.lng];
      bounds.push(coord);
      dayCoords.push(coord);

      const markerIcon = L.divIcon({
        className: "numbered-marker",
        html: `<div class="map-marker" style="background:${color}" data-poi-id="${stop.poi_id || ""}" data-day-idx="${dayIndex}" data-stop-idx="${dayStopIndex - 1}">
          <span class="map-marker-num">${dayStopIndex}</span>
        </div>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -16],
      });

      // Minimal popup: name + time only. Details in card sidebar.
      const marker = L.marker(coord, { icon: markerIcon, draggable: true });
      const popupImg = stop.image_url ? '<img src="' + stop.image_url + '" class="map-popup-img" loading="lazy" onerror="this.style.display=\'none\'">' : '';
      marker.bindPopup(
        '<div class="map-popup">' + popupImg +
          '<div class="map-popup-name">' + escapeHtml(stop.poi_name) + '</div>' +
          '<div class="map-popup-time">' + typeIcon(stop.poi_type) + ' ' + escapeHtml(stop.start_time) + '-' + escapeHtml(stop.end_time) + '</div>' +
        '</div>'
      );
      marker._tourpass = { poiId: stop.poi_id, dayIndex: dayIndex, stopIndex: dayStopIndex - 1 };
      marker.addTo(markerGroup);
      if (stop.poi_id) mapMarkerByPoiId[stop.poi_id] = marker;
    }

    markerGroup.addTo(planMap);
    let polyline = null;
    if (dayCoords.length > 1) {
      polyline = L.polyline(dayCoords, {
        color, weight: 3, opacity: 0.7,
        dashArray: dayIndex > 0 ? "6 4" : null,
      }).addTo(planMap);
    }

    mapDayLayers.push({ markers: markerGroup, polyline, color, dayIndex });
  });

  if (bounds.length > 0) planMap.fitBounds(bounds, { padding: [30, 30] });
  setTimeout(() => planMap.invalidateSize(), 50);
  initMapDragReorder();
  loadUnselectedPois();
}

/* ── Show unselected attraction POIs on map ── */
let unselectedPoiLayer = null;
async function loadUnselectedPois() {
  if (!planMap) return;
  if (unselectedPoiLayer) { planMap.removeLayer(unselectedPoiLayer); unselectedPoiLayer = null; }
  const city = state.lastPayload && state.lastPayload.city || "";
  if (!city) return;
  try {
    const res = await api("/poi/search?city=" + encodeURIComponent(city) + "&limit=500");
    const allPois = res.data || [];
    const candidate = state.candidates[state.selectedIndex];
    const usedIds = new Set();
    const usedNames = new Set();
    if (candidate && candidate.days) {
      candidate.days.forEach(function(d) { (d.stops||[]).forEach(function(s) {
        if (s.poi_id) usedIds.add(s.poi_id);
        if (s.poi_name) usedNames.add(s.poi_name);
      });});
    }
    const unselected = allPois.filter(function(p) {
      return !usedIds.has(p.id) && !usedNames.has(p.name) && p.lat && p.lng;
    });
    if (unselected.length === 0) return;
    unselectedPoiLayer = L.layerGroup();
    unselected.forEach(function(poi) {
      var typeColors = {attraction:"#3b82f6", restaurant:"#f97316", nightlife:"#a855f7", transit:"#6b7280"};
      var color = typeColors[poi.type] || "#94a3b8";
      var icon = L.divIcon({
        className: "unselected-poi-marker",
        html: '<div style="width:12px;height:12px;border-radius:50%;background:'+color+';border:1.5px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:pointer;opacity:0.7;"></div>',
        iconSize: [12, 12],
        iconAnchor: [6, 6],
        popupAnchor: [0, -8],
      });
      var marker = L.marker([poi.lat, poi.lng], {icon: icon});
      var days = (candidate && candidate.days) || [];
      var btns = days.map(function(d) {
        return '<button class="poi-day-add-btn" data-poi-idx="' + poi.id + '" data-day-idx="' + (d.day - 1) + '" style="padding:2px 6px;border:1px solid #146b5d;border-radius:3px;background:#146b5d;color:#fff;font-size:10px;cursor:pointer;margin:1px;">Day ' + d.day + '</button>';
      }).join("");
      if (!window.__browsePoiMap) window.__browsePoiMap = {};
      window.__browsePoiMap[poi.id] = poi;
      marker.bindPopup(
        '<div style="min-width:140px">' +
          '<div style="font-weight:600;font-size:13px;">' + typeIcon(poi.type) + ' ' + escapeHtml(poi.name) + '</div>' +
          '<div style="font-size:11px;color:#65706d;">' + escapeHtml(poi.area) + (poi.popularity ? ' · ⭐' + Number(poi.popularity).toFixed(1) : '') + '</div>' +
          (poi.description ? '<div style="font-size:12px;color:#444;margin-top:4px;line-height:1.4;">' + escapeHtml(String(poi.description).slice(0,80)) + (String(poi.description).length > 80 ? '...' : '') + '</div>' : '') +
          (poi.recommendation ? '<div style="font-size:11px;color:#146b5d;margin-top:3px;font-style:italic;">💡 ' + escapeHtml(String(poi.recommendation).slice(0,60)) + '</div>' : '') +
          '<div style="margin-top:6px;display:flex;gap:3px;flex-wrap:wrap;align-items:center;">' +
            '<span style="font-size:10px;color:#888;">添加到：</span>' + btns +
          '</div>' +
        '</div>'
      );
      marker.addTo(unselectedPoiLayer);
    });
    unselectedPoiLayer.addTo(planMap);
  } catch(e) { console.warn("Load unselected POIs failed:", e); }
}

/* ── Add POI to a specific day ── */
function addPoiToDay(poi, dayIdx) {
  var candidate = state.candidates[state.selectedIndex];
  if (!candidate || !candidate.days || !candidate.days[dayIdx]) { toast("无效的天数", "error"); return; }
  var day = candidate.days[dayIdx];
  var visitDuration = 60;
  if (poi.type === "restaurant") { visitDuration = poi.meal_type === "drink" ? 30 : 60; }
  var newStop = {
    poi_id: poi.id || ("browse_" + Date.now()),
    poi_name: poi.name,
    poi_type: poi.type || "attraction",
    meal_type: poi.meal_type || "main",
    area: poi.area || "",
    lat: poi.lat,
    lng: poi.lng,
    start_time: "00:00",
    end_time: "00:00",
    visit_duration_minutes: visitDuration,
    travel_minutes_from_previous: 0,
    score: 0,
    reason: "手动添加",
    recommendation: poi.recommendation || "",
    slot: "自由时间",
    time_window_status: "ok",
  };
  day.stops = day.stops || [];
  day.stops.push(newStop);
  recalcDayTimes(day);
  renderPlan();
  saveTripState();
  toast("已添加 " + poi.name + " 到 Day " + day.day, "success");
}

/* ── Event delegation: add unselected POI to day ── */
document.addEventListener("click", function(e) {
  var btn = e.target.closest(".poi-day-add-btn");
  if (!btn) return;
  try {
    var poiId = btn.dataset.poiIdx;
    var dayIdx = parseInt(btn.dataset.dayIdx, 10);
    var poi = window.__browsePoiMap && window.__browsePoiMap[poiId];
    if (poi) addPoiToDay(poi, dayIdx);
  } catch(err) { console.error("Add POI to day error:", err); }
});

function initMapDayFilter(candidate) {
  const filterContainer = $("mapDayFilter");
  if (!filterContainer) return;
  filterContainer.addEventListener("click", (e) => {
    const btn = e.target.closest(".map-filter-btn");
    if (!btn) return;
    // Update active state
    filterContainer.querySelectorAll(".map-filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const dayVal = btn.dataset.day;
    if (dayVal === "all") {
      // Show all days
      mapDayLayers.forEach(layer => {
        layer.markers.addTo(planMap);
        if (layer.polyline) layer.polyline.addTo(planMap);
      });
      // Fit bounds to all
      const allBounds = [];
      mapDayLayers.forEach(layer => {
        layer.markers.eachLayer(m => { if (m.getLatLng) allBounds.push(m.getLatLng()); });
      });
      if (allBounds.length > 0) planMap.fitBounds(allBounds, { padding: [30, 30] });
    } else {
      const dayIdx = parseInt(dayVal, 10);
      mapDayLayers.forEach((layer, i) => {
        if (i === dayIdx) {
          layer.markers.addTo(planMap);
          if (layer.polyline) layer.polyline.addTo(planMap);
        } else {
          planMap.removeLayer(layer.markers);
          if (layer.polyline) planMap.removeLayer(layer.polyline);
        }
      });
      // Fit bounds to selected day
      const dayBounds = [];
      mapDayLayers[dayIdx]?.markers.eachLayer(m => { if (m.getLatLng) dayBounds.push(m.getLatLng()); });
      if (dayBounds.length > 0) planMap.fitBounds(dayBounds, { padding: [40, 40] });
    }
  });
}

function initMapDragReorder() {
  if (!planMap) return;
  // Listen for dragend on all markers
  planMap.eachLayer(function(layer) {
    if (layer instanceof L.Marker && layer._tourpass) {
      layer.on("dragend", function(e) {
        var info = e.target._tourpass;
        var candidate = state.candidates[state.selectedIndex];
        if (!candidate || !candidate.days) return;
        var day = candidate.days[info.dayIndex];
        if (!day || !day.stops) return;
        var draggedStop = day.stops[info.stopIndex];
        if (!draggedStop) return;

        // Find nearest stop to the new position to determine new order
        var newPos = e.target.getLatLng();
        var nearestIdx = info.stopIndex;
        var nearestDist = Infinity;
        day.stops.forEach(function(s, i) {
          if (i === info.stopIndex || !s.lat || !s.lng) return;
          var dx = s.lat - newPos.lat;
          var dy = s.lng - newPos.lng;
          var dist = dx * dx + dy * dy;
          if (dist < nearestDist) { nearestDist = dist; nearestIdx = i; }
        });

        // Reorder: move dragged stop to nearest position
        if (nearestIdx !== info.stopIndex) {
          day.stops.splice(info.stopIndex, 1);
          day.stops.splice(nearestIdx, 0, draggedStop);
          // Recalculate times
          recalcDayTimes(day);
          // Re-render cards and map
          renderPlan();
          toast("行程顺序已更新", "info");
        }
      });
    }
  });
}

function initCardMarkerInteraction() {
  // Hover day card stop -> highlight map marker
  document.addEventListener("mouseenter", (e) => {
    if (!(e.target instanceof HTMLElement)) return;
    const stopEl = e.target.closest(".day-card-stop[data-poi-id]");
    if (!stopEl || !stopEl.dataset.poiId) return;
    const marker = mapMarkerByPoiId[stopEl.dataset.poiId];
    if (marker) {
      const el = marker.getElement()?.querySelector(".map-marker");
      if (el) { el.style.transform = "scale(1.3)"; el.style.zIndex = "1000"; }
    }
    stopEl.classList.add("map-highlight");
  }, true);
  document.addEventListener("mouseleave", (e) => {
    if (!(e.target instanceof HTMLElement)) return;
    const stopEl = e.target.closest(".day-card-stop[data-poi-id]");
    if (!stopEl || !stopEl.dataset.poiId) return;
    const marker = mapMarkerByPoiId[stopEl.dataset.poiId];
    if (marker) {
      const el = marker.getElement()?.querySelector(".map-marker");
      if (el) { el.style.transform = ""; el.style.zIndex = ""; }
    }
    stopEl.classList.remove("map-highlight");
  }, true);

  // Click day card stop -> pan map to marker and open popup
  document.addEventListener("click", (e) => {
    const stopEl = e.target.closest(".day-card-stop[data-poi-id]");
    if (!stopEl || !stopEl.dataset.poiId) return;
    const marker = mapMarkerByPoiId[stopEl.dataset.poiId];
    if (marker && planMap) {
      planMap.setView(marker.getLatLng(), Math.max(planMap.getZoom(), 15), { animate: true });
      marker.openPopup();
    }
  });

  // Click map marker -> scroll to corresponding card
  document.addEventListener("click", (e) => {
    const mapMarkerEl = e.target.closest(".map-marker");
    if (!mapMarkerEl) return;
    const poiId = mapMarkerEl.dataset.poiId;
    if (!poiId) return;
    const cardStop = document.querySelector(`.day-card-stop[data-poi-id="${poiId}"]`);
    if (cardStop) {
      cardStop.scrollIntoView({ behavior: "smooth", block: "center" });
      cardStop.classList.add("map-highlight");
      setTimeout(() => cardStop.classList.remove("map-highlight"), 2000);
    }
  });
}

// Initialize card-marker interaction once
initCardMarkerInteraction();

// ---- Map POI Search (Amap integration) ----
function initMapSearch() {
  const input = $("mapSearchInput");
  const resultsDiv = $("mapSearchResults");
  if (!input || !resultsDiv) return;

  let debounceTimer = null;
  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (q.length < 2) { resultsDiv.hidden = true; return; }
    debounceTimer = setTimeout(() => doMapSearch(q), 400);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      clearTimeout(debounceTimer);
      const q = input.value.trim();
      if (q.length >= 2) doMapSearch(q);
    }
    if (e.key === "Escape") { resultsDiv.hidden = true; }
  });

  // Close on click outside
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".map-search-box")) resultsDiv.hidden = true;
  });
}

async function doMapSearch(query) {
  const resultsDiv = $("mapSearchResults");
  if (!resultsDiv) return;
  resultsDiv.hidden = false;
  resultsDiv.innerHTML = '<div style="padding:10px;font-size:12px;color:var(--muted);">搜索中...</div>';

  try {
    const city = $("city")?.value?.trim() || state.lastPayload?.city || "";
    const data = await api(`/poi/amap-search?q=${encodeURIComponent(query)}&city=${encodeURIComponent(city)}&limit=10`);
    const pois = data.data || [];
    if (pois.length === 0) {
      resultsDiv.innerHTML = '<div style="padding:10px;font-size:12px;color:var(--muted);">未找到结果</div>';
      return;
    }

    resultsDiv.innerHTML = pois.map((poi, i) => `
      <div class="map-search-item" data-index="${i}">
        <span>📍</span>
        <div>
          <div class="search-name">${escapeHtml(poi.name)}</div>
          <div class="search-addr">${escapeHtml(poi.district || "")} ${escapeHtml(poi.address || "")}</div>
        </div>
        <button class="search-add-btn" data-index="${i}">+ 添加</button>
      </div>
    `).join("");

    // Show search results on map
    showSearchResultsOnMap(pois);

    // Handle clicks
    resultsDiv.querySelectorAll(".map-search-item").forEach(item => {
      item.addEventListener("click", (e) => {
        if (e.target.closest(".search-add-btn")) return; // handled separately
        const idx = parseInt(item.dataset.index, 10);
        const poi = pois[idx];
        if (poi && planMap) planMap.setView([poi.lat, poi.lng], 16, { animate: true });
      });
    });

    resultsDiv.querySelectorAll(".search-add-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.dataset.index, 10);
        const poi = pois[idx];
        if (poi) addSearchPoiToItinerary(poi);
      });
    });
  } catch (err) {
    resultsDiv.innerHTML = `<div style="padding:10px;font-size:12px;color:#c0392b;">搜索失败: ${escapeHtml(err.message)}</div>`;
  }
}

function showSearchResultsOnMap(pois) {
  if (!planMap || !leafletReady()) return;
  // Remove old search markers
  if (searchResultMarkers) { planMap.removeLayer(searchResultMarkers); }

  searchResultMarkers = L.layerGroup();
  pois.forEach(poi => {
    if (!poi.lat || !poi.lng) return;
    const icon = L.divIcon({
      className: "search-marker-cluster",
      html: `<div style="background:#ff6b35;color:#fff;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3);opacity:0.85;">📍</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      popupAnchor: [0, -16],
    });
    const marker = L.marker([poi.lat, poi.lng], { icon });
    const popupId = 'poi_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
    // Store for retrieval by day-add buttons
    if (!window.__browsePoiMap) window.__browsePoiMap = {};
    window.__browsePoiMap[popupId] = poi;
    var candidate = state.candidates[state.selectedIndex];
    var dayBtns = ((candidate && candidate.days) || []).map(function(d) {
      return '<button class="poi-day-add-btn" data-poi-idx="' + popupId + '" data-day-idx="' + (d.day - 1) + '" style="padding:2px 6px;border:1px solid #146b5d;border-radius:3px;background:#146b5d;color:#fff;font-size:10px;cursor:pointer;margin:1px;">Day ' + d.day + '</button>';
    }).join("");
    marker.bindPopup(`
      <div style="min-width:160px;">
        <div style="font-weight:700;font-size:13px;">${escapeHtml(poi.name)}</div>
        <div style="font-size:11px;color:#65706d;">${escapeHtml(poi.district || "")} ${escapeHtml(poi.address || "")}</div>
        ${poi.rating ? `<div style="font-size:11px;margin-top:2px;">⭐ ${poi.rating}</div>` : ""}
        <div style="margin-top:6px;display:flex;gap:3px;flex-wrap:wrap;align-items:center;">
          <span style="font-size:10px;color:#888;">添加到：</span>${dayBtns}
        </div>
      </div>
    `);
    marker.addTo(searchResultMarkers);
  });
  searchResultMarkers.addTo(planMap);
}

function addSearchPoiToItinerary(poi) {
  if (!poi || !poi.lat || !poi.lng) return;
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate?.days?.length) { toast("请先生成行程再添加", "info"); return; }

  // Auto-detect POI type
  var poiType = poi.type || "attraction";
  var mealType = poi.meal_type || "main";
  var visitDuration = 60;
  if (poiType === "restaurant") {
    if (mealType === "drink") { visitDuration = 30; }
    else { visitDuration = 60; }
  }

  // Find best day to add (prefer day with fewest stops, or day 1)
  var targetDay = candidate.days[0];
  var minStops = (targetDay.stops || []).length;
  candidate.days.forEach(function(d) {
    var count = (d.stops || []).length;
    if (count < minStops) { minStops = count; targetDay = d; }
  });

  var newStop = {
    poi_id: poi.id || ("browse_" + Date.now()),
    poi_name: poi.name,
    poi_type: poiType,
    meal_type: mealType,
    area: poi.area || poi.district || "",
    lat: poi.lat,
    lng: poi.lng,
    start_time: "00:00",
    end_time: "00:00",
    visit_duration_minutes: visitDuration,
    travel_minutes_from_previous: 0,
    score: 0,
    reason: "地图浏览添加",
    recommendation: poi.recommendation || "",
    slot: "自由时间",
    time_window_status: "ok",
  };
  targetDay.stops = targetDay.stops || [];
  targetDay.stops.push(newStop);
  recalcDayTimes(targetDay);

  renderPlan();
  saveTripState();
  toast("已添加 " + poi.name + " 到第 " + targetDay.day + " 天", "success");

  // Clean up search markers
  if (searchResultMarkers && planMap) {
    planMap.removeLayer(searchResultMarkers);
    searchResultMarkers = null;
  }
  var resultsDiv = $("mapSearchResults");
  if (resultsDiv) resultsDiv.hidden = true;
  var input = $("mapSearchInput");
  if (input) input.value = "";
}

// ---- POI Browser: browse all POIs on map by category ----
let browsePoiLayers = {}; // type -> L.layerGroup

function initPoiBrowse() {
  const bar = document.getElementById("poiBrowseBar");
  if (!bar) return;
  bar.addEventListener("click", function(e) {
    const btn = e.target.closest(".poi-browse-btn");
    if (!btn) return;
    const type = btn.dataset.browseType;
    const mealFilter = btn.dataset.mealFilter;
    const key = mealFilter ? type + ":" + mealFilter : type;
    btn.classList.toggle("active");
    if (btn.classList.contains("active")) {
      loadPoiBrowseLayer(type, mealFilter, key);
    } else {
      hidePoiBrowseLayer(key);
    }
  });
}

async function loadPoiBrowseLayer(type, mealFilter, key) {
  if (!planMap) return;
  if (browsePoiLayers[key]) {
    browsePoiLayers[key].addTo(planMap);
    return;
  }
  const city = document.getElementById("city")?.value?.trim() || state.lastPayload?.city || "";
  try {
    const res = await api("/poi/browse?city=" + encodeURIComponent(city) + "&type=" + type + "&limit=80");
    const pois = (res.data || []).filter(function(p) {
      if (mealFilter === "drink") return p.meal_type === "drink";
      if (mealFilter === "snack") return p.meal_type === "snack";
      if (type === "restaurant" && !mealFilter) return p.meal_type === "main";
      return true;
    });
    const layer = L.layerGroup();
    var typeColors = {attraction:"#10b981", restaurant:"#f59e0b", nightlife:"#8b5cf6"};
    var color = typeColors[type] || "#6b7280";
    pois.forEach(function(poi) {
      if (!poi.lat || !poi.lng) return;
      // Check if already in itinerary
      var inItinerary = false;
      var candidate = state.candidates[state.selectedIndex];
      if (candidate?.days) {
        candidate.days.forEach(function(d) {
          (d.stops||[]).forEach(function(s) { if (s.poi_name === poi.name) inItinerary = true; });
        });
      }
      if (inItinerary) return;
      var icon = L.divIcon({
        className: "poi-browse-marker-wrap",
        html: '<div class="poi-browse-marker" style="background:' + color + '"></div>',
        iconSize: [14, 14],
        iconAnchor: [7, 7],
        popupAnchor: [0, -10],
      });
      var marker = L.marker([poi.lat, poi.lng], {icon: icon});
      var rec = poi.recommendation ? '<div class="poi-browse-rec">' + escapeHtml(poi.recommendation.slice(0,60)) + '</div>' : '';
      marker.bindPopup(
        '<div class="poi-browse-popup">' +
          '<div class="poi-browse-name">' + escapeHtml(poi.name) + '</div>' +
          '<div class="poi-browse-meta">' + typeIcon(poi.type) + ' ' + escapeHtml(poi.area) + ' · 热度 ' + (poi.popularity||0).toFixed(1) + '</div>' +
          rec +
          '<button class="poi-browse-add" data-poi=\'' + escapeHtml(JSON.stringify(poi)) + '\'>+ 添加到行程</button>' +
        '</div>'
      );
      marker.addTo(layer);
    });
    browsePoiLayers[key] = layer;
    layer.addTo(planMap);
    toast("已显示 " + pois.length + " 个" + (mealFilter === "drink" ? "茶饮" : type === "attraction" ? "景点" : type === "restaurant" ? "美食" : "夜生活") + " POI", "info");
  } catch(e) {
    console.error("POI browse error:", e);
  }
}

function hidePoiBrowseLayer(key) {
  if (browsePoiLayers[key] && planMap) {
    planMap.removeLayer(browsePoiLayers[key]);
  }
}

// Event delegation for "Add to itinerary" from browse popups
document.addEventListener("click", function(e) {
  var btn = e.target.closest(".poi-browse-add");
  if (!btn) return;
  try {
    var poi = JSON.parse(btn.dataset.poi);
    addSearchPoiToItinerary(poi);
  } catch(err) { console.error("Browse add error:", err); }
});

// Initialize map search on first render
setTimeout(initMapSearch, 100);

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
    city: $("city").value.trim() || "",
    days: Number($("days").value || 2),
    start_time: $("startTime").value.trim() || "09:30",
    end_time: $("endTime").value.trim() || "21:30",
    hotel_location: $("hotelLocation").value.trim() || "",
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
  let data = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      if (!response.ok) throw new Error("服务返回了无法解析的响应");
      data = null;
    }
  }
  // Update query remaining from response header
  const remaining = response.headers.get("X-Query-Remaining");
  if (remaining !== null) updateQueryCounter(parseInt(remaining));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth")) {
      // Don't auto-logout — show confirmation to preserve user state
      const shouldRelogin = confirm("登录已过期，是否重新登录？\n（取消可继续浏览当前页面）");
      if (shouldRelogin) {
        logout();
      }
      throw new Error("登录已过期，请重新登录");
    }
    throw new Error(data?.error?.message || `请求失败 (${response.status})`);
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
  const urlParams = new URLSearchParams(window.location.search);
  const showParam = urlParams.get("show");
  // If guest user lands on ?show=register, redirect to register form
  if (state.user?.role === "guest" && showParam === "register") {
    $("authOverlay").hidden = false;
    $("mainApp").hidden = true;
    $("authLoginForm").hidden = true;
    $("authRegisterForm").hidden = true;
    $("authEmailForm").hidden = false;
    return;
  }
  $("authOverlay").hidden = true;
  $("mainApp").hidden = false;
  $("userBadge").textContent = state.user?.username || "";
  updateQueryCounter(state.user?.query_remaining);
  // Show admin link for admin users
  const adminLink = $("adminLink");
  if (adminLink) adminLink.hidden = state.user?.role !== "admin";
  // Guest retention banner
  let guestBanner = document.getElementById("guestRetentionBanner");
  if (state.user?.role === "guest") {
    if (!guestBanner) {
      guestBanner = document.createElement("div");
      guestBanner.id = "guestRetentionBanner";
      guestBanner.className = "guest-retention-banner";
      guestBanner.innerHTML = `<span>游客数据保留 7 天，<a href="/?show=register">注册账号</a>可长期保存</span>`;
      document.querySelector(".app-shell")?.insertBefore(guestBanner, document.querySelector(".workspace"));
    }
    guestBanner.hidden = false;
  } else if (guestBanner) {
    guestBanner.hidden = true;
  }
  loadHealth();
  // Restore trip state from sessionStorage if available
  if (restoreTripState() && state.candidates.length > 0) {
    renderPlan();
    setStage(state.activeStage);
  } else {
    renderHotRecommendations();
  }
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
  document.body.style.visibility = "visible";
  if (!state.token) { showAuth(); return; }
  try {
    const data = await api("/auth/me");
    state.user = data;
    showApp();
    handleRoute();
  } catch (e) {
    console.warn("checkAuth:", e.message);
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
  } catch (e) {
    console.warn("loadHealth:", e.message);
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
  window.__currentCandidate = (state.candidates || [])[state.selectedIndex] || (state.candidates || [])[0] || null;

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
      ${(candidate.days || []).map(renderDay).join("")}
    </section>
    <section class="stage-section" data-plan-section="debug">
      ${renderComparisonTable()}
      ${renderAlgorithmDebug(candidate)}
    </section>
  `;
  bindComparisonCards();
  renderOverviewMap(candidate);
  initDragDrop();
  initMapDayFilter(candidate);
  initMapSearch();
  initPoiBrowse();
  // Fetch weather asynchronously
  const city = state.lastPayload?.city || "";
  fetchWeather(city).then(weather => {
    const bar = $("weatherBar");
    if (bar && weather) bar.innerHTML = renderWeatherBar(weather, candidate.days || []);
  });
  // Fetch guidebook
  loadGuidebook(city);

  // City consistency check
  if (city && candidate.city && candidate.city !== city) {
    toast(`注意：AI 返回的是「${candidate.city}」的行程，但你选择的城市是「${city}」`, "error");
  }
}

// ---- Drag & Drop itinerary editing ----
let dragState = { dayIndex: -1, stopIndex: -1, el: null };

function initDragDrop() {
  // Desktop: HTML5 Drag and Drop
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

  // Mobile: Touch drag support
  initTouchDrag();
}

let touchDragState = { active: false, card: null, clone: null, startX: 0, startY: 0, dayIdx: -1, stopIdx: -1 };

function initTouchDrag() {
  document.querySelectorAll(".stop-card[draggable]").forEach(card => {
    card.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 1) return;
      const touch = e.touches[0];
      const stopList = card.closest(".stop-list");
      const dayBlock = card.closest(".day-block");
      const dayIdx = [...document.querySelectorAll(".day-block")].indexOf(dayBlock);
      const stopIdx = [...stopList.querySelectorAll(".stop-card")].indexOf(card);
      touchDragState = { active: false, card, clone: null, startX: touch.clientX, startY: touch.clientY, dayIdx, stopIdx, moved: false };
    }, { passive: true });

    card.addEventListener("touchmove", (e) => {
      if (!touchDragState.card) return;
      const touch = e.touches[0];
      const dx = touch.clientX - touchDragState.startX;
      const dy = touch.clientY - touchDragState.startY;

      // Start dragging after 10px movement
      if (!touchDragState.active && Math.abs(dy) > 10) {
        touchDragState.active = true;
        touchDragState.moved = true;
        card.classList.add("dragging");
        // Create visual clone
        const clone = card.cloneNode(true);
        clone.style.position = "fixed";
        clone.style.zIndex = "9999";
        clone.style.width = card.offsetWidth + "px";
        clone.style.opacity = "0.85";
        clone.style.pointerEvents = "none";
        clone.style.boxShadow = "0 4px 16px rgba(0,0,0,0.2)";
        document.body.appendChild(clone);
        touchDragState.clone = clone;
      }

      if (touchDragState.active) {
        e.preventDefault();
        if (touchDragState.clone) {
          touchDragState.clone.style.left = (touch.clientX - 20) + "px";
          touchDragState.clone.style.top = (touch.clientY - 20) + "px";
        }
        // Highlight drop target
        document.querySelectorAll(".drag-over").forEach(el => el.classList.remove("drag-over"));
        const target = document.elementFromPoint(touch.clientX, touch.clientY);
        const targetList = target?.closest(".stop-list");
        if (targetList) {
          const afterEl = getDragAfterElement(targetList, touch.clientY);
          if (afterEl) afterEl.classList.add("drag-over");
        }
      }
    }, { passive: false });

    card.addEventListener("touchend", () => {
      if (!touchDragState.moved) { touchDragState = { active: false, card: null, clone: null, dayIdx: -1, stopIdx: -1 }; return; }
      if (touchDragState.active) {
        card.classList.remove("dragging");
        document.querySelectorAll(".drag-over").forEach(el => el.classList.remove("drag-over"));
        if (touchDragState.clone) { touchDragState.clone.remove(); }

        // Find drop target
        const clone = touchDragState.clone;
        if (clone) {
          const rect = clone.getBoundingClientRect();
          const centerX = rect.left + rect.width / 2;
          const centerY = rect.top + rect.height / 2;
          clone.remove();
          const target = document.elementFromPoint(centerX, centerY);
          const targetList = target?.closest(".stop-list");
          if (targetList) {
            const targetDayBlock = targetList.closest(".day-block");
            const targetDayIdx = [...document.querySelectorAll(".day-block")].indexOf(targetDayBlock);
            const afterEl = getDragAfterElement(targetList, centerY);
            let targetStopIdx = afterEl
              ? [...targetList.querySelectorAll(".stop-card")].indexOf(afterEl)
              : targetList.querySelectorAll(".stop-card").length;
            moveStop(touchDragState.dayIdx, touchDragState.stopIdx, targetDayIdx, targetStopIdx);
          }
        }
      }
      touchDragState = { active: false, card: null, clone: null, dayIdx: -1, stopIdx: -1 };
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
  const totalTravelMin = days.reduce((s, d) => s + (d.total_travel_minutes || 0), 0);

  return `
    <div class="overview-header">
      <div class="overview-stats">
        <div class="overview-stat"><strong>${days.length}</strong><span>天</span></div>
        <div class="overview-stat"><strong>${totalStops}</strong><span>站</span></div>
        <div class="overview-stat"><strong>${totalTravelMin}</strong><span>分钟通勤</span></div>
        <div class="overview-stat accent"><strong>¥${totalLo}-${totalHi}</strong><span>预估花费</span></div>
      </div>
      <div class="overview-actions">
        <button class="primary-action small" id="saveTripBtn" type="button">💾 保存行程</button>
        <button class="secondary-action small" id="shareTripBtn" type="button">🔗 分享</button>
        <button class="secondary-action small" id="shareImageBtn" type="button">📸 生成图片</button>
        <button class="secondary-action small" id="exportBtn" type="button">🖨️ 导出/打印</button>
        <button class="secondary-action small" id="navAmapBtn" type="button">🗺️ 导航到高德</button>
      </div>
    </div>

    <div class="overview-map-section">
      <div id="overviewMapWrap" class="overview-map-wrap">
        <div id="map"></div>
        <div class="map-search-box" id="mapSearchBox">
          <input id="mapSearchInput" type="text" placeholder="🔍 搜索景点、餐厅..." />
          <div id="mapSearchResults" class="map-search-results" hidden></div>
        </div>
        <div class="map-day-filter" id="mapDayFilter">
          <button class="map-filter-btn active" data-day="all">全部</button>
          ${days.map((d, i) => `<button class="map-filter-btn" data-day="${i}" style="--filter-color:${DAY_COLORS[i % DAY_COLORS.length]}">Day ${d.day}</button>`).join("")}
        </div>
      </div>
      <div class="map-legend">
        ${days.map((d, i) => `<span class="legend-item"><span class="legend-dot" style="background:${DAY_COLORS[i % DAY_COLORS.length]}"></span>Day ${d.day} · ${d.stops?.length || 0} 站</span>`).join("")}
      </div>
      <div class="poi-browse-bar" id="poiBrowseBar">
        <span class="poi-browse-label">浏览 POI：</span>
        <button class="poi-browse-btn" data-browse-type="attraction">🏛 景点</button>
        <button class="poi-browse-btn" data-browse-type="restaurant">🍜 美食</button>
        <button class="poi-browse-btn poi-browse-drink" data-browse-type="restaurant" data-meal-filter="drink">☕ 茶饮</button>
        <button class="poi-browse-btn" data-browse-type="nightlife">🌙 夜生活</button>
      </div>
    </div>

    <div id="weatherBar"></div>
    <div id="guidebookSection"></div>

    <div class="day-cards-grid">
      ${days.map((day) => {
        const stops = day.stops || [];
        const cost = estimateDayCost(stops);
        const actual = getActualCost(day.day);
        return `
        <div class="day-card" data-day-index="${day.day - 1}">
          <div class="day-card-header" style="border-left: 4px solid ${DAY_COLORS[(day.day - 1) % DAY_COLORS.length]}">
            <strong>Day ${day.day}</strong>
            <span class="day-card-stats">${stops.length} 站 · ≈¥${cost.lo}-${cost.hi}${actual ? ` · 实际 ¥${actual}` : ""}</span>
          </div>
          <div class="day-card-timeline">
            <div class="day-card-stop day-card-hotel" style="opacity:0.85;">
              <span class="stop-icon">🏨</span>
              <span class="stop-time"></span>
              <span class="stop-name" style="color:#059669;font-weight:600;">🏨 ​</span>
            </div>

            ${stops.map((stop, j) => `
              <div class="day-card-stop" data-poi-id="${stop.poi_id || ""}" data-day-idx="${day.day - 1}" data-stop-idx="${j}">
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
        ${(day.stops || []).map(renderStop).join("")}
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

function renderStop(stop) {
  const travel = stop.travel_minutes_from_previous || 0;
  const hasRisk = stop.time_window_status && stop.time_window_status !== "ok";
  const isMeal = stop.slot === "午餐" || stop.slot === "晚餐" || stop.slot === "下午茶" || stop.slot === "下午茶";
  const mealLabel = isMeal ? `<div class="stop-meal-badge">${stop.slot}</div>` : "";
  const hasImg = stop.image_url && stop.image_url.length > 0;
  const guideText = stop.guide_text || "";
  const shortGuide = guideText.length > 120 ? guideText.substring(0, 120) : guideText;
  const needToggle = guideText.length > 120;
  const uid = "g_" + (stop.poi_id || Math.random().toString(36).slice(2, 8));
  return `
    <article class="stop-card type-${stop.poi_type || "attraction"} ${hasRisk ? "stop-risk" : ""} ${isMeal ? "stop-meal" : ""}" draggable="true" data-poi-id="${stop.poi_id || ""}">
      ${hasImg ? `<img class="stop-hero-img" src="${stop.image_url}" alt="${escapeHtml(stop.poi_name)}" loading="lazy" onerror="this.classList.add('error');var _p=document.createElement('div');_p.className='agent-stop-noimg';_p.textContent='\uD83C\uDFDB\uFE0F';this.parentNode.insertBefore(_p,this.nextSibling)">` : ""}
      ${travel > 0 ? `<div class="stop-transport-bar">${transportIcon(travel)} ${travel} 分钟</div>` : ""}
      <div class="stop-main">
        <span class="stop-type-icon">${typeIcon(stop.poi_type)}</span>
        <div class="stop-info">
          <div class="stop-name-line">
            ${mealLabel}
            <strong>${escapeHtml(stop.poi_name)}</strong>
            <span class="stop-time-badge">${escapeHtml(stop.start_time)}-${escapeHtml(stop.end_time)}</span>
          </div>
          <div class="stop-meta">${escapeHtml(stop.area)}${hasRisk ? ` · ⚠️ ${escapeHtml(timeWindowLabel(stop.time_window_status))}` : ""}</div>
          ${isMeal ? `<div class="stop-area-hint">📍 建议在 <strong>${escapeHtml(stop.area)}</strong> 一带用餐</div>` : ""}
          <div class="stop-reason">${escapeHtml(stop.reason) || ""}</div>
          ${stop.recommendation ? `<div class="stop-tip">💡 ${escapeHtml(stop.recommendation)}</div>` : ""}
          ${guideText ? `<div class="stop-guide"><div class="stop-guide-text" id="${uid}">${escapeHtml(shortGuide)}${needToggle ? "..." : ""}</div>${needToggle ? `<button class="stop-guide-toggle" data-full-text="${escapeHtml(guideText)}" data-short-text="${escapeHtml(shortGuide)}..." data-target="${uid}" onclick="toggleGuide(this)">展开攻略</button>` : ""}</div>` : ""}
        </div>
      </div>
      <div class="stop-actions">
        ${isMeal ? `<button class="stop-action-btn stop-swap-btn" data-poi-id="${stop.poi_id || ""}" data-area="${escapeHtml(stop.area || "")}" data-slot="${escapeHtml(stop.slot || "")}" title="查看该区域其他餐厅">🔄 换一家</button>` : `<button class="stop-action-btn stop-replace-btn" data-poi-id="${stop.poi_id || ""}" data-poi-type="${stop.poi_type || "attraction"}" data-area="${escapeHtml(stop.area || "")}" title="替换此景点">🔄 替换</button>`}
        <button class="stop-action-btn stop-remove-btn" data-poi-id="${stop.poi_id || ""}" title="移除此站点">✕ 移除</button>
      </div>
      ${isMeal ? `<div class="stop-alternatives" data-poi-id="${stop.poi_id || ""}" hidden></div>` : ""}
    </article>
  `;
}

function toggleGuide(btn) {
  const target = document.getElementById(btn.dataset.target);
  if (!target) return;
  if (target.classList.contains("expanded")) {
    target.classList.remove("expanded");
    target.textContent = btn.dataset.shortText;
    btn.textContent = "展开攻略";
  } else {
    target.classList.add("expanded");
    target.textContent = btn.dataset.fullText;
    btn.textContent = "收起";
  }
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

async function generatePlan(event) {
  event.preventDefault();
  // Cancel any in-flight plan request
  if (state.planAbortController) state.planAbortController.abort();
  state.planAbortController = new AbortController();
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
      signal: state.planAbortController.signal,
    });
    state.candidates = data.candidates || [data];
    state.selectedIndex = 0;
    state.tripSaved = false;
    state.savedTripId = null;
    renderPlan();
    updateStageVisibility();
    saveTripState();
  } catch (error) {
    state.candidates = [];
    $("planOutput").className = "plan-output empty-state error-state";
    $("planOutput").textContent = `生成失败：${error.message}`;
  }
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
  $("chatOutput").hidden = true;

  var prog = $("agentProgress");
  var stepsEl = $("progressSteps");
  if (prog) { prog.hidden = false; }
  if (stepsEl) { stepsEl.innerHTML = ""; }
  var agentRes = $("agentResult");
  if (agentRes) { agentRes.hidden = true; agentRes.innerHTML = ""; }
  var planOut = $("planOutput");
  if (planOut) { planOut.hidden = true; }

  try {
    var itinerary = null;
    var response = await fetch("/agent/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message }),
    });
    if (!response.ok) throw new Error("HTTP " + response.status);

    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";
    while (true) {
      var result = await reader.read();
      if (result.done) break;
      buffer += decoder.decode(result.value, { stream: true });
      var lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (line.startsWith("event: ")) continue;
        if (line.startsWith("data: ")) {
          try {
            var evt = JSON.parse(line.slice(6));
            if (evt.type === "itinerary") { itinerary = evt.itinerary; }
            else if (evt.type === "error") { throw new Error(evt.content || "Planning failed"); }
            else if (evt.type !== "done" && stepsEl) {
              stepsEl.innerHTML += '<span class="agent-progress-step done">' + escapeHtml(evt.content || evt.type) + "</span>";
            }
          } catch (e) {}
        }
      }
    }
    if (prog) prog.hidden = true;
    if (itinerary) {
      renderAgentResult(itinerary);
      $("chatOutput").innerHTML = '<p style="color:var(--accent-dark);font-size:13px;">&#10003; 行程已生成，请查看详情</p>';
      $("chatOutput").hidden = false;
    } else { throw new Error("未能生成行程"); }
  } catch (error) {
    if (prog) prog.hidden = true;
    $("chatOutput").innerHTML = '<p style="color:#c0392b;">' + escapeHtml(error.message) + "</p>";
    $("chatOutput").hidden = false;
  } finally {
    $("chatButton").disabled = false;
    $("chatBtnText").hidden = false;
    $("chatBtnLoading").hidden = true;
  }
}

function renderAgentResult(itinerary) {
  var container = $("agentResult");
  if (!container) return;
  container.hidden = false;
  container.innerHTML = "";
  var city = itinerary.city || "";
  var days = itinerary.days || [];
  var hotel = itinerary.hotel;
  var summary = itinerary.summary || "";

  var header = document.createElement("div");
  header.className = "agent-header";
  var h = '<h2>' + escapeHtml(city) + ' &middot; AI 智能行程</h2>';
  h += '<div class="agent-header-summary">' + escapeHtml(summary) + '</div>';
  h += '<div class="agent-header-meta"><span>&#128197; ' + days.length + ' 天</span>';
  if (hotel) h += '<span>&#127976; ' + escapeHtml(hotel.name) + '</span>';
  h += '</div>';
  header.innerHTML = h;
  container.appendChild(header);

  if (hotel) {
    var hCard = document.createElement("div");
    hCard.className = "agent-hotel-card";
    var hImgSrc = hotel.image_url || "/vendor/images/hotel-placeholder.svg";
    var hImg = document.createElement("img");
    hImg.className = "agent-hotel-img";
    hImg.src = hImgSrc;
    hImg.alt = hotel.name || "";
    hImg.onerror = function() { this.src = "/vendor/images/hotel-placeholder.svg"; };
    hCard.appendChild(hImg);
    var hInfo = document.createElement("div");
    hInfo.className = "agent-hotel-info";
    hInfo.innerHTML = '<h3>&#127976; ' + escapeHtml(hotel.name) + '</h3><p>&#128205; ' + escapeHtml(hotel.area || '') + '</p>';
    hCard.appendChild(hInfo);
    container.appendChild(hCard);
  }

  var timeline = document.createElement("div");
  timeline.className = "agent-timeline";
  for (var d = 0; d < days.length; d++) {
    var day = days[d];
    var dayDiv = document.createElement("div");
    dayDiv.className = "agent-day";
    var dn = document.createElement("div");
    dn.className = "agent-day-node";
    dayDiv.appendChild(dn);
    var dt = document.createElement("h3");
    dt.className = "agent-day-title";
    dt.textContent = '\u{1F4C5} \u7B2C ' + day.day + ' \u5929';
    dayDiv.appendChild(dt);
    if (day.summary) {
      var ds = document.createElement("p");
      ds.className = "agent-day-summary";
      ds.textContent = day.summary;
      dayDiv.appendChild(ds);
    }
    var stops = day.stops || [];
    for (var s = 0; s < stops.length; s++) {
      dayDiv.appendChild(renderStopCard(stops[s]));
    }
    timeline.appendChild(dayDiv);
  }
  container.appendChild(timeline);
  container.scrollIntoView({ behavior: "smooth", block: "start" });
}

function getStopImageUrls(stop) {
  var urls = [];
  function addUrl(url) {
    if (!url || typeof url !== "string") return;
    var clean = url.trim();
    if (clean && urls.indexOf(clean) === -1) urls.push(clean);
  }
  addUrl(stop.image_url);
  if (Array.isArray(stop.images)) {
    for (var i = 0; i < stop.images.length; i++) {
      var item = stop.images[i];
      addUrl(typeof item === "string" ? item : item && item.url);
    }
  }
  return urls;
}

function normalizeStopText(value) {
  return (value || "").trim().replace(/\s+/g, " ");
}

function renderStopCard(stop) {
  var card = document.createElement("div");
  card.className = "agent-stop";
  var poiType = stop.poi_type || "attraction";
  var typeLabels = { attraction: "\u{1F3DB}\uFE0F \u666F\u70B9", restaurant: "\u{1F35C} \u9910\u5385", hotel: "\u{1F3E8} \u9152\u5E97", nightlife: "\u{1F319} \u591C\u751F\u6D3B" };
  var typeLabel = typeLabels[poiType] || "\u{1F4CD} \u666F\u70B9";
  var imageUrls = getStopImageUrls(stop);
  var hasImg = imageUrls.length > 0;
  var timeStr = (stop.start_time || "") + (stop.end_time ? " - " + stop.end_time : "");

  if (hasImg) {
    var imgWrap = document.createElement("div");
    imgWrap.className = "agent-stop-img-wrap";
    var img = document.createElement("img");
    img.className = "agent-stop-img";
    img.src = imageUrls[0];
    img.alt = stop.poi_name || "";
    img.loading = "lazy";
    img.onerror = function() {
      this.classList.add("error");
      if (this.parentNode.querySelector(".agent-stop-noimg")) return;
      var ph = document.createElement("div");
      ph.className = "agent-stop-noimg";
      ph.textContent = poiType === "restaurant" ? "\u{1F35C}" : "\u{1F3DB}\uFE0F";
      this.parentNode.appendChild(ph);
    };
    imgWrap.appendChild(img);
    if (imageUrls.length > 1) {
      var currentImageIndex = 0;
      var showImage = function(nextIndex) {
        currentImageIndex = (nextIndex + imageUrls.length) % imageUrls.length;
        img.classList.remove("error");
        var ph = imgWrap.querySelector(".agent-stop-noimg");
        if (ph) ph.remove();
        img.src = imageUrls[currentImageIndex];
      };
      var addCarouselButton = function(direction, className, label, text) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "agent-stop-carousel-btn " + className;
        btn.setAttribute("aria-label", label);
        btn.title = label;
        btn.textContent = text;
        btn.addEventListener("click", function(e) {
          e.preventDefault();
          e.stopPropagation();
          showImage(currentImageIndex + direction);
        });
        imgWrap.appendChild(btn);
      };
      addCarouselButton(-1, "prev", "\u4E0A\u4E00\u5F20\u56FE\u7247", "\u2039");
      addCarouselButton(1, "next", "\u4E0B\u4E00\u5F20\u56FE\u7247", "\u203A");
    }
    if (timeStr) {
      var tb = document.createElement("div");
      tb.className = "agent-stop-time-badge";
      tb.textContent = timeStr;
      imgWrap.appendChild(tb);
    }
    var tpb = document.createElement("div");
    tpb.className = "agent-stop-type-badge";
    tpb.textContent = typeLabel;
    imgWrap.appendChild(tpb);
    card.appendChild(imgWrap);
  }

  var body = document.createElement("div");
  body.className = "agent-stop-body";
  var nameEl = document.createElement("h4");
  nameEl.className = "agent-stop-name";
  nameEl.textContent = (hasImg ? "" : typeLabel + " ") + (stop.poi_name || "");
  body.appendChild(nameEl);

  if (stop.area) {
    var areaEl = document.createElement("p");
    areaEl.className = "agent-stop-area";
    areaEl.textContent = '\u{1F4CD} ' + stop.area + (timeStr && !hasImg ? ' \u00B7 ' + timeStr : '');
    body.appendChild(areaEl);
  }
  var reason = normalizeStopText(stop.reason);
  if (reason) {
    var reasonEl = document.createElement("div");
    reasonEl.className = "agent-stop-reason";
    reasonEl.textContent = reason;
    body.appendChild(reasonEl);
  }
  var guide = normalizeStopText(stop.guide_text);
  if (guide) {
    var guideDiv = document.createElement("div");
    guideDiv.className = "agent-stop-guide";
    var guideId = "guide_" + Math.random().toString(36).slice(2, 8);
    var guideText = document.createElement("div");
    guideText.className = "agent-stop-guide-text";
    guideText.id = guideId;
    guideText.textContent = guide;
    guideDiv.appendChild(guideText);
    if (guide.length > 120) {
      var toggleBtn = document.createElement("button");
      toggleBtn.className = "agent-stop-guide-toggle";
      toggleBtn.textContent = '\u5C55\u5F00\u653B\u7565';
      toggleBtn.setAttribute("data-guide-id", guideId);
      toggleBtn.onclick = function() {
        var el = document.getElementById(this.getAttribute("data-guide-id"));
        if (el.classList.contains("expanded")) {
          el.classList.remove("expanded");
          this.textContent = '\u5C55\u5F00\u653B\u7565';
        } else {
          el.classList.add("expanded");
          this.textContent = '\u6536\u8D77';
        }
      };
      guideDiv.appendChild(toggleBtn);
    }
    body.appendChild(guideDiv);
  }
  var recommendation = normalizeStopText(stop.recommendation);
  if (recommendation && recommendation !== reason && recommendation !== guide) {
    var tipEl = document.createElement("div");
    tipEl.className = "agent-stop-tip";
    tipEl.innerHTML = '\u{1F4A1} ' + escapeHtml(recommendation);
    body.appendChild(tipEl);
  }
  card.appendChild(body);
  return card;
}

$("chatButton").addEventListener("click", chatPlan);
document.querySelectorAll(".chat-hint").forEach(function(btn) {
  btn.addEventListener("click", function() {
    $("chatInput").value = btn.dataset.prompt;
    chatPlan();
  });
});
document.querySelectorAll(".agent-keyword").forEach(function(tag) {
  tag.addEventListener("click", function() {
    var input = $("chatInput");
    var kw = tag.dataset.kw;
    if (input.value.indexOf(kw) === -1) {
      input.value = input.value.trim() + (input.value.trim() ? "\uFF0C" : "") + "\u559C\u6B22" + kw;
    }
    input.focus();
  });
});

// Event delegation for stop remove buttons (CSP-safe)
document.addEventListener("click", function(e) {
  var rmBtn = e.target.closest(".stop-remove-btn");
  if (rmBtn) { removeStop(rmBtn.dataset.poiId); }
});

// Event delegation for meal swap buttons
document.addEventListener("click", async function(e) {
  var swapBtn = e.target.closest(".stop-swap-btn");
  if (!swapBtn) return;
  var card = swapBtn.closest(".stop-card");
  var altContainer = card?.querySelector(".stop-alternatives");
  if (!altContainer) return;

  // Toggle visibility
  if (!altContainer.hidden) { altContainer.hidden = true; return; }

  var area = swapBtn.dataset.area;
  if (!area) return;

  altContainer.hidden = false;
  altContainer.innerHTML = '<div style="font-size:12px;color:var(--muted);">加载中...</div>';

  try {
    var city = state.lastPayload?.city || "";
    var data = await api(`/poi/by-area?city=${encodeURIComponent(city)}&area=${encodeURIComponent(area)}&type=restaurant&limit=5`);
    var restaurants = data.data || [];
    if (restaurants.length === 0) {
      altContainer.innerHTML = '<div style="font-size:12px;color:var(--muted);">该区域暂无其他餐厅</div>';
      return;
    }
    var currentPoiId = swapBtn.dataset.poiId;
    altContainer.innerHTML = restaurants.map(function(r) {
      var isCurrent = r.id === currentPoiId;
      return '<div class="alt-restaurant-item' + (isCurrent ? ' map-highlight' : '') + '" data-poi-id="' + r.id + '" data-name="' + escapeHtml(r.name) + '">' +
        '<span>🍜</span>' +
        '<span class="alt-name">' + escapeHtml(r.name) + (isCurrent ? ' (当前)' : '') + '</span>' +
        '<span class="alt-score">⭐ ' + (r.popularity || 0).toFixed(1) + '</span>' +
      '</div>';
    }).join("");

    // Handle click on alternative restaurant
    altContainer.querySelectorAll(".alt-restaurant-item").forEach(function(item) {
      item.addEventListener("click", function() {
        var newPoiId = item.dataset.poiId;
        var newName = item.dataset.name;
        if (newPoiId === currentPoiId) return;
        swapRestaurant(currentPoiId, newPoiId, newName);
      });
    });
  } catch (err) {
    altContainer.innerHTML = '<div style="font-size:12px;color:#c0392b;">加载失败: ' + escapeHtml(err.message) + '</div>';
  }
});

/* ── Replace stop with alternative POI ── */
document.addEventListener("click", async function(e) {
  var btn = e.target.closest(".stop-replace-btn");
  if (!btn) return;
  var card = btn.closest(".stop-card");
  var altContainer = card && card.querySelector(".stop-alternatives");
  if (!altContainer) {
    // Create alternatives container if not exists
    altContainer = document.createElement("div");
    altContainer.className = "stop-alternatives";
    altContainer.dataset.poiId = btn.dataset.poiId;
    card.appendChild(altContainer);
  }
  if (!altContainer.hidden) { altContainer.hidden = true; return; }
  altContainer.hidden = false;
  altContainer.innerHTML = '<div style="font-size:12px;color:var(--muted);">加载中...</div>';
  var city = state.lastPayload && state.lastPayload.city || "";
  var area = btn.dataset.area;
  var poiType = btn.dataset.poiType || "attraction";
  try {
    var url = area
      ? "/poi/by-area?city=" + encodeURIComponent(city) + "&area=" + encodeURIComponent(area) + "&type=" + poiType + "&limit=8"
      : "/poi/search?city=" + encodeURIComponent(city) + "&type=" + poiType + "&limit=8";
    var data = await api(url);
    var alternatives = (data.data || []).filter(function(p) { return p.id !== btn.dataset.poiId; });
    if (alternatives.length === 0) {
      altContainer.innerHTML = '<div style="font-size:12px;color:var(--muted);">该区域暂无其他' + (poiType === "restaurant" ? "餐厅" : "景点") + '</div>';
      return;
    }
    altContainer.innerHTML = alternatives.map(function(p) {
      return '<div class="alt-restaurant-item" data-new-poi-id="' + p.id + '" data-new-name="' + escapeHtml(p.name) + '">' +
        '<span>' + typeIcon(p.type || poiType) + '</span>' +
        '<span class="alt-name">' + escapeHtml(p.name) + '</span>' +
        '<span class="alt-score">⭐ ' + (p.popularity || 0).toFixed(1) + '</span>' +
      '</div>';
    }).join("");
    altContainer.querySelectorAll(".alt-restaurant-item").forEach(function(item) {
      item.addEventListener("click", function() {
        var newId = item.dataset.newPoiId;
        var newName = item.dataset.newName;
        replaceStop(btn.dataset.poiId, newId, newName);
      });
    });
  } catch(err) {
    altContainer.innerHTML = '<div style="font-size:12px;color:#c0392b;">加载失败: ' + escapeHtml(err.message) + '</div>';
  }
});

function replaceStop(oldPoiId, newPoiId, newName) {
  var candidate = state.candidates[state.selectedIndex];
  if (!candidate || !candidate.days) return;
  for (var d = 0; d < candidate.days.length; d++) {
    var day = candidate.days[d];
    var stops = day.stops || [];
    for (var i = 0; i < stops.length; i++) {
      if (stops[i].poi_id === oldPoiId) {
        stops[i].poi_id = newPoiId;
        stops[i].poi_name = newName;
        recalcDayTimes(day);
        renderPlan();
        saveTripState();
        toast("已替换为 " + newName, "success");
        return;
      }
    }
  }
}

function swapRestaurant(oldPoiId, newPoiId, newName) {
  var candidate = state.candidates[state.selectedIndex];
  if (!candidate?.days) return;
  for (var day of candidate.days) {
    var stops = day.stops || [];
    for (var i = 0; i < stops.length; i++) {
      if (stops[i].poi_id === oldPoiId) {
        // Look up new POI details from the alternatives data
        var altContainer = document.querySelector('.stop-alternatives[data-poi-id="' + oldPoiId + '"]');
        var selectedItem = altContainer?.querySelector('[data-poi-id="' + newPoiId + '"]');
        // Update the stop with new POI info (name only, keep time/area)
        stops[i].poi_id = newPoiId;
        stops[i].poi_name = newName;
        // Re-render the plan
        renderPlan();
        saveTripState();
        toast("已替换为 " + newName, "success");
        return;
      }
    }
  }
}
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

/* ── Day card: click to focus on map ── */
document.addEventListener("click", function(e) {
  var card = e.target.closest(".day-card");
  if (!card) return;
  // Ignore clicks on inputs/buttons inside the card
  if (e.target.closest("input") || e.target.closest("button")) return;
  var dayIdx = parseInt(card.dataset.dayIndex, 10);
  if (isNaN(dayIdx)) return;
  // Scroll to the corresponding day block in itinerary view
  var dayBlocks = document.querySelectorAll(".day-block");
  if (dayBlocks[dayIdx]) {
    setStage("itinerary");
    dayBlocks[dayIdx].scrollIntoView({ behavior: "smooth", block: "start" });
    dayBlocks[dayIdx].style.outline = "2px solid #146b5d";
    dayBlocks[dayIdx].style.borderRadius = "8px";
    setTimeout(function() { dayBlocks[dayIdx].style.outline = ""; }, 3000);
  }
  // Also focus map on this day
  if (planMap && mapDayLayers[dayIdx]) {
    planMap.removeLayer(mapDayLayers[dayIdx].markers);
    mapDayLayers[dayIdx].markers.addTo(planMap);
    if (mapDayLayers[dayIdx].polyline) {
      planMap.removeLayer(mapDayLayers[dayIdx].polyline);
      mapDayLayers[dayIdx].polyline.addTo(planMap);
    }
    var dayBounds = [];
    mapDayLayers[dayIdx].markers.eachLayer(function(m) { if (m.getLatLng) dayBounds.push(m.getLatLng()); });
    if (dayBounds.length > 0) planMap.fitBounds(dayBounds, { padding: [40, 40] });
  }
});

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
    // Reload hotels for new city
    allHotels = [];
    loadHotels();
    // Clear hotel when city changes; user picks from hotel list
    $("hotelLocation").value = "";
  });
});
// Initialize default city from backend and load guidebook
(async () => {
  try {
    const data = await fetch('/cities').then(r => r.json());
    const defaultCity = data.default || (data.cities && data.cities[0]?.name) || '';
    if (defaultCity) {
      $("city").value = defaultCity;
      const card = document.querySelector(`.city-card[data-city="${defaultCity}"]`);
      if (card) {
        document.querySelectorAll(".city-card").forEach(c => c.classList.remove("active"));
        card.classList.add("active");
      }
      loadHotels();
    }
  } catch {}
  setTimeout(() => loadGuidebook($("city")?.value || ""), 500);
})();

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
    const city = document.getElementById("city")?.value?.trim() || state.lastPayload?.city || "";
    const data = await api(`/poi/search?type=hotel&city=${encodeURIComponent(city)}&limit=100`);
    allHotels = data.data || [];
    renderHotelList(allHotels);
  } catch (e) { console.warn("loadHotels failed:", e); }
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
let saveCooldownUntil = 0;
async function saveTrip() {
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate) return;
  const now = Date.now();
  if (now < saveCooldownUntil) { toast("请勿频繁操作", "info"); return; }
  if (state.tripSaved) { toast("该行程已保存", "info"); return; }
  const saveBtn = document.getElementById("saveTripBtn");
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = "保存中..."; }
  saveCooldownUntil = now + 2000;
  try {
    const res = await api("/trips/save", {
      method: "POST",
      body: JSON.stringify({
        title: (() => {
          const city = state.lastPayload?.city || "旅行";
          const days = candidate.days?.length || state.lastPayload?.days || 1;
          const interests = (state.lastPayload?.interests || []).slice(0, 2).join("·");
          return `${city}${interests ? "·" + interests : ""} ${days}日游`;
        })(),
        request: state.lastPayload,
        response: candidate,
      }),
    });
    state.tripSaved = true;
    state.savedTripId = res?.id;
    if (saveBtn) { saveBtn.textContent = "✅ 已保存"; }
    const guestHint = state.user?.role === "guest" ? " (游客数据保留 7 天，注册后可长期保存)" : "";
    toast(`行程已保存！${guestHint}`, "success",
      `<a href="/profile.html" class="toast-link">查看已保存</a>`);
  } catch (e) {
    toast("保存失败：" + e.message, "error");
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = "💾 保存行程"; }
  }
}
async function shareTrip() {
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate) return;
  const shareBtn = document.getElementById("shareTripBtn");
  if (shareBtn) { shareBtn.disabled = true; shareBtn.textContent = "分享中..."; }
  try {
    // Save first if not already saved
    if (!state.tripSaved) {
      await saveTrip();
    }
    // If still not saved (e.g. save failed), abort
    if (!state.tripSaved) {
      toast("请先保存行程再分享", "info");
      return;
    }
    // Get latest trip ID
    const trips = await api("/trips/list");
    const tripId = state.savedTripId || (trips.data?.[0]?.id);
    if (!tripId) { toast("未找到已保存的行程", "error"); return; }
    // Generate share link
    const shareData = await api(`/trips/${tripId}/share`, { method: "POST", body: "{}" });
    const url = location.origin + "/#/share/" + shareData.share_id;
    try { await navigator.clipboard.writeText(url); } catch {}
    toast("分享链接已复制", "success",
      `<a href="${shareData.share_url}" target="_blank" class="toast-link">预览分享页</a>`);
    if (shareBtn) {
      shareBtn.textContent = "🔗 复制链接";
      shareBtn.disabled = false;
      shareBtn.onclick = () => { navigator.clipboard.writeText(url).catch(() => {}); toast("链接已复制", "success"); };
    }
  } catch (e) {
    toast("分享失败：" + e.message, "error");
    if (shareBtn) { shareBtn.textContent = "🔗 分享"; shareBtn.disabled = false; }
  }
}

// ---- Itinerary templates ----
const TEMPLATES = [
  { city: "武汉", days: 2, icon: "🏙️", name: "武汉文化之旅", theme: "历史文化",
    msg: "2天武汉行，想去黄鹤楼和东湖，喜欢历史文化", spots: "黄鹤楼 · 东湖 · 湖北省博物馆" },
  { city: "武汉", days: 2, icon: "🍜", name: "武汉美食探索", theme: "美食",
    msg: "2天武汉行，主要吃美食，不要太累", spots: "户部巷 · 吉庆街 · 热干面" },
  { city: "武汉", days: 3, icon: "🌙", name: "武汉深度游", theme: "文化+美食+夜景",
    msg: "3天武汉行，想去黄鹤楼、东湖、湖北省博物馆，也要吃地道美食，看夜景", spots: "黄鹤楼 · 东湖 · 博物馆 · 江汉路" },
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
  { city: "北京", days: 3, icon: "🏯", name: "北京经典游", theme: "历史文化",
    msg: "3天北京行，想去故宫、长城和天安门", spots: "故宫 · 长城 · 天安门 · 颐和园" },
  { city: "成都", days: 3, icon: "🐼", name: "成都休闲游", theme: "美食+熊猫",
    msg: "3天成都行，想看大熊猫，吃火锅和串串", spots: "大熊猫基地 · 宽窄巷子 · 锦里" },
  { city: "重庆", days: 2, icon: "🔥", name: "重庆山城游", theme: "美食+夜景",
    msg: "2天重庆行，想吃火锅看夜景，体验山城", spots: "洪崖洞 · 解放碑 · 磁器口" },
  { city: "杭州", days: 2, icon: "🌊", name: "杭州西湖游", theme: "自然+文化",
    msg: "2天杭州行，想去西湖和灵隐寺", spots: "西湖 · 灵隐寺 · 河坊街" },
  { city: "西安", days: 3, icon: "🏛️", name: "西安古都游", theme: "历史+美食",
    msg: "3天西安行，想看兵马俑和古城墙，吃肉夹馍", spots: "兵马俑 · 古城墙 · 回民街 · 大雁塔" },
  { city: "上海", days: 3, icon: "🌃", name: "上海都市游", theme: "都市+文化",
    msg: "3天上海行，想去外滩、豫园和迪士尼", spots: "外滩 · 豫园 · 南京路 · 东方明珠" },
  { city: "广州", days: 2, icon: "🥘", name: "广州美食游", theme: "美食+文化",
    msg: "2天广州行，想吃早茶和粤菜，看看广州塔", spots: "广州塔 · 北京路 · 上下九 · 沙面" },
  { city: "深圳", days: 2, icon: "🏙️", name: "深圳科技游", theme: "科技+休闲",
    msg: "2天深圳行，想去世界之窗和欢乐海岸", spots: "世界之窗 · 欢乐海岸 · 华侨城 · 大梅沙" },
  { city: "厦门", days: 3, icon: "🏖️", name: "厦门海岛游", theme: "海岛+文艺",
    msg: "3天厦门行，想去鼓浪屿和曾厝垵，看海吃海鲜", spots: "鼓浪屿 · 曾厝垵 · 环岛路 · 南普陀寺" },
  { city: "青岛", days: 2, icon: "🍺", name: "青岛海滨游", theme: "海滨+啤酒",
    msg: "2天青岛行，想去栈桥和八大关，喝啤酒吃海鲜", spots: "栈桥 · 八大关 · 五四广场 · 崂山" },
  { city: "桂林", days: 3, icon: "🏞️", name: "桂林山水游", theme: "自然风光",
    msg: "3天桂林行，想去漓江和阳朔，看山水风光", spots: "漓江 · 阳朔 · 象鼻山 · 龙脊梯田" },
  { city: "三亚", days: 3, icon: "🌊", name: "三亚海滨游", theme: "海滨度假",
    msg: "3天三亚行，想去亚龙湾和天涯海角，看海吃海鲜", spots: "亚龙湾 · 天涯海角 · 南山寺 · 蜈支洲岛" },
  { city: "哈尔滨", days: 2, icon: "❄️", name: "哈尔滨冰雪游", theme: "冰雪+建筑",
    msg: "2天哈尔滨行，想去冰雪大世界和中央大街", spots: "冰雪大世界 · 中央大街 · 圣索菲亚教堂 · 太阳岛" },
  { city: "昆明", days: 3, icon: "🌸", name: "昆明春城游", theme: "自然+民族",
    msg: "3天昆明行，想去滇池和石林，感受春城", spots: "滇池 · 石林 · 翠湖 · 西山" },
  { city: "张家界", days: 3, icon: "🏔️", name: "张家界奇峰游", theme: "自然奇观",
    msg: "3天张家界行，想去天门山和玻璃桥，看奇峰", spots: "天门山 · 玻璃桥 · 袁家界 · 金鞭溪" },
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
  if (e.target.id === "shareImageBtn" || e.target.closest?.("#shareImageBtn")) generateShareImage();
  if (e.target.id === "exportBtn" || e.target.closest?.("#exportBtn")) exportTrip();
  if (e.target.id === "navAmapBtn" || e.target.closest?.("#navAmapBtn")) exportToAmap();
});

function removeStop(poiId) {
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate || !candidate.days) return;
  let removed = false;
  for (const day of candidate.days) {
    const idx = (day.stops || []).findIndex(s => s.poi_id === poiId);
    if (idx >= 0) {
      day.stops.splice(idx, 1);
      removed = true;
      break;
    }
  }
  if (removed) {
    renderPlan();
    toast("已移除站点", "info");
  }
}

function exportTrip() {
  setStage("overview");
  setTimeout(() => window.print(), 300);
}

function exportToAmap() {
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate?.days?.length) { toast("请先生成行程", "info"); return; }

  // Collect all stops with coordinates
  const stops = [];
  for (const day of candidate.days) {
    for (const stop of day.stops || []) {
      if (stop.lat && stop.lng) stops.push(stop);
    }
  }
  if (stops.length === 0) { toast("行程中没有可导航的地点", "info"); return; }

  // Generate Amap web navigation links for each segment
  const links = [];
  for (let i = 0; i < stops.length; i++) {
    const s = stops[i];
    const dest = `${s.lng},${s.lat}`;
    const name = encodeURIComponent(s.poi_name || "目的地");
    if (i === 0) {
      // First stop: navigate from current location
      links.push({ name: s.poi_name, url: `https://uri.amap.com/navigation?to=${dest},${name}&mode=car&coordinate=gaode` });
    }
    // If there's a next stop, add route link
    if (i < stops.length - 1) {
      const next = stops[i + 1];
      const from = `${s.lng},${s.lat}`;
      const to = `${next.lng},${next.lat}`;
      const fromName = encodeURIComponent(s.poi_name || "起点");
      const toName = encodeURIComponent(next.poi_name || "终点");
      links.push({ name: `${s.poi_name} → ${next.poi_name}`, url: `https://uri.amap.com/route/plan/?from=${from},${fromName}&to=${to},${toName}&mode=car&coordinate=gaode` });
    }
  }

  // Open first stop navigation in new tab
  if (links.length > 0) {
    window.open(links[0].url, "_blank");
    toast(`已在高德地图打开导航（共 ${stops.length} 站）`, "success");
  }
}

async function generateShareImage() {
  const candidate = state.candidates[state.selectedIndex];
  if (!candidate) { toast("请先生成行程", "info"); return; }
  const btn = document.getElementById("shareImageBtn");
  if (btn) { btn.disabled = true; btn.textContent = "生成中..."; }
  try {
    // Switch to overview to ensure it's visible
    setStage("overview");
    await new Promise(r => setTimeout(r, 300));
    const target = document.querySelector(".overview-section") || document.querySelector("[data-plan-section='overview']");
    if (!target) { toast("未找到行程内容", "error"); return; }
    if (typeof html2canvas === "undefined") { toast("图片生成组件未加载", "error"); return; }
    const canvas = await html2canvas(target, {
      backgroundColor: "#ffffff",
      scale: 2,
      useCORS: true,
      logging: false,
    });
    const city = state.lastPayload?.city || "旅行";
    const days = candidate.days?.length || 1;
    const link = document.createElement("a");
    link.download = `TourPass_${city}_${days}天行程.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
    toast("图片已下载！", "success");
  } catch (e) {
    console.error("Share image error:", e);
    toast("图片生成失败：" + e.message, "error");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "📸 生成图片"; }
  }
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
  "长沙": { lat: 28.23, lon: 112.94 }, "changsha": { lat: 28.23, lon: 112.94 },
  "武汉": { lat: 30.59, lon: 114.31 }, "wuhan": { lat: 30.59, lon: 114.31 },
  "大理": { lat: 25.61, lon: 100.27 }, "dali": { lat: 25.61, lon: 100.27 },
  "丽江": { lat: 26.87, lon: 100.23 }, "lijiang": { lat: 26.87, lon: 100.23 },
  "南京": { lat: 32.06, lon: 118.80 }, "nanjing": { lat: 32.06, lon: 118.80 },
  "苏州": { lat: 31.30, lon: 120.62 }, "suzhou": { lat: 31.30, lon: 120.62 },
  "成都": { lat: 30.57, lon: 104.07 }, "chengdu": { lat: 30.57, lon: 104.07 },
  "重庆": { lat: 29.56, lon: 106.55 }, "chongqing": { lat: 29.56, lon: 106.55 },
  "西安": { lat: 34.26, lon: 108.94 }, "xian": { lat: 34.26, lon: 108.94 },
  "杭州": { lat: 30.27, lon: 120.15 }, "hangzhou": { lat: 30.27, lon: 120.15 },
  "北京": { lat: 39.90, lon: 116.40 }, "beijing": { lat: 39.90, lon: 116.40 },
  "上海": { lat: 31.23, lon: 121.47 }, "shanghai": { lat: 31.23, lon: 121.47 },
  "广州": { lat: 23.13, lon: 113.26 }, "guangzhou": { lat: 23.13, lon: 113.26 },
  "深圳": { lat: 22.54, lon: 114.06 }, "shenzhen": { lat: 22.54, lon: 114.06 },
  "厦门": { lat: 24.48, lon: 118.09 }, "xiamen": { lat: 24.48, lon: 118.09 },
  "青岛": { lat: 36.07, lon: 120.38 }, "qingdao": { lat: 36.07, lon: 120.38 },
  "桂林": { lat: 25.27, lon: 110.29 }, "guilin": { lat: 25.27, lon: 110.29 },
  "三亚": { lat: 18.25, lon: 109.50 }, "sanya": { lat: 18.25, lon: 109.50 },
  "哈尔滨": { lat: 45.75, lon: 126.65 }, "harbin": { lat: 45.75, lon: 126.65 },
  "昆明": { lat: 25.04, lon: 102.68 }, "kunming": { lat: 25.04, lon: 102.68 },
  "张家界": { lat: 29.12, lon: 110.48 }, "zhangjiajie": { lat: 29.12, lon: 110.48 },
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
const CITY_KEY_MAP = {
  "长沙": "changsha", "武汉": "wuhan", "大理": "dali", "丽江": "lijiang",
  "南京": "nanjing", "苏州": "suzhou", "北京": "beijing", "成都": "chengdu",
  "重庆": "chongqing", "杭州": "hangzhou", "西安": "xian",
  "上海": "shanghai", "广州": "guangzhou", "深圳": "shenzhen",
  "厦门": "xiamen", "青岛": "qingdao",
  "桂林": "guilin", "三亚": "sanya", "哈尔滨": "harbin",
  "昆明": "kunming", "张家界": "zhangjiajie",
  "changsha": "changsha", "wuhan": "wuhan", "dali": "dali", "lijiang": "lijiang",
  "nanjing": "nanjing", "suzhou": "suzhou", "beijing": "beijing", "chengdu": "chengdu",
  "chongqing": "chongqing", "hangzhou": "hangzhou", "xian": "xian",
  "shanghai": "shanghai", "guangzhou": "guangzhou", "shenzhen": "shenzhen",
  "xiamen": "xiamen", "qingdao": "qingdao"
};

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
  } catch (e) { console.warn("loadGuidebook failed:", e); }
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
function getDeviceId() {
  let id = localStorage.getItem("tp_device_id");
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36));
    localStorage.setItem("tp_device_id", id);
  }
  return id;
}
async function doGuestLogin() {
  const errEl = $("authError");
  errEl.hidden = true;
  try {
    const data = await api("/auth/guest", {
      method: "POST",
      body: JSON.stringify({ device_id: getDeviceId() }),
    });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("tp_token", data.token);
    showApp();
    toast("游客模式已启用，数据将保留 7 天", "info");
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

// ---- Hash Router (SPA navigation) ----
function navigateTo(hash) {
  window.location.hash = hash;
}

async function loadSharedTrip(shareId) {
  try {
    const output = $("planOutput");
    if (output) { output.className = "plan-output empty-state"; output.textContent = "正在加载分享行程..."; }
    const data = await api("/api/share/" + shareId);
    if (!data) { toast("分享链接无效", "error"); if (output) output.textContent = "分享链接无效或已过期"; return; }
    // Parse response_json if it's a string
    const trip = typeof data.response_json === "string" ? JSON.parse(data.response_json) : data.response_json;
    if (!trip || !trip.days) { toast("\u5206\u4eab\u94fe\u63a5\u65e0\u6548", "error"); return; }
    state.candidates = [trip];
    state.selectedIndex = 0;
    state.lastPayload = { city: trip.city || data.request_json?.city || "" };
    state.tripSaved = true;
    state.savedTripId = data.id;
    renderPlan();
    setStage("overview");
    toast("\u5df2\u52a0\u8f7d\u5206\u4eab\u7684\u884c\u7a0b: " + (data.title || ""), "success");
  } catch (e) {
    toast("\u52a0\u8f7d\u5206\u4eab\u884c\u7a0b\u5931\u8d25: " + e.message, "error");
  }
}

function handleRoute() {
  const hash = window.location.hash || "#/";

  // Check for share route
  if (hash.startsWith("#/share/")) {
    const shareId = hash.replace("#/share/", "");
    if (shareId) loadSharedTrip(shareId);
    return;
  }
  const mainApp = $("mainApp");
  const profileView = $("profileView");

  if (hash === "#/profile") {
    // Show profile, hide main app
    if (mainApp) mainApp.hidden = true;
    if (profileView) { profileView.hidden = false; loadProfileView(); }
  } else {
    // Show main app, hide profile
    if (profileView) profileView.hidden = true;
    if (mainApp && state.user) mainApp.hidden = false;
  }
}

window.addEventListener("hashchange", handleRoute);

// Profile back button
document.getElementById("profileBackBtn")?.addEventListener("click", () => navigateTo("#/"));
document.getElementById("profileViewLoginLink")?.addEventListener("click", (e) => { e.preventDefault(); navigateTo("#/"); });

// Topbar profile link - intercept to use hash routing
document.addEventListener("click", (e) => {
  const link = e.target.closest('a[href="/profile.html"]');
  if (link) { e.preventDefault(); navigateTo("#/profile"); }
});

async function loadProfileView() {
  const content = $("profileViewContent");
  const error = $("profileViewError");
  if (!content || !error) return;

  const token = localStorage.getItem("tp_token");
  if (!token) { error.hidden = false; content.hidden = true; return; }
  error.hidden = true; content.hidden = false;

  try {
    const me = await api("/auth/me");
    $("pvUsername").textContent = me.username || "";
    $("pvEmail").textContent = me.email || "未绑定";
    const roleLabels = { user: "普通用户", guest: "游客", admin: "管理员" };
    $("pvRole").innerHTML = `<span class="role-badge ${me.role}">${roleLabels[me.role] || me.role}</span>`;
    $("pvCreated").textContent = (me.created_at || "").replace("T", " ").slice(0, 19);

    // Usage ring
    const limit = me.role === "guest" ? 3 : me.role === "admin" ? 999 : 10;
    const remaining = me.query_remaining || 0;
    const used = Math.max(0, limit - remaining);
    const pct = limit < 100 ? Math.min(100, (used / limit) * 100) : 0;
    const circumference = 176;
    const ring = $("pvUsageRing");
    if (ring) ring.style.strokeDashoffset = circumference - (pct / 100) * circumference;
    $("pvUsageNum").textContent = remaining;
    $("pvUsageDetail").innerHTML = me.role === "admin"
      ? '<strong>管理员</strong>，查询次数无限制'
      : `今日已用 <strong>${used}</strong> / ${limit} 次<br>剩余 <strong class="${remaining <= 3 ? 'warn' : ''}">${remaining}</strong> 次`;

    // Guest banner
    const banner = $("pvGuestBanner");
    if (banner) banner.hidden = me.role !== "guest";
    const pwdCard = $("pvChangePwdCard");
    if (pwdCard) pwdCard.hidden = me.role === "guest";
  } catch (e) {
    error.hidden = false;
    content.hidden = true;
    return;
  }

  // Load saved trips
  try {
    const trips = await api("/trips/list");
    const tripList = $("pvTripList");
    if (!tripList) return;
    const tripData = trips.data || [];
    if (tripData.length === 0) {
      tripList.innerHTML = '<div class="empty-state-box"><div class="emoji">📂</div><p><strong>还没有保存过行程</strong></p><p><a href="#/">去规划你的第一个行程</a></p></div>';
      return;
    }
    const cityEmojis = {"长沙":"🏙","武汉":"🌉","大理":"🏔","丽江":"🏘","南京":"🏛","苏州":"🏡","北京":"🏯","成都":"🐼","重庆":"🔥","杭州":"🌊","西安":"🏛","上海":"🌃","广州":"🌺","深圳":"💎","厦门":"🏖","青岛":"🍺"};
    tripList.innerHTML = tripData.map(t => {
      const title = t.title || "未命名行程";
      const city = title.split("·")[0] || "";
      const emoji = cityEmojis[city] || "✈️";
      const date = (t.created_at || "").replace("T", " ").slice(0, 16);
      const shareBtn = t.share_id
        ? `<button class="trip-btn pv-copy-btn" data-share-id="${t.share_id}">📋 复制链接</button>`
        : `<button class="trip-btn pv-share-btn" data-trip-id="${t.id}">🔗 分享</button>`;
      return `<div class="trip-item pv-trip-item" data-trip-id="${t.id}">
        <div class="trip-emoji">${emoji}</div>
        <div class="trip-info">
          <div class="trip-title">${escapeHtml(title)}</div>
          <div class="trip-date">🕐 ${date}</div>
        </div>
        <div class="trip-actions">${shareBtn}</div>
      </div>`;
    }).join("");

    // Event delegation for trip actions
    tripList.onclick = async (e) => {
      // Click on trip item -> load it
      const tripItem = e.target.closest(".pv-trip-item");
      const copyBtn = e.target.closest(".pv-copy-btn");
      const shareBtn = e.target.closest(".pv-share-btn");

      if (copyBtn) {
        const url = location.origin + "/#/share/" + copyBtn.dataset.shareId;
        try { await navigator.clipboard.writeText(url); } catch { var inp = document.createElement("input"); inp.value = url; document.body.appendChild(inp); inp.select(); document.execCommand("copy"); document.body.removeChild(inp); }
        copyBtn.textContent = "\u2705 \u5df2\u590d\u5236";
        setTimeout(() => { copyBtn.textContent = "📋 复制链接"; }, 2000);
        return;
      }
      if (shareBtn) {
        try {
          const data = await api(`/trips/${shareBtn.dataset.tripId}/share`, { method: "POST", body: "{}" });
          const url = location.origin + "/#/share/" + data.share_id;
          try { await navigator.clipboard.writeText(url); } catch {}
          $("pvShareMsg").hidden = false;
          $("pvShareMsg").textContent = "分享链接已复制";
          setTimeout(() => { $("pvShareMsg").hidden = true; }, 2500);
        } catch (err) {
          $("pvShareMsg").hidden = false;
          $("pvShareMsg").textContent = "分享失败：" + err.message;
          $("pvShareMsg").className = "msg-err";
          setTimeout(() => { $("pvShareMsg").hidden = true; $("pvShareMsg").className = "msg-ok"; }, 3000);
        }
        return;
      }
      if (tripItem && !copyBtn && !shareBtn) {
        // Load this trip into the main view
        await loadSavedTrip(tripItem.dataset.tripId);
      }
    };
  } catch (e) {
    console.error("Trip load error:", e);
  }
}

async function loadSavedTrip(tripId) {
  try {
    const trip = await api(`/trips/${tripId}`);
    const response = typeof trip.response_json === "string" ? JSON.parse(trip.response_json) : trip.response_json;
    const request = typeof trip.request_json === "string" ? JSON.parse(trip.request_json) : trip.request_json;
    if (!response?.days) { toast("行程数据格式异常", "error"); return; }
    state.candidates = [response];
    state.selectedIndex = 0;
    state.lastPayload = request || { city: response.city || "旅行", days: response.days?.length || 1 };
    state.tripSaved = true;
    state.savedTripId = tripId;
    saveTripState();
    navigateTo("#/");
    renderPlan();
    setStage("overview");
    toast("已加载行程：" + (trip.title || ""), "success");
  } catch (e) {
    toast("加载行程失败：" + e.message, "error");
  }
}

// Password change handler for profile view
document.getElementById("pvChangePwdBtn")?.addEventListener("click", async () => {
  const oldPwd = $("pvOldPwd").value;
  const newPwd = $("pvNewPwd").value;
  const confirmPwd = $("pvConfirmPwd").value;
  const msg = $("pvPwdMsg");
  msg.hidden = true;
  if (newPwd !== confirmPwd) { msg.textContent = "两次输入的密码不一致"; msg.className = "msg-err"; msg.hidden = false; return; }
  if (newPwd.length < 6) { msg.textContent = "新密码至少6位"; msg.className = "msg-err"; msg.hidden = false; return; }
  try {
    await api("/auth/password", { method: "PATCH", body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }) });
    msg.textContent = "✅ 密码修改成功！"; msg.className = "msg-ok"; msg.hidden = false;
    $("pvOldPwd").value = ""; $("pvNewPwd").value = ""; $("pvConfirmPwd").value = "";
  } catch (e) { msg.textContent = e.message; msg.className = "msg-err"; msg.hidden = false; }
});

// Tools tab queries are triggered by user clicking the buttons, not on page load
