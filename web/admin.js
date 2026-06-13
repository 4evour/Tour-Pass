// Tour Pass Admin Panel
async function api(path, opts = {}) {
  const token = localStorage.getItem("tp_token");
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = "Bearer " + token;
  const res = await fetch(path, { headers, ...opts });
  const data = await res.json();
  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem("tp_token");
      throw new Error("登录已过期，请返回首页重新登录");
    }
    throw new Error(data.error?.message || "请求失败");
  }
  return data;
}

// ---- Init ----
async function init() {
  if (!localStorage.getItem("tp_token")) { showLoginError(); return; }
  try {
    const me = await api("/auth/me");
    if (me.role !== "admin") { showLoginError(); return; }
    document.getElementById("adminUser").textContent = me.username;
    document.getElementById("adminContent").hidden = false;
    loadDashboard();
  } catch { showLoginError(); }
}

function showLoginError() {
  document.getElementById("adminLogin").hidden = false;
}

// ---- Tab navigation ----
document.querySelectorAll(".admin-nav button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".admin-nav button").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".admin-section").forEach(s => s.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("sec-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "dashboard") loadDashboard();
    if (btn.dataset.tab === "users") loadUsers();
    if (btn.dataset.tab === "feedback") loadFeedback();
    if (btn.dataset.tab === "pois") loadPois();
  });
});

// ---- Dashboard ----
async function loadDashboard() {
  try {
    const stats = await api("/admin/stats");
    document.getElementById("statsGrid").innerHTML = `
      <div class="stat-card"><div class="num">${stats.total_users || 0}</div><div class="label">总用户数</div></div>
      <div class="stat-card"><div class="num">${stats.today_active_users || 0}</div><div class="label">今日活跃</div></div>
      <div class="stat-card"><div class="num">${stats.total_queries || 0}</div><div class="label">总查询量</div></div>
      <div class="stat-card"><div class="num">${stats.pending_feedback || 0}</div><div class="label">待处理反馈</div></div>
    `;
    // Load chart data
    const chartData = await api("/admin/query-stats?days=14");
    drawChart(chartData.data || []);
  } catch (e) {
    document.getElementById("statsGrid").innerHTML = `<div class="admin-error">加载失败：${e.message}</div>`;
  }
}

function drawChart(data) {
  const canvas = document.getElementById("queryChart");
  if (!canvas || !data.length) return;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const W = rect.width, H = rect.height;
  const pad = { top: 20, right: 20, bottom: 30, left: 40 };
  const chartW = W - pad.left - pad.right;
  const chartH = H - pad.top - pad.bottom;

  const maxVal = Math.max(1, ...data.map(d => d.total_queries || 0));
  const stepX = chartW / Math.max(1, data.length - 1);

  // Grid
  ctx.strokeStyle = "#e0e0e0";
  ctx.lineWidth = 0.5;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (chartH / 4) * i;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
    ctx.fillStyle = "#999"; ctx.font = "11px sans-serif"; ctx.textAlign = "right";
    ctx.fillText(Math.round(maxVal * (4 - i) / 4), pad.left - 6, y + 4);
  }

  // Line
  ctx.beginPath();
  ctx.strokeStyle = "#146b5d";
  ctx.lineWidth = 2;
  data.forEach((d, i) => {
    const x = pad.left + i * stepX;
    const y = pad.top + chartH - ((d.total_queries || 0) / maxVal) * chartH;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Fill
  ctx.lineTo(pad.left + (data.length - 1) * stepX, pad.top + chartH);
  ctx.lineTo(pad.left, pad.top + chartH);
  ctx.closePath();
  ctx.fillStyle = "rgba(20, 107, 93, 0.1)";
  ctx.fill();

  // Labels
  ctx.fillStyle = "#999"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  data.forEach((d, i) => {
    const x = pad.left + i * stepX;
    const label = (d.date || "").slice(5); // MM-DD
    if (i % Math.ceil(data.length / 7) === 0 || i === data.length - 1) {
      ctx.fillText(label, x, H - 8);
    }
    // Dot
    const y = pad.top + chartH - ((d.total_queries || 0) / maxVal) * chartH;
    ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fillStyle = "#146b5d"; ctx.fill();
  });
}

// ---- Users ----
async function loadUsers() {
  try {
    const data = await api("/admin/users?limit=100");
    const tbody = document.getElementById("usersTable");
    tbody.innerHTML = (data.data || []).map(u => `
      <tr>
        <td>${u.id}</td>
        <td>${escHtml(u.username)}</td>
        <td><span class="fb-badge ${u.role === 'admin' ? 'reviewed' : u.role === 'guest' ? '' : 'resolved'}">${u.role}</span></td>
        <td>${u.total_queries || 0}</td>
        <td>${(u.created_at || "").replace("T"," ").slice(0, 16)}</td>
        <td>
          ${u.role !== 'admin' ? `<button class="promote-btn" data-user-id="${u.id}" data-role="admin" style="padding:3px 8px;border:1px solid var(--accent);border-radius:4px;background:transparent;cursor:pointer;font-size:11px;color:var(--accent);">设为管理员</button>` : `<button class="promote-btn" data-user-id="${u.id}" data-role="user" style="padding:3px 8px;border:1px solid #c0392b;border-radius:4px;background:transparent;cursor:pointer;font-size:11px;color:#c0392b;">取消管理员</button>`}
        </td>
      </tr>
    `).join("") || '<tr><td colspan="6" style="text-align:center;color:var(--muted);">暂无用户</td></tr>';
  } catch (e) {
    document.getElementById("usersTable").innerHTML = `<tr><td colspan="6">加载失败：${e.message}</td></tr>`;
  }
}

async function promoteUser(userId, newRole) {
  if (!confirm(`确定要将用户 #${userId} 的角色改为 ${newRole} 吗？`)) return;
  try {
    await api(`/admin/users/${userId}/role`, { method: "PATCH", body: JSON.stringify({ role: newRole }) });
    loadUsers();
  } catch (e) { alert("操作失败：" + e.message); }
}

// ---- Feedback ----
let currentFbStatus = "";

async function loadFeedback(status) {
  if (status !== undefined) currentFbStatus = status;
  try {
    const url = "/admin/feedback?limit=50" + (currentFbStatus ? "&status=" + currentFbStatus : "");
    const data = await api(url);
    const list = document.getElementById("feedbackList");
    list.innerHTML = (data.data || []).map(fb => `
      <div class="fb-item" data-id="${fb.id}">
        <div class="fb-item-header">
          <strong>${escHtml(fb.category)} — ${escHtml(fb.username || "匿名")}</strong>
          <span class="fb-badge ${fb.status}">${statusLabel(fb.status)}</span>
        </div>
        <div class="fb-content">${escHtml(fb.content)}</div>
        <div class="fb-meta">${(fb.created_at || "").slice(0, 16)}${fb.contact ? " · 联系：" + escHtml(fb.contact) : ""}</div>
        ${fb.admin_reply ? `<div class="fb-content" style="color:var(--accent);">管理员回复：${escHtml(fb.admin_reply)}</div>` : ""}
        <div class="fb-reply">
          <input placeholder="管理员回复..." value="${escHtml(fb.admin_reply || "")}" />
          <button class="fb-action-btn" data-fb-id="${fb.id}" data-status="reviewed">已查看</button>
          <button class="fb-action-btn" data-fb-id="${fb.id}" data-status="resolved" style="background:var(--accent);color:#fff;">已解决</button>
        </div>
      </div>
    `).join("") || '<div class="admin-error">暂无反馈</div>';
  } catch (e) {
    document.getElementById("feedbackList").innerHTML = `<div class="admin-error">加载失败：${e.message}</div>`;
  }
}

async function updateFeedback(id, status, btn) {
  const replyInput = btn.parentElement.querySelector("input");
  const reply = replyInput ? replyInput.value.trim() : "";
  try {
    await api(`/admin/feedback/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status, admin_reply: reply }),
    });
    loadFeedback();
  } catch (e) { alert("更新失败：" + e.message); }
}

// Feedback filter buttons
document.querySelectorAll("#fbFilter button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#fbFilter button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    loadFeedback(btn.dataset.status);
  });
});

function statusLabel(s) {
  return { pending: "待处理", reviewed: "已查看", resolved: "已解决" }[s] || s;
}

function escHtml(t) {
  if (t == null) return "";
  return String(t)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Event delegation for dynamically rendered buttons (CSP-safe)
document.addEventListener("click", (e) => {
  const promoteBtn = e.target.closest(".promote-btn");
  if (promoteBtn) {
    promoteUser(promoteBtn.dataset.userId, promoteBtn.dataset.role);
    return;
  }
  const fbBtn = e.target.closest(".fb-action-btn");
  if (fbBtn) {
    updateFeedback(fbBtn.dataset.fbId, fbBtn.dataset.status, fbBtn);
    return;
  }
});

document.getElementById("adminLogoutBtn")?.addEventListener("click", () => {
  localStorage.removeItem("tp_token");
  window.location.href = "/";
});

init();

// ---- POI Management ----
let poiCities = [];
let poiCurrentCity = "";
let poiCurrentPage = 1;
let poiCurrentType = "";
let poiCurrentSearch = "";
let poiTotal = 0;
const POI_PAGE_SIZE = 30;

async function loadPois() {
  if (poiCities.length === 0) {
    try {
      const res = await api("/cities");
      poiCities = res.cities || [];
      const sel = document.getElementById("poiCitySelect");
      sel.innerHTML = poiCities.map(c =>
        `<option value="${escHtml(c.name)}">${escHtml(c.name)} (${c.poi_count})</option>`
      ).join("");
      if (poiCities.length > 0) poiCurrentCity = poiCities[0].name;
      sel.addEventListener("change", () => { poiCurrentCity = sel.value; poiCurrentPage = 1; refreshPoiList(); });
    } catch (e) {
      document.getElementById("poiList").innerHTML = `<div class="admin-error">加载城市失败：${e.message}</div>`;
      return;
    }
  }
  refreshPoiList();
}

document.getElementById("poiTypeFilter").addEventListener("change", function() {
  poiCurrentType = this.value; poiCurrentPage = 1; refreshPoiList();
});

let poiSearchTimer = null;
document.getElementById("poiSearch").addEventListener("input", function() {
  clearTimeout(poiSearchTimer);
  poiSearchTimer = setTimeout(() => { poiCurrentSearch = this.value; poiCurrentPage = 1; refreshPoiList(); }, 300);
});

async function refreshPoiList() {
  const list = document.getElementById("poiList");
  list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--muted);">加载中...</div>';
  try {
    let url = `/admin/pois?city=${encodeURIComponent(poiCurrentCity)}&page=${poiCurrentPage}&page_size=${POI_PAGE_SIZE}`;
    if (poiCurrentType) url += `&type=${poiCurrentType}`;
    if (poiCurrentSearch) url += `&q=${encodeURIComponent(poiCurrentSearch)}`;
    const res = await api(url);
    poiTotal = res.total || 0;
    document.getElementById("poiCount").textContent = `共 ${poiTotal} 条`;
    renderPoiList(res.data || []);
    renderPoiPagination();
  } catch (e) {
    list.innerHTML = `<div class="admin-error">加载失败：${e.message}</div>`;
  }
}

function renderPoiList(pois) {
  const list = document.getElementById("poiList");
  if (pois.length === 0) {
    list.innerHTML = '<div class="admin-error">暂无数据</div>';
    return;
  }
  list.innerHTML = pois.map(poi => {
    const img = poi.image_url
      ? `<img class="poi-thumb" src="/${escHtml(poi.image_url)}" alt="" loading="lazy" onerror="this.outerHTML='<div class=poi-thumb-placeholder>🏔</div>'">`
      : '<div class="poi-thumb-placeholder">🏔</div>';
    const typeLabel = { attraction: "景点", restaurant: "餐厅", hotel: "酒店", transit: "交通", nightlife: "夜间" }[poi.type] || poi.type;
    return `
      <div class="poi-card" data-poi-id="${escHtml(poi.id)}" data-city="${escHtml(poiCurrentCity)}">
        ${img}
        <div class="poi-info">
          <h4>${escHtml(poi.name)} <small>${typeLabel}</small></h4>
          <div class="poi-meta">
            <span>⭐ ${Number(poi.popularity || 0).toFixed(1)}</span>
            <span>📍 ${escHtml(poi.area || '-')}</span>
            <span>💰 ${poi.price_level || 1}</span>
            <span>🖼 ${poi.images ? poi.images.length : 0}张</span>
            <span style="color:#aaa;font-size:11px;">${escHtml(poi.id)}</span>
          </div>
        </div>
        <div class="poi-actions">
          <button class="poi-edit-btn" data-poi-id="${escHtml(poi.id)}" data-city="${escHtml(poiCurrentCity)}">编辑</button>
          <button class="poi-img-btn" data-poi-id="${escHtml(poi.id)}" data-city="${escHtml(poiCurrentCity)}">选图</button>
        </div>
      </div>`;
  }).join("");
}

function renderPoiPagination() {
  const totalPages = Math.ceil(poiTotal / POI_PAGE_SIZE);
  const div = document.getElementById("poiPagination");
  if (totalPages <= 1) { div.innerHTML = ""; return; }
  let html = '';
  html += `<button ${poiCurrentPage <= 1 ? 'disabled' : ''} class="poi-page-btn" data-page="${poiCurrentPage - 1}">‹</button>`;
  const start = Math.max(1, poiCurrentPage - 3);
  const end = Math.min(totalPages, poiCurrentPage + 3);
  if (start > 1) html += `<button class="poi-page-btn" data-page="1">1</button><span style="padding:6px;">...</span>`;
  for (let i = start; i <= end; i++) {
    html += `<button class="poi-page-btn ${i === poiCurrentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
  }
  if (end < totalPages) html += `<span style="padding:6px;">...</span><button class="poi-page-btn" data-page="${totalPages}">${totalPages}</button>`;
  html += `<button ${poiCurrentPage >= totalPages ? 'disabled' : ''} class="poi-page-btn" data-page="${poiCurrentPage + 1}">›</button>`;
  div.innerHTML = html;
}

// ---- POI Edit Modal ----
let editingPoi = null;

async function openPoiEdit(poiId, city) {
  try {
    const poi = await api(`/admin/pois/${encodeURIComponent(poiId)}`);
    editingPoi = poi;
    document.getElementById("poiModalTitle").textContent = `编辑 — ${poi.name}`;
    document.getElementById("poiModalBody").innerHTML = buildPoiForm(poi);
    document.getElementById("poiEditModal").hidden = false;
  } catch (e) { alert("加载 POI 失败：" + e.message); }
}

function buildPoiForm(poi) {
  const tagsHtml = (poi.tags || []).map(t =>
    `<span class="tag">${escHtml(t)}<button type="button" class="tag-remove">&times;</button></span>`
  ).join("");
  return `
    <div class="poi-form">
      <div><label>ID</label><input value="${escHtml(poi.id)}" disabled /></div>
      <div><label>名称</label><input id="ef_name" value="${escHtml(poi.name)}" /></div>
      <div><label>类型</label>
        <select id="ef_type">
          ${["attraction","restaurant","hotel","transit","nightlife"].map(t =>
            `<option value="${t}" ${poi.type === t ? 'selected' : ''}>${t}</option>`
          ).join("")}
        </select>
      </div>
      <div><label>区域</label><input id="ef_area" value="${escHtml(poi.area || '')}" /></div>
      <div><label>纬度</label><input id="ef_lat" type="number" step="any" value="${poi.lat || 0}" /></div>
      <div><label>经度</label><input id="ef_lng" type="number" step="any" value="${poi.lng || 0}" /></div>
      <div><label>开放时间</label><input id="ef_open" value="${escHtml(poi.open_time || '00:00')}" /></div>
      <div><label>关闭时间</label><input id="ef_close" value="${escHtml(poi.close_time || '24:00')}" /></div>
      <div><label>建议游玩(分钟)</label><input id="ef_duration" type="number" value="${poi.visit_duration_minutes || 60}" /></div>
      <div><label>热度</label><input id="ef_pop" type="number" step="0.1" value="${poi.popularity || 0}" /></div>
      <div><label>价格等级</label><input id="ef_price" type="number" min="1" max="5" value="${poi.price_level || 1}" /></div>
      <div><label>餐饮类型</label><input id="ef_meal" value="${escHtml(poi.meal_type || 'main')}" /></div>
      <div class="full"><label>标签（回车添加）</label>
        <div class="tags-input" id="ef_tags">${tagsHtml}<input class="tag-input-field" id="ef_tagInput" placeholder="输入标签..." /></div>
      </div>
      <div class="full"><label>描述</label><textarea id="ef_desc">${escHtml(poi.description || '')}</textarea></div>
      <div class="full"><label>推荐语</label><textarea id="ef_rec">${escHtml(poi.recommendation || '')}</textarea></div>
      <div class="full"><label>攻略文本</label><textarea id="ef_guide">${escHtml(poi.guide_text || '')}</textarea></div>
      <div class="full"><label>主图 URL</label><input id="ef_img" value="${escHtml(poi.image_url || '')}" /></div>
    </div>`;
}

async function savePoi() {
  if (!editingPoi) return;
  const body = {
    _city: editingPoi._city || "",
    name: document.getElementById("ef_name").value,
    type: document.getElementById("ef_type").value,
    area: document.getElementById("ef_area").value,
    lat: parseFloat(document.getElementById("ef_lat").value) || 0,
    lng: parseFloat(document.getElementById("ef_lng").value) || 0,
    open_time: document.getElementById("ef_open").value,
    close_time: document.getElementById("ef_close").value,
    visit_duration_minutes: parseInt(document.getElementById("ef_duration").value) || 60,
    popularity: parseFloat(document.getElementById("ef_pop").value) || 0,
    price_level: parseInt(document.getElementById("ef_price").value) || 1,
    meal_type: document.getElementById("ef_meal").value,
    description: document.getElementById("ef_desc").value,
    recommendation: document.getElementById("ef_rec").value,
    guide_text: document.getElementById("ef_guide").value,
    image_url: document.getElementById("ef_img").value,
    tags: Array.from(document.querySelectorAll("#ef_tags .tag")).map(t => t.textContent.replace("×", "").trim()),
    images: editingPoi.images || [],
  };
  try {
    await api(`/admin/pois/${encodeURIComponent(editingPoi.id)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    document.getElementById("poiEditModal").hidden = true;
    editingPoi = null;
    refreshPoiList();
  } catch (e) { alert("保存失败：" + e.message); }
}

// ---- Image Picker ----
let imagePickerPoi = null;
let selectedImageUrl = "";

async function openImagePicker(poiId, city) {
  try {
    const poi = await api(`/admin/pois/${encodeURIComponent(poiId)}`);
    imagePickerPoi = poi;
    selectedImageUrl = poi.image_url || "";
    const body = document.getElementById("imagePickerBody");
    let html = `<div class="img-picker-current">当前主图：${poi.image_url ? `<img src="/${escHtml(poi.image_url)}" />` : '无'}</div>`;
    if (!poi.images || poi.images.length === 0) {
      html += '<div class="admin-error">该 POI 暂无候选图片</div>';
    } else {
      html += '<div class="img-picker-grid">';
      poi.images.forEach((img, i) => {
        const isSelected = img.url === selectedImageUrl;
        html += `
          <div class="img-picker-card ${isSelected ? 'selected' : ''}" data-url="${escHtml(img.url)}">
            <img src="/${escHtml(img.url)}" alt="图片 ${i + 1}" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22150%22><text x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 fill=%22%23999%22>加载失败</text></svg>'">
            <div class="img-label">${escHtml(img.source || 'unknown')} #${i + 1}</div>
          </div>`;
      });
      html += '</div>';
    }
    body.innerHTML = html;
    document.getElementById("imagePickerModal").hidden = false;
  } catch (e) { alert("加载图片失败：" + e.message); }
}

async function saveImageChoice() {
  if (!imagePickerPoi || !selectedImageUrl) { alert("请先选择一张图片"); return; }
  try {
    await api(`/admin/pois/${encodeURIComponent(imagePickerPoi.id)}/image`, {
      method: "PUT",
      body: JSON.stringify({ image_url: selectedImageUrl, _city: imagePickerPoi._city || "" }),
    });
    document.getElementById("imagePickerModal").hidden = true;
    imagePickerPoi = null;
    refreshPoiList();
  } catch (e) { alert("保存失败：" + e.message); }
}

// ---- Event Delegation for POI ----
document.addEventListener("click", (e) => {
  const editBtn = e.target.closest(".poi-edit-btn");
  if (editBtn) { openPoiEdit(editBtn.dataset.poiId, editBtn.dataset.city); return; }

  const imgBtn = e.target.closest(".poi-img-btn");
  if (imgBtn) { openImagePicker(imgBtn.dataset.poiId, imgBtn.dataset.city); return; }

  const pageBtn = e.target.closest(".poi-page-btn");
  if (pageBtn && !pageBtn.disabled) { poiCurrentPage = parseInt(pageBtn.dataset.page); refreshPoiList(); return; }

  const imgCard = e.target.closest(".img-picker-card");
  if (imgCard) {
    document.querySelectorAll(".img-picker-card").forEach(c => c.classList.remove("selected"));
    imgCard.classList.add("selected");
    selectedImageUrl = imgCard.dataset.url;
    return;
  }

  const tagRemove = e.target.closest(".tag-remove");
  if (tagRemove) { tagRemove.parentElement.remove(); return; }
});

// Tag input
document.addEventListener("keydown", (e) => {
  if (e.target.id === "ef_tagInput" && e.key === "Enter") {
    e.preventDefault();
    const val = e.target.value.trim();
    if (val) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.innerHTML = `${escHtml(val)}<button type="button" class="tag-remove">&times;</button>`;
      e.target.parentElement.insertBefore(tag, e.target);
      e.target.value = "";
    }
  }
});

// Modal close/cancel/save
document.getElementById("poiModalClose")?.addEventListener("click", () => { document.getElementById("poiEditModal").hidden = true; editingPoi = null; });
document.getElementById("poiModalCancel")?.addEventListener("click", () => { document.getElementById("poiEditModal").hidden = true; editingPoi = null; });
document.getElementById("poiModalSave")?.addEventListener("click", savePoi);
document.getElementById("poiEditModal")?.querySelector(".poi-modal-overlay")?.addEventListener("click", () => { document.getElementById("poiEditModal").hidden = true; editingPoi = null; });

document.getElementById("imagePickerClose")?.addEventListener("click", () => { document.getElementById("imagePickerModal").hidden = true; imagePickerPoi = null; });
document.getElementById("imagePickerCancel")?.addEventListener("click", () => { document.getElementById("imagePickerModal").hidden = true; imagePickerPoi = null; });
document.getElementById("imagePickerSave")?.addEventListener("click", saveImageChoice);
document.getElementById("imagePickerModal")?.querySelector(".poi-modal-overlay")?.addEventListener("click", () => { document.getElementById("imagePickerModal").hidden = true; imagePickerPoi = null; });